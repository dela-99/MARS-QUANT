"""
Abstract interfaces for the Data Platform.
 
All concrete ingestors, validators, normalizers, and stores implement these.
Interfaces keep ingestion sources (MT5, CSV, vendor feeds) interchangeable.
"""
 
from __future__ import annotations
 
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Protocol, runtime_checkable
 
import pandas as pd
 
from mars.core.schemas import DatasetFingerprint, DatasetMetadata
from mars.core.timeframes import Timeframe
from mars.core.types import DatasetLayer
 
 
@runtime_checkable
class DataIngestor(Protocol):
    """Ingest market data from an external source into a raw DataFrame."""
 
    def ingest(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
        **kwargs: Any,
    ) -> pd.DataFrame:
        """Return raw bars. Columns may be source-specific before normalization."""
        ...
 
 
class DataValidator(ABC):
    """Validate OHLCV bars for research-grade quality."""
 
    @abstractmethod
    def validate(self, df: pd.DataFrame, timeframe: Timeframe) -> "ValidationReport":
        """Run all checks and return a structured report (never mutates silently)."""
        ...
 
 
class DataNormalizer(ABC):
    """Normalize raw bars into the canonical OHLCV schema (UTC-indexed)."""
 
    @abstractmethod
    def normalize(self, df: pd.DataFrame, timezone: str = "UTC") -> pd.DataFrame:
        """
        Return a DataFrame with:
            - DatetimeIndex (tz-aware UTC)
            - columns: open, high, low, close, volume [, spread]
            - sorted ascending, no duplicate timestamps
        """
        ...
 
 
class DatasetStore(ABC):
    """Persist and load versioned datasets (parquet + metadata)."""
 
    @abstractmethod
    def write(
        self,
        df: pd.DataFrame,
        metadata: DatasetMetadata,
    ) -> Path:
        """Write dataset and return the path to the primary parquet file."""
        ...
 
    @abstractmethod
    def read(
        self,
        layer: DatasetLayer,
        symbol: str,
        timeframe: Timeframe,
        version: str,
    ) -> pd.DataFrame:
        """Load a specific dataset version."""
        ...
 
    @abstractmethod
    def exists(
        self,
        layer: DatasetLayer,
        symbol: str,
        timeframe: Timeframe,
        version: str,
    ) -> bool:
        ...
 
 
class DatasetCatalog(ABC):
    """Discover and register datasets (DuckDB-friendly metadata index)."""
 
    @abstractmethod
    def register(self, metadata: DatasetMetadata) -> None:
        ...
 
    @abstractmethod
    def get(self, dataset_id: str) -> Optional[DatasetMetadata]:
        ...
 
    @abstractmethod
    def list(
        self,
        layer: Optional[DatasetLayer] = None,
        symbol: Optional[str] = None,
        timeframe: Optional[Timeframe] = None,
    ) -> list[DatasetMetadata]:
        ...
 
 
# Forward-declared report type used by validators
class ValidationIssue:
    """Single data quality issue."""
 
    __slots__ = ("code", "severity", "message", "count", "examples")
 
    def __init__(
        self,
        code: str,
        severity: str,
        message: str,
        count: int = 1,
        examples: Optional[list[Any]] = None,
    ) -> None:
        self.code = code
        self.severity = severity  # "error" | "warning" | "info"
        self.message = message
        self.count = count
        self.examples = examples or []
 
    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "count": self.count,
            "examples": self.examples[:5],
        }
 
 
class ValidationReport:
    """Aggregate validation result."""
 
    def __init__(self) -> None:
        self.issues: list[ValidationIssue] = []
        self.row_count: int = 0
        self.passed: bool = True
 
    def add(self, issue: ValidationIssue) -> None:
        self.issues.append(issue)
        if issue.severity == "error":
            self.passed = False
 
    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]
 
    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]
 
    def summary(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "row_count": self.row_count,
            "n_errors": len(self.errors),
            "n_warnings": len(self.warnings),
            "issues": [i.to_dict() for i in self.issues],
        }