"""Walk-forward validation splitter for out-of-sample research."""
 
from __future__ import annotations
 
from dataclasses import dataclass
from typing import Iterator, Optional
 
import numpy as np
import pandas as pd
 
 
@dataclass
class WalkForwardSplitter:
    """
    Expanding or rolling walk-forward splits.
 
    Args:
        train_size: initial training bars
        test_size: out-of-sample bars per step
        step_size: how far to roll forward each step (default = test_size)
        mode: "expanding" | "rolling"
    """
 
    train_size: int
    test_size: int
    step_size: Optional[int] = None
    mode: str = "expanding"
 
    def __post_init__(self) -> None:
        if self.train_size < 1 or self.test_size < 1:
            raise ValueError("train_size and test_size must be >= 1")
        if self.mode not in ("expanding", "rolling"):
            raise ValueError("mode must be 'expanding' or 'rolling'")
        if self.step_size is None:
            self.step_size = self.test_size
 
    def split(
        self,
        X: pd.DataFrame | np.ndarray,
    ) -> Iterator[tuple[np.ndarray, np.ndarray]]:
        n = len(X)
        step = self.step_size or self.test_size
        start_test = self.train_size
 
        while start_test + self.test_size <= n:
            test_idx = np.arange(start_test, start_test + self.test_size)
            if self.mode == "expanding":
                train_idx = np.arange(0, start_test)
            else:
                train_start = max(0, start_test - self.train_size)
                train_idx = np.arange(train_start, start_test)
            yield train_idx, test_idx
            start_test += step
 
 
def walk_forward_splits(
    n_samples: int,
    train_size: int,
    test_size: int,
    step_size: Optional[int] = None,
    mode: str = "expanding",
) -> list[tuple[np.ndarray, np.ndarray]]:
    X = np.arange(n_samples)
    splitter = WalkForwardSplitter(
        train_size=train_size,
        test_size=test_size,
        step_size=step_size,
        mode=mode,
    )
    return list(splitter.split(X))