"""
Pydantic / dataclass schemas for dataset metadata, fingerprints,
feature metadata, and hypothesis records.
 
These schemas are the contracts between systems.
"""
 
from __future__ import annotations
 
from datetime import datetime, timezone
from typing import Any, Optional
 
from pydantic import BaseModel, Field, field_validator
 
from mars.core.timeframes import Timeframe
from mars.core.types import DatasetLayer, HypothesisStatus
 
 
class BarSchema(BaseModel):
    """Canonical OHLCV bar schema after normalization."""
 
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    spread: Optional[float] = None
 
    model_config = {"extra": "forbid"}
 
    @field_validator("high")
    @classmethod
    def high_must_be_max(cls, v: float, info) -> float:
        # Cross-field checks are done in the data validator pipeline.
        return v
 
 
class DatasetFingerprint(BaseModel):
    """
    Content fingerprint for a dataset version.
 
    Enables reproducibility: two datasets with the same fingerprint
    are byte-identical in content (after canonical serialization).
    """
 
    algorithm: str = "sha256"
    digest: str
    row_count: int
    column_names: list[str]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
 
    def short(self) -> str:
        return self.digest[:12]
 
 
class DatasetMetadata(BaseModel):
    """
    Versioned dataset metadata stored alongside parquet partitions.
 
    Compatible with DuckDB catalog queries and local filesystem layout:
        data/{layer}/{symbol}/{timeframe}/v{version}/...
    """
 
    dataset_id: str
    layer: DatasetLayer
    symbol: str
    timeframe: Timeframe
    version: str
    source: str = "unknown"
    timezone: str = "UTC"
    start_ts: Optional[datetime] = None
    end_ts: Optional[datetime] = None
    row_count: int = 0
    columns: list[str] = Field(default_factory=list)
    fingerprint: Optional[DatasetFingerprint] = None
    parent_dataset_id: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
 
    def uri_parts(self) -> dict[str, str]:
        """Path components for storage layout."""
        return {
            "layer": self.layer.value,
            "symbol": self.symbol.lower(),
            "timeframe": self.timeframe.value.lower(),
            "version": self.version,
        }
 
 
class FeatureMetadata(BaseModel):
    """
    Metadata contract for every feature implementation.
 
    Features MUST be deterministic, versioned, and free of look-ahead bias.
    """
 
    name: str
    version: str
    category: str
    description: str = ""
    lookback: int = 0
    inputs: list[str] = Field(default_factory=lambda: ["open", "high", "low", "close"])
    outputs: list[str] = Field(default_factory=list)
    timeframe_agnostic: bool = True
    requires_volume: bool = False
    experimental: bool = False
    tags: list[str] = Field(default_factory=list)
 
    def qualified_name(self) -> str:
        return f"{self.name}@v{self.version}"
 
 
class HypothesisRecord(BaseModel):
    """
    Formal hypothesis record.
 
    Every research idea must be captured with:
        - unique ID
        - problem statement
        - mathematical formulation
        - required datasets / features
        - experiments
        - statistical validation plan
        - status
    """
 
    hypothesis_id: str
    title: str
    problem_statement: str
    mathematical_formulation: str = ""
    required_datasets: list[str] = Field(default_factory=list)
    required_features: list[str] = Field(default_factory=list)
    experiments: list[str] = Field(default_factory=list)
    statistical_validation: list[str] = Field(default_factory=list)
    status: HypothesisStatus = HypothesisStatus.DRAFT
    author: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tags: list[str] = Field(default_factory=list)
    notes: str = ""
    related_literature: list[str] = Field(default_factory=list)
 
    @field_validator("hypothesis_id")
    @classmethod
    def id_must_be_nonempty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("hypothesis_id must be non-empty")
        return v