"""
Parquet-backed versioned dataset store.
 
Layout:
    {root}/{layer}/{symbol}/{timeframe}/v{version}/data.parquet
    {root}/{layer}/{symbol}/{timeframe}/v{version}/metadata.json
    {root}/{layer}/{symbol}/{timeframe}/v{version}/data.parquet.fingerprint.json
 
DuckDB can query these paths directly:
    SELECT * FROM read_parquet('data/processed/xauusd/h1/v1.0.0/data.parquet')
"""
 
from __future__ import annotations
 
import json
from pathlib import Path
from typing import Optional
 
import pandas as pd
 
from mars.core.config import PathConfig, DEFAULT_CONFIG
from mars.core.schemas import DatasetMetadata
from mars.core.timeframes import Timeframe
from mars.core.types import DatasetLayer
from mars.data.interfaces import DatasetStore
from mars.data.versioning.fingerprint import compute_fingerprint, write_fingerprint_sidecar
 
 
class ParquetDatasetStore(DatasetStore):
    """Filesystem parquet store with sidecar metadata and fingerprints."""
 
    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = Path(root) if root else DEFAULT_CONFIG.paths.data_root
 
    def _version_dir(
        self,
        layer: DatasetLayer,
        symbol: str,
        timeframe: Timeframe,
        version: str,
    ) -> Path:
        ver = version if version.startswith("v") else f"v{version}"
        return (
            self.root
            / layer.value
            / symbol.lower()
            / timeframe.value.lower()
            / ver
        )
 
    def write(self, df: pd.DataFrame, metadata: DatasetMetadata) -> Path:
        version_dir = self._version_dir(
            metadata.layer,
            metadata.symbol,
            metadata.timeframe,
            metadata.version,
        )
        version_dir.mkdir(parents=True, exist_ok=True)
 
        parquet_path = version_dir / "data.parquet"
        meta_path = version_dir / "metadata.json"
 
        # Ensure fingerprint is present
        if metadata.fingerprint is None:
            fp = compute_fingerprint(df)
            metadata = metadata.model_copy(
                update={
                    "fingerprint": fp,
                    "row_count": len(df),
                    "columns": [str(c) for c in df.columns],
                }
            )
        else:
            metadata = metadata.model_copy(
                update={
                    "row_count": len(df),
                    "columns": [str(c) for c in df.columns],
                }
            )
 
        # Write parquet (index preserved as column via reset for DuckDB friendliness)
        out = df.copy()
        if isinstance(out.index, pd.DatetimeIndex):
            out = out.reset_index()
        out.to_parquet(parquet_path, index=False, engine="pyarrow")
 
        meta_path.write_text(
            metadata.model_dump_json(indent=2),
            encoding="utf-8",
        )
        if metadata.fingerprint is not None:
            write_fingerprint_sidecar(parquet_path, metadata.fingerprint)
 
        return parquet_path
 
    def read(
        self,
        layer: DatasetLayer,
        symbol: str,
        timeframe: Timeframe,
        version: str,
    ) -> pd.DataFrame:
        version_dir = self._version_dir(layer, symbol, timeframe, version)
        parquet_path = version_dir / "data.parquet"
        if not parquet_path.exists():
            raise FileNotFoundError(f"Dataset not found: {parquet_path}")
 
        df = pd.read_parquet(parquet_path)
        # Restore datetime index if timestamp column exists
        for col in ("timestamp", "time"):
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], utc=True)
                df = df.set_index(col)
                df.index.name = "timestamp"
                break
        return df
 
    def exists(
        self,
        layer: DatasetLayer,
        symbol: str,
        timeframe: Timeframe,
        version: str,
    ) -> bool:
        return (self._version_dir(layer, symbol, timeframe, version) / "data.parquet").exists()
 
    def read_metadata(
        self,
        layer: DatasetLayer,
        symbol: str,
        timeframe: Timeframe,
        version: str,
    ) -> DatasetMetadata:
        meta_path = self._version_dir(layer, symbol, timeframe, version) / "metadata.json"
        if not meta_path.exists():
            raise FileNotFoundError(f"Metadata not found: {meta_path}")
        return DatasetMetadata.model_validate_json(meta_path.read_text(encoding="utf-8"))
 
    def duckdb_path(
        self,
        layer: DatasetLayer,
        symbol: str,
        timeframe: Timeframe,
        version: str,
    ) -> str:
        """Return a path string suitable for DuckDB read_parquet()."""
        p = self._version_dir(layer, symbol, timeframe, version) / "data.parquet"
        return str(p.as_posix())