"""Typed market candle schemas for M.A.R.S. data contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


REQUIRED_CANDLE_COLUMNS: tuple[str, ...] = (
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
)

OPTIONAL_CANDLE_COLUMNS: tuple[str, ...] = (
    "symbol",
    "timeframe",
    "spread",
    "session_label",
    "news_flag",
)


@dataclass(frozen=True)
class CandleSchema:
    """
    Canonical OHLCV (+ optional metadata) row contract.

    All pipelines should normalize raw vendor data into this shape before
    feature engineering. Timestamps are expected in UTC.
    """

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    symbol: Optional[str] = None
    timeframe: Optional[str] = None
    spread: Optional[float] = None
    session_label: Optional[str] = None
    news_flag: Optional[bool] = None
