"""
End-to-end raw → processed ingestion pipeline.
 
Flow:
    source.ingest → normalize → validate → fingerprint → store → catalog
"""
 
from __future__ import annotations
 
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4
 
import pandas as pd
 
from mars.core.schemas import DatasetMetadata
from mars.core.timeframes import Timeframe
from mars.core.types import DatasetLayer
from mars.data.catalog.catalog import LocalDatasetCatalog
from mars.data.interfaces import DataIngestor, ValidationReport
from mars.data.normalization.ohlcv import OHLCVNormalizer
from mars.data.storage.parquet_store import ParquetDatasetStore
from mars.data.validation.pipeline import MarketDataValidator
from mars.data.versioning.fingerprint import compute_fingerprint
 
 
class IngestionPipeline:
    """Orchestrate ingest → normalize → validate → versioned store."""
 
    def __init__(
        self,
        ingestor: DataIngestor,
        store: Optional[ParquetDatasetStore] = None,
        catalog: Optional[LocalDatasetCatalog] = None,
        normalizer: Optional[OHLCVNormalizer] = None,
        validator: Optional[MarketDataValidator] = None,
        fail_on_validation_error: bool = True,
    ) -> None:
        self.ingestor = ingestor
        self.store = store or ParquetDatasetStore()
        self.catalog = catalog or LocalDatasetCatalog()
        self.normalizer = normalizer or OHLCVNormalizer()
        self.validator = validator or MarketDataValidator()
        self.fail_on_validation_error = fail_on_validation_error
 
    def run(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
        version: str = "1.0.0",
        source_name: str = "unknown",
        layer: DatasetLayer = DatasetLayer.PROCESSED,
        **ingest_kwargs: Any,
    ) -> tuple[Path, DatasetMetadata, ValidationReport]:
        raw = self.ingestor.ingest(symbol, timeframe, start, end, **ingest_kwargs)
        normalized = self.normalizer.normalize(raw, timezone="UTC")
        report = self.validator.validate(normalized, timeframe)
 
        if not report.passed and self.fail_on_validation_error:
            raise ValueError(
                f"Validation failed with {len(report.errors)} error(s): "
                f"{report.summary()}"
            )
 
        # Also persist raw snapshot if layer is processed (optional dual-write)
        fingerprint = compute_fingerprint(normalized)
        start_ts = normalized.index.min().to_pydatetime() if len(normalized) else None
        end_ts = normalized.index.max().to_pydatetime() if len(normalized) else None
 
        metadata = DatasetMetadata(
            dataset_id=f"{symbol.lower()}_{timeframe.value.lower()}_{version}_{uuid4().hex[:8]}",
            layer=layer,
            symbol=symbol.upper(),
            timeframe=timeframe,
            version=version,
            source=source_name,
            timezone="UTC",
            start_ts=start_ts,
            end_ts=end_ts,
            row_count=len(normalized),
            columns=[str(c) for c in normalized.columns],
            fingerprint=fingerprint,
            tags=["ingestion_pipeline"],
        )
 
        path = self.store.write(normalized, metadata)
        self.catalog.register(metadata)
        return path, metadata, report