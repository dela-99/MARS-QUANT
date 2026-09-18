"""
Volatility-Scaled Position Sizing using CARR/GARCH vol forecasts.

Integrates with the CARR range-GARCH baseline already validated in Hyp-B.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional

import json
import numpy as np
import pandas as pd

from mars.libs.models.garch_baseline import GARCHBaseline


@dataclass
class SizingConfig:
    """Configuration for volatility-scaled position sizing."""
    target_vol: float = 0.15          # Target annualized volatility (15%)
    max_leverage: float = 3.0         # Maximum position leverage
    min_leverage: float = 0.01        # Minimum position leverage (1% - allows true vol scaling)
    vol_lookback: int = 20            # Lookback for realized vol calibration
    max_position_pct: float = 0.10    # Max position as % of equity
    kelly_fraction: float = 0.5       # Kelly fraction for sizing


def calculate_equity_floor(
    min_lot: float,
    contract_size: float,
    atr: float,
    stop_multiplier: float,
    ceiling_pct: float,
    quote_to_usd: float = 1.0,
) -> float:
    """
    Calculate the minimum equity required so that a min-lot trade's risk
    does not exceed the specified ceiling percentage.

    Formula: equity_floor = (min_lot * contract_size * atr * stop_multiplier * quote_to_usd) / ceiling_pct

    This represents the equity level at which the min-lot position's risk-at-stop
    equals the ceiling percentage of account equity. Below this equity, any trade
    at min-lot size would exceed the ceiling and require an override (or be rejected).

    Parameters
    ----------
    min_lot : float
        Minimum lot size allowed by broker (typically 0.01)
    contract_size : float
        Contract size (units per lot): 100,000 for FX, 100 for XAUUSD
    atr : float
        Current ATR value in price units (e.g., 0.000235 for EURUSD, 3.62 for XAUUSD)
    stop_multiplier : float
        Stop distance multiplier (typically 2.0 for 2x ATR stop)
    ceiling_pct : float
        Risk ceiling as decimal (e.g., 0.15 for 15% hard ceiling)
    quote_to_usd : float, optional
        Conversion factor from quote currency to USD (default 1.0 for USD-quoted pairs).
        For example, for USDJPY, quote_to_usd = 1 / current_USDJPY_rate.

    Returns
    -------
    float
        Minimum equity required in USD.
    """
    stop_distance = atr * stop_multiplier
    risk_per_min_lot = min_lot * contract_size * stop_distance * quote_to_usd
    equity_floor = risk_per_min_lot / ceiling_pct
    return equity_floor



class VolScaledSizer:
    """
    Volatility-scaled position sizer using CARR/GARCH vol forecasts.

    Position size = target_vol / forecasted_vol * kelly_fraction
    Capped by max_leverage, max_position_pct, and stop distance.
    """

    def __init__(
        self,
        config: Optional[SizingConfig] = None,
        garch_variant: Literal["carr", "garch"] = "carr",
    ) -> None:
        self.config = config or SizingConfig()
        self.garch = GARCHBaseline(variant=garch_variant)
        self._vol_forecasts: Optional[pd.Series] = None

    def fit(self, price: pd.DataFrame, session_meta: Optional[pd.DataFrame] = None) -> "VolScaledSizer":
        """
        Fit the CARR model on historical data.

        Parameters
        ----------
        price: OHLCV DataFrame with DatetimeIndex
        session_meta: Optional session-level data for CARR fitting
        """
        if session_meta is not None:
            self.garch.fit(session_meta, session_meta.index)
        else:
            # Create session data from price
            from mars.libs.features.hyp_b_session_vol import HypBSessionVolFeatures
            feat_pipe = HypBSessionVolFeatures()
            _, session_meta = feat_pipe.transform_with_sessions(price)
            self.garch.fit(session_meta, session_meta.index)
        return self

    def forecast_vol(self, price: pd.DataFrame, horizon: int = 1) -> pd.Series:
        """
        Generate 1-step ahead vol forecasts.

        Returns vol forecasts (annualized) aligned with price index.
        """
        # Create session meta for forecasting
        from mars.libs.features.hyp_b_session_vol import HypBSessionVolFeatures
        feat_pipe = HypBSessionVolFeatures()
        _, session_meta = feat_pipe.transform_with_sessions(price)

        # Get forecasts
        forecasts = self.garch.predict(session_meta, session_meta.index)

        # Convert to annualized percentage vol
        # For GARCH: forecasts are % return volatility PER SESSION
        # Session ≈ 4-6 hours. Annualize: session_vol * sqrt(252 * sessions_per_day)
        # Typical trading day: 4 sessions (Asia, London, Overlap, NY)
        # Annualized % vol = session_vol * sqrt(252 * 4) = session_vol * sqrt(1008)
        annualized_vol = forecasts * np.sqrt(252 * 4)  # 4 sessions per day

        # Create Series with session index
        vol_series = pd.Series(annualized_vol, index=session_meta.index, name='vol')

        # Align session forecasts to price timestamps
        # session_meta.index has session_keys like '2024-01-01_0'
        # We need to map these to the actual session end timestamps
        session_timestamps = session_meta.index.to_series().map(lambda x: pd.Timestamp(x.split('_')[0]))
        # This won't work directly - let's use the session_meta's actual timestamps if available
        # Actually, session_meta should have a timestamp column or we can infer from the index

        # For now, create a mapping from session_key to the session end time
        # Session 0 (Asia) ends at 07:55 UTC, session 1 (London) at 12:55, etc.
        # We'll use the last bar's timestamp from each session
        # But session_meta doesn't have that... let me check

        # The session_meta was built from transform_with_sessions which has timestamp in the meta_rows
        # Let's check if there's a timestamp column
        if 'timestamp' in session_meta.columns:
            session_ts = pd.to_datetime(session_meta['timestamp'])
        else:
            # Fallback: parse from session_key
            # session_key format: 'YYYY-MM-DD_N' where N is session_id
            def parse_session_ts(key):
                date_str, session_id = key.split('_')
                session_id = int(session_id)
                base = pd.Timestamp(date_str, tz='UTC')
                # Session end times in UTC
                end_times = {0: 7, 1: 12, 2: 16, 3: 21}
                return base + pd.Timedelta(hours=end_times.get(session_id, 21))
            session_ts = vol_series.index.to_series().apply(parse_session_ts)

        # Reindex vol_series to use session timestamps
        vol_series.index = session_ts
        vol_series = vol_series.sort_index()

        # Resample to match price frequency using forward fill
        vol_hourly = vol_series.reindex(price.index, method='ffill')

        self._vol_forecasts = vol_hourly
        return self._vol_forecasts

    def compute_position_size(
        self,
        price: pd.DataFrame,
        signal: pd.Series | np.ndarray | pd.DataFrame,
        equity: float,
        forecast_vol: Optional[pd.Series] = None,
        contract_multiplier: float = 100.0,  # 100 for XAUUSD (1 lot = 100 oz), 100000 for FX pairs
    ) -> pd.DataFrame:
        """
        Compute position sizes for each bar given signal and vol forecast.

        Returns DataFrame with: position_size (contracts),
                                position_value, leverage, stop_price.
        """
        if forecast_vol is None:
            forecast_vol = self.forecast_vol(price)

        # Forward fill NaN values in forecast (happens at start of series)
        forecast_vol = forecast_vol.ffill().bfill()

        # Ensure signal is a pandas Series with proper index
        # Signal can be DataFrame with 'signal' column or Series
        if isinstance(signal, pd.DataFrame):
            signal = signal["signal"]
        elif isinstance(signal, np.ndarray):
            signal = pd.Series(signal, index=price.index[:len(signal)])
        elif not isinstance(signal, pd.Series):
            signal = pd.Series(signal, index=price.index[:len(signal)])

        # Align forecast with signal
        common_idx = signal.index.intersection(forecast_vol.index)
        signal = signal.loc[common_idx]
        forecast_vol = forecast_vol.loc[common_idx]

        # Align price
        price_aligned = price.loc[common_idx]

        # Vol-scaled leverage
        # Formula: leverage = (target_vol / forecast_vol) * kelly_fraction
        # target_vol is in decimal (0.15 = 15%), forecast_vol is in % (14.55 = 14.55%)
        # Convert forecast_vol to decimal for correct unit matching
        forecast_vol_decimal = forecast_vol / 100
        leverage = (self.config.target_vol / forecast_vol_decimal) * self.config.kelly_fraction
        leverage = leverage.clip(self.config.min_leverage, self.config.max_leverage)

        # Position value = equity * leverage
        position_value = equity * leverage

        # Convert to contracts using provided contract multiplier
        position_size = position_value / (price_aligned["close"] * contract_multiplier)

        # Cap by max position % of equity
        max_position_value = equity * self.config.max_position_pct
        max_contracts = max_position_value / (price_aligned["close"] * contract_multiplier)
        position_size = position_size.clip(upper=max_contracts)

        # Recalculate position_value from capped position_size
        position_value = position_size * price_aligned["close"] * contract_multiplier

        return pd.DataFrame({
            "position_size": position_size,
            "position_value": position_value,
            "leverage": leverage,
            "forecast_vol": forecast_vol,
            "target_vol": self.config.target_vol,
        }, index=common_idx)


class RiskManager:
    """
    Hard risk rules for the trading system with tiered, account-scale-aware configuration.

    Risk tiers define per-trade risk and concurrent exposure based on account equity.
    Tier is locked at session start to prevent flapping.

    - Max drawdown limit (daily, weekly, monthly) — FIXED across all tiers
    - Max position size per symbol — from current tier
    - Max correlation exposure — from current tier
    - Daily loss limit — FIXED across all tiers
    - Per-trade risk % — from current tier (now a CEILING on total concurrent risk)
    - Min-lot override handling with hard ceiling
    - Consecutive loss circuit breaker — halts new signals after N consecutive losses
    """

    # Default persistence file for kill-switch state
    DEFAULT_KILL_SWITCH_FILE = "risk_kill_switch.json"

    # Risk tiers: (min_equity, max_equity, max_concurrent_trades, risk_pct_per_trade, reward_risk_ratio)
    # Tier is selected at session start based on equity and locked for the session
    # risk_pct_per_trade is now the MAXIMUM TOTAL RISK across ALL concurrent positions
    RISK_TIERS = [
        (0,      100,    1, 0.07, 3.0),      # $0-100: 7% risk, 1 trade max
        (100,    1000,   2, 0.03, 2.5),      # $100-1k: 3% risk, 2 trades max
        (1000,   10000,  4, 0.015, 2.0),     # $1k-10k: 1.5% risk, 4 trades max
        (10000,  float('inf'), 6, 0.01, 2.0), # $10k+: 1% risk, 6 trades max
    ]

    # Fixed thresholds (do not vary by tier)
    FIXED_MAX_DAILY_LOSS_PCT = 0.02
    FIXED_MAX_WEEKLY_LOSS_PCT = 0.05
    FIXED_MAX_MONTHLY_LOSS_PCT = 0.10
    FIXED_MAX_DRAWDOWN_PCT = 0.15

    # Min-lot override ceiling — no single trade may exceed this risk regardless of tier/min-lot
    MIN_LOT_OVERRIDE_CEILING_PCT = 0.15  # 15% hard ceiling

    # Consecutive loss circuit breaker
    DEFAULT_MAX_CONSECUTIVE_LOSSES = 2
    DEFAULT_CONSECUTIVE_LOSS_COOLDOWN_HOURS = 24  # 0 = remainder of session

    def __init__(
        self,
        kill_switch_file: Optional[str] = None,
        max_consecutive_losses: Optional[int] = None,
        consecutive_loss_cooldown_hours: Optional[int] = None,
    ) -> None:
        # Fixed thresholds
        self.max_daily_loss_pct = self.FIXED_MAX_DAILY_LOSS_PCT
        self.max_weekly_loss_pct = self.FIXED_MAX_WEEKLY_LOSS_PCT
        self.max_monthly_loss_pct = self.FIXED_MAX_MONTHLY_LOSS_PCT
        self.max_drawdown_pct = self.FIXED_MAX_DRAWDOWN_PCT

        # Tier state (set by select_tier_for_equity)
        self._current_tier: Optional[dict] = None
        self._tier_locked = False
        self._tier_locked_at_equity: float = 0.0
        self._tier_locked_at: Optional[datetime] = None

        # Kill-switch persistence file
        self.KILL_SWITCH_FILE = kill_switch_file or self.DEFAULT_KILL_SWITCH_FILE

        # State
        self.daily_pnl = 0.0
        self.weekly_pnl = 0.0
        self.monthly_pnl = 0.0
        self.peak_equity = 0.0
        self.current_equity = 0.0
        self.current_positions = {}
        self.trades_today = 0

        # Kill-switch state (persisted)
        self.kill_switch_halted = False
        self.kill_switch_triggered_at: Optional[datetime] = None
        self.kill_switch_drawdown_at_trigger: float = 0.0
        self.kill_switch_requires_manual_reset = True

        # Consecutive loss circuit breaker state
        self.max_consecutive_losses = max_consecutive_losses or self.DEFAULT_MAX_CONSECUTIVE_LOSSES
        self.consecutive_loss_cooldown_hours = consecutive_loss_cooldown_hours if consecutive_loss_cooldown_hours is not None else self.DEFAULT_CONSECUTIVE_LOSS_COOLDOWN_HOURS
        self.consecutive_losses = 0
        self.consecutive_loss_halted = False
        self.consecutive_loss_halted_at: Optional[datetime] = None
        self.last_trade_outcome: Optional[str] = None  # "win" or "loss"

        # Aggregate concurrent risk tracking
        self.total_open_risk = 0.0  # Sum of risk_at_stop for all open positions

        # Load persisted state on init (includes peak_equity)
        self._load_kill_switch_state()

    def select_tier_for_equity(self, equity: float) -> dict:
        """
        Select risk tier based on current equity.
        Called ONCE at session start — tier is then locked.
        Returns the tier dict with parameters.
        """
        if self._tier_locked:
            return self._current_tier

        for min_eq, max_eq, max_trades, risk_pct, rr_ratio in self.RISK_TIERS:
            if min_eq <= equity < max_eq:
                tier = {
                    "min_equity": min_eq,
                    "max_equity": max_eq,
                    "max_concurrent_trades": max_trades,
                    "risk_pct_per_trade": risk_pct,
                    "reward_risk_ratio": rr_ratio,
                }
                self._current_tier = tier
                self._tier_locked = True
                self._tier_locked_at_equity = equity
                self._tier_locked_at = datetime.now()
                return tier

        # Should never reach here if tiers cover all ranges
        raise ValueError(f"No tier found for equity ${equity:.2f}")

    def get_current_tier(self) -> dict:
        """Get current tier parameters (requires tier to be locked)."""
        if self._current_tier is None:
            raise RuntimeError("Tier not selected — call select_tier_for_equity() first")
        return self._current_tier

    def is_tier_locked(self) -> bool:
        return self._tier_locked

    def reset_tier_lock(self, equity: float) -> dict:
        """
        Reset tier lock for new session/day. Called at session boundary.
        Returns the newly selected tier.
        """
        self._tier_locked = False
        self._current_tier = None
        return self.select_tier_for_equity(equity)

    @property
    def max_risk_per_trade_pct(self) -> float:
        """Current tier's per-trade risk percentage (now a ceiling on total concurrent risk)."""
        if self._current_tier is None:
            raise RuntimeError("Tier not selected")
        return self._current_tier["risk_pct_per_trade"]

    @property
    def max_concurrent_trades(self) -> int:
        """Current tier's max concurrent trades."""
        if self._current_tier is None:
            raise RuntimeError("Tier not selected")
        return self._current_tier["max_concurrent_trades"]

    @property
    def reward_risk_ratio(self) -> float:
        """Current tier's target reward:risk ratio."""
        if self._current_tier is None:
            raise RuntimeError("Tier not selected")
        return self._current_tier["reward_risk_ratio"]

    def _load_kill_switch_state(self) -> None:
        """Load kill-switch state and peak_equity from disk if it exists."""
        try:
            import os
            if os.path.exists(self.KILL_SWITCH_FILE):
                with open(self.KILL_SWITCH_FILE, 'r') as f:
                    state = json.load(f)
                self.kill_switch_halted = state.get('halted', False)
                self.kill_switch_triggered_at = datetime.fromisoformat(state['triggered_at']) if state.get('triggered_at') else None
                self.kill_switch_drawdown_at_trigger = state.get('drawdown_at_trigger', 0.0)
                self.kill_switch_requires_manual_reset = state.get('requires_manual_reset', True)
                # Load persisted peak_equity if available and greater than current
                persisted_peak = state.get('peak_equity')
                if persisted_peak is not None and persisted_peak > self.peak_equity:
                    self.peak_equity = persisted_peak
        except Exception as e:
            # If loading fails, start fresh (don't block initialization)
            pass

    def _save_kill_switch_state(self) -> None:
        """Save kill-switch state and peak_equity to disk."""
        try:
            state = {
                'halted': self.kill_switch_halted,
                'triggered_at': self.kill_switch_triggered_at.isoformat() if self.kill_switch_triggered_at else None,
                'drawdown_at_trigger': self.kill_switch_drawdown_at_trigger,
                'requires_manual_reset': self.kill_switch_requires_manual_reset,
                'peak_equity': self.peak_equity,
            }
            with open(self.KILL_SWITCH_FILE, 'w') as f:
                json.dump(state, f)
        except Exception as e:
            # Log but don't crash
            pass

    def update_pnl(self, pnl: float) -> None:
        """Update PnL tracking after each trade and persist peak_equity."""
        self.daily_pnl += pnl
        self.weekly_pnl += pnl
        self.monthly_pnl += pnl
        self.current_equity += pnl
        self.peak_equity = max(self.peak_equity, self.current_equity)
        self._save_kill_switch_state()

        # Update consecutive loss tracking
        if pnl < 0:
            self.consecutive_losses += 1
            self.last_trade_outcome = "loss"
        elif pnl > 0:
            self.consecutive_losses = 0
            self.last_trade_outcome = "win"

        # Check consecutive loss circuit breaker
        if self.consecutive_losses >= self.max_consecutive_losses:
            self._trigger_consecutive_loss_halt()

    def _trigger_consecutive_loss_halt(self) -> None:
        """Trigger the consecutive loss circuit breaker halt."""
        if not self.consecutive_loss_halted:
            self.consecutive_loss_halted = True
            self.consecutive_loss_halted_at = datetime.now()
            self._log_risk_event(
                "CONSECUTIVE_LOSS_HALT",
                f"Consecutive loss circuit breaker triggered after {self.consecutive_losses} consecutive losses. "
                f"Max allowed: {self.max_consecutive_losses}. "
                f"Cooldown: {self.consecutive_loss_cooldown_hours} hours (0 = remainder of session).",
                self.current_equity, 0.0, self.daily_pnl, self.kill_switch_halted
            )

    def _check_consecutive_loss_cooldown(self) -> bool:
        """
        Check if consecutive loss cooldown period has elapsed.
        Returns True if cooldown is over and trading can resume.
        """
        if not self.consecutive_loss_halted:
            return True

        if self.consecutive_loss_halted_at is None:
            return True

        if self.consecutive_loss_cooldown_hours == 0:
            # 0 = remainder of session (never auto-clear)
            return False

        elapsed_hours = (datetime.now() - self.consecutive_loss_halted_at).total_seconds() / 3600
        if elapsed_hours >= self.consecutive_loss_cooldown_hours:
            self.consecutive_loss_halted = False
            self.consecutive_loss_halted_at = None
            self.consecutive_losses = 0
            self._log_risk_event(
                "CONSECUTIVE_LOSS_COOLDOWN_EXPIRED",
                f"Consecutive loss cooldown expired after {elapsed_hours:.1f} hours. Trading resumed.",
                self.current_equity, 0.0, self.daily_pnl, self.kill_switch_halted
            )
            return True
        return False

    def reset_weekly(self, equity: float) -> None:
        """Call at start of each trading week."""
        self.weekly_pnl = 0.0
        self.current_equity = equity
        self.peak_equity = max(self.peak_equity, equity)
        self.trades_today = 0
        # Reset consecutive loss tracker at week boundary (configurable)
        self.consecutive_losses = 0
        self.consecutive_loss_halted = False
        self.consecutive_loss_halted_at = None
        self.last_trade_outcome = None

    def reset_monthly(self, equity: float) -> None:
        """Call at start of each trading month."""
        self.monthly_pnl = 0.0
        self.current_equity = equity
        self.peak_equity = max(self.peak_equity, equity)
        self.trades_today = 0
        # Reset consecutive loss tracker at month boundary (configurable)
        self.consecutive_losses = 0
        self.consecutive_loss_halted = False
        self.consecutive_loss_halted_at = None
        self.last_trade_outcome = None

    def check_limits(self) -> tuple[bool, list[str]]:
        """
        Check all risk limits.

        Returns (can_trade, violations_list)
        """
        # Check kill-switch first - if halted, block all trading
        if self.kill_switch_halted and self.kill_switch_requires_manual_reset:
            return False, [f"KILL-SWITCH ACTIVE: Drawdown {self.kill_switch_drawdown_at_trigger:.2%} exceeded at {self.kill_switch_triggered_at}. Manual reset required."]

        # Check consecutive loss halt
        if self.consecutive_loss_halted:
            # Check if cooldown has expired
            if self._check_consecutive_loss_cooldown():
                pass  # Cooldown expired, allow trading
            else:
                return False, [f"CONSECUTIVE LOSS HALT: {self.consecutive_losses} consecutive losses. Cooldown active for {self.consecutive_loss_cooldown_hours} hours."]

        violations = []

        # Daily loss limit
        if self.daily_pnl < -self.max_daily_loss_pct * self.current_equity:
            violations.append(f"Daily loss limit exceeded: {self.daily_pnl:.2%}")

        # Weekly loss limit
        if self.weekly_pnl < -self.max_weekly_loss_pct * self.current_equity:
            violations.append(f"Weekly loss limit exceeded: {self.weekly_pnl:.2%}")

        # Monthly loss limit
        if self.monthly_pnl < -self.max_monthly_loss_pct * self.current_equity:
            violations.append(f"Monthly loss limit exceeded: {self.monthly_pnl:.2%}")

        # Max drawdown
        current_dd = (self.peak_equity - self.current_equity) / self.peak_equity
        if current_dd > self.max_drawdown_pct:
            violations.append(f"Max drawdown exceeded: {current_dd:.2%}")
            # Trigger kill-switch
            if not self.kill_switch_halted:
                self.kill_switch_halted = True
                self.kill_switch_triggered_at = datetime.now()
                self.kill_switch_drawdown_at_trigger = current_dd
                self.kill_switch_requires_manual_reset = True
                self._save_kill_switch_state()

        return len(violations) == 0, violations

    def can_open_position(self, symbol: str, position_value: float, equity: float) -> tuple[bool, str]:
        """Check if new position can be opened using current tier's limits."""
        can_trade, violations = self.check_limits()
        if not can_trade:
            return False, "; ".join(violations)

        # Position size limit (concurrent exposure cap) — from current tier
        if self._current_tier is None:
            return False, "Tier not selected — cannot open position"

        max_concurrent_trades = self._current_tier["max_concurrent_trades"]
        # Count current open trades for this symbol (and total)
        current_trades = sum(1 for pos in self.current_positions.values() if pos.get("symbol") == symbol)
        if current_trades >= max_concurrent_trades:
            return False, f"Max concurrent trades ({max_concurrent_trades}) reached for {symbol}"

        return True, "OK"

    def check_aggregate_risk(self, config: "TradeConfig", equity: float) -> tuple[bool, str]:
        """
        Check if adding this trade would exceed the tier's TOTAL concurrent risk ceiling.
        This is the AGGREGATE risk cap - the sum of all open position risks plus this
        new trade's risk must not exceed tier_risk_pct * equity.
        
        Logic:
        - Min-lot trades that exceed tier budget are exceptions handled by per-trade check
          (MIN_LOT_OVERRIDE if under 15% ceiling, REJECT if over ceiling)
        - ALL trades that exceed tier budget (min-lot or not) pass through to per-trade check
          which handles ceiling logic
        - Trades within tier budget are subject to aggregate cap
        """
        if self._current_tier is None:
            return False, "Tier not selected — cannot check aggregate risk"

        tier_risk_pct = self._current_tier["risk_pct_per_trade"]
        max_total_risk = equity * tier_risk_pct

        stop_distance = abs(config.entry_price - config.stop_price)
        risk_per_contract = stop_distance * 100  # XAUUSD: 1 pip = $1 per oz, 100 oz per lot
        new_trade_risk = config.position_size * risk_per_contract
        
        actual_risk_pct = new_trade_risk / equity
        is_min_lot = config.position_size <= 0.01
        exceeds_tier = actual_risk_pct > tier_risk_pct

        # ALL trades exceeding tier budget pass through to per-trade check
        # (min-lot gets MIN_LOT_OVERRIDE if under 15%, non-min-lot gets ceiling rejection)
        if exceeds_tier:
            return True, "OK (exceeds tier -> per-trade handles override/ceiling)"

        # For trades within tier budget, enforce aggregate cap
        projected_total_risk = self.total_open_risk + new_trade_risk
        if projected_total_risk > max_total_risk:
            if self.total_open_risk >= max_total_risk:
                return False, (
                    f"Aggregate risk cap reached: current open risk ${self.total_open_risk:.2f} "
                    f"equals/exceeds limit ${max_total_risk:.2f}. New trade risk ${new_trade_risk:.2f} rejected."
                )
            else:
                remaining_risk_budget = max_total_risk - self.total_open_risk
                return False, (
                    f"Aggregate risk cap would be exceeded: current ${self.total_open_risk:.2f} + "
                    f"new ${new_trade_risk:.2f} = ${projected_total_risk:.2f} > limit ${max_total_risk:.2f}. "
                    f"Remaining budget: ${remaining_risk_budget:.2f}"
                )

        return True, "OK"

    def check_per_trade_risk(self, config: "TradeConfig", equity: float) -> tuple[bool, str]:
        """
        Check if trade risk exceeds current tier's per-trade risk limit with min-lot override handling.
        This now also includes the aggregate risk check.
        """
        if self._current_tier is None:
            return False, "Tier not selected — cannot check trade risk"

        tier_risk_pct = self._current_tier["risk_pct_per_trade"]
        max_risk = equity * tier_risk_pct

        stop_distance = abs(config.entry_price - config.stop_price)
        risk_per_contract = stop_distance * 100  # XAUUSD: 1 pip = $1 per oz, 100 oz per lot
        total_risk = config.position_size * risk_per_contract

        # First check aggregate risk cap
        aggregate_ok, aggregate_reason = self.check_aggregate_risk(config, equity)
        if not aggregate_ok:
            return False, f"AGGREGATE_RISK_CAP: {aggregate_reason}"

        # Then check per-trade risk (with min-lot override)
        if total_risk > max_risk:
            # MIN-LOT OVERRIDE CHECK
            # If the trade uses min lot and risk exceeds tier target but is under ceiling
            min_lot = 0.01  # XAUUSDm min lot
            min_lot_risk = min_lot * risk_per_contract
            actual_risk_pct = total_risk / equity
            ceiling_pct = self.MIN_LOT_OVERRIDE_CEILING_PCT

            if actual_risk_pct > self.MIN_LOT_OVERRIDE_CEILING_PCT:
                # Hard ceiling exceeded — REJECT
                self._log_min_lot_override_event(
                    config, equity, tier_risk_pct, actual_risk_pct,
                    min_lot_risk, "REJECTED_CEILING_EXCEEDED"
                )
                return False, (
                    f"Trade risk ${total_risk:.2f} ({actual_risk_pct:.2%}) exceeds "
                    f"hard ceiling {ceiling_pct:.0%} — trade REJECTED"
                )

            # Log min-lot override but allow
            self._log_min_lot_override_event(
                config, equity, tier_risk_pct, actual_risk_pct,
                min_lot_risk, "ALLOWED_MIN_LOT_OVERRIDE"
            )
            return True, f"OK (MIN_LOT_OVERRIDE: intended {tier_risk_pct:.1%}, actual {actual_risk_pct:.2%})"

        return True, "OK"

    def register_position_risk(self, symbol: str, risk_at_stop: float, is_min_lot_override: bool = False) -> None:
        """Register a new position's risk-at-stop for aggregate tracking."""
        if is_min_lot_override:
            # Min-lot override trades don't consume the aggregate risk budget
            # They are tracked separately for monitoring but don't consume the tier budget
            self.current_positions[symbol] = {
                "risk_at_stop": risk_at_stop,
                "entry_time": datetime.now(),
                "is_min_lot_override": True,
            }
        else:
            self.total_open_risk += risk_at_stop
            self.current_positions[symbol] = {
                "risk_at_stop": risk_at_stop,
                "entry_time": datetime.now(),
                "is_min_lot_override": False,
            }

    def unregister_position_risk(self, symbol: str) -> None:
        """Remove a position's risk-at-stop from aggregate tracking when closed."""
        if symbol in self.current_positions:
            risk_at_stop = self.current_positions[symbol].get("risk_at_stop", 0.0)
            is_min_lot_override = self.current_positions[symbol].get("is_min_lot_override", False)
            if not is_min_lot_override:
                self.total_open_risk = max(0.0, self.total_open_risk - risk_at_stop)
            del self.current_positions[symbol]

    def _log_min_lot_override_event(self, config: "TradeConfig", equity: float,
                                     intended_risk_pct: float, actual_risk_pct: float,
                                     min_lot_risk: float, event_type: str) -> None:
        """Log min-lot override event for audit trail."""
        self._log_risk_event(
            "MIN_LOT_OVERRIDE",
            f"{event_type}: intended={intended_risk_pct:.2%}, actual={actual_risk_pct:.2%}, "
            f"min_lot_risk=${min_lot_risk:.2f}, equity=${equity:.2f}",
            equity, 0.0, 0.0, self.kill_switch_halted
        )

    def _log_risk_event(self, event_type: str, details: str,
                        equity: float, drawdown_pct: float,
                        daily_pnl: float, kill_switch_active: bool) -> None:
        """Log risk event to audit database."""
        import sqlite3
        from pathlib import Path
        db_path = Path(self.KILL_SWITCH_FILE).with_suffix('.risk_events.db')
        try:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS risk_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        details TEXT,
                        equity REAL,
                        drawdown_pct REAL,
                        daily_pnl REAL,
                        kill_switch_active BOOLEAN
                    )
                """)
                cursor.execute("""
                    INSERT INTO risk_events (timestamp, event_type, details, equity, drawdown_pct, daily_pnl, kill_switch_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (datetime.now().isoformat(), event_type, details, equity, drawdown_pct, daily_pnl, kill_switch_active))
                conn.commit()
        except Exception as e:
            # Log but don't crash
            pass

    def manual_reset_kill_switch(self) -> None:
        """Manually reset the kill-switch (operator action required)."""
        self.kill_switch_halted = False
        self.kill_switch_triggered_at = None
        self.kill_switch_drawdown_at_trigger = 0.0
        self.kill_switch_requires_manual_reset = False
        # Reset peak equity to current equity to accept the drawdown and prevent immediate re-trigger
        self.peak_equity = self.current_equity
        self._save_kill_switch_state()

    def forced_liquidation(self) -> dict[str, float]:
        """Return all positions to liquidate (placeholder - implement with broker)."""
        return {symbol: -pos for symbol, pos in self.current_positions.items()}

    def reset_daily(self, equity: float) -> None:
        """Call at start of each trading day."""
        self.daily_pnl = 0.0
        # Note: weekly_pnl and monthly_pnl are NOT reset daily - they accumulate
        self.current_equity = equity
        self.peak_equity = max(self.peak_equity, equity)
        self.trades_today = 0
        # Also reset tier lock for new day (session boundary)
        self._tier_locked = False
        self._current_tier = None
        # Reset consecutive loss tracker at day boundary (configurable)
        self.consecutive_losses = 0
        self.consecutive_loss_halted = False
        self.consecutive_loss_halted_at = None
        self.last_trade_outcome = None


