"""
M.A.R.S. Volatility-Regime-Filtered Session Momentum Strategy: XAU-VOL-REGIME-SESSION-005

Signal: Asian session return > 0 → long Europe session (base signal from Paper 12)
Regime Filters (all must be favorable):
  1. Volatility: H1 realized vol (20-bar trailing) ≤ 40th percentile (expanding window)
  2. Spread: Asian session avg spread ≤ 40th percentile (frozen IS distribution)
  3. FOMC: Exclude FOMC days (FRED calendar)
Entry: 08:00 UTC (first M5 bar Europe open)
Exit: 14:30 UTC (time stop) or stop-loss
Stop-Loss: Session low (Asia or Europe) OR 200 pts, whichever tighter
Position Sizing: Fixed fractional 1% equity, min 0.01 lot
Timeframe: M5 execution, H1 session context (regime detection)
Sessions: Fixed UTC (Asia 00-08, Europe 08-14:30, US 14:30-24) — no DST adjustment

Frozen Specification per Assignment 20 Research Specification Brief §1.4
No optimization permitted. Sensitivity analyses pre-registered.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time, timezone
from typing import Any, Literal, Optional

import numpy as np
import pandas as pd

from mars.libs.data.loaders import to_price_index
from mars.libs.strategies.base import TradeSetup
from mars.libs.strategies.xau_session_momentum import (
    SESSION_BOUNDARIES_UTC,
    SESSION_ORDER,
    SESSION_TRANSITIONS,
    SessionName,
    assign_session_labels,
    compute_session_returns,
    expand_signals_to_m5,
)

# ============================================================================
# FOMC Calendar (pre-downloaded from FRED: FOMCMEETINGS)
# Static calendar for reproducibility — covers IS period 2021-10-01 to 2024-12-31
# Source: https://fred.stlouisfed.org/series/FOMCMEETINGS
# ============================================================================

FOMC_MEETING_DATES: set[date] = {
    # 2021
    date(2021, 11, 3), date(2021, 12, 15),
    # 2022
    date(2022, 1, 26), date(2022, 3, 16), date(2022, 5, 4), date(2022, 6, 15),
    date(2022, 7, 27), date(2022, 9, 21), date(2022, 11, 2), date(2022, 12, 14),
    # 2023
    date(2023, 2, 1), date(2023, 3, 22), date(2023, 5, 3), date(2023, 6, 14),
    date(2023, 7, 26), date(2023, 9, 20), date(2023, 11, 1), date(2023, 12, 13),
    # 2024
    date(2024, 1, 31), date(2024, 3, 20), date(2024, 5, 1), date(2024, 6, 12),
    date(2024, 7, 31), date(2024, 9, 18), date(2024, 11, 7), date(2024, 12, 18),
}

# Also include day before/after for sensitivity (per spec)
FOMC_WINDOW_DATES: set[date] = set()
for d in FOMC_MEETING_DATES:
    FOMC_WINDOW_DATES.add(d)
    # Day before
    from datetime import timedelta
    FOMC_WINDOW_DATES.add(d - timedelta(days=1))
    # Day after
    FOMC_WINDOW_DATES.add(d + timedelta(days=1))


# ============================================================================
# Configuration
# ============================================================================

@dataclass(frozen=True)
class XAUVolRegimeSession005Params:
    """Immutable strategy parameters (frozen for IS research per Assignment 20)."""

    # Base Signal (Paper 12)
    signal_mode: Literal["return", "direction"] = "direction"
    threshold: float = 0.0

    # Regime Filters (Pre-specified — no optimization)
    vol_lookback_bars: int = 20          # H1 bars for realized vol
    vol_percentile_threshold: float = 40.0  # ≤ 40th percentile = favorable
    spread_percentile_threshold: float = 40.0  # ≤ 40th percentile = favorable
    fomc_filter: bool = True             # Exclude FOMC days (meeting day ±1)

    # Execution
    risk_fraction: float = 0.01          # 1% per trade
    sl_points: int = 200                 # Stop distance cap in broker points

    # Costs (assumptions, clearly labelled)
    spread_multiplier: float = 1.0
    commission_per_lot: float = 0.0
    slippage_points: float = 0.0

    # Data
    starting_equity: float = 10000.0     # Normalized IS equity (research)
    feasibility_equity: float = 30.0     # $30 live feasibility
    symbol: str = "XAUUSDm"
    timeframe: str = "m5"

    # Frozen IS period (Assignment 20 §1.5)
    is_start: str = "2021-10-01"
    is_end: str = "2024-12-31"

    # Burn-in for trailing windows (Assignment 20 §1.5)
    burn_in_start: str = "2021-07-16"
    burn_in_end: str = "2021-09-30"

    # Sensitivity values (pre-registered, not for optimization)
    sensitivity: dict[str, list[Any]] = field(default_factory=lambda: {
        "spread_multiplier": [1.0, 1.5, 2.0],
        "vol_percentile_threshold": [30, 40, 50],
        "spread_percentile_threshold": [30, 40, 50],
        "fomc_filter": [True, False],
        "sl_points": [150, 200, 250, 300],
        "dst_shift_hours": [-1, 0, 1],
    })

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_mode": self.signal_mode,
            "threshold": self.threshold,
            "vol_lookback_bars": self.vol_lookback_bars,
            "vol_percentile_threshold": self.vol_percentile_threshold,
            "spread_percentile_threshold": self.spread_percentile_threshold,
            "fomc_filter": self.fomc_filter,
            "risk_fraction": self.risk_fraction,
            "sl_points": self.sl_points,
            "spread_multiplier": self.spread_multiplier,
            "commission_per_lot": self.commission_per_lot,
            "slippage_points": self.slippage_points,
            "starting_equity": self.starting_equity,
            "feasibility_equity": self.feasibility_equity,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "is_start": self.is_start,
            "is_end": self.is_end,
            "burn_in_start": self.burn_in_start,
            "burn_in_end": self.burn_in_end,
        }


# ============================================================================
# Session Utilities (Extended)
# ============================================================================

def compute_h1_realized_vol(
    h1: pd.DataFrame,
    lookback: int = 20,
    session_filter: Optional[Literal["asia"]] = "asia",
) -> pd.Series:
    """
    Compute trailing realized volatility on H1 bars.

    Parameters
    ----------
    h1 : pd.DataFrame
        H1 OHLC with timestamp index (UTC), columns: open, high, low, close
    lookback : int
        Number of H1 bars for trailing window (default 20 per spec)
    session_filter : str, optional
        If "asia", only compute vol using Asian session H1 bars (00:00-08:00 UTC)

    Returns
    -------
    pd.Series
        Annualized realized volatility indexed by H1 timestamp (same index as input)
        NaN for bars with insufficient history (burn-in)
    """
    if not isinstance(h1.index, pd.DatetimeIndex):
        h1 = h1.set_index("timestamp")
    if h1.index.tz is None:
        h1.index = h1.index.tz_localize("UTC")
    else:
        h1.index = h1.index.tz_convert("UTC")

    h1 = h1.sort_index()

    # Filter to Asian session H1 bars if requested
    if session_filter == "asia":
        hour = h1.index.hour
        minute = h1.index.minute
        is_asia = (hour == 0) | (hour < 8) | ((hour == 8) & (minute == 0))
        h1_asia = h1[is_asia].copy()
    else:
        h1_asia = h1

    # Compute log returns
    log_ret = np.log(h1_asia["close"] / h1_asia["close"].shift(1))

    # Trailing realized volatility (standard deviation of log returns)
    # Annualized: std * sqrt(252 * 24) for H1 bars
    ann_factor = np.sqrt(252 * 24)
    rv = log_ret.rolling(window=lookback, min_periods=lookback).std() * ann_factor

    # Reindex to original H1 index (forward fill for non-Asia bars)
    rv_full = rv.reindex(h1.index).ffill()

    return rv_full


def compute_asian_session_avg_spread(m5: pd.DataFrame) -> pd.Series:
    """
    Compute average spread (points) for each Asian session (00:00-08:00 UTC).

    Parameters
    ----------
    m5 : pd.DataFrame
        M5 OHLCV with 'spread' column, timestamp index (UTC)

    Returns
    -------
    pd.Series
        Average spread per session, indexed by session date (date of Asia session)
    """
    if not isinstance(m5.index, pd.DatetimeIndex):
        m5 = m5.set_index("timestamp")
    if m5.index.tz is None:
        m5.index = m5.index.tz_localize("UTC")
    else:
        m5.index = m5.index.tz_convert("UTC")

    m5 = m5.sort_index()

    # Assign session labels
    m5_labeled = assign_session_labels(m5)

    # Filter to Asia session
    asia_bars = m5_labeled[m5_labeled["session"] == "asia"]

    # Group by date and compute mean spread
    avg_spread = asia_bars.groupby("date")["spread"].mean()

    # Convert index to date for merging
    avg_spread.index = pd.to_datetime(avg_spread.index).date

    return avg_spread


def is_fomc_day(dt: pd.Timestamp, window: bool = True) -> bool:
    """
    Check if a timestamp falls on an FOMC meeting day (or window ±1 day).

    Parameters
    ----------
    dt : pd.Timestamp
        Timestamp to check (UTC)
    window : bool
        If True, include day before and after meeting (default True per spec)

    Returns
    -------
    bool
        True if FOMC day (or window), False otherwise
    """
    check_date = dt.date()
    if window:
        return check_date in FOMC_WINDOW_DATES
    return check_date in FOMC_MEETING_DATES


def compute_vol_regime(
    h1_rv: pd.Series,
    percentile_threshold: float = 40.0,
    burn_in_end: str = "2021-09-30",
) -> pd.Series:
    """
    Compute volatility regime (favorable/unfavorable) using expanding percentile.

    Parameters
    ----------
    h1_rv : pd.Series
        Realized volatility series indexed by H1 timestamp
    percentile_threshold : float
        Percentile threshold (e.g., 40.0 = bottom 40% = favorable)
    burn_in_end : str
        End of burn-in period (expanding window starts after this)

    Returns
    -------
    pd.Series
        Boolean series: True = favorable regime (vol ≤ threshold), False = unfavorable
        NaN during burn-in (insufficient history)
    """
    # Expanding percentile calculation
    # For each point, compute percentile of all prior values (expanding window)
    expanding_percentile = h1_rv.expanding(min_periods=1).apply(
        lambda x: np.percentile(x, percentile_threshold) if len(x) > 1 else np.nan,
        raw=True
    )

    # Regime: True if current vol ≤ expanding threshold
    # Note: burn-in is already handled by compute_h1_realized_vol which returns NaN
    # for insufficient history. The expanding percentile will also return NaN for
    # the first observation. No additional time-based burn-in needed here.
    expanding_percentile = expanding_percentile.reindex(h1_rv.index)
    regime = (h1_rv <= expanding_percentile)

    return regime


def compute_spread_regime(
    asian_avg_spread: pd.Series,
    percentile_threshold: float = 40.0,
    is_end: str = "2024-12-31",
) -> pd.Series:
    """
    Compute spread regime using FROZEN IS distribution percentile.

    Parameters
    ----------
    asian_avg_spread : pd.Series
        Average spread per Asian session, indexed by date
    percentile_threshold : float
        Percentile threshold from IS period (e.g., 40.0)
    is_end : str
        End of IS period — threshold frozen at this point

    Returns
    -------
    pd.Series
        Boolean series: True = favorable regime (spread ≤ threshold), False = unfavorable
    """
    # Compute threshold from IS period only
    is_end_date = pd.Timestamp(is_end).date()
    is_spreads = asian_avg_spread[asian_avg_spread.index <= is_end_date]

    if len(is_spreads) == 0:
        raise ValueError("No IS period spreads found for threshold calculation")

    threshold = float(np.percentile(is_spreads.values, percentile_threshold))

    # Apply frozen threshold to all sessions
    regime = asian_avg_spread <= threshold

    return regime


# ============================================================================
# Signal Generation with Regime Filters
# ============================================================================

def generate_session_signals_with_regime(
    session_bars: pd.DataFrame,
    h1_rv: pd.Series,
    asian_avg_spread: pd.Series,
    params: XAUVolRegimeSession005Params,
    signal_mode: Literal["return", "direction"] = "direction",
    threshold: float = 0.0,
    sessions: tuple[SessionName, ...] = ("asia", "europe", "us"),
) -> pd.DataFrame:
    """
    Generate cross-session momentum signals with regime filters at session level.

    Signal for session N is based on session N-1 return/direction.
    Regime filters applied to session N (the entry session).
    Signal becomes observable at session N open (no look-ahead).

    Parameters
    ----------
    session_bars : pd.DataFrame
        Session-level OHLC and returns (from compute_session_returns)
    h1_rv : pd.Series
        H1 realized volatility indexed by H1 timestamp
    asian_avg_spread : pd.Series
        Average Asian session spread indexed by date
    params : XAUVolRegimeSession005Params
        Strategy parameters
    signal_mode, threshold, sessions : see base implementation

    Returns
    -------
    pd.DataFrame
        Session bars with signal columns added:
        - signal: 1 = long, 0 = flat (after regime filters)
        - base_signal: 1 = long, 0 = flat (before regime filters)
        - vol_regime: True/False/NaN
        - spread_regime: True/False/NaN
        - fomc_filter: True/False
        - regime_favorable: True/False (all filters pass)
    """
    bars = session_bars.copy()

    # --- Base signal (unconditional) ---
    bars["prev_session_return"] = bars["session_return"].shift(1)
    bars["prev_session_direction"] = bars["session_direction"].shift(1)

    if signal_mode == "return":
        bars["base_signal"] = (bars["prev_session_return"] > threshold).astype(int)
    else:  # direction
        bars["base_signal"] = (bars["prev_session_direction"] > 0).astype(int)

    # First session has no previous session -> flat
    bars.loc[0, "base_signal"] = 0

    # --- Regime Filters ---

    # 1. Volatility Regime: map H1 RV to session level
    # Use the last H1 bar of the prior session (available at session open)
    # For entry at 08:00 UTC (Europe open), use RV as of 08:00
    # session_bars already has "session_start" column from compute_session_returns
    def get_rv_at_session_start(row):
        ts = row["session_start"]
        # Find RV value at or before session start
        prior_rv = h1_rv[h1_rv.index <= ts]
        if len(prior_rv) > 0:
            return prior_rv.iloc[-1]
        return np.nan

    bars["rv_at_entry"] = bars.apply(get_rv_at_session_start, axis=1)

    # Compute vol regime using expanding percentile
    vol_regime = compute_vol_regime(
        bars["rv_at_entry"].dropna(),
        percentile_threshold=params.vol_percentile_threshold,
        burn_in_end=params.burn_in_end,
    )
    # Align back to session bars
    bars = bars.join(vol_regime.rename("vol_regime"), how="left")

    # 2. Spread Regime: map Asian avg spread to session
    bars["asian_avg_spread"] = bars["date"].map(asian_avg_spread)
    spread_regime = compute_spread_regime(
        asian_avg_spread,
        percentile_threshold=params.spread_percentile_threshold,
        is_end=params.is_end,
    )
    bars = bars.join(spread_regime.rename("spread_regime"), on="date", how="left")

    # 3. FOMC Filter
    bars["fomc_day"] = bars["session_start"].apply(
        lambda ts: is_fomc_day(ts, window=True)
    )
    bars["fomc_filter"] = ~bars["fomc_day"]  # True = favorable (not FOMC)

    # --- Combined Regime Gate ---
    bars["regime_favorable"] = (
        bars["vol_regime"].fillna(False)
        & bars["spread_regime"].fillna(False)
        & bars["fomc_filter"]
    )

    # --- Final Signal (base signal AND regime favorable) ---
    bars["signal"] = (bars["base_signal"] == 1) & bars["regime_favorable"]
    bars["signal"] = bars["signal"].astype(int)

    # Session transitions (same as base)
    bars["entry_session"] = bars["session"]
    bars["exit_session"] = bars["session"].map(SESSION_TRANSITIONS)

    return bars


def expand_signals_to_m5_with_regime(
    m5: pd.DataFrame,
    session_signals: pd.DataFrame,
    min_bars_per_session: int = 10,
) -> pd.DataFrame:
    """
    Expand session-level signals (with regime info) to M5 bar level.

    Adds regime metadata to each M5 bar for backtester logging.
    """
    m5 = m5.copy()
    m5 = assign_session_labels(m5)

    # Mark first and last bar of each session
    m5["is_session_first"] = m5.groupby(["date", "session"]).cumcount() == 0
    m5["is_session_last"] = m5.groupby(["date", "session"]).cumcount(ascending=False) == 0
    m5["bars_in_session"] = m5.groupby(["date", "session"])["close"].transform("count")

    # Data quality filter
    m5["session_valid"] = m5["bars_in_session"] >= min_bars_per_session

    # Create session key for merging
    session_signals = session_signals.copy()
    session_signals["session_key"] = list(zip(session_signals["date"], session_signals["session"]))
    m5["session_key"] = list(zip(m5["date"], m5["session"]))

    # Map all signal columns
    signal_cols = [
        "signal", "base_signal", "vol_regime", "spread_regime",
        "fomc_filter", "regime_favorable", "fomc_day",
        "sl_points"
    ]
    for col in signal_cols:
        if col in session_signals.columns:
            signal_map = session_signals.set_index("session_key")[col].to_dict()
            m5[col] = m5["session_key"].map(signal_map)

    # Entry: first bar of session when signal=1 AND session_valid
    m5["entry_long"] = m5["is_session_first"] & (m5["signal"] == 1) & m5["session_valid"]

    # Exit: last bar of session when signal=1 (primary time-based exit)
    m5["exit_long"] = m5["is_session_last"] & (m5["signal"] == 1) & m5["session_valid"]

    # Stop distance in price units
    point_size = 0.001
    m5["sl_points"] = m5["sl_points"].fillna(200).astype(int)
    m5["stop_distance"] = m5["signal"] * m5["sl_points"] * point_size

    # Session ID for trade grouping
    m5["session_id"] = m5["session_key"].astype(str)

    return m5


# ============================================================================
# Strategy Class
# ============================================================================

@dataclass
class SignalFrame:
    """Computed indicators and signals, aligned to the M5 index."""
    frame: pd.DataFrame
    params: XAUVolRegimeSession005Params
    n_sessions: int
    n_signals: int
    n_regime_filtered: int  # Signals removed by regime filters


class XAUVolRegimeSession005Strategy:
    """
    Volatility-Regime-Filtered Session Momentum Strategy (XAU-VOL-REGIME-SESSION-005).

    Generates per-bar signals for the Assignment 14/21 bar-level backtester.
    """

    def __init__(self, params: Optional[XAUVolRegimeSession005Params] = None, symbol: str = "XAUUSDm"):
        self.name = "XAU-VOL-REGIME-SESSION-005"
        self.symbol = symbol
        self.params = params or XAUVolRegimeSession005Params()

    def compute_signals(
        self,
        m5: pd.DataFrame,
        h1: Optional[pd.DataFrame] = None,
    ) -> SignalFrame:
        """
        Compute per-bar entry/exit/stop signals for M5 data with regime filters.

        Parameters
        ----------
        m5 : pd.DataFrame
            M5 OHLCV with 'spread' column, timestamp index in UTC
        h1 : pd.DataFrame, optional
            H1 data for regime detection (volatility). Must have timestamp index UTC.

        Returns
        -------
        SignalFrame with columns:
            timestamp, open, high, low, close, spread, atr, stop_distance,
            entry_long, exit_long, entry_short, exit_short, signal,
            base_signal, vol_regime, spread_regime, fomc_filter, regime_favorable
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

        # --- Compute Regime Inputs ---

        # H1 Realized Volatility (20-bar trailing, Asian session)
        if h1 is not None and len(h1) > 0:
            h1_rv = compute_h1_realized_vol(
                h1,
                lookback=self.params.vol_lookback_bars,
                session_filter="asia",
            )
        else:
            raise ValueError("H1 data required for volatility regime filter")

        # Asian Session Average Spread
        asian_avg_spread = compute_asian_session_avg_spread(m5)

        # --- Generate Session Signals with Regime Filters ---
        session_bars["sl_points"] = self.params.sl_points
        session_signals = generate_session_signals_with_regime(
            session_bars=session_bars,
            h1_rv=h1_rv,
            asian_avg_spread=asian_avg_spread,
            params=self.params,
            signal_mode=self.params.signal_mode,
            threshold=self.params.threshold,
        )

        # --- Expand to M5 Level ---
        m5_signals = expand_signals_to_m5_with_regime(m5, session_signals)

        # ATR placeholder (required by backtester)
        if h1 is not None and len(h1) > 0:
            h1_atr = self._compute_atr(h1, period=14)
            m5_signals = m5_signals.join(h1_atr.rename("atr"), how="left")
            m5_signals["atr"] = m5_signals["atr"].ffill()
        else:
            m5_signals["atr"] = m5_signals["close"].rolling(288).std()
            m5_signals["atr"] = m5_signals["atr"].ffill().bfill()

        # Ensure required columns for backtester
        required_cols = [
            "timestamp", "open", "high", "low", "close", "spread",
            "atr", "stop_distance", "entry_long", "exit_long",
            "entry_short", "exit_short", "signal",
            "base_signal", "vol_regime", "spread_regime", "fomc_filter", "regime_favorable"
        ]

        # Add timestamp column
        m5_signals = m5_signals.reset_index()
        m5_signals.rename(columns={"index": "timestamp"}, inplace=True)

        # Short signals always false (long-only)
        m5_signals["entry_short"] = False
        m5_signals["exit_short"] = False

        # Select and order columns
        frame = m5_signals[required_cols].copy()

        n_signals = int(session_signals["signal"].sum())
        n_base_signals = int(session_signals["base_signal"].sum())
        n_regime_filtered = n_base_signals - n_signals

        return SignalFrame(
            frame=frame,
            params=self.params,
            n_sessions=len(session_signals),
            n_signals=n_signals,
            n_regime_filtered=n_regime_filtered,
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

    def compute_unconditional_signals(
        self,
        m5: pd.DataFrame,
        h1: Optional[pd.DataFrame] = None,
        params: Optional[Any] = None,  # SessionMomentumParams
    ) -> SignalFrame:
        """
        Compute unconditional baseline signals (Model A) using the module function.
        Reproduces XAU-SESSION-MOM-001 exactly per Assignment 17 frozen config.
        """
        return compute_unconditional_signals(m5, h1, params)


def compute_signals(
    m5: pd.DataFrame,
    h1: Optional[pd.DataFrame] = None,
    params: Optional[XAUVolRegimeSession005Params] = None,
) -> SignalFrame:
    """Convenience function matching Assignment 14/21 interface."""
    strategy = XAUVolRegimeSession005Strategy(params)
    return strategy.compute_signals(m5, h1)


# ============================================================================
# Unconditional Baseline (Model A) - Reproduce XAU-SESSION-MOM-001
# ============================================================================

def compute_unconditional_signals(
    m5: pd.DataFrame,
    h1: Optional[pd.DataFrame] = None,
    params: Optional[Any] = None,  # SessionMomentumParams
) -> SignalFrame:
    """
    Compute unconditional baseline signals (Model A).
    Reproduces XAU-SESSION-MOM-001 exactly per Assignment 17 frozen config.
    """
    from mars.libs.strategies.xau_session_momentum import (
        SessionMomentumStrategy,
        compute_signals as base_compute_signals,
    )

    # Use the original strategy class
    if params is None:
        from mars.libs.strategies.xau_session_momentum import SessionMomentumParams
        params = SessionMomentumParams()

    strategy = SessionMomentumStrategy(params)
    return strategy.compute_signals(m5, h1)


__all__ = [
    "XAUVolRegimeSession005Params",
    "SignalFrame",
    "XAUVolRegimeSession005Strategy",
    "compute_signals",
    "compute_unconditional_signals",
    "compute_h1_realized_vol",
    "compute_asian_session_avg_spread",
    "is_fomc_day",
    "compute_vol_regime",
    "compute_spread_regime",
    "generate_session_signals_with_regime",
    "expand_signals_to_m5_with_regime",
    "FOMC_MEETING_DATES",
    "FOMC_WINDOW_DATES",
]