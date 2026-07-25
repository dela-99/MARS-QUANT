"""
Canonical timeframe definitions for multi-timeframe (MTF) analysis.
 
M.A.R.S. performs top-down analysis across:
    H1 → M30 → M15 → M5 → M3
 
All feature computation is timeframe-aware. Models are NOT trained
separately per timeframe; features are aligned into a single
synchronized representation via the AlignmentEngine.
"""
 
from __future__ import annotations
 
from enum import Enum
from typing import Final
 
 
class Timeframe(str, Enum):
    """Supported research timeframes (order is coarsest → finest)."""
 
    H1 = "H1"
    M30 = "M30"
    M15 = "M15"
    M5 = "M5"
    M3 = "M3"
 
    @property
    def minutes(self) -> int:
        return TIMEFRAME_MINUTES[self]
 
    def is_coarser_than(self, other: "Timeframe") -> bool:
        return self.minutes > other.minutes
 
    def is_finer_than(self, other: "Timeframe") -> bool:
        return self.minutes < other.minutes
 
 
TIMEFRAME_MINUTES: Final[dict[Timeframe, int]] = {
    Timeframe.H1: 60,
    Timeframe.M30: 30,
    Timeframe.M15: 15,
    Timeframe.M5: 5,
    Timeframe.M3: 3,
}
 
# Default top-down stack used by MultiTimeframeFeatureEngine
SUPPORTED_TIMEFRAMES: Final[tuple[Timeframe, ...]] = (
    Timeframe.H1,
    Timeframe.M30,
    Timeframe.M15,
    Timeframe.M5,
    Timeframe.M3,
)
 
# Context roles in the AlignmentEngine (top-down)
TIMEFRAME_ROLES: Final[dict[Timeframe, str]] = {
    Timeframe.H1: "trend_context",
    Timeframe.M30: "market_bias",
    Timeframe.M15: "execution_context",
    Timeframe.M5: "confirmation_context",
    Timeframe.M3: "entry_timing_context",
}
 
 
def parse_timeframe(value: str) -> Timeframe:
    """Parse a string (case-insensitive) into a Timeframe enum."""
    key = value.strip().upper()
    try:
        return Timeframe(key)
    except ValueError as exc:
        valid = ", ".join(t.value for t in Timeframe)
        raise ValueError(f"Unknown timeframe '{value}'. Valid: {valid}") from exc