"""
XAU-SCALPING-DONCHIAN-001 — Short-Horizon Scalping Architecture (Assignment 22).

Recovers the earliest working Donchian breakout system (XAU-MTF-DONCHIAN-001 from
Assignment 14) and extends it for short-horizon scalping on M1/M5 timeframes with
~3-6 minute holding duration.

Strategy rules (Version 1 recovered + Assignment 22 extensions)
--------------------------------------------------------------

**Base Version 1 Rules (XAU-MTF-DONCHIAN-001, Assignment 14)**
* H1 regime: EMA(50) on completed H1 candles; long when rising vs 5 bars ago,
  short when falling vs 5 bars ago.
* M5 entry: Donchian(20) breakout on completed M5 bars (prior 20 bars, excl. current).
  Long when close > prior Donchian high AND H1 regime long.
  Short when close < prior Donchian low AND H1 regime short.
* Initial stop: 2 x ATR(14) on completed M5 bars.
* Exit: Completed M5 close crossing Donchian midpoint against position, OR stop hit.
* Timing: All indicators from COMPLETED bars only. H1-to-M5 alignment via
  merge_asof(backward) on completion timestamps.

**Assignment 22 Scalping Extensions**
* Timeframe flexibility: M1 (execution) + M5/H1 (context) OR M5 (execution) + H1 (context)
  — configurable via `execution_timeframe` parameter.
* Max holding duration: Configurable max bars (default 6 M5 bars = 30 min; for
  true scalping ~3-6 min use M1 execution with max_bars=6).
* Scalping exits: Time-based exit at max holding duration (in addition to
  Donchian midpoint and stop).
* Risk engine integration: ContractAwareFixedFractionalRisk with $30 equity,
  1% risk/trade, 0.01 min lot, Exness XAUUSDm specs. Reject if min lot breaches
  risk budget — NEVER force trade.
* Signal/Execution separation: `compute_signals()` is pure signal generation
  (no position state). Backtester handles execution, fills, risk checks.

Data Requirements
-----------------
* M5 v1.2.0 / H1 v1.2.0: Available (369,972 M5 bars, 30,898 H1 bars, 2021-07 to 2026-10)
* M1: NOT currently available in repository. Architecture supports it when added.

Version Preservation
--------------------
This module EXTENDS Version 1 — it does NOT overwrite or modify
`mars.libs.strategies.xau_mtf_donchian`. All Version 1 code and historical
results are preserved.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Literal, Optional

import numpy as np
import pandas as pd

from mars.libs.strategies.base import BaseStrategy, TradeSetup
from mars.libs.strategies.xau_mtf_donchian import (
    MtfDonchianParams,
    SignalFrame,
    compute_atr,
    compute_h1_regime,
    compute_signals as compute_v1_signals,
    H1_MINUTES,
    M5_MINUTES,
)

# Timeframe constants in minutes
M1_MINUTES = 1
M5_MINUTES = 5
H1_MINUTES = 60


@dataclass(frozen=True)
class ScalpingDonchianParams:
    """
    Immutable parameter set for XAU-SCALPING-DONCHIAN-001.

    Extends MtfDonchianParams with scalping-specific parameters.
    """

    # --- Version 1 Base Parameters (preserved from XAU-MTF-DONCHIAN-001) ---
    donchian_lookback: int = 20           # bars of the Donchian channel (entry + exit midpoint)
    ema_period: int = 50                  # H1 EMA period
    ema_slope_bars: int = 5               # H1 bars back for the regime slope comparison
    atr_period: int = 14                  # M5 ATR period (base context timeframe)
    atr_stop_multiplier: float = 2.0      # initial stop distance = multiplier x ATR
    risk_fraction: float = 0.01           # fraction of equity risked per trade
    starting_equity: float = 10_000.0     # research starting equity (USD) — preserved for reproducibility
    allow_short: bool = True
    allow_long: bool = True

    # --- Assignment 22 Scalping Extensions ---
    execution_timeframe: Literal["M1", "M5"] = "M5"   # execution timeframe: M1 or M5
    max_holding_bars: int = 6             # max bars in execution timeframe before time exit
    max_holding_minutes: int = 0          # alternative: max minutes (used only if > 0, else max_holding_bars)
    use_m1_context: bool = False          # if True and execution_timeframe=M1, also compute M1 Donchian/ATR
    m1_donchian_lookback: int = 20        # Donchian lookback for M1 (if used)
    m1_atr_period: int = 14               # ATR period for M1 (if used)
    m1_atr_stop_multiplier: float = 2.0   # Stop multiplier for M1 (if used)

    # --- $30 Account Risk Parameters (Exness XAUUSDm verified) ---
    account_equity_usd: float = 30.0      # actual starting equity for live feasibility
    leverage: int = 2000                  # 1:2000 leverage (verify with Exness)
    min_lot: float = 0.01                 # Exness minimum lot
    max_lot: float = 200.0                # Exness maximum lot
    lot_step: float = 0.01                # Exness lot step
    contract_size: float = 100.0          # XAUUSDm: 100 oz per lot
    point_size: float = 0.001             # broker tick size
    pip_size: float = 0.01                # 1 pip = 0.01 price units

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_v1_params(self) -> MtfDonchianParams:
        """Convert to Version 1 base parameters for reuse of V1 signal computation."""
        return MtfDonchianParams(
            donchian_lookback=self.donchian_lookback,
            ema_period=self.ema_period,
            ema_slope_bars=self.ema_slope_bars,
            atr_period=self.atr_period,
            atr_stop_multiplier=self.atr_stop_multiplier,
            risk_fraction=self.risk_fraction,
            starting_equity=self.starting_equity,
            allow_short=self.allow_short,
            allow_long=self.allow_long,
        )


@dataclass
class ScalpingSignalFrame:
    """
    Computed scalping indicators and signals, aligned to the execution timeframe index.

    Contains both Version 1 base signals and scalping-specific fields.
    """

    frame: pd.DataFrame
    params: ScalpingDonchianParams
    execution_bars_used: int
    context_bars_used: int


def _require_timestamp(df: pd.DataFrame, name: str) -> pd.DataFrame:
    """Return a copy of ``df`` with a UTC ``timestamp`` column."""
    out = df.copy()
    if "timestamp" not in out.columns:
        if isinstance(out.index, pd.DatetimeIndex):
            out = out.reset_index()
            if out.columns[0] != "timestamp":
                out = out.rename(columns={out.columns[0]: "timestamp"})
        else:
            raise ValueError(f"{name} requires a 'timestamp' column or a DatetimeIndex")
    ts = pd.DatetimeIndex(out["timestamp"])
    if ts.tz is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    out["timestamp"] = ts
    return out.sort_values("timestamp").reset_index(drop=True)


def _get_completion_col(tf_minutes: int) -> str:
    """Get the completion timestamp column name for a timeframe."""
    return f"{tf_minutes}min_completion"


def compute_scalping_signals(
    execution_tf: pd.DataFrame,
    context_tf: pd.DataFrame,
    h1: pd.DataFrame,
    params: ScalpingDonchianParams,
) -> ScalpingSignalFrame:
    """
    Compute scalping signals with configurable execution timeframe.

    Parameters
    ----------
    execution_tf:
        Execution timeframe OHLCV (M1 or M5) with timestamp, open/high/low/close,
        spread, tick_volume columns.
    context_tf:
        Context timeframe OHLCV (M5 if execution=M1, else M5 is both execution and context).
        Used for Donchian/ATR when execution=M1 and use_m1_context=False.
    h1:
        H1 OHLCV for regime detection.
    params:
        ScalpingDonchianParams with all configuration.

    Returns
    -------
    ScalpingSignalFrame with signals aligned to execution_tf index.

    Notes
    -----
    * When execution_timeframe="M5": execution_tf == context_tf (M5), H1 for regime.
      Uses Version 1 signal computation directly.
    * When execution_timeframe="M1": execution_tf=M1, context_tf=M5, H1 for regime.
      Donchian/ATR can be computed on M1 (if use_m1_context=True) or on M5 (if False).
      H1 regime aligned to M1 via merge_asof on completion timestamps.
    * All indicators use COMPLETED bars only — no look-ahead.
    """
    # Validate execution timeframe
    tf_minutes = M1_MINUTES if params.execution_timeframe == "M1" else M5_MINUTES

    exec_f = _require_timestamp(execution_tf, "execution_tf")
    ctx_f = _require_timestamp(context_tf, "context_tf")
    h1_f = _require_timestamp(h1, "h1")

    lookback = params.donchian_lookback

    # --- H1 Regime (always computed on H1, aligned to execution timeframe) ---
    h1_regime = compute_h1_regime(h1_f, params.to_v1_params())

    # Add execution completion timestamps
    exec_f["_pos"] = np.arange(len(exec_f))
    exec_f["exec_completion"] = exec_f["timestamp"] + pd.Timedelta(minutes=tf_minutes)

    # Align H1 regime to execution timeframe via backward merge_asof on completions
    aligned = pd.merge_asof(
        exec_f.sort_values("exec_completion"),
        h1_regime.sort_values("h1_completion"),
        left_on="exec_completion",
        right_on="h1_completion",
        direction="backward",
    )
    aligned = aligned.sort_values("_pos").reset_index(drop=True)

    # Regime: 1=long, -1=short, 0=flat/unavailable
    regime = aligned["h1_regime"].fillna(0).astype("int64")
    regime[aligned["h1_completion"].isna()] = 0

    # --- Donchian Channel & ATR ---
    if params.execution_timeframe == "M1" and params.use_m1_context:
        # Compute Donchian/ATR on M1 execution timeframe
        tf_for_indicators = aligned
        d_lookback = params.m1_donchian_lookback
        atr_period = params.m1_atr_period
        atr_mult = params.m1_atr_stop_multiplier
    else:
        # Compute Donchian/ATR on M5 context timeframe, then align to execution
        # First compute on context (M5)
        ctx_aligned = ctx_f.copy()
        ctx_aligned["ctx_completion"] = ctx_aligned["timestamp"] + pd.Timedelta(minutes=M5_MINUTES)

        prior_high = ctx_aligned["high"].shift(1)
        prior_low = ctx_aligned["low"].shift(1)
        donchian_high_ctx = prior_high.rolling(lookback, min_periods=lookback).max()
        donchian_low_ctx = prior_low.rolling(lookback, min_periods=lookback).min()
        donchian_mid_ctx = (donchian_high_ctx + donchian_low_ctx) / 2.0

        # ATR on context
        atr_ctx = compute_atr(ctx_aligned, params.atr_period)
        stop_dist_ctx = params.atr_stop_multiplier * atr_ctx

        # Align context indicators to execution timeframe
        ctx_indicators = pd.DataFrame({
            "ctx_completion": ctx_aligned["ctx_completion"],
            "donchian_high": donchian_high_ctx,
            "donchian_low": donchian_low_ctx,
            "donchian_mid": donchian_mid_ctx,
            "atr": atr_ctx,
            "stop_distance": stop_dist_ctx,
        })

        aligned = pd.merge_asof(
            aligned.sort_values("exec_completion"),
            ctx_indicators.sort_values("ctx_completion"),
            left_on="exec_completion",
            right_on="ctx_completion",
            direction="backward",
        )
        aligned = aligned.sort_values("_pos").reset_index(drop=True)

        tf_for_indicators = aligned
        d_lookback = lookback
        atr_period = params.atr_period
        atr_mult = params.atr_stop_multiplier

    # Donchian on the chosen timeframe (execution or aligned context)
    prior_high = tf_for_indicators["high"].shift(1)
    prior_low = tf_for_indicators["low"].shift(1)
    donchian_high = prior_high.rolling(d_lookback, min_periods=d_lookback).max()
    donchian_low = prior_low.rolling(d_lookback, min_periods=d_lookback).min()
    donchian_mid = (donchian_high + donchian_low) / 2.0

    # ATR on the chosen timeframe
    atr = compute_atr(tf_for_indicators, atr_period)
    stop_distance = atr_mult * atr

    # --- Entry/Exit Signals ---
    close = tf_for_indicators["close"]
    entry_long = (close > donchian_high) & (regime == 1)
    entry_short = (close < donchian_low) & (regime == -1)
    if not params.allow_long:
        entry_long = entry_long & False
    if not params.allow_short:
        entry_short = entry_short & False

    # Structural exit: close crossing Donchian midpoint against position
    exit_long = close < donchian_mid
    exit_short = close > donchian_mid

    # Time-based exit: max holding duration
    # This is handled in the backtester (position state), but we mark the max bars here
    max_holding_bars = params.max_holding_bars
    if params.max_holding_minutes > 0:
        max_holding_bars = max(1, params.max_holding_minutes // tf_minutes)

    # Build output frame
    out = pd.DataFrame({
        "timestamp": aligned["timestamp"],
        "open": aligned["open"].to_numpy(),
        "high": aligned["high"].to_numpy(),
        "low": aligned["low"].to_numpy(),
        "close": aligned["close"].to_numpy(),
        "spread": aligned["spread"].to_numpy() if "spread" in aligned.columns else np.nan,
        "tick_volume": aligned["tick_volume"].to_numpy()
            if "tick_volume" in aligned.columns else np.nan,
        "donchian_high": donchian_high.to_numpy(),
        "donchian_low": donchian_low.to_numpy(),
        "donchian_mid": donchian_mid.to_numpy(),
        "atr": atr.to_numpy(),
        "stop_distance": stop_distance.to_numpy(),
        "h1_ema": aligned["h1_ema"].to_numpy() if "h1_ema" in aligned.columns else np.nan,
        "h1_ema_prev": aligned["h1_ema_prev"].to_numpy() if "h1_ema_prev" in aligned.columns else np.nan,
        "h1_regime": regime.to_numpy(),
        "h1_completion": aligned["h1_completion"].to_numpy(),
        "entry_long": entry_long.to_numpy(),
        "entry_short": entry_short.to_numpy(),
        "exit_long": exit_long.to_numpy(),
        "exit_short": exit_short.to_numpy(),
        "max_holding_bars": max_holding_bars,
    })

    return ScalpingSignalFrame(
        frame=out,
        params=params,
        execution_bars_used=int(len(out)),
        context_bars_used=int(len(ctx_f)),
    )


class XauScalpingDonchianStrategy(BaseStrategy):
    """
    BaseStrategy adapter for XAU-SCALPING-DONCHIAN-001.

    Converts the vectorised signal frame into TradeSetup objects.
    The backtester consumes compute_scalping_signals() output directly
    for bar-level control over fills.
    """

    def __init__(
        self,
        params: Optional[ScalpingDonchianParams] = None,
        symbol: str = "XAUUSDm",
    ) -> None:
        super().__init__(name="XAU-SCALPING-DONCHIAN-001", symbol=symbol)
        self.params = params or ScalpingDonchianParams()

    def generate_setups(
        self,
        market_data: pd.DataFrame,
        *,
        context_tf: Optional[pd.DataFrame] = None,
        h1: Optional[pd.DataFrame] = None,
        **kwargs: Any,
    ) -> List[TradeSetup]:
        """
        Return candidate setups from frames carrying execution, context, and H1 data.

        Parameters
        ----------
        market_data: Execution timeframe frame (M1 or M5)
        context_tf: Context timeframe frame (M5 when execution=M1)
        h1: H1 timeframe frame
        """
        # Use explicit checks to avoid DataFrame truth value ambiguity
        ctx = context_tf if context_tf is not None else kwargs.get("context_tf")
        h1_f = h1 if h1 is not None else kwargs.get("h1")

        if ctx is None or (isinstance(ctx, pd.DataFrame) and ctx.empty):
            raise ValueError("XauScalpingDonchianStrategy.generate_setups requires context_tf")
        if h1_f is None or (isinstance(h1_f, pd.DataFrame) and h1_f.empty):
            raise ValueError("XauScalpingDonchianStrategy.generate_setups requires h1")

        signals = compute_scalping_signals(market_data, ctx, h1_f, self.params).frame
        setups: List[TradeSetup] = []
        for i in range(len(signals)):
            row = signals.iloc[i]
            side = "flat"
            if bool(row["entry_long"]):
                side = "long"
            elif bool(row["entry_short"]):
                side = "short"
            else:
                continue
            setups.append(
                TradeSetup(
                    timestamp=row["timestamp"].to_pydatetime(),
                    symbol=self.symbol,
                    side=side,
                    confidence=None,
                    rationale=(
                        f"Donchian({self.params.donchian_lookback}) breakout with "
                        f"H1 EMA({self.params.ema_period}) regime {int(row['h1_regime']):+d} "
                        f"[{self.params.execution_timeframe} execution]"
                    ),
                    metadata={
                        "stop_distance": float(row["stop_distance"]),
                        "atr": float(row["atr"]),
                        "donchian_high": float(row["donchian_high"]),
                        "donchian_low": float(row["donchian_low"]),
                        "regime": int(row["h1_regime"]),
                        "execution_timeframe": self.params.execution_timeframe,
                        "max_holding_bars": int(row["max_holding_bars"]),
                    },
                )
            )
        return setups


__all__ = [
    "ScalpingDonchianParams",
    "ScalpingSignalFrame",
    "XauScalpingDonchianStrategy",
    "compute_scalping_signals",
    "M1_MINUTES",
    "M5_MINUTES",
    "H1_MINUTES",
]