"""Performance metrics for research evaluation (not trading PnL engines)."""
 
from __future__ import annotations
 
from typing import Optional
 
import numpy as np
import pandas as pd
 
 
def _to_array(x) -> np.ndarray:
    if isinstance(x, pd.Series):
        return x.dropna().to_numpy(dtype=float)
    return np.asarray(x, dtype=float)
 
 
def sharpe_ratio(
    returns: pd.Series | np.ndarray,
    risk_free: float = 0.0,
    periods_per_year: float = 252.0,
) -> float:
    """Annualized Sharpe ratio of a return series."""
    r = _to_array(returns)
    if len(r) < 2:
        return float("nan")
    excess = r - risk_free / periods_per_year
    std = excess.std(ddof=1)
    if std == 0 or np.isnan(std):
        return float("nan")
    return float(np.sqrt(periods_per_year) * excess.mean() / std)
 
 
def sortino_ratio(
    returns: pd.Series | np.ndarray,
    risk_free: float = 0.0,
    periods_per_year: float = 252.0,
) -> float:
    """Annualized Sortino ratio (downside deviation)."""
    r = _to_array(returns)
    if len(r) < 2:
        return float("nan")
    excess = r - risk_free / periods_per_year
    downside = excess[excess < 0]
    if len(downside) < 1:
        return float("nan")
    dd = downside.std(ddof=1)
    if dd == 0 or np.isnan(dd):
        return float("nan")
    return float(np.sqrt(periods_per_year) * excess.mean() / dd)
 
 
def max_drawdown(returns: pd.Series | np.ndarray) -> float:
    """
    Maximum drawdown of a return series (negative number or 0).
 
    Computes equity curve from cumulative product of (1+r).
    """
    r = _to_array(returns)
    if len(r) == 0:
        return float("nan")
    equity = np.cumprod(1.0 + r)
    peak = np.maximum.accumulate(equity)
    dd = equity / peak - 1.0
    return float(dd.min())
 
 
def calmar_ratio(
    returns: pd.Series | np.ndarray,
    periods_per_year: float = 252.0,
) -> float:
    """Annualized return / |max drawdown|."""
    r = _to_array(returns)
    if len(r) < 2:
        return float("nan")
    ann_ret = float((np.prod(1.0 + r) ** (periods_per_year / len(r))) - 1.0)
    mdd = max_drawdown(r)
    if mdd == 0 or np.isnan(mdd):
        return float("nan")
    return float(ann_ret / abs(mdd))
 
 
def performance_summary(
    returns: pd.Series | np.ndarray,
    periods_per_year: float = 252.0,
) -> dict[str, float]:
    r = _to_array(returns)
    return {
        "n_obs": float(len(r)),
        "mean": float(np.nanmean(r)) if len(r) else float("nan"),
        "std": float(np.nanstd(r, ddof=1)) if len(r) > 1 else float("nan"),
        "sharpe": sharpe_ratio(r, periods_per_year=periods_per_year),
        "sortino": sortino_ratio(r, periods_per_year=periods_per_year),
        "calmar": calmar_ratio(r, periods_per_year=periods_per_year),
        "max_drawdown": max_drawdown(r),
    }