@dataclass
class TradeConfig:
    """Configuration for a single trade."""
    symbol: str
    signal: int           # 1 = long, -1 = short
    entry_price: float
    stop_price: float
    position_size: float
    take_profit: Optional[float] = None
    max_hold_hours: int = 24
    risk_pct: float = 0.01   # 1% risk per trade
    entry_time: pd.Timestamp = None  # Bar timestamp for time-based exits


class TradeExecutor:
    """
    Execute trades with full risk management.

    Handles: entry, stop loss, take profit, trailing stop, time-based exit.
    """

    def __init__(
        self,
        equity: float,
        risk_manager: Optional[RiskManager] = None,
        sizer: Optional[VolScaledSizer] = None,
    ) -> None:
        self.equity = equity
        self.risk_manager = risk_manager or RiskManager()
        self.sizer = sizer
        self.open_positions = {}
        self.closed_trades = []
        self.equity_curve = [equity]

    def open_position(self, config: TradeConfig) -> bool:
        """Open a new position with risk checks."""
        # Check concurrent exposure cap
        can_open, reason = self.risk_manager.can_open_position(
            config.symbol,
            config.position_size * config.entry_price,
            self.equity
        )
        if not can_open:
            return False

        # Check per-trade risk limit (delegated to risk_manager)
        can_open, reason = self.risk_manager.check_per_trade_risk(config, self.equity)
        if not can_open:
            return False

        # Determine if this is a min-lot override trade
        stop_distance = abs(config.entry_price - config.stop_price)
        risk_per_contract = stop_distance * 100  # XAUUSD: 1 pip = $1 per oz, 100 oz per lot
        total_risk = config.position_size * risk_per_contract
        actual_risk_pct = total_risk / self.equity
        tier_risk_pct = self.risk_manager.max_risk_per_trade_pct
        is_min_lot_override = (
            config.position_size <= 0.01 and
            actual_risk_pct > tier_risk_pct and
            actual_risk_pct <= self.risk_manager.MIN_LOT_OVERRIDE_CEILING_PCT
        )

        # Open position
        self.open_positions[config.symbol] = {
            "entry_price": config.entry_price,
            "stop_price": config.stop_price,
            "take_profit": config.take_profit,
            "position_size": config.position_size,
            "entry_time": config.entry_time,  # Use the bar's timestamp
            "max_hold_hours": config.max_hold_hours,
            "entry_equity": self.equity,
        }

        # Register risk for aggregate tracking
        risk_at_stop = config.position_size * risk_per_contract
        self.risk_manager.register_position_risk(config.symbol, risk_at_stop, is_min_lot_override)

        return True

    def update_position(self, symbol: str, current_price: float, current_time: pd.Timestamp) -> dict:
        """Update position with current price, check stops/time exits."""
        if symbol not in self.open_positions:
            return {"action": "none", "reason": "no_position"}

        pos = self.open_positions[symbol]
        entry_price = pos["entry_price"]
        stop_price = pos["stop_price"]
        take_profit = pos.get("take_profit")
        position_size = pos["position_size"]
        entry_time = pos["entry_time"]

        # Calculate current PnL
        if position_size > 0:  # Long
            pnl = (current_price - entry_price) * 100 * position_size
            hit_stop = current_price <= stop_price
            hit_tp = take_profit and current_price >= take_profit
        else:  # Short
            pnl = (entry_price - current_price) * 100 * abs(position_size)
            hit_stop = current_price >= stop_price
            hit_tp = take_profit and current_price <= take_profit

        # Time-based exit
        hours_held = (current_time - entry_time).total_seconds() / 3600
        time_exit = hours_held >= pos["max_hold_hours"]

        # Determine action
        if hit_stop:
            return {"action": "close", "reason": "stop_loss", "pnl": pnl}
        elif hit_tp:
            return {"action": "close", "reason": "take_profit", "pnl": pnl}
        elif time_exit:
            return {"action": "close", "reason": "time_exit", "pnl": pnl}

        return {"action": "hold", "pnl": pnl, "stop_distance": abs(current_price - stop_price)}

    def close_position(self, symbol: str, price: float, reason: str) -> float:
        """Close position and return PnL."""
        if symbol not in self.open_positions:
            return 0.0

        pos = self.open_positions.pop(symbol)
        entry_price = pos["entry_price"]
        position_size = pos["position_size"]

        if position_size > 0:
            pnl = (price - entry_price) * 100 * position_size
        else:
            pnl = (entry_price - price) * 100 * abs(position_size)

        self.risk_manager.update_pnl(pnl)
        self.risk_manager.unregister_position_risk(symbol)
        self.equity += pnl
        self.closed_trades.append({
            "symbol": symbol,
            "entry_price": entry_price,
            "exit_price": price,
            "position_size": position_size,
            "pnl": pnl,
            "reason": reason,
        })

        return pnl


