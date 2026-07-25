"""
Statistical validation suite for M.A.R.S. research.
 
Supports:
    Sharpe, Sortino, Calmar, Maximum Drawdown,
    Bootstrap confidence intervals,
    Information Coefficient,
    Purged Cross Validation,
    Walk Forward Validation,
    Out-of-sample testing,
    Feature importance / stability
"""
 
from mars.validation.performance import (
    sharpe_ratio,
    sortino_ratio,
    calmar_ratio,
    max_drawdown,
    performance_summary,
)
from mars.validation.bootstrap import bootstrap_confidence_interval
from mars.validation.cross_validation import PurgedKFold, purged_cv_split
from mars.validation.walk_forward import WalkForwardSplitter, walk_forward_splits
from mars.validation.feature_stability import feature_stability_score
 
__all__ = [
    "sharpe_ratio",
    "sortino_ratio",
    "calmar_ratio",
    "max_drawdown",
    "performance_summary",
    "bootstrap_confidence_interval",
    "PurgedKFold",
    "purged_cv_split",
    "WalkForwardSplitter",
    "walk_forward_splits",
    "feature_stability_score",
]