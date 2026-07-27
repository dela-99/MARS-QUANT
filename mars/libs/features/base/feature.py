"""Abstract feature interfaces. Pure feature generation only."""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Iterable
import hashlib
import pandas as pd
from .metadata import FeatureMetadata

@dataclass
class FeatureResult:
    data: pd.DataFrame
    metadata: FeatureMetadata
    validation: dict[str, Any] = field(default_factory=dict)

    @property
    def columns(self) -> list[str]:
        return list(self.data.columns)

class BaseFeature(ABC):
    name = "base"
    version = "1.0.0"
    category = "base"
    inputs: tuple[str, ...] = ("open", "high", "low", "close")
    outputs: tuple[str, ...] = ()
    lookback = 0
    mathematical_definition = "abstract feature"
    dependencies: tuple[str, ...] = ()
    experimental = False

    def __init__(self, **params: Any) -> None:
        self.params = dict(params)

    @property
    def metadata(self) -> FeatureMetadata:
        return FeatureMetadata(
            name=self.name,
            version=self.version,
            category=self.category,
            mathematical_definition=self.mathematical_definition,
            parameters=self.params,
            dependencies=self.dependencies,
            inputs=self.inputs,
            outputs=tuple(self.output_columns()),
            lookback=int(self.lookback),
            experimental=self.experimental,
        )

    def output_columns(self) -> list[str]:
        return list(self.outputs)

    def validate_inputs(self, df: pd.DataFrame) -> None:
        missing = set(self.inputs) - set(df.columns)
        if missing:
            raise ValueError(f"{self.metadata.qualified_name()} missing inputs: {sorted(missing)}")
        if not isinstance(df.index, pd.DatetimeIndex):
            raise ValueError("feature input must use a DatetimeIndex")
        if not df.index.is_monotonic_increasing:
            raise ValueError("feature input index must be monotonic increasing")

    @abstractmethod
    def compute(self, df: pd.DataFrame, **kwargs: Any) -> FeatureResult: ...

    def fingerprint(self) -> str:
        payload = repr(sorted(self.metadata.to_dict().items())).encode()
        return hashlib.sha256(payload).hexdigest()

    def validation_report(self, result: FeatureResult) -> dict[str, Any]:
        data = result.data
        return {
            "feature": self.metadata.qualified_name(),
            "rows": int(len(data)),
            "columns": list(data.columns),
            "nan_count": {c: int(data[c].isna().sum()) for c in data.columns},
            "metadata": self.metadata.to_dict(),
        }

class FeaturePipeline:
    def __init__(self, features: Iterable[BaseFeature] = ()) -> None:
        self.features = list(features)

    def add(self, feature: BaseFeature) -> "FeaturePipeline":
        self.features.append(feature)
        return self

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        parts = [f.compute(df).data for f in self.features]
        return pd.concat(parts, axis=1) if parts else pd.DataFrame(index=df.index)

    def metadata(self) -> list[dict[str, Any]]:
        return [f.metadata.to_dict() for f in self.features]
