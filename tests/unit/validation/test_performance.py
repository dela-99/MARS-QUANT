"""Tests for performance metrics and CV splitters."""
 
from __future__ import annotations
 
import numpy as np
 
from mars.validation.performance import (
    sharpe_ratio,
    sortino_ratio,
    max_drawdown,
    calmar_ratio,
    performance_summary,
)
from mars.validation.bootstrap import bootstrap_confidence_interval
from mars.validation.cross_validation import PurgedKFold, purged_cv_split
from mars.validation.walk_forward import WalkForwardSplitter, walk_forward_splits
 
 
def test_sharpe_positive_drift(returns_series):
    s = sharpe_ratio(returns_series)
    assert np.isfinite(s)
 
 
def test_max_drawdown_non_positive(returns_series):
    mdd = max_drawdown(returns_series)
    assert mdd <= 0 or np.isnan(mdd)
 
 
def test_performance_summary_keys(returns_series):
    summary = performance_summary(returns_series)
    for k in ("sharpe", "sortino", "calmar", "max_drawdown"):
        assert k in summary
 
 
def test_bootstrap_ci(returns_series):
    result = bootstrap_confidence_interval(
        returns_series,
        statistic=lambda x: float(np.mean(x)),
        n_bootstrap=200,
        seed=1,
    )
    assert result["ci_low"] <= result["estimate"] <= result["ci_high"]
 
 
def test_purged_kfold_no_overlap():
    splits = purged_cv_split(100, n_splits=5, purge_bars=3, embargo_bars=2)
    assert len(splits) >= 1
    for train, test in splits:
        assert len(set(train) & set(test)) == 0
 
 
def test_walk_forward():
    splits = walk_forward_splits(200, train_size=50, test_size=20, mode="expanding")
    assert len(splits) >= 1
    train, test = splits[0]
    assert train.max() < test.min()