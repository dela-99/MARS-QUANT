"""
Multi-Timeframe Hierarchy Gate for M.A.R.S. Trading System.

Sits between signal generation (Donchian breakout) and order execution.
Enforces multi-timeframe alignment before any trade is placed.

Architecture:
- 1H: Trend context (EMA50 slope sign over last 10 bars)
- 30M: Directional bias (same classifier, shorter lookback)
- 15M: Execution context (spread + ATR volatility checks)
- 5M: Entry signal (Donchian breakout - already generated)

Gate Logic: 5M signal only becomes entry if:
  1H trend AND 30M bias agree with each other AND with breakout direction,
  AND 15M context is TRADEABLE.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, Literal

import numpy as np
import pandas as pd
from mars.libs.data.loaders import normalize_ohlcv
from mars.libs.data.validation import validate_ohlcv
from mars.libs.features.volatility.range import ATRFeature


class TrendBias(Enum):
    """Trend direction at a given timeframe."""
    LONG_BIAS = 1
    SHORT_BIAS = -1
    NO_BIAS = 0


class ExecutionContext(Enum):
    """15M execution context status."""
    TRADEABLE = "TRADEABLE"
    NOT_TRADEABLE = "NOT_TRADEABLE"


class GateResult(Enum):
    """Final gate decision."""
    ALLOWED = "ALLOWED"
    REJECTED = "REJECTED"


@dataclass
class TimeframeData:
    """Normalized and validated OHLCV data for one timeframe."""
    timeframe: str
    data: pd.DataFrame
    is_valid: bool
    validation_errors: list
    validation_warnings: list


@dataclass
class MTFSignalContext:
    """Complete multi-timeframe signal context."""
    # Timeframe analyses
    trend_1h: TrendBias
    bias_30m: TrendBias
    context_15m: ExecutionContext
    context_15m_reason: str
    
    # Breakout signal from 5M
    breakout_signal: int  # 1=long, -1=short, 0=flat
    breakout_price: float
    breakout_stop: float
    
    # Gate decision
    gate_result: GateResult
    rejection_reason: Optional[str]
    
    # Metadata
    timestamp: datetime
    symbol: str


class MTFGate:
    """
    Multi-Timeframe Hierarchy Gate.
    
    Fetches, normalizes, and validates data for 1H, 30M, 15M, 5M timeframes.
    Classifies trend/bias/context at each level.
    Gates 5M breakout signals based on multi-timeframe alignment.
    """
    
    # Timeframe configurations
    TIMEFRAMES = {
        '1H': {'mt5_timeframe': 16385, 'bars': 100},      # PERIOD_H1 = 16385
        '30M': {'mt5_timeframe': 16384, 'bars': 100},     # PERIOD_M30 = 16384 (may not be available)
        '15M': {'mt5_timeframe': 15, 'bars': 200},        # PERIOD_M15 = 15
        '5M': {'mt5_timeframe': 5, 'bars': 500},          # PERIOD_M5 = 5
    }
    
    # Fallback mapping: if primary timeframe fails, resample from this source
    FALLBACK_RESAMPLE = {
        '30M': '15M',  # Resample 15M -> 30M if 30M not available
    }
    
    def __init__(
        self,
        mt5_module,
        symbol: str = 'XAUUSDm',
        ema_window: int = 50,
        trend_lookback: int = 10,
        bias_lookback: int = 8,
        spread_zscore_threshold: float = 2.0,
        atr_spike_multiplier: float = 2.5,
    ) -> None:
        self.mt5 = mt5_module
        self.symbol = symbol
        self.ema_window = ema_window
        self.trend_lookback = trend_lookback
        self.bias_lookback = bias_lookback
        self.spread_zscore_threshold = spread_zscore_threshold
        self.atr_spike_multiplier = atr_spike_multiplier
        
        # Cached data
        self._tf_data: Dict[str, TimeframeData] = {}
        self._last_fetch_time: Optional[datetime] = None
    
    def _resample_timeframe(self, source_df: pd.DataFrame, source_tf: str, target_tf: str) -> Optional[pd.DataFrame]:
        """
        Resample source timeframe to target timeframe.
        
        Uses OHLCV resampling rules:
        - Open: first open of period
        - High: max high of period
        - Low: min low of period
        - Close: last close of period
        - Volume: sum of volumes
        - Spread: mean (or last) of spreads
        """
        if source_df is None or len(source_df) == 0:
            return None
        
        # Ensure we have DatetimeIndex
        if not isinstance(source_df.index, pd.DatetimeIndex):
            return None
        
        # Determine resample rule
        resample_rules = {
            '30M': '30min',  # 30 minutes (pandas 2.0+ uses 'min' not 'T')
        }
        rule = resample_rules.get(target_tf)
        if not rule:
            return None
        
        # OHLCV resampling
        ohlcv_dict = {
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum',
        }
        
        # Add spread if present
        if 'spread' in source_df.columns:
            ohlcv_dict['spread'] = 'mean'
        
        try:
            resampled = source_df.resample(rule).agg(ohlcv_dict)
            # Drop rows with NaN (incomplete periods)
            resampled = resampled.dropna()
            
            # Reset index to have timestamp as column for normalize_ohlcv
            resampled = resampled.reset_index()
            resampled = resampled.rename(columns={'timestamp': 'timestamp'})  # keep as is
            
            return resampled
        except Exception:
            return None
    
    def fetch_all_timeframes(self) -> Dict[str, TimeframeData]:
            """
            Fetch and normalize/validate all required timeframes from MT5.
            Each timeframe goes through the SAME pipeline as historical data.
            """
            tf_data = {}
        
            # First pass: fetch all timeframes directly available from MT5
            for tf_name, config in self.TIMEFRAMES.items():
                try:
                    rates = self.mt5.copy_rates_from_pos(
                        self.symbol,
                        config['mt5_timeframe'],
                        0,
                        config['bars']
                    )
                
                    if rates is None or len(rates) == 0:
                        tf_data[tf_name] = TimeframeData(
                            timeframe=tf_name,
                            data=pd.DataFrame(),
                            is_valid=False,
                            validation_errors=[f"MT5 returned no data for {tf_name}"],
                            validation_warnings=[]
                        )
                        continue
                
                    # Convert to DataFrame (same as Phase 2 live data)
                    df = pd.DataFrame(rates)
                    df['timestamp'] = pd.to_datetime(df['time'], unit='s', utc=True)
                    # DO NOT set_index - normalize_ohlcv expects timestamp as column
                    df.rename(columns={
                        'open': 'open', 'high': 'high', 'low': 'low', 'close': 'close',
                        'tick_volume': 'volume', 'spread': 'spread', 'real_volume': 'real_volume'
                    }, inplace=True)
                
                    # NORMALIZE (same as historical data)
                    df = normalize_ohlcv(df, symbol=self.symbol, timeframe=tf_name, assume_utc=True)
                    # normalize_ohlcv returns DataFrame with RangeIndex and timestamp as column
                    # Keep it this way for validation (which expects timestamp column)
                
                    # VALIDATE (same as historical data)
                    validation_report = validate_ohlcv(df, strict=False)
                
                    # For feature computations later, we need DatetimeIndex
                    df_for_features = df.copy()
                    df_for_features.set_index('timestamp', inplace=True)
                
                    tf_data[tf_name] = TimeframeData(
                        timeframe=tf_name,
                        data=df_for_features,
                        is_valid=validation_report.ok,
                        validation_errors=validation_report.errors,
                        validation_warnings=validation_report.warnings
                    )
                
                    if validation_report.warnings:
                        print(f"[{datetime.now()}] {tf_name} validation warnings: {validation_report.warnings}")
                
                except Exception as e:
                    tf_data[tf_name] = TimeframeData(
                        timeframe=tf_name,
                        data=pd.DataFrame(),
                        is_valid=False,
                        validation_errors=[f"Fetch/normalize failed for {tf_name}: {str(e)}"],
                        validation_warnings=[]
                    )
        
            # Second pass: handle fallback resampling for failed timeframes
            for tf_name in self.FALLBACK_RESAMPLE:
                if tf_name in tf_data and not tf_data[tf_name].is_valid:
                    source_tf = self.FALLBACK_RESAMPLE[tf_name]
                    if source_tf in tf_data and tf_data[source_tf].is_valid:
                        # Resample from source timeframe
                        resampled_df = self._resample_timeframe(tf_data[source_tf].data, source_tf, tf_name)
                        if resampled_df is not None and len(resampled_df) > 0:
                            # Normalize and validate the resampled data
                            df = resampled_df.copy()
                            df = normalize_ohlcv(df, symbol=self.symbol, timeframe=tf_name, assume_utc=True)
                        
                            validation_report = validate_ohlcv(df, strict=False)
                        
                            df_for_features = df.copy()
                            df_for_features.set_index('timestamp', inplace=True)
                        
                            tf_data[tf_name] = TimeframeData(
                                timeframe=tf_name,
                                data=df_for_features,
                                is_valid=validation_report.ok,
                                validation_errors=validation_report.errors,
                                validation_warnings=validation_report.warnings
                            )
                            if validation_report.warnings:
                                print(f"[{datetime.now()}] {tf_name} validation warnings (resampled): {validation_report.warnings}")
                            continue
        
            self._tf_data = tf_data
            self._last_fetch_time = datetime.now()
            return tf_data
    
    def classify_trend_bias(self, df: pd.DataFrame, lookback: int) -> TrendBias:
        """
        Classify trend direction using EMA50 slope sign over lookback bars.
        
        Why EMA50 slope:
        - EMA reacts faster than SMA, better for trend detection
        - 50-period is standard for intermediate trend
        - Slope sign over N bars gives clear directional signal
        - No look-ahead: uses only closed bars (last bar is fully formed)
        
        Alternative considered: Higher-high/higher-low structure
        - More subjective, requires pattern recognition
        - EMA slope is deterministic and faster to compute
        """
        if len(df) < self.ema_window + lookback + 1:
            return TrendBias.NO_BIAS
        
        # Compute EMA50 on CLOSED bars only (exclude current forming bar)
        close_prices = df['close'].iloc[:-1]  # Last bar is forming
        ema = close_prices.ewm(span=self.ema_window, adjust=False).mean()
        
        # Get slope over lookback period (using .diff() on EMA)
        ema_slope = ema.diff()
        
        # Average slope over lookback period
        recent_slope = ema_slope.iloc[-lookback:].mean()
        
        if recent_slope > 0:
            return TrendBias.LONG_BIAS
        elif recent_slope < 0:
            return TrendBias.SHORT_BIAS
        else:
            return TrendBias.NO_BIAS
    
    def check_execution_context(self, df: pd.DataFrame) -> tuple[ExecutionContext, str]:
        """
        Check 15M execution context:
        1. Spread within normal range (within 2x rolling median)
        2. No extreme ATR spike (current ATR vs recent average)
        
        Returns (context, reason)
        """
        if len(df) < 50:
            return ExecutionContext.NOT_TRADEABLE, "Insufficient 15M data"
        
        # --- Spread check ---
        if 'spread' not in df.columns:
            return ExecutionContext.NOT_TRADEABLE, "No spread data"
        
        # Use closed bars only
        spread = df['spread'].iloc[:-1]
        median_spread = spread.rolling(50).median().iloc[-1]
        current_spread = spread.iloc[-1]
        
        if median_spread > 0:
            spread_ratio = current_spread / median_spread
            if spread_ratio > self.spread_zscore_threshold:
                return ExecutionContext.NOT_TRADEABLE, \
                    f"Spread spike: {spread_ratio:.1f}x median ({current_spread:.1f} vs {median_spread:.1f})"
        
        # --- ATR volatility spike check ---
        atr_result = ATRFeature(window=14).compute(df)
        atr = atr_result.data['atr'].iloc[:-1]  # Closed bars only
        
        if len(atr) < 20:
            return ExecutionContext.NOT_TRADEABLE, "Insufficient ATR data"
        
        atr_mean = atr.rolling(20).mean().iloc[-1]
        current_atr = atr.iloc[-1]
        
        if atr_mean > 0:
            atr_ratio = current_atr / atr_mean
            if atr_ratio > self.atr_spike_multiplier:
                return ExecutionContext.NOT_TRADEABLE, \
                    f"ATR spike: {atr_ratio:.1f}x avg ({current_atr:.2f} vs {atr_mean:.2f})"
        
        return ExecutionContext.TRADEABLE, "Spread and ATR within normal range"
    
    def evaluate_gate(self, breakout_signal: int, breakout_price: float, breakout_stop: float) -> MTFSignalContext:
        """
        Evaluate the complete multi-timeframe gate.
        
        Gate logic:
        - 5M breakout signal direction must match 1H trend AND 30M bias
        - 1H and 30M must agree with each other
        - 15M context must be TRADEABLE
        """
        # Ensure data is fresh
        if not self._tf_data:
            self.fetch_all_timeframes()
        
        # Check all timeframes are valid
        for tf in ['1H', '30M', '15M', '5M']:
            if tf not in self._tf_data or not self._tf_data[tf].is_valid:
                return MTFSignalContext(
                    trend_1h=TrendBias.NO_BIAS,
                    bias_30m=TrendBias.NO_BIAS,
                    context_15m=ExecutionContext.NOT_TRADEABLE,
                    context_15m_reason=f"{tf} data invalid",
                    breakout_signal=breakout_signal,
                    breakout_price=breakout_price,
                    breakout_stop=breakout_stop,
                    gate_result=GateResult.REJECTED,
                    rejection_reason=f"{tf} data invalid or missing",
                    timestamp=datetime.now(),
                    symbol=self.symbol
                )
        
        # Classify 1H trend
        tf_1h = self._tf_data['1H'].data
        trend_1h = self.classify_trend_bias(tf_1h, self.trend_lookback)
        
        # Classify 30M bias
        tf_30m = self._tf_data['30M'].data
        bias_30m = self.classify_trend_bias(tf_30m, self.bias_lookback)
        
        # Check 15M execution context
        tf_15m = self._tf_data['15M'].data
        context_15m, context_reason = self.check_execution_context(tf_15m)
        
        # Gate logic
        gate_result = GateResult.REJECTED
        rejection_reason = None
        
        if breakout_signal == 0:
            gate_result = GateResult.REJECTED
            rejection_reason = "No breakout signal (flat)"
            
        elif trend_1h == TrendBias.NO_BIAS:
            gate_result = GateResult.REJECTED
            rejection_reason = "1H trend unclear (NO_BIAS)"
            
        elif bias_30m == TrendBias.NO_BIAS:
            gate_result = GateResult.REJECTED
            rejection_reason = "30M bias unclear (NO_BIAS)"
            
        elif trend_1h != bias_30m:
            gate_result = GateResult.REJECTED
            rejection_reason = f"1H ({trend_1h.name}) vs 30M ({bias_30m.name}) disagreement"
            
        elif breakout_signal == 1 and trend_1h != TrendBias.LONG_BIAS:
            gate_result = GateResult.REJECTED
            rejection_reason = f"Long breakout but 1H trend is {trend_1h.name}"
            
        elif breakout_signal == -1 and trend_1h != TrendBias.SHORT_BIAS:
            gate_result = GateResult.REJECTED
            rejection_reason = f"Short breakout but 1H trend is {trend_1h.name}"
            
        elif context_15m == ExecutionContext.NOT_TRADEABLE:
            gate_result = GateResult.REJECTED
            rejection_reason = f"15M context NOT_TRADEABLE: {context_reason}"
            
        else:
            gate_result = GateResult.ALLOWED
            rejection_reason = None
        
        return MTFSignalContext(
            trend_1h=trend_1h,
            bias_30m=bias_30m,
            context_15m=context_15m,
            context_15m_reason=context_reason,
            breakout_signal=breakout_signal,
            breakout_price=breakout_price,
            breakout_stop=breakout_stop,
            gate_result=gate_result,
            rejection_reason=rejection_reason,
            timestamp=datetime.now(),
            symbol=self.symbol
        )


# Convenience function for integration
def create_mtf_gate(mt5_module, symbol: str = 'XAUUSDm') -> MTFGate:
    """Factory function to create MTFGate with default config."""
    return MTFGate(mt5_module=mt5_module, symbol=symbol)