class TradingSystem:
    """
    Complete trading system integrating signals, sizing, and risk management.

    Usage:
        system = TradingSystem(
            signal_generator=DonchianBreakoutSignal(window=20),
            equity=100000,
        )

        # In main loop:
        signal = system.signal_generator.generate(price)
        position = system.sizer.compute_position_size(price, signal, equity)
        trade = system.execute(signal, position)
    """

    def __init__(
        self,
        signal_generator,
        equity: float = 100000,
        sizer: Optional[VolScaledSizer] = None,
        risk_manager: Optional[RiskManager] = None,
    ) -> None:
        self.signal_generator = signal_generator
        self.sizer = sizer or VolScaledSizer()
        self.risk_manager = risk_manager or RiskManager()
        self.executor = TradeExecutor(equity, self.risk_manager, self.sizer)
        self.equity = equity

    def run_backtest(
        self,
        price: pd.DataFrame,
        initial_equity: float = 100000,
    ) -> dict:
        """Run full backtest of the system."""
        self.equity = initial_equity
        self.risk_manager.current_equity = initial_equity
        self.risk_manager.peak_equity = initial_equity

        # Fit sizer
        self.sizer.fit(price)

        # Generate signals
        signals = self.signal_generator.generate(price)

        # Get vol forecasts
        forecast_vol = self.sizer.forecast_vol(price)

        # Compute position sizes
        positions = self.sizer.compute_position_size(price, signals["signal"], self.equity, forecast_vol)

        # Run simulation
        equity_curve = [self.equity]
        trades = []

        for i in range(len(price)):
            if i < len(signals):
                signal = signals["signal"].iloc[i]
                position = positions["position_size"].iloc[i] if i < len(positions) else 0
                price_i = price.iloc[i]["close"]
                time_i = price.index[i]

                # Check for exits on existing positions
                for symbol in list(self.executor.open_positions.keys()):
                    update = self.executor.update_position(symbol, price.iloc[i]["close"], price.index[i])
                    if update["action"] == "close":
                        pnl = self.executor.close_position("XAUUSD", price.iloc[i]["close"], update["reason"])
                        trades.append({
                            "time": price.index[i],
                            "pnl": pnl,
                            "reason": update["reason"],
                        })

                # Enter new position if signal and no open position
                if signal != 0 and "XAUUSD" not in self.executor.open_positions:
                    # Create trade config from signal
                    # (simplified - in reality would use signal's entry/stop)
                    pass

            equity_curve.append(self.equity)

        return {
            "equity_curve": equity_curve,
            "trades": trades,
            "final_equity": self.equity,
            "total_return": (self.equity - initial_equity) / initial_equity,
        }