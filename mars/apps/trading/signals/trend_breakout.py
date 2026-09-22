"""
Trend/Breakout Signal Generator for XAUUSD

Implements:
- Donchian channel breakout (classic trend following)
- Dual MA crossover (trend confirmation)
- Session-aware signal generation (respects market hours)
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Literal, Optional

import numpy as np
import pandas as pd

from mars.libs.data.loaders import to_price_index
from mars.libs.features.indicators import add_baseline_indicators


class DonchianBreakoutSignal:
    """
    Donchian channel breakout signal.
    
    Long:  Close > highest high of last N periods
    Short: Close < lowest low of last N periods
    Exit:  Opposite breakout or trailing stop
    """

    def __init__(
        self,
        window: int = 20,
        exit_window: int = 10,
        session_filter: Optional[Literal["london", "ny", "overlap", "all"]] = "all",
        stop_mode: str = "atr",  # "atr" or "fixed_pips"
        risk_pips: Optional[float] = None,
        pip_size: Optional[float] = None,
        stop_multiplier: float = 2.0,
    ) -> None:
        self.window = window
        self.exit_window = exit_window
        self.session_filter = session_filter
        self.stop_mode = stop_mode
        self.risk_pips = risk_pips
        self.pip_size = pip_size
        self.stop_multiplier = stop_multiplier

    def _session_mask(self, index: pd.DatetimeIndex) -> pd.Series:
        """Filter signals by trading session (UTC)."""
        hour = index.hour
        if self.session_filter == "london":
            return (hour >= 8) & (hour < 17)
        elif self.session_filter == "ny":
            return (hour >= 13) & (hour < 22)
        elif self.session_filter == "overlap":
            return (hour >= 13) & (hour < 17)
        return pd.Series(True, index=index)

    def generate(self, price: pd.DataFrame) -> pd.DataFrame:
        """
        Generate breakout signals.
        
        Parameters
        ----------
        price: DataFrame with DatetimeIndex and OHLC columns
        
        Returns
        -------
        DataFrame with columns: signal (1=long, -1=short, 0=flat), 
                                entry_price, exit_price, stop_price
        """
        price = to_price_index(price).sort_index()
        
        # Donchian channels
        high_max = price["high"].rolling(self.window).max()
        low_min = price["low"].rolling(self.window).min()
        exit_high = price["high"].rolling(self.exit_window).max()
        exit_low = price["low"].rolling(self.exit_window).min()
        
        # Breakout conditions
        long_entry = price["close"] > high_max.shift(1)
        short_entry = price["close"] < low_min.shift(1)
        long_exit = price["close"] < exit_low.shift(1)
        short_exit = price["close"] > exit_high.shift(1)
        
        # Session filter
        session_ok = self._session_mask(price.index)
        long_entry &= session_ok
        short_entry &= session_ok
        
        # Build signal (1=long, -1=short, 0=flat)
        signal = pd.Series(0, index=price.index, dtype=int)
        position = 0
        
        for i in range(len(price)):
            if position == 0:
                if long_entry.iloc[i]:
                    position = 1
                elif short_entry.iloc[i]:
                    position = -1
            elif position == 1:
                if long_exit.iloc[i] or short_entry.iloc[i]:
                    position = 0
            elif position == -1:
                if short_exit.iloc[i] or long_entry.iloc[i]:
                    position = 0
            signal.iloc[i] = position
        
        # Entry/exit prices (approximate with next open)
        entry_price = price["open"].shift(-1)
        exit_price = price["open"].shift(-1)
        
        # Stop prices
        if self.stop_mode == "fixed_pips" and self.risk_pips is not None and self.pip_size is not None:
            stop_distance = self.risk_pips * self.pip_size
        else:
            # ATR-based trailing stop
            from mars.libs.features.volatility.range import ATRFeature
            atr = ATRFeature(window=14).compute(price).data["atr"]
            stop_distance = self.stop_multiplier * atr
        
        long_stop = price["close"] - stop_distance
        short_stop = price["close"] + stop_distance
        
        # Forward fill stops while in position
        long_stop = long_stop.where(signal == 1).ffill()
        short_stop = short_stop.where(signal == -1).ffill()
        
        return pd.DataFrame({
            "signal": signal,
            "entry_price": entry_price.where(signal.diff() != 0),
            "exit_price": exit_price.where(signal.diff() != 0),
            "long_stop": long_stop,
            "short_stop": short_stop,
            "long_entry": long_entry,
            "short_entry": short_entry,
            "long_exit": long_exit,
            "short_exit": short_exit,
        }, index=price.index)

    def compute_live(self, mt5, symbol: str, equity: float) -> dict:
        """
        Compute live signal for a symbol using recent MT5 data.
        
        Parameters
        ----------
        mt5: MT5 module/connection
        symbol: Trading symbol
        equity: Current account equity (for position sizing)
        
        Returns
        -------
        dict with: signal (1=long, -1=short, 0=flat), entry_price, stop_price, take_profit
        """
        import pandas as pd
        from datetime import datetime, timezone
        
        # Fetch recent bars (need window + exit_window + some buffer)
        n_bars = max(self.window, self.exit_window) + 50
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, n_bars)
        if rates is None or len(rates) < self.window:
            return {'signal': 0, 'entry_price': 0, 'stop_price': 0, 'take_profit': 0}
        
        # Convert to DataFrame
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s', utc=True)
        df = df.set_index('time')
        df = df.rename(columns={'open': 'open', 'high': 'high', 'low': 'low', 'close': 'close', 'tick_volume': 'volume'})
        df = df[['open', 'high', 'low', 'close', 'volume']]
        
        # Generate signals
        signals = self.generate(df)
        
        # Get latest signal
        latest_signal = signals['signal'].iloc[-1]
        latest_long_stop = signals['long_stop'].iloc[-1]
        latest_short_stop = signals['short_stop'].iloc[-1]
        
        if latest_signal == 1:
            return {
                'signal': 1,
                'entry_price': signals['entry_price'].iloc[-1],
                'stop_price': latest_long_stop,
                'take_profit': signals['entry_price'].iloc[-1] + (signals['entry_price'].iloc[-1] - latest_long_stop) * 3  # 3:1 R:R
            }
        elif latest_signal == -1:
            return {
                'signal': -1,
                'entry_price': signals['entry_price'].iloc[-1],
                'stop_price': latest_short_stop,
                'take_profit': signals['entry_price'].iloc[-1] - (latest_short_stop - signals['entry_price'].iloc[-1]) * 3  # 3:1 R:R
            }
        else:
            return {'signal': 0, 'entry_price': 0, 'stop_price': 0, 'take_profit': 0}


class MACrossoverSignal:
    """
    Dual Moving Average Crossover Signal.
    
    Long:  Fast MA > Slow MA (and was <= previous bar)
    Short: Fast MA < Slow MA (and was >= previous bar)
    """

    def __init__(
        self,
        fast_window: int = 50,
        slow_window: int = 200,
        ma_type: Literal["SMA", "EMA"] = "EMA",
        session_filter: Optional[Literal["london", "ny", "overlap", "all"]] = "all",
        stop_mode: str = "atr",
        risk_pips: Optional[float] = None,
        pip_size: Optional[float] = None,
        stop_multiplier: float = 2.0,
    ) -> None:
        self.fast_window = fast_window
        self.slow_window = slow_window
        self.ma_type = ma_type
        self.session_filter = session_filter
        self.stop_mode = stop_mode
        self.risk_pips = risk_pips
        self.pip_size = pip_size
        self.stop_multiplier = stop_multiplier

    def _session_mask(self, index: pd.DatetimeIndex) -> pd.Series:
        hour = index.hour
        if self.session_filter == "london":
            return (hour >= 8) & (hour < 17)
        elif self.session_filter == "ny":
            return (hour >= 13) & (hour < 22)
        elif self.session_filter == "overlap":
            return (hour >= 13) & (hour < 17)
        return pd.Series(True, index=index)

    def generate(self, price: pd.DataFrame) -> pd.DataFrame:
        price = to_price_index(price).sort_index()
        
        # Compute MAs
        if self.ma_type == "EMA":
            fast_ma = price["close"].ewm(span=self.fast_window, adjust=False).mean()
            slow_ma = price["close"].ewm(span=self.slow_window, adjust=False).mean()
        else:
            fast_ma = price["close"].rolling(self.fast_window).mean()
            slow_ma = price["close"].rolling(self.slow_window).mean()
        
        # Crossover conditions
        bullish = (fast_ma > slow_ma).astype(bool)
        bearish = (fast_ma < slow_ma).astype(bool)
        
        bullish_cross = bullish & ~bullish.shift(1, fill_value=False)
        bearish_cross = bearish & ~bearish.shift(1, fill_value=False)
        
        # Session filter
        session_ok = self._session_mask(price.index)
        bullish_cross &= session_ok
        bearish_cross &= session_ok
        
        # Build signal
        signal = pd.Series(0, index=price.index, dtype=int)
        position = 0
        
        for i in range(len(price)):
            if position == 0:
                if bullish_cross.iloc[i]:
                    position = 1
                elif bearish_cross.iloc[i]:
                    position = -1
            elif position == 1:
                if bearish_cross.iloc[i]:
                    position = 0
            elif position == -1:
                if bullish_cross.iloc[i]:
                    position = 0
            signal.iloc[i] = position
        
        entry_price = price["open"].shift(-1)
        exit_price = price["open"].shift(-1)
        
        # ATR trailing stop
        if self.stop_mode == "fixed_pips" and self.risk_pips is not None and self.pip_size is not None:
            stop_distance = self.risk_pips * self.pip_size
        else:
            from mars.libs.features.volatility.range import ATRFeature
            atr = ATRFeature(window=14).compute(price).data["atr"]
            stop_distance = self.stop_multiplier * atr
        
        long_stop = (price["close"] - stop_distance).where(signal == 1).ffill()
        short_stop = (price["close"] + stop_distance).where(signal == -1).ffill()
        
        return pd.DataFrame({
            "signal": signal,
            "entry_price": entry_price.where(signal.diff() != 0),
            "exit_price": exit_price.where(signal.diff() != 0),
            "long_stop": long_stop,
            "short_stop": short_stop,
            "bullish_cross": bullish_cross,
            "bearish_cross": bearish_cross,
        }, index=price.index)


class TrendSignalFactory:
    """Factory for creating configured trend signals."""
    
    @staticmethod
    def donchian_trend(
        window: int = 20,
        exit_window: int = 10,
        session: str = "london"
    ) -> DonchianBreakoutSignal:
        return DonchianBreakoutSignal(
            window=window,
            exit_window=exit_window,
            session_filter=session
        )
    
    @staticmethod
    def ma_crossover_trend(
        fast: int = 50,
        slow: int = 200,
        ma_type: Literal["SMA", "EMA"] = "EMA",
        session: str = "london"
    ) -> MACrossoverSignal:
        return MACrossoverSignal(
            fast_window=fast,
            slow_window=slow,
            ma_type=ma_type,
            session_filter=session
        )
    
    @staticmethod
    def combined_trend(
        donchian_window: int = 20,
        ma_fast: int = 50,
        ma_slow: int = 200,
        session: str = "london"
    ) -> "CombinedTrendSignal":
        return CombinedTrendSignal(
            donchian=DonchianBreakoutSignal(donchian_window, session_filter=session),
            ma=MACrossoverSignal(ma_fast, ma_slow, session_filter=session),
        )


class CombinedTrendSignal:
    """
    Combined signal: Donchian breakout confirmed by MA trend.
    
    Long:  Donchian long AND MA bullish
    Short: Donchian short AND MA bearish
    """
    
    def __init__(
        self,
        donchian: DonchianBreakoutSignal,
        ma: MACrossoverSignal,
    ) -> None:
        self.donchian = donchian
        self.ma = ma
    
    def generate(self, price: pd.DataFrame) -> pd.DataFrame:
        donchian_sig = self.donchian.generate(price)
        ma_sig = self.ma.generate(price)
        
        # Combine: both must agree
        combined_signal = pd.Series(0, index=price.index, dtype=int)
        combined_signal[(donchian_sig["signal"] == 1) & (ma_sig["signal"] == 1)] = 1
        combined_signal[(donchian_sig["signal"] == -1) & (ma_sig["signal"] == -1)] = -1
        
        # Use Donchian for stops, MA for entry/exit timing
        entry_price = pd.Series(np.nan, index=price.index)
        exit_price = pd.Series(np.nan, index=price.index)
        
        entry_price[donchian_sig["long_entry"] & ma_sig["bullish_cross"]] = \
            pd.concat([donchian_sig["entry_price"], ma_sig["entry_price"]], axis=1).min(axis=1)
        exit_price[donchian_sig["long_exit"] | ma_sig["bearish_cross"]] = \
            pd.concat([donchian_sig["exit_price"], ma_sig["exit_price"]], axis=1).max(axis=1)
        
        # Stops from Donchian (more conservative)
        long_stop = donchian_sig["long_stop"]
        short_stop = donchian_sig["short_stop"]
        
        return pd.DataFrame({
            "signal": combined_signal,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "long_stop": long_stop,
            "short_stop": short_stop,
        }, index=price.index)