"""
Purged cross-validation for time series.
 
Based on the methodology popularized in López de Prado's work:
    - purge training samples that overlap the test label horizon
    - optional embargo after the test set
 
This is infrastructure for statistical validation — not a strategy.
"""
 
from __future__ import annotations
 
from dataclasses import dataclass
from typing import Iterator, Optional
 
import numpy as np
import pandas as pd
 
 
@dataclass
class PurgedKFold:
    """
    K-fold splits with purging and embargo for financial time series.
 
    Args:
        n_splits: number of folds
        purge_bars: number of bars to purge around test set (label horizon)
        embargo_bars: bars after test set excluded from training
    """
 
    n_splits: int = 5
    purge_bars: int = 5
    embargo_bars: int = 0
 
    def split(
        self,
        X: pd.DataFrame | np.ndarray,
        y: Optional[pd.Series | np.ndarray] = None,
    ) -> Iterator[tuple[np.ndarray, np.ndarray]]:
        n = len(X)
        if self.n_splits < 2:
            raise ValueError("n_splits must be >= 2")
        if n < self.n_splits:
            raise ValueError("Not enough samples for the requested n_splits")
 
        indices = np.arange(n)
        fold_sizes = np.full(self.n_splits, n // self.n_splits, dtype=int)
        fold_sizes[: n % self.n_splits] += 1
        current = 0
        folds = []
        for fold_size in fold_sizes:
            start, stop = current, current + fold_size
            folds.append(indices[start:stop])
            current = stop
 
        for i, test_idx in enumerate(folds):
            test_start = test_idx[0]
            test_end = test_idx[-1]
            train_mask = np.ones(n, dtype=bool)
            # Remove test
            train_mask[test_idx] = False
            # Purge before test
            purge_start = max(0, test_start - self.purge_bars)
            train_mask[purge_start:test_start] = False
            # Purge after test + embargo
            purge_end = min(n, test_end + 1 + self.purge_bars + self.embargo_bars)
            train_mask[test_end + 1 : purge_end] = False
 
            train_idx = indices[train_mask]
            if len(train_idx) == 0 or len(test_idx) == 0:
                continue
            yield train_idx, test_idx
 
 
def purged_cv_split(
    n_samples: int,
    n_splits: int = 5,
    purge_bars: int = 5,
    embargo_bars: int = 0,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Convenience: return all purged splits for a given sample count."""
    X = np.arange(n_samples)
    cv = PurgedKFold(n_splits=n_splits, purge_bars=purge_bars, embargo_bars=embargo_bars)
    return list(cv.split(X))