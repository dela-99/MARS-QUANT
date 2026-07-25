"""
M.A.R.S. Data Platform
 
Responsibilities:
    - market data ingestion
    - validation & quality checks
    - normalization & timezone handling
    - parquet storage with DuckDB compatibility
    - versioned datasets with fingerprints & metadata
 
Layers: Raw → Processed → Research → Feature Store
"""
 
from mars.data.interfaces import (
    DataIngestor,
    DataValidator,
    DataNormalizer,
    DatasetStore,
    DatasetCatalog,
)
from mars.data.storage.parquet_store import ParquetDatasetStore
from mars.data.catalog.catalog import LocalDatasetCatalog
from mars.data.validation.pipeline import MarketDataValidator
from mars.data.normalization.ohlcv import OHLCVNormalizer
from mars.data.versioning.fingerprint import compute_fingerprint
 
__all__ = [
    "DataIngestor",
    "DataValidator",
    "DataNormalizer",
    "DatasetStore",
    "DatasetCatalog",
    "ParquetDatasetStore",
    "LocalDatasetCatalog",
    "MarketDataValidator",
    "OHLCVNormalizer",
    "compute_fingerprint",
]