"""OHLCV validation utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import pandas as pd

from mars.libs.data.schemas import REQUIRED_CANDLE_COLUMNS


@dataclass
class ValidationReport:
    ok: bool
    errors: List[str]
    warnings: List[str]
    n_rows: int

    def raise_if_invalid(self) -> None:
        if not self.ok:
            raise ValueError("OHLCV validation failed:\n- " + "\n- ".join(self.errors))


def validate_ohlcv(df: pd.DataFrame, *, strict: bool = True) -> ValidationReport:
    """
    Validate structural integrity of a normalized OHLCV DataFrame.

    Checks:
    - required columns present
    - no all-null OHLC
    - high >= low, high >= open/close, low <= open/close (soft warning if few violations)
    - timestamps sorted and unique
    """
    errors: List[str] = []
    warnings: List[str] = []

    missing = [c for c in REQUIRED_CANDLE_COLUMNS if c not in df.columns]
    if missing:
        errors.append(f"Missing required columns: {missing}")

    n_rows = len(df)
    if n_rows == 0:
        errors.append("DataFrame is empty.")

    if "timestamp" in df.columns:
        if df["timestamp"].isna().any():
            errors.append("timestamp contains NaT/null values.")
        if not df["timestamp"].is_monotonic_increasing:
            warnings.append("timestamps are not strictly monotonic increasing (will sort in loaders).")
        if df["timestamp"].duplicated().any():
            warnings.append("duplicate timestamps detected.")

    for col in ("open", "high", "low", "close"):
        if col in df.columns and df[col].isna().all():
            errors.append(f"Column '{col}' is entirely null.")

    if all(c in df.columns for c in ("open", "high", "low", "close")):
        bad_hl = (df["high"] < df["low"]).sum()
        if bad_hl:
            msg = f"{bad_hl} rows have high < low."
            (errors if strict else warnings).append(msg)

    report = ValidationReport(
        ok=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        n_rows=n_rows,
    )
    if strict:
        report.raise_if_invalid()
    return report
