"""
Fetch macro data from FRED for Hyp-C regime classification.

This script fetches DXY, real yields, and VIX from FRED,
normalizes and validates them, then stores as cataloged datasets.
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd

from mars.core.config import DEFAULT_CONFIG
from mars.core.timeframes import Timeframe
from mars.core.types import DatasetLayer
from mars.core.schemas import DatasetMetadata
from mars.data.ingestion import FREDIngestor
from mars.data.normalization.ohlcv import OHLCVNormalizer
from mars.data.validation.pipeline import MarketDataValidator
from mars.data.storage.parquet_store import ParquetDatasetStore
from mars.data.catalog.catalog import LocalDatasetCatalog
from mars.data.versioning.fingerprint import compute_fingerprint
from mars.data.ingestion.fred_source import get_default_fred_series
from uuid import uuid4


def fetch_and_store_macro(
    series: list[str] = None,
    start: datetime = None,
    end: datetime = None,
    save_artifacts: bool = True,
) -> dict:
    """
    Fetch macro series from FRED, normalize, validate, store, and catalog.

    Returns dict with paths and metadata for each series.
    """
    series = series or ["DXY", "REAL_YIELD_10Y", "VIX"]
    start = start or datetime(2003, 1, 1)
    end = end or datetime.now()

    results = {}
    ingestor = FREDIngestor()
    normalizer = OHLCVNormalizer(source_timezone="UTC", drop_extra=True)
    validator = MarketDataValidator()
    store = ParquetDatasetStore()
    catalog = LocalDatasetCatalog()

    for symbol in series:
        print(f"\n=== Processing {symbol} ===")
        
        # Ingest from FRED
        raw = ingestor.ingest(symbol=symbol, start=start, end=end)
        print(f"  Fetched {len(raw)} observations")
        print(f"  Columns: {raw.columns.tolist()}")

        # Normalize - FRED data is already daily and UTC with lag-adjusted timestamps
        # The ingestor returns: timestamp, close, series_id, symbol
        df = raw.copy()
        df = df.set_index("timestamp")
        df = df.sort_index()
        df = df[["close"]].copy()
        df["volume"] = 0.0  # placeholder

        # Validate
        validator = MarketDataValidator(bad_tick_z=10.0, max_spread_pct=1.0)
        report = validator.validate(df, Timeframe.D)  # FRED is daily
        print(f"  Validation: passed={report.passed}, warnings={len(report.warnings)}")

        # Store
        fp = compute_fingerprint(df)
        start_ts = df.index.min().to_pydatetime()
        end_ts = df.index.max().to_pydatetime()

        from mars.core.schemas import DatasetMetadata
        from uuid import uuid4

        metadata = DatasetMetadata(
            dataset_id=f"{symbol.lower()}_daily_v1.0.0_{uuid4().hex[:8]}",
            layer=DatasetLayer.PROCESSED,
            symbol=symbol.upper(),
            timeframe=Timeframe.D,
            version="1.0.0",
            source="fred",
            timezone="UTC",
            start_ts=df.index.min().to_pydatetime(),
            end_ts=df.index.max().to_pydatetime(),
            row_count=len(df),
            columns=[str(c) for c in df.columns],
            fingerprint=compute_fingerprint(df),
            tags=["fred", "macro", "hyp_c"],
        )

        if save_artifacts:
            path = store.write(df, metadata)
            print(f"  Stored to: {path}")

            # Register in catalog
            catalog = LocalDatasetCatalog()
            catalog.register(metadata)
            print(f"  Registered in catalog: {metadata.dataset_id}")

        results[symbol] = {
            "path": str(path) if save_artifacts else None,
            "metadata": metadata,
            "rows": len(df),
            "start": start_ts,
            "end": end_ts,
        }

    return results


def main():
    parser = argparse.ArgumentParser(description="Fetch macro data from FRED for Hyp-C")
    parser.add_argument("--series", nargs="+", default=["DXY", "REAL_YIELD_10Y", "VIX"])
    parser.add_argument("--start", type=str, default="2003-01-01")
    parser.add_argument("--end", type=str, default=None)
    parser.add_argument("--no-save", action="store_true")
    args = parser.parse_args()

    start = datetime.fromisoformat(args.start)
    end = datetime.fromisoformat(args.end) if args.end else datetime.now()

    results = fetch_and_store_macro(
        series=args.series,
        start=start,
        end=end,
        save_artifacts=not args.no_save,
    )

    print("\n=== SUMMARY ===")
    for symbol, info in results.items():
        print(f"  {symbol}: {info['rows']} rows, {info['start'].date()} to {info['end'].date()}")


if __name__ == "__main__":
    main()