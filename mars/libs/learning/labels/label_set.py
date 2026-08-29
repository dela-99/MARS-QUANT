from __future__ import annotations
from dataclasses import dataclass, field
import hashlib
import pandas as pd

@dataclass(frozen=True)
class LabelSet:
    labels: pd.DataFrame | pd.Series
    name: str = "labels"
    version: str = "1.0.0"
    horizon: int | None = None
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.labels.index, pd.DatetimeIndex): raise ValueError("labels must use a DatetimeIndex")
        if not self.labels.index.is_monotonic_increasing: raise ValueError("labels index must be sorted")

    @property
    def columns(self) -> list[str]:
        return [self.labels.name or "label"] if isinstance(self.labels, pd.Series) else list(self.labels.columns)

    def aligned_to(self, features: pd.DataFrame) -> "LabelSet":
        aligned = self.labels.reindex(features.index).dropna()
        return LabelSet(aligned, self.name, self.version, self.horizon, self.metadata)

    def fingerprint(self) -> str:
        obj = self.labels.to_frame() if isinstance(self.labels, pd.Series) else self.labels
        payload = pd.util.hash_pandas_object(obj, index=True).values.tobytes()+repr(self.columns).encode()
        return hashlib.sha256(payload).hexdigest()
