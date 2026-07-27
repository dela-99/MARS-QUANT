"""Feature metadata contracts for M.A.R.S."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
from typing import Any

@dataclass(frozen=True)
class FeatureMetadata:
    name: str
    version: str
    category: str
    mathematical_definition: str
    parameters: dict[str, Any] = field(default_factory=dict)
    dependencies: tuple[str, ...] = ()
    inputs: tuple[str, ...] = ("open", "high", "low", "close")
    outputs: tuple[str, ...] = ()
    lookback: int = 0
    timeframe_agnostic: bool = True
    deterministic: bool = True
    vectorized: bool = True
    experimental: bool = False
    tags: tuple[str, ...] = ()

    def qualified_name(self) -> str:
        return f"{self.category}.{self.name}@{self.version}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
