"""
Atomic data quality checks.
 
Each function is pure: input DataFrame + params → list[ValidationIssue].
"""
 
from __future__ import annotations
 
from typing import Optional
 
import numpy as np
import pandas as pd
 
from mars.core.timeframes import Timeframe, TIMEFRAME_MINUTES
from mars.data.interfaces import ValidationIssue
 
 
REQUIRED_COLUMNS = ("open", "high", "low", "close")
 
 
def check_schema(df: pd.DataFrame) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        issues.append(
            ValidationIssue(
                code="SCHEMA_MISSING_COLUMNS",
                severity="error",
                message=f"Missing required columns: {missing}",
                count=len(missing),
            )
        )
    if not isinstance(df.index, pd.DatetimeIndex):
        issues.append(
            ValidationIssue(
                code="SCHEMA_INDEX_NOT_DATETIME",
                severity="error",
                message="Index must be a DatetimeIndex (UTC preferred).",
            )
        )
    return issues
 
 
def check_duplicates(df: pd.DataFrame) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not isinstance(df.index, pd.DatetimeIndex):
        return issues
    dup_mask = df.index.duplicated(keep=False)
    n_dup = int(dup_mask.sum())
    if n_dup:
        examples = [str(t) for t in df.index[dup_mask][:5]]
        issues.append(
            ValidationIssue(
                code="DUPLICATE_TIMESTAMPS",
                severity="error",
                message=f"Found {n_dup} rows with duplicate timestamps.",
                count=n_dup,
                examples=examples,
            )
        )
    return issues
 
 
def check_missing_candles(
    df: pd.DataFrame,
    timeframe: Timeframe,
    session_hours: Optional[tuple[int, int]] = None,
) -> list[ValidationIssue]:
    """
    Detect gaps larger than the expected bar interval.
 
    Note: FX markets have weekend gaps; those are reported as warnings
    only when the gap is not a standard weekend break.
    """
    issues: list[ValidationIssue] = []
    if len(df) < 2 or not isinstance(df.index, pd.DatetimeIndex):
        return issues
 
    expected = pd.Timedelta(minutes=TIMEFRAME_MINUTES[timeframe])
    deltas = df.index.to_series().diff().dropna()
    # Gaps larger than 1.5x expected bar are candidates
    gap_mask = deltas > expected * 1.5
    gap_times = deltas[gap_mask]
 
    if gap_times.empty:
        return issues
 
    # Classify weekend vs anomalous
    anomalous = []
    weekendish = 0
    for ts, delta in gap_times.items():
        # Weekend: Friday close → Monday open roughly
        hours = delta.total_seconds() / 3600.0
        if 24 <= hours <= 72:
            weekendish += 1
        else:
            anomalous.append((str(ts), str(delta)))
 
    if weekendish:
        issues.append(
            ValidationIssue(
                code="MISSING_CANDLES_WEEKEND",
                severity="info",
                message=f"{weekendish} gaps consistent with weekend/session breaks.",
                count=weekendish,
            )
        )
    if anomalous:
        issues.append(
            ValidationIssue(
                code="MISSING_CANDLES",
                severity="warning",
                message=f"{len(anomalous)} anomalous gaps detected (>{expected}).",
                count=len(anomalous),
                examples=[f"{t}: {d}" for t, d in anomalous[:5]],
            )
        )
    return issues
 
 
def check_ohlc_consistency(df: pd.DataFrame) -> list[ValidationIssue]:
    """high >= max(open, close), low <= min(open, close), high >= low."""
    issues: list[ValidationIssue] = []
    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            return issues
 
    high_ok = (df["high"] >= df[["open", "close"]].max(axis=1)) & (df["high"] >= df["low"])
    low_ok = (df["low"] <= df[["open", "close"]].min(axis=1)) & (df["low"] <= df["high"])
    bad = ~(high_ok & low_ok)
    n_bad = int(bad.sum())
    if n_bad:
        examples = [str(t) for t in df.index[bad][:5]]
        issues.append(
            ValidationIssue(
                code="OHLC_INCONSISTENT",
                severity="error",
                message=f"{n_bad} bars fail OHLC consistency (high/low vs open/close).",
                count=n_bad,
                examples=examples,
            )
        )
    return issues
 
 
def check_bad_ticks(
    df: pd.DataFrame,
    z_threshold: float = 8.0,
    min_price: float = 0.0,
) -> list[ValidationIssue]:
    """
    Flag extreme returns and non-positive prices as bad ticks.
 
    Uses log-return z-scores; pure research heuristic, not a trading filter.
    """
    issues: list[ValidationIssue] = []
    if "close" not in df.columns or len(df) < 10:
        return issues
 
    non_positive = df["close"] <= min_price
    n_np = int(non_positive.sum())
    if n_np:
        issues.append(
            ValidationIssue(
                code="BAD_TICK_NONPOSITIVE",
                severity="error",
                message=f"{n_np} bars with non-positive close.",
                count=n_np,
                examples=[str(t) for t in df.index[non_positive][:5]],
            )
        )
 
    rets = np.log(df["close"].replace(0, np.nan)).diff()
    mu = rets.mean()
    sigma = rets.std()
    if sigma and sigma > 0:
        z = (rets - mu).abs() / sigma
        extreme = z > z_threshold
        n_ext = int(extreme.fillna(False).sum())
        if n_ext:
            issues.append(
                ValidationIssue(
                    code="BAD_TICK_EXTREME_RETURN",
                    severity="warning",
                    message=f"{n_ext} bars with |z-return| > {z_threshold}.",
                    count=n_ext,
                    examples=[str(t) for t in df.index[extreme.fillna(False)][:5]],
                )
            )
    return issues
 
 
def check_spread(
    df: pd.DataFrame,
    max_spread_pct: float = 0.01,
) -> list[ValidationIssue]:
    """
    Validate spread column if present.
 
    If no spread column, reports info only (not an error).
    """
    issues: list[ValidationIssue] = []
    if "spread" not in df.columns:
        issues.append(
            ValidationIssue(
                code="SPREAD_MISSING",
                severity="info",
                message="No 'spread' column present; skip spread validation.",
            )
        )
        return issues
 
    neg = df["spread"] < 0
    if neg.any():
        issues.append(
            ValidationIssue(
                code="SPREAD_NEGATIVE",
                severity="error",
                message=f"{int(neg.sum())} bars with negative spread.",
                count=int(neg.sum()),
            )
        )
 
    if "close" in df.columns:
        pct = df["spread"] / df["close"].replace(0, np.nan)
        wide = pct > max_spread_pct
        n_wide = int(wide.fillna(False).sum())
        if n_wide:
            issues.append(
                ValidationIssue(
                    code="SPREAD_WIDE",
                    severity="warning",
                    message=f"{n_wide} bars with spread > {max_spread_pct:.2%} of close.",
                    count=n_wide,
                )
            )
    return issues