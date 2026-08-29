from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import hashlib
import pandas as pd

@dataclass(frozen=True)
class FeatureDataset:
    features: pd.DataFrame
    name: str = "feature_dataset"
    version: str = "1.0.0"
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.features, pd.DataFrame): raise TypeError("features must be a DataFrame")
        if not isinstance(self.features.index, pd.DatetimeIndex): raise ValueError("features must use a DatetimeIndex")
        if not self.features.index.is_monotonic_increasing: raise ValueError("features index must be sorted")
        if self.features.columns.duplicated().any(): raise ValueError("feature columns must be unique")

    @property
    def columns(self) -> list[str]: return list(self.features.columns)

    def fingerprint(self) -> str:
        payload = pd.util.hash_pandas_object(self.features, index=True).values.tobytes()+repr(self.columns).encode()
        return hashlib.sha256(payload).hexdigest()

    @classmethod
    def from_parquet(cls, path: str | Path, **kwargs) -> "FeatureDataset":
        df = pd.read_parquet(path)
        if "timestamp" in df.columns: df = df.set_index("timestamp")
        return cls(df.sort_index(), **kwargs)
