from __future__ import annotations
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

@dataclass(frozen=True)
class LearningMetadata:
    name: str
    version: str
    task_type: str
    estimator_type: str
    feature_columns: tuple[str, ...]
    label_columns: tuple[str, ...]
    parameters: dict[str, Any] = field(default_factory=dict)
    random_state: int | None = None
    feature_fingerprint: str = ""
    label_fingerprint: str = ""
    metrics: dict[str, float] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    tags: tuple[str, ...] = ()

    def qualified_name(self) -> str:
        return f"{self.name}@{self.version}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
