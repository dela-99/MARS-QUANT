"""Tests for chronological split utility."""

import pandas as pd

from mars.libs.evaluation.splits import time_series_split


def test_time_series_split_order_and_sizes():
    idx = pd.date_range("2020-01-01", periods=100, freq="D")
    split = time_series_split(idx, train_ratio=0.7, val_ratio=0.15, test_ratio=0.15)

    assert len(split.train_idx) == 70
    assert len(split.val_idx) == 15
    assert len(split.test_idx) == 15
    # chronological: last train < first test
    assert split.train_idx[-1] < split.test_idx[0]
    if len(split.val_idx):
        assert split.train_idx[-1] < split.val_idx[0]
        assert split.val_idx[-1] < split.test_idx[0]


def test_no_overlap():
    idx = pd.RangeIndex(0, 50)
    split = time_series_split(idx, train_ratio=0.6, val_ratio=0.2, test_ratio=0.2)
    train_set = set(split.train_idx)
    val_set = set(split.val_idx)
    test_set = set(split.test_idx)
    assert train_set.isdisjoint(val_set)
    assert train_set.isdisjoint(test_set)
    assert val_set.isdisjoint(test_set)
