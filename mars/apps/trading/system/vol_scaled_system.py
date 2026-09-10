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
        
        # Convert to contracts (assuming 1 contract = 100 oz for XAUUSD, 
        # or use contract multiplier from broker)
        contract_multiplier = 100  # 1 lot = 100 oz
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
    Hard risk rules for the trading system.

    - Max drawdown limit (daily, weekly, monthly)
    - Max position size per symbol
    - Max correlation exposure
    - Daily loss limit
    - Forced liquidation on breach
    """
    
    # Default persistence file for kill-switch state
    DEFAULT_KILL_SWITCH_FILE = "risk_kill_switch.json"
    
    def __init__(
        self,
        max_daily_loss_pct: float = 0.02,
        max_weekly_loss_pct: float = 0.05,
        max_monthly_loss_pct: float = 0.10,
        max_drawdown_pct: float = 0.15,
        max_position_pct: float = 0.10,
        max_correlation_exposure: float = 0.30,
        max_risk_per_trade_pct: float = 0.01,  # 1% per trade
        kill_switch_file: Optional[str] = None,
    ) -> None:
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_weekly_loss_pct = max_weekly_loss_pct
        self.max_monthly_loss_pct = max_monthly_loss_pct
        self.max_drawdown_pct = max_drawdown_pct
        self.max_position_pct = max_position_pct
        self.max_correlation_exposure = max_correlation_exposure
        self.max_risk_per_trade_pct = max_risk_per_trade_pct
        
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
        
        # Load persisted kill-switch state on init
        self._load_kill_switch_state()
    
    def _load_kill_switch_state(self) -> None:
        """Load kill-switch state from disk if it exists."""
        try:
            import os
            if os.path.exists(self.KILL_SWITCH_FILE):
                with open(self.KILL_SWITCH_FILE, 'r') as f:
                    state = json.load(f)
                self.kill_switch_halted = state.get('halted', False)
                self.kill_switch_triggered_at = datetime.fromisoformat(state['triggered_at']) if state.get('triggered_at') else None
                self.kill_switch_drawdown_at_trigger = state.get('drawdown_at_trigger', 0.0)
                self.kill_switch_requires_manual_reset = state.get('requires_manual_reset', True)
        except Exception as e:
            # If loading fails, start fresh (don't block initialization)
            pass
    
    def _save_kill_switch_state(self) -> None:
        """Save kill-switch state to disk."""
        try:
            state = {
                'halted': self.kill_switch_halted,
                'triggered_at': self.kill_switch_triggered_at.isoformat() if self.kill_switch_triggered_at else None,
                'drawdown_at_trigger': self.kill_switch_drawdown_at_trigger,
                'requires_manual_reset': self.kill_switch_requires_manual_reset,
            }
            with open(self.KILL_SWITCH_FILE, 'w') as f:
                json.dump(state, f)
        except Exception as e:
            # Log but don't crash
            pass
    
    def update_pnl(self, pnl: float) -> None:
        """Update PnL tracking after each trade."""
        self.daily_pnl += pnl
        self.weekly_pnl += pnl
        self.monthly_pnl += pnl
        self.current_equity += pnl
        self.peak_equity = max(self.peak_equity, self.current_equity)
    
    def reset_weekly(self, equity: float) -> None:
        """Call at start of each trading week."""
        self.weekly_pnl = 0.0
        self.current_equity = equity
        self.peak_equity = max(self.peak_equity, equity)
        self.trades_today = 0
    
    def reset_monthly(self, equity: float) -> None:
        """Call at start of each trading month."""
        self.monthly_pnl = 0.0
        self.current_equity = equity
        self.peak_equity = max(self.peak_equity, equity)
        self.trades_today = 0
    
    def check_limits(self) -> tuple[bool, list[str]]:
        """
        Check all risk limits.
        
        Returns (can_trade, violations_list)
        """
        # Check kill-switch first - if halted, block all trading
        if self.kill_switch_halted and self.kill_switch_requires_manual_reset:
            return False, [f"KILL-SWITCH ACTIVE: Drawdown {self.kill_switch_drawdown_at_trigger:.2%} exceeded at {self.kill_switch_triggered_at}. Manual reset required."]
        
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
        """Check if new position can be opened."""
        can_trade, violations = self.check_limits()
        if not can_trade:
            return False, "; ".join(violations)
        
        # Position size limit (concurrent exposure cap)
        if position_value > self.max_position_pct * equity:
            return False, f"Position value {position_value:.2f} exceeds max {self.max_position_pct:.1%} of equity"
        
        return True, "OK"
    
    def check_per_trade_risk(self, config: "TradeConfig", equity: float) -> tuple[bool, str]:
        """Check if trade risk exceeds per-trade risk limit."""
        stop_distance = abs(config.entry_price - config.stop_price)
        risk_per_contract = stop_distance * 100  # XAUUSD: 1 pip = $1 per oz, 100 oz per lot
        total_risk = config.position_size * risk_per_contract
        max_risk = equity * self.max_risk_per_trade_pct
        
        if total_risk > max_risk:
            return False, f"Trade risk ${total_risk:.2f} exceeds max {self.max_risk_per_trade_pct:.1%} of equity (${max_risk:.2f})"
        
        return True, "OK"
    
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
    
    def reset_weekly(self, equity: float) -> None:
        """Call at start of each trading week."""
        self.weekly_pnl = 0.0
        self.current_equity = equity
        self.peak_equity = max(self.peak_equity, equity)
        self.trades_today = 0
    
    def reset_monthly(self, equity: float) -> None:
        """Call at start of each trading month."""
        self.monthly_pnl = 0.0
        self.current_equity = equity
        self.peak_equity = max(self.peak_equity, equity)
        self.trades_today = 0


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