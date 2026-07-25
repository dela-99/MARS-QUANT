"""
Local dataset catalog backed by a JSON index (DuckDB-queryable via parquet export).
 
For institutional scale this would be a database; for research reproducibility
a local JSON index is sufficient and git-friendly.
"""
 
from __future__ import annotations
 
import json
from pathlib import Path
from typing import Optional
 
from mars.core.config import DEFAULT_CONFIG
from mars.core.schemas import DatasetMetadata
from mars.core.timeframes import Timeframe
from mars.core.types import DatasetLayer
from mars.data.interfaces import DatasetCatalog
 
 
class LocalDatasetCatalog(DatasetCatalog):
    """JSON-file catalog of registered datasets."""
 
    def __init__(self, catalog_path: Optional[Path] = None) -> None:
        self.catalog_path = catalog_path or (
            DEFAULT_CONFIG.paths.data_root / "catalog.json"
        )
        self._entries: dict[str, DatasetMetadata] = {}
        self._load()
 
    def _load(self) -> None:
        if not self.catalog_path.exists():
            self._entries = {}
            return
        raw = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        self._entries = {
            k: DatasetMetadata.model_validate(v) for k, v in raw.items()
        }
 
    def _save(self) -> None:
        self.catalog_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {k: v.model_dump(mode="json") for k, v in self._entries.items()}
        self.catalog_path.write_text(
            json.dumps(payload, indent=2, default=str),
            encoding="utf-8",
        )
 
    def register(self, metadata: DatasetMetadata) -> None:
        self._entries[metadata.dataset_id] = metadata
        self._save()
 
    def get(self, dataset_id: str) -> Optional[DatasetMetadata]:
        return self._entries.get(dataset_id)
 
    def list(
        self,
        layer: Optional[DatasetLayer] = None,
        symbol: Optional[str] = None,
        timeframe: Optional[Timeframe] = None,
    ) -> list[DatasetMetadata]:
        results = list(self._entries.values())
        if layer is not None:
            results = [m for m in results if m.layer == layer]
        if symbol is not None:
            results = [m for m in results if m.symbol.lower() == symbol.lower()]
        if timeframe is not None:
            results = [m for m in results if m.timeframe == timeframe]
        return sorted(results, key=lambda m: m.created_at, reverse=True)