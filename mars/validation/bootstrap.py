"""Bootstrap confidence intervals for research metrics."""
 
from __future__ import annotations
 
from typing import Callable, Optional
 
import numpy as np
import pandas as pd
 
 
def bootstrap_confidence_interval(
    data: pd.Series | np.ndarray,
    statistic: Callable[[np.ndarray], float],
    n_bootstrap: int = 1000,
    ci: float = 0.95,
    seed: Optional[int] = 42,
) -> dict[str, float]:
    """
    Non-parametric bootstrap CI for an arbitrary statistic.
 
    Returns dict with point estimate, low, high, and std of bootstrap dist.
    """
    if isinstance(data, pd.Series):
        arr = data.dropna().to_numpy(dtype=float)
    else:
        arr = np.asarray(data, dtype=float)
        arr = arr[~np.isnan(arr)]
 
    if len(arr) < 2:
        return {
            "estimate": float("nan"),
            "ci_low": float("nan"),
            "ci_high": float("nan"),
            "boot_std": float("nan"),
        }
 
    rng = np.random.default_rng(seed)
    estimates = np.empty(n_bootstrap, dtype=float)
    n = len(arr)
    for i in range(n_bootstrap):
        sample = rng.choice(arr, size=n, replace=True)
        estimates[i] = statistic(sample)
 
    alpha = 1.0 - ci
    low = float(np.nanquantile(estimates, alpha / 2))
    high = float(np.nanquantile(estimates, 1.0 - alpha / 2))
    return {
        "estimate": float(statistic(arr)),
        "ci_low": low,
        "ci_high": high,
        "boot_std": float(np.nanstd(estimates)),
    }