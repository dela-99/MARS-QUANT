"""Technical indicator helpers (stateless, candle-level)."""

from __future__ import annotations

import numpy as np
import pandas as pd

try:
    import pandas_ta as ta
except ImportError:  # pragma: no cover
    ta = None  # type: ignore


def _ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def _rsi(close: pd.Series, length: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _atr(df: pd.DataFrame, length: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()


def add_baseline_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Append EMA(50), EMA(200), RSI(14), ATR(14) to an OHLCV frame.

    Expects columns: open, high, low, close (volume optional).
    Uses pandas_ta when available; otherwise pure pandas fallbacks with the
    same column names expected by Hyp-A feature code (EMA_50, RSI_14, ATRr_14).
    """
    out = df.copy()
    if ta is not None:
        out.ta.ema(length=50, append=True)
        out.ta.ema(length=200, append=True)
        out.ta.rsi(length=14, append=True)
        out.ta.atr(length=14, append=True)
        return out

    # Pure pandas fallback (compatible with Python builds lacking pandas_ta/numba)
    out["EMA_50"] = _ema(out["close"], 50)
    out["EMA_200"] = _ema(out["close"], 200)
    out["RSI_14"] = _rsi(out["close"], 14)
    out["ATRr_14"] = _atr(out, 14)
    return out


def add_advanced_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Rich indicator set used by the paper-tuned XGBoost experiment (legacy).

    Ported from ``legacy/src/feature_engineering_utils.py``. Prefer baseline
    indicators for the clean V1 pipeline; advanced set is optional research.
    """
    if ta is None:
        raise ImportError(
            "pandas_ta is required for advanced indicators. "
            "Baseline Hyp-A workflow does not need it."
        )

    out = df.copy()
    study = ta.Study(
        name="MARS Advanced Indicators",
        description="Expanded TA set from research notebooks",
        ta=[
            {"kind": "rsi"},
            {"kind": "mom"},
            {"kind": "stoch"},
            {"kind": "macd"},
            {"kind": "cci"},
            {"kind": "roc"},
            {"kind": "cmo"},
            {"kind": "stochrsi"},
            {"kind": "willr"},
            {"kind": "adx"},
            {"kind": "trix"},
            {"kind": "psar"},
            {"kind": "tema"},
            {"kind": "trima"},
            {"kind": "wma"},
            {"kind": "dema"},
            {"kind": "mfi"},
            {"kind": "bop"},
            {"kind": "atr"},
        ],
    )
    out.ta.study(study)
    return out
