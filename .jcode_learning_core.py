from pathlib import Path
root=Path(r'C:\Users\RIDGE\OneDrive\Desktop\MARS-QUANT')
base=root/'mars'/'libs'/'learning'
def w(rel,text):
    p=base/rel; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(text.strip()+'\n',encoding='utf-8')

w('base/metadata.py', r'''
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
''')
w('base/model.py', r'''
from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd

ArrayLike = pd.DataFrame | pd.Series | np.ndarray

class BaseLearningModel(ABC):
    name = "base_learning_model"
    version = "1.0.0"
    task_type = "generic"
    estimator_type = "base"

    def __init__(self, random_state: int | None = 42, **parameters: Any) -> None:
        self.random_state = random_state
        self.parameters = dict(parameters)
        self.feature_columns_: list[str] = []
        self.is_fitted = False

    @abstractmethod
    def fit(self, X: pd.DataFrame, y: ArrayLike, **kwargs: Any) -> "BaseLearningModel": ...

    @abstractmethod
    def predict(self, X: pd.DataFrame) -> np.ndarray: ...

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        raise NotImplementedError(f"{self.__class__.__name__} does not expose probabilities")

    @abstractmethod
    def save(self, path: str | Path) -> None: ...

    @classmethod
    @abstractmethod
    def load(cls, path: str | Path) -> "BaseLearningModel": ...

    def _record_features(self, X: pd.DataFrame) -> None:
        self.feature_columns_ = list(X.columns)

    def _validate_features(self, X: pd.DataFrame) -> None:
        if self.feature_columns_ and list(X.columns) != self.feature_columns_:
            raise ValueError("feature schema mismatch")
''')
w('base/result.py', r'''
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
''')
w('base/__init__.py','from .metadata import LearningMetadata\nfrom .model import ArrayLike, BaseLearningModel\nfrom .result import PredictionResult, TrainingResult\n__all__=["LearningMetadata","ArrayLike","BaseLearningModel","PredictionResult","TrainingResult"]')

w('datasets/dataset.py', r'''
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
''')
w('datasets/splits.py', r'''
from __future__ import annotations
from dataclasses import dataclass
import pandas as pd

@dataclass(frozen=True)
class TemporalSplit:
    train_idx: pd.Index
    validation_idx: pd.Index
    test_idx: pd.Index
    embargo: int = 0

    def assert_no_overlap(self) -> None:
        a,b,c = set(self.train_idx), set(self.validation_idx), set(self.test_idx)
        if a & b or a & c or b & c: raise ValueError("temporal split overlap detected")
        if len(self.train_idx) and len(self.validation_idx) and self.train_idx.max() >= self.validation_idx.min(): raise ValueError("train must precede validation")
        if len(self.validation_idx) and len(self.test_idx) and self.validation_idx.max() >= self.test_idx.min(): raise ValueError("validation must precede test")

class TemporalSplitter:
    def __init__(self, train_ratio=.7, validation_ratio=.15, test_ratio=.15, embargo:int=0):
        total=train_ratio+validation_ratio+test_ratio
        if abs(total-1)>1e-9: raise ValueError("split ratios must sum to 1")
        self.train_ratio=train_ratio; self.validation_ratio=validation_ratio; self.test_ratio=test_ratio; self.embargo=embargo
    def split(self, index: pd.Index) -> TemporalSplit:
        n=len(index)
        if n < 10: raise ValueError("at least 10 rows required")
        n_train=int(n*self.train_ratio); n_val=int(n*self.validation_ratio)
        tr_end=max(0,n_train-self.embargo); val_start=min(n,n_train+self.embargo); val_end=max(val_start,n_train+n_val-self.embargo); test_start=min(n,n_train+n_val+self.embargo)
        split=TemporalSplit(index[:tr_end], index[val_start:val_end], index[test_start:], self.embargo)
        split.assert_no_overlap(); return split
''')
w('datasets/__init__.py','from .dataset import FeatureDataset\nfrom .splits import TemporalSplit, TemporalSplitter\n__all__=["FeatureDataset","TemporalSplit","TemporalSplitter"]')

w('labels/label_set.py', r'''
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
''')
w('labels/__init__.py','from .label_set import LabelSet\n__all__=["LabelSet"]')
print('base dataset labels written')
