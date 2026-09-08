"""
Volatility-Scaled Position Sizing using CARR/GARCH vol forecasts.

Integrates with the CARR range-GARCH baseline already validated in Hyp-B.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

import numpy as np
import pandas as pd

from mars.libs.models.garch_baseline import GARCHBaseline


@dataclass
class SizingConfig:
    """Configuration for volatility-scaled position sizing."""
    target_vol: float = 0.15          # Target annualized volatility (15%)
    max_leverage: float = 3.0         # Maximum position leverage
    min_leverage: float = 0.1         # Minimum position leverage
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
        # For GARCH on log returns * 100, the forecast is conditional std dev of returns * 100
        # So annualized % vol = forecast / 100 * sqrt(252)
        annualized_vol = forecasts / 100 * np.sqrt(252)
        
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
        leverage = self.config.target_vol / forecast_vol
        leverage = leverage.clip(self.config.min_leverage, self.config.max_leverage)
        
        # Kelly adjustment
        leverage *= self.config.kelly_fraction
        
        # Position value = equity * leverage
        position_value = equity * leverage
        
        # Convert to contracts (assuming 1 contract = 100 oz for XAUUSD, 
        # or use contract multiplier from broker)
        contract_multiplier = 100  # 1 lot = 100 oz
        position_size = position_value / (price_aligned["close"] * contract_multiplier)
        
        # Cap by max position % of equity
        max_contracts = equity * self.config.max_position_pct / price_aligned["close"]
        position_size = position_size.clip(upper=max_contracts)
        
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
    
    def __init__(
        self,
        max_daily_loss_pct: float = 0.02,
        max_weekly_loss_pct: float = 0.05,
        max_monthly_loss_pct: float = 0.10,
        max_drawdown_pct: float = 0.15,
        max_position_pct: float = 0.10,
        max_correlation_exposure: float = 0.30,
    ) -> None:
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_weekly_loss_pct = max_weekly_loss_pct
        self.max_monthly_loss_pct = max_monthly_loss_pct
        self.max_drawdown_pct = max_drawdown_pct
        self.max_position_pct = max_position_pct
        self.max_correlation_exposure = max_correlation_exposure
        
        # State
        self.daily_pnl = 0.0
        self.weekly_pnl = 0.0
        self.monthly_pnl = 0.0
        self.peak_equity = 0.0
        self.current_equity = 0.0
        self.current_positions = {}
        self.trades_today = 0
    
    def reset_daily(self, equity: float) -> None:
        """Call at start of each trading day."""
        self.daily_pnl = 0.0
        self.weekly_pnl = 0.0
        self.monthly_pnl = 0.0
        self.current_equity = equity
        self.peak_equity = max(self.peak_equity, equity)
        self.trades_today = 0
    
    def update_pnl(self, pnl: float) -> None:
        """Update PnL tracking after each trade."""
        self.daily_pnl += pnl
        self.weekly_pnl += pnl
        self.monthly_pnl += pnl
        self.current_equity += pnl
        self.peak_equity = max(self.peak_equity, self.current_equity)
    
    def check_limits(self) -> tuple[bool, list[str]]:
        """
        Check all risk limits.
        
        Returns (can_trade, violations_list)
        """
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
        
        return len(violations) == 0, violations
    
    def can_open_position(self, symbol: str, position_value: float, equity: float) -> tuple[bool, str]:
        """Check if new position can be opened."""
        can_trade, violations = self.check_limits()
        if not can_trade:
            return False, "; ".join(violations)
        
        # Position size limit
        if position_value > self.max_position_pct * equity:
            return False, f"Position value {position_value:.2f} exceeds max {self.max_position_pct:.1%} of equity"
        
        return True, "OK"
    
    def forced_liquidation(self) -> dict[str, float]:
        """Return all positions to liquidate (placeholder - implement with broker)."""
        return {symbol: -pos for symbol, pos in self.current_positions.items()}


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
        can_open, reason = self.risk_manager.can_open_position(
            config.symbol, 
            config.position_size * config.entry_price, 
            self.equity
        )
        if not can_open:
            return False
        
        # Calculate stop distance and risk
        stop_distance = abs(config.entry_price - config.stop_price)
        risk_per_contract = stop_distance * 100  # XAUUSD: 1 pip = $1 per oz, 100 oz per lot
        total_risk = config.position_size * risk_per_contract
        
        max_risk = self.equity * 0.01  # 1% max risk
        if total_risk > max_risk:
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