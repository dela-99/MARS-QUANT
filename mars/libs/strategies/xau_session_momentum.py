"""
M.A.R.S. Session Momentum Strategy: XAU-SESSION-MOM-001
Asian-Session Momentum Continuation (Cross-Session Momentum per Wei 2026)

Signal: Previous session return > 0 → long next session
Entry: Session open (first M5 bar)
Exit: Session close (last M5 bar) or stop-loss
Timeframe: M5 execution, H1 session context
Sessions: Fixed UTC (Asia 00-08, Europe 08-14:30, US 14:30-24)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time, timezone
from typing import Any, Literal, Optional

import numpy as np
import pandas as pd

from mars.libs.data.loaders import to_price_index
from mars.libs.strategies.base import TradeSetup
from dataclasses import dataclass


@dataclass
class SignalFrame:
    """Computed indicators and signals, aligned to the M5 index (matches Donchian pattern)."""

    frame: pd.DataFrame
    params: SessionMomentumParams
    n_sessions: int
    n_signals: int


# ============================================================================
# Session Definitions (Fixed UTC — No DST Adjustment)
# ============================================================================

SessionName = Literal["asia", "europe", "us"]

SESSION_BOUNDARIES_UTC: dict[SessionName, tuple[time, time]] = {
    "asia": (time(0, 0, tzinfo=timezone.utc), time(8, 0, tzinfo=timezone.utc)),
    "europe": (time(8, 0, tzinfo=timezone.utc), time(14, 30, tzinfo=timezone.utc)),
    "us": (time(14, 30, tzinfo=timezone.utc), time(23, 59, 59, 999999, tzinfo=timezone.utc)),
}

SESSION_ORDER: list[SessionName] = ["asia", "europe", "us"]

SESSION_TRANSITIONS: dict[SessionName, SessionName] = {
    "asia": "europe",
    "europe": "us",
    "us": "asia",  # next day's Asia
}


# ============================================================================
# Configuration
# ============================================================================

@dataclass(frozen=True)
class SessionMomentumParams:
    """Immutable strategy parameters (frozen for IS research)."""

    # Signal
    signal_mode: Literal["return", "direction"] = "direction"  # Paper 12: direction
    threshold: float = 0.0  # Paper 12: positive previous-session return

    # Risk
    risk_fraction: float = 0.01  # 1% per trade
    sl_points: int = 200  # Stop distance in broker points (200 pts = 0.2 price = 20 pips)

    # Costs (assumptions, clearly labelled)
    spread_multiplier: float = 1.0
    commission_per_lot: float = 0.0
    slippage_points: float = 0.0

    # No-trade filters (sensitivity only)
    block_fomc: bool = False
    block_high_vol: bool = False
    block_high_spread: bool = False

    # Data
    starting_equity: float = 10000.0  # Normalized IS equity
    symbol: str = "XAUUSDm"
    timeframe: str = "m5"

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_mode": self.signal_mode,
            "threshold": self.threshold,
            "risk_fraction": self.risk_fraction,
            "sl_points": self.sl_points,
            "spread_multiplier": self.spread_multiplier,
            "commission_per_lot": self.commission_per_lot,
            "slippage_points": self.slippage_points,
            "block_fomc": self.block_fomc,
            "block_high_vol": self.block_high_vol,
            "block_high_spread": self.block_high_spread,
            "starting_equity": self.starting_equity,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
        }


# ============================================================================
# Session Utilities
# ============================================================================

def assign_session_labels(
    df: pd.DataFrame,
    sessions: tuple[SessionName, ...] = ("asia", "europe", "us"),
) -> pd.DataFrame:
    """Assign each M5 bar to a session based on UTC hour/minute."""
    df = df.copy()
    hour = df.index.hour
    minute = df.index.minute

    def get_session(h: int, m: int) -> str:
        total_min = h * 60 + m
        if 0 <= total_min < 8 * 60:
            return "asia"
        elif 8 * 60 <= total_min < 14 * 60 + 30:
            return "europe"
        else:
            return "us"

    df["session"] = [get_session(h, m) for h, m in zip(hour, minute)]
    df["date"] = df.index.date
    return df


def compute_session_returns(
    m5: pd.DataFrame,
    sessions: tuple[SessionName, ...] = ("asia", "europe", "us"),
) -> pd.DataFrame:
    """
    Compute session-level OHLC and returns from M5 bars.

    Returns DataFrame with one row per (date, session):
    - session_open, session_high, session_low, session_close
    - session_return, session_direction
    - session_start (sortable datetime)
    """
    df = assign_session_labels(m5, sessions)

    grouped = df.groupby(["date", "session"])
    session_bars = grouped.agg(
        session_open=("open", "first"),
        session_high=("high", "max"),
        session_low=("low", "min"),
        session_close=("close", "last"),
        session_volume=("volume", "sum"),
        n_bars=("close", "count"),
    ).reset_index()

    # Compute return and direction
    session_bars["session_return"] = (
        (session_bars["session_close"] - session_bars["session_open"])
        / session_bars["session_open"]
    )
    session_bars["session_direction"] = np.sign(session_bars["session_return"])

    # Sortable session datetime
    session_start_times = {
        "asia": time(0, 0),
        "europe": time(8, 0),
        "us": time(14, 30),
    }
    session_bars["session_start"] = pd.to_datetime([
        pd.Timestamp.combine(row["date"], session_start_times[row["session"]]).tz_localize("UTC")
        for _, row in session_bars.iterrows()
    ])
    session_bars = session_bars.sort_values("session_start").reset_index(drop=True)
    session_bars["session_idx"] = range(len(session_bars))

    return session_bars


def generate_session_signals(
    session_bars: pd.DataFrame,
    signal_mode: Literal["return", "direction"] = "direction",
    threshold: float = 0.0,
    sessions: tuple[SessionName, ...] = ("asia", "europe", "us"),
) -> pd.DataFrame:
    """
    Generate cross-session momentum signals at session level.

    Signal for session N is based on session N-1 return/direction.
    Signal becomes observable at session N open (no look-ahead).
    """
    bars = session_bars.copy()

    # Previous session return/direction
    bars["prev_session_return"] = bars["session_return"].shift(1)
    bars["prev_session_direction"] = bars["session_direction"].shift(1)

    # Signal: 1 = long, 0 = flat
    if signal_mode == "return":
        bars["signal"] = (bars["prev_session_return"] > threshold).astype(int)
    else:  # direction
        bars["signal"] = (bars["prev_session_direction"] > 0).astype(int)

    # First session has no previous session -> flat
    bars.loc[0, "signal"] = 0

    # Session transitions
    bars["entry_session"] = bars["session"]
    bars["exit_session"] = bars["session"].map(SESSION_TRANSITIONS)

    return bars


def expand_signals_to_m5(
    m5: pd.DataFrame,
    session_signals: pd.DataFrame,
    min_bars_per_session: int = 10,
) -> pd.DataFrame:
    """
    Expand session-level signals to M5 bar level for bar-by-bar backtesting.

    Each M5 bar gets:
    - entry_long: True only on first bar of session when signal=1
    - exit_long: True only on last bar of session when signal=1
    - stop_distance: SL in price units (points * point_size)
    - session_id: (date, session) for grouping
    """
    m5 = m5.copy()
    m5 = assign_session_labels(m5)

    # Mark first and last bar of each session
    m5["is_session_first"] = m5.groupby(["date", "session"]).cumcount() == 0
    m5["is_session_last"] = m5.groupby(["date", "session"]).cumcount(ascending=False) == 0
    m5["bars_in_session"] = m5.groupby(["date", "session"])["close"].transform("count")

    # Data quality filter: skip sessions with too few bars
    m5["session_valid"] = m5["bars_in_session"] >= min_bars_per_session

    # Merge session signals
    # Create session key for merging
    session_signals = session_signals.copy()
    session_signals["session_key"] = list(zip(session_signals["date"], session_signals["session"]))
    m5["session_key"] = list(zip(m5["date"], m5["session"]))

    signal_map = session_signals.set_index("session_key")["signal"].to_dict()
    m5["signal"] = m5["session_key"].map(signal_map).fillna(0).astype(int)

    # Entry: first bar of session when signal=1 AND session_valid
    m5["entry_long"] = m5["is_session_first"] & (m5["signal"] == 1) & m5["session_valid"]

    # Exit: last bar of session when signal=1 (primary time-based exit)
    m5["exit_long"] = m5["is_session_last"] & (m5["signal"] == 1) & m5["session_valid"]

    # Stop distance in price units (points * point_size = 0.001 per point)
    # 200 points * 0.001 = 0.2 price units
    point_size = 0.001
    # Default sl_points from params, can be overridden per bar if needed
    m5["sl_points"] = 200  # Will be set from params
    m5["stop_distance"] = m5["signal"] * m5["sl_points"] * point_size

    # Session ID for trade grouping
    m5["session_id"] = m5["session_key"].astype(str)

    return m5


# ============================================================================
# Strategy Class
# ============================================================================

class SessionMomentumStrategy:
    """
    Session Momentum Continuation Strategy (XAU-SESSION-MOM-001).

    Generates per-bar signals for the Assignment 14 bar-level backtester.
    """

    def __init__(self, params: Optional[SessionMomentumParams] = None, symbol: str = "XAUUSDm"):
        self.name = "XAU-SESSION-MOM-001"
        self.symbol = symbol
        self.params = params or SessionMomentumParams()

    def compute_signals(
        self,
        m5: pd.DataFrame,
        h1: Optional[pd.DataFrame] = None,
    ) -> SignalFrame:
        """
        Compute per-bar entry/exit/stop signals for M5 data.

        Parameters
        ----------
        m5 : pd.DataFrame
            M5 OHLCV with 'spread' column, timestamp index in UTC
        h1 : pd.DataFrame, optional
            H1 data for regime filters (volatility, etc.)

        Returns
        -------
        SignalFrame with columns:
            timestamp, open, high, low, close, spread, atr, stop_distance,
            entry_long, exit_long, entry_short, exit_short, signal
        """
        # Ensure timestamp index
        if "timestamp" in m5.columns:
            m5 = m5.set_index("timestamp")
        if m5.index.tz is None:
            m5.index = m5.index.tz_localize("UTC")
        else:
            m5.index = m5.index.tz_convert("UTC")
        m5 = m5.sort_index()

        # Compute session returns
        session_bars = compute_session_returns(m5)

        # Generate session signals
        session_bars = generate_session_signals(
            session_bars,
            signal_mode=self.params.signal_mode,
            threshold=self.params.threshold,
        )

        # Add SL points to session bars for expansion
        session_bars["sl_points"] = self.params.sl_points

        # Expand to M5 level
        m5_signals = expand_signals_to_m5(m5, session_bars)

        # Set stop_distance from params (in price units)
        point_size = 0.001
        m5_signals["stop_distance"] = m5_signals["signal"] * self.params.sl_points * point_size

        # ATR placeholder (not used for this strategy but required by backtester)
        # Use H1 ATR if available, else rolling M5 std
        if h1 is not None and len(h1) > 0:
            # Resample H1 ATR to M5
            h1_atr = self._compute_atr(h1, period=14)
            m5_signals = m5_signals.join(h1_atr.rename("atr"), how="left")
            m5_signals["atr"] = m5_signals["atr"].ffill()
        else:
            # Fallback: M5 rolling volatility
            m5_signals["atr"] = m5_signals["close"].rolling(288).std()  # ~1 day of M5 bars
            m5_signals["atr"] = m5_signals["atr"].ffill().bfill()

        # Ensure required columns for backtester
        required_cols = [
            "timestamp", "open", "high", "low", "close", "spread",
            "atr", "stop_distance", "entry_long", "exit_long",
            "entry_short", "exit_short", "signal"
        ]

        # Add timestamp column
        m5_signals = m5_signals.reset_index()
        m5_signals.rename(columns={"index": "timestamp"}, inplace=True)

        # Short signals are always false (long-only)
        m5_signals["entry_short"] = False
        m5_signals["exit_short"] = False

        # Select and order columns
        frame = m5_signals[required_cols].copy()

        return SignalFrame(
            frame=frame,
            params=self.params,
            n_sessions=len(session_bars),
            n_signals=int(session_bars["signal"].sum()),
        )

    def _compute_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Compute ATR from OHLC data."""
        high = df["high"]
        low = df["low"]
        close = df["close"]
        prev_close = close.shift(1)

        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(period).mean()
        return atr


def compute_signals(
    m5: pd.DataFrame,
    h1: Optional[pd.DataFrame] = None,
    params: Optional[SessionMomentumParams] = None,
) -> SignalFrame:
    """Convenience function matching Assignment 14 interface."""
    strategy = SessionMomentumStrategy(params)
    return strategy.compute_signals(m5, h1)


__all__ = [
    "SessionMomentumParams",
    "SignalFrame",
    "SessionMomentumStrategy",
    "compute_signals",
    "SESSION_BOUNDARIES_UTC",
    "SESSION_ORDER",
    "SESSION_TRANSITIONS",
    "assign_session_labels",
    "compute_session_returns",
    "generate_session_signals",
    "expand_signals_to_m5",
]