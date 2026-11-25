"""
XAU-MTF-DONCHIAN-001 — H1-regime M5 Donchian trend breakout (Assignment 14).

Strategy rules (as specified by Assignment 14, section C)
-----------------------------------------------------------

**H1 regime**
    EMA(50) computed on completed H1 candles.
    Long regime  when the EMA is rising versus its value five completed H1 bars earlier.
    Short regime when the EMA is falling versus its value five completed H1 bars earlier.
    No trade when the regime is flat or unavailable.

**M5 entry**
    Donchian high/low from the previous 20 completed M5 bars, excluding the
    current signal candle.
    Long  when a completed M5 candle closes above the prior Donchian high and the
          H1 regime is long.
    Short when a completed M5 candle closes below the prior Donchian low and the
          H1 regime is short.

**Initial stop**
    ATR(14) on completed M5 bars; stop distance = 2 x ATR(14).

**Exit**
    A completed M5 close crossing the 20-bar Donchian midpoint against the
    position, or the initial stop being hit.

Timing model (no look-ahead)
----------------------------
Every indicator is computed from **completed** bars only:

* the Donchian channel at M5 bar *t* uses bars ``t-20 .. t-1``;
* the ATR at bar *t* uses completed bars up to and including *t*;
* the H1 regime used by M5 bar *t* is taken from the last H1 bar whose
  **completion time** (``bar_start + 1h``) is at or before the M5 bar's
  completion time (``bar_start + 5min``).  The H1 bar that is still forming
  inside the M5 bar is therefore never used.

The alignment is performed with ``pandas.merge_asof(direction="backward")`` on
completion timestamps, which makes the "no future information" property a
property of the code rather than of a comment.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from mars.libs.strategies.base import BaseStrategy, TradeSetup

#: Timeframe lengths in minutes, used to derive completion timestamps.
M5_MINUTES = 5
H1_MINUTES = 60


@dataclass(frozen=True)
class MtfDonchianParams:
    """Immutable parameter set for XAU-MTF-DONCHIAN-001."""

    donchian_lookback: int = 20          # bars of the Donchian channel (entry + exit midpoint)
    ema_period: int = 50                 # H1 EMA period
    ema_slope_bars: int = 5              # H1 bars back for the regime slope comparison
    atr_period: int = 14                 # M5 ATR period
    atr_stop_multiplier: float = 2.0     # initial stop distance = multiplier x ATR
    risk_fraction: float = 0.01          # fraction of equity risked per trade
    starting_equity: float = 10_000.0   # research starting equity (USD)
    allow_short: bool = True
    allow_long: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SignalFrame:
    """Computed indicators and signals, aligned to the M5 index."""

    frame: pd.DataFrame
    params: MtfDonchianParams
    h1_bars_used: int
    m5_bars_used: int


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


def compute_atr(df: pd.DataFrame, period: int) -> pd.Series:
    """ATR over completed bars.

    Reuses the repository's :class:`mars.libs.features.volatility.range.ATRFeature`
    convention (simple moving average of the true range) so that the ATR used
    here is identical to the ATR used by the live Donchian signal module.
    """
    from mars.libs.features.volatility.range import ATRFeature

    price = df[["open", "high", "low", "close"]].copy()
    price.index = pd.DatetimeIndex(df["timestamp"])
    result = ATRFeature(window=period).compute(price)
    return result.data["atr"].reset_index(drop=True)


def compute_h1_regime(h1: pd.DataFrame, params: MtfDonchianParams) -> pd.DataFrame:
    """Compute the H1 EMA regime with explicit completion timestamps."""
    frame = _require_timestamp(h1, "h1")
    ema = frame["close"].ewm(span=params.ema_period, adjust=False).mean()
    ema_prev = ema.shift(params.ema_slope_bars)
    regime = pd.Series(0, index=frame.index, dtype="int64")
    regime[ema > ema_prev] = 1
    regime[ema < ema_prev] = -1
    regime[ema.isna() | ema_prev.isna()] = 0     # flat / unavailable -> no trade
    out = pd.DataFrame(
        {
            "h1_start": frame["timestamp"],
            "h1_completion": frame["timestamp"] + pd.Timedelta(minutes=H1_MINUTES),
            "h1_ema": ema,
            "h1_ema_prev": ema_prev,
            "h1_regime": regime,
        }
    )
    return out.sort_values("h1_completion").reset_index(drop=True)


def compute_signals(
    m5: pd.DataFrame,
    h1: pd.DataFrame,
    params: MtfDonchianParams,
) -> SignalFrame:
    """Compute the Donchian channel, ATR, H1 regime and the entry/exit signals.

    Parameters
    ----------
    m5:
        M5 OHLCV frame with a ``timestamp`` column (or DatetimeIndex) and
        ``open``/``high``/``low``/``close`` columns.
    h1:
        H1 OHLCV frame in the **same time frame** as ``m5``.
    params:
        Strategy parameters.
    """
    m5f = _require_timestamp(m5, "m5")
    lookback = params.donchian_lookback

    # Donchian channel from the previous N completed bars (current bar excluded).
    prior_high = m5f["high"].shift(1)
    prior_low = m5f["low"].shift(1)
    donchian_high = prior_high.rolling(lookback, min_periods=lookback).max()
    donchian_low = prior_low.rolling(lookback, min_periods=lookback).min()
    donchian_mid = (donchian_high + donchian_low) / 2.0

    atr = compute_atr(m5f, params.atr_period)
    stop_distance = params.atr_stop_multiplier * atr

    # H1 regime aligned on completion timestamps (backward as-of join).
    h1_regime = compute_h1_regime(h1, params)
    m5f["_pos"] = np.arange(len(m5f))
    m5f["m5_completion"] = m5f["timestamp"] + pd.Timedelta(minutes=M5_MINUTES)
    aligned = pd.merge_asof(
        m5f.sort_values("m5_completion"),
        h1_regime.sort_values("h1_completion"),
        left_on="m5_completion",
        right_on="h1_completion",
        direction="backward",
    )
    # merge_asof may reorder rows: restore the original M5 bar order so that the
    # positionally-constructed indicator arrays stay aligned.
    aligned = aligned.sort_values("_pos").reset_index(drop=True)
    # Rows without any completed H1 bar have no regime -> no trade.
    regime = aligned["h1_regime"].fillna(0).astype("int64")
    # A missing H1 bar means the regime is unavailable, not flat: treat it as flat.
    regime[aligned["h1_completion"].isna()] = 0

    close = aligned["close"]
    entry_long = (close > donchian_high) & (regime == 1)
    entry_short = (close < donchian_low) & (regime == -1)
    if not params.allow_long:
        entry_long = entry_long & False
    if not params.allow_short:
        entry_short = entry_short & False

    # Structural exit: a completed close crossing the channel midpoint against
    # the position (long exits below the midpoint, short exits above it).
    exit_long = close < donchian_mid
    exit_short = close > donchian_mid

    frame = pd.DataFrame(
        {
            "timestamp": aligned["timestamp"],
            "open": aligned["open"].to_numpy(),
            "high": aligned["high"].to_numpy(),
            "low": aligned["low"].to_numpy(),
            "close": aligned["close"].to_numpy(),
            "spread": aligned["spread"].to_numpy() if "spread" in aligned.columns else np.nan,
            "tick_volume": aligned["tick_volume"].to_numpy()
            if "tick_volume" in aligned.columns
            else np.nan,
            "donchian_high": donchian_high.to_numpy(),
            "donchian_low": donchian_low.to_numpy(),
            "donchian_mid": donchian_mid.to_numpy(),
            "atr": atr.to_numpy(),
            "stop_distance": stop_distance.to_numpy(),
            "h1_ema": aligned["h1_ema"].to_numpy(),
            "h1_ema_prev": aligned["h1_ema_prev"].to_numpy(),
            "h1_regime": regime.to_numpy(),
            "h1_completion": aligned["h1_completion"].to_numpy(),
            "entry_long": entry_long.to_numpy(),
            "entry_short": entry_short.to_numpy(),
            "exit_long": exit_long.to_numpy(),
            "exit_short": exit_short.to_numpy(),
        }
    )
    return SignalFrame(
        frame=frame,
        params=params,
        h1_bars_used=int(len(h1_regime)),
        m5_bars_used=int(len(frame)),
    )


class XauMtfDonchianStrategy(BaseStrategy):
    """
    ``BaseStrategy`` adapter for XAU-MTF-DONCHIAN-001.

    The adapter converts the vectorised signal frame into ``TradeSetup`` objects
    so that the strategy plugs into the repository's existing strategy /
    risk-policy interface.  The research backtester consumes the vectorised
    :func:`compute_signals` output directly (it needs bar-level control over
    fills), but both paths run the exact same indicator code.
    """

    def __init__(
        self,
        params: Optional[MtfDonchianParams] = None,
        symbol: str = "XAUUSDm",
    ) -> None:
        super().__init__(name="XAU-MTF-DONCHIAN-001", symbol=symbol)
        self.params = params or MtfDonchianParams()

    def generate_setups(self, market_data: pd.DataFrame, **kwargs: Any) -> List[TradeSetup]:
        """
        Return candidate setups from a frame that carries both M5 and H1 data.

        ``market_data`` must contain the M5 columns plus an ``h1`` column holding
        the H1 frame, or the H1 frame must be passed as ``h1=`` keyword.
        """
        h1 = kwargs.get("h1")
        if h1 is None:
            raise ValueError("XauMtfDonchianStrategy.generate_setups requires the H1 frame")
        signals = compute_signals(market_data, h1, self.params).frame
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
                        f"H1 EMA({self.params.ema_period}) regime {int(row['h1_regime']):+d}"
                    ),
                    metadata={
                        "stop_distance": float(row["stop_distance"]),
                        "atr": float(row["atr"]),
                        "donchian_high": float(row["donchian_high"]),
                        "donchian_low": float(row["donchian_low"]),
                        "regime": int(row["h1_regime"]),
                    },
                )
            )
        return setups


__all__ = [
    "MtfDonchianParams",
    "SignalFrame",
    "XauMtfDonchianStrategy",
    "compute_atr",
    "compute_h1_regime",
    "compute_signals",
]
