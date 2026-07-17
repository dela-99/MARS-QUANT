"""Time-aware train / validation / test splits (no shuffle)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import pandas as pd


@dataclass
class TimeSeriesSplitResult:
    """Chronological split boundaries and index slices."""

    train_idx: pd.Index
    val_idx: pd.Index
    test_idx: pd.Index
    train_start: object
    train_end: object
    val_start: Optional[object]
    val_end: Optional[object]
    test_start: object
    test_end: object

    def describe(self) -> str:
        lines = [
            f"Train: {self.train_start} → {self.train_end} (n={len(self.train_idx)})",
            f"Val:   {self.val_start} → {self.val_end} (n={len(self.val_idx)})",
            f"Test:  {self.test_start} → {self.test_end} (n={len(self.test_idx)})",
        ]
        return "\n".join(lines)


def time_series_split(
    index: pd.Index,
    *,
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
    test_ratio: float = 0.15,
) -> TimeSeriesSplitResult:
    """
    Chronological split of a sorted index.

    Ratios must sum to ~1.0. No shuffling — order is preserved.
    Validation slice may be empty if val_ratio == 0.
    """
    total = train_ratio + val_ratio + test_ratio
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"Split ratios must sum to 1.0, got {total}")

    n = len(index)
    if n < 10:
        raise ValueError(f"Need at least 10 samples for a meaningful split, got {n}")

    n_train = int(n * train_ratio)
    n_val = int(n * val_ratio)
    # remainder to test to avoid off-by-one loss
    n_test = n - n_train - n_val
    if n_train < 1 or n_test < 1:
        raise ValueError("train and test partitions must be non-empty")

    train_idx = index[:n_train]
    val_idx = index[n_train : n_train + n_val]
    test_idx = index[n_train + n_val :]

    def _bounds(idx: pd.Index) -> Tuple[Optional[object], Optional[object]]:
        if len(idx) == 0:
            return None, None
        return idx[0], idx[-1]

    tr_s, tr_e = _bounds(train_idx)
    va_s, va_e = _bounds(val_idx)
    te_s, te_e = _bounds(test_idx)

    return TimeSeriesSplitResult(
        train_idx=train_idx,
        val_idx=val_idx,
        test_idx=test_idx,
        train_start=tr_s,
        train_end=tr_e,
        val_start=va_s,
        val_end=va_e,
        test_start=te_s,
        test_end=te_e,
    )


def train_test_time_split(
    index: pd.Index, *, test_ratio: float = 0.2
) -> TimeSeriesSplitResult:
    """Convenience 80/20 chronological split with empty validation."""
    return time_series_split(
        index, train_ratio=1.0 - test_ratio, val_ratio=0.0, test_ratio=test_ratio
    )
