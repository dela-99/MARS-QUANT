from __future__ import annotations
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
import json
import numpy as np
import pandas as pd
from .metadata import LearningMetadata

@dataclass
class PredictionResult:
    index: pd.Index
    values: np.ndarray
    probabilities: np.ndarray | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_frame(self) -> pd.DataFrame:
        frame = pd.DataFrame({"prediction": self.values}, index=self.index)
        if self.probabilities is not None:
            probs = np.asarray(self.probabilities)
            if probs.ndim == 2:
                for i in range(probs.shape[1]): frame[f"probability_{i}"] = probs[:, i]
            else:
                frame["probability"] = probs
        return frame

@dataclass
class TrainingResult:
    metadata: LearningMetadata
    train_metrics: dict[str, float]
    validation_metrics: dict[str, float]
    test_metrics: dict[str, float] = field(default_factory=dict)
    artifact_path: str | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def save_json(self, path: str | Path) -> None:
        path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, default=str), encoding="utf-8")
