"""
M5→M1 Signal/Execution Alignment Module.

Aligns M5 signal decisions to M1 execution bars without look-ahead bias.

Rules:
- M5 signal generated at M5 bar close (completion timestamp)
- Entry occurs at NEXT M1 bar OPEN after signal completion
- Stop/TP evaluated on M1 bar HIGH/LOW intrabar
- Time exit measured in elapsed M1 bars (not M5 bars)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from mars.core.timeframes import Timeframe, M1_MINUTES, M5_MINUTES, H1_MINUTES


@dataclass
class AlignmentConfig:
    """Configuration for M5→M1 alignment."""
    execution_timeframe_minutes: int = M1_MINUTES
    context_timeframe_minutes: int = M5_MINUTES
    regime_timeframe_minutes: int = H1_MINUTES
    max_holding_bars_m1: int = 6  # default max holding in M1 bars


class M5ToM1Alignment:
    """
    Align M5 signal decisions to M1 execution bars without look-ahead.
    
    The alignment uses merge_asof(backward) on bar completion timestamps,
    consistent with the Version 1 / Assignment 22 architecture.
    """
    
    def __init__(self, config: Optional[AlignmentConfig] = None):
        self.config = config or AlignmentConfig()
    
    def _add_completion_timestamp(
        self,
        df: pd.DataFrame,
        timeframe_minutes: int,
        completion_col: str,
    ) -> pd.DataFrame:
        """Add completion timestamp column to a dataframe."""
        out = df.copy()
        out[completion_col] = out["timestamp"] + pd.Timedelta(minutes=timeframe_minutes)
        return out
    
    def _prepare_signals(
        self,
        m5_signals: pd.DataFrame,
        signal_columns: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """
        Prepare M5 signals for alignment.
        
        Adds completion timestamp and selects relevant signal columns.
        """
        # Default signal columns to propagate from M5
        default_signal_cols = [
            "donchian_high", "donchian_low", "donchian_mid",
            "atr", "stop_distance",
            "h1_regime", "h1_ema", "h1_ema_prev",
            "entry_long", "entry_short",
            "exit_long", "exit_short",
            "max_holding_bars",
        ]
        
        cols = signal_columns or default_signal_cols
        available = [c for c in cols if c in m5_signals.columns]
        
        # Add completion timestamp
        m5_prepped = self._add_completion_timestamp(
            m5_signals, self.config.context_timeframe_minutes, "m5_completion"
        )
        
        # Keep timestamp and signal columns
        keep_cols = ["timestamp"] + available + ["m5_completion"]
        return m5_prepped[keep_cols].copy()
    
    def _prepare_execution(
        self,
        m1_execution: pd.DataFrame,
    ) -> pd.DataFrame:
        """Prepare M1 execution data for alignment."""
        m1_prepped = self._add_completion_timestamp(
            m1_execution, self.config.execution_timeframe_minutes, "m1_completion"
        )
        # Add position index for stable sorting
        m1_prepped["_m1_pos"] = np.arange(len(m1_prepped))
        return m1_prepped
    
    def align_signals_to_execution(
        self,
        m5_signals: pd.DataFrame,
        m1_execution: pd.DataFrame,
        signal_columns: Optional[List[str]] = None,
        forward_fill_within_m5: bool = True,
    ) -> pd.DataFrame:
        """
        Align M5 signals to M1 execution bars using merge_asof on completions.
        
        Parameters
        ----------
        m5_signals: DataFrame with M5 signals (from compute_scalping_signals)
            Must have 'timestamp' column and signal columns.
        m1_execution: DataFrame with M1 OHLCV execution data
            Must have 'timestamp', 'open', 'high', 'low', 'close', 'spread'.
        signal_columns: Optional list of signal columns to propagate.
        forward_fill_within_m5: If True, forward-fill M5 signals within each M5 bar's
            M1 children so all M1 bars in the same M5 period share the same signal.
        
        Returns
        -------
        DataFrame indexed by M1 execution bars with:
        - m1_ohlc: open, high, low, close, spread, volume
        - m5_signal_*: propagated signal columns prefixed with 'm5_signal_'
        - entry_fill_price: next M1 open + spread (for long) / open (for short)
        - stop_price, tp_price: computed from M5 signal stop_distance
        - signal_bar_index: which M1 bar the signal was generated on
        - entry_bar_index: which M1 bar entry would occur (signal_bar + 1)
        """
        # Prepare both frames
        m5_prepped = self._prepare_signals(m5_signals, signal_columns)
        m1_prepped = self._prepare_execution(m1_execution)
        
        # Ensure both have timestamp column
        if "timestamp" not in m5_prepped.columns:
            raise ValueError("m5_signals must have 'timestamp' column")
        if "timestamp" not in m1_prepped.columns:
            raise ValueError("m1_execution must have 'timestamp' column")
        
        # Get signal columns (excluding metadata columns)
        meta_cols = {"timestamp", "m5_completion"}
        sig_cols = [c for c in m5_prepped.columns if c not in meta_cols]
        
        # merge_asof: M1 execution completions <- M5 signal completions (backward)
        # This means: for each M1 bar, find the latest M5 signal that completed
        # at or before this M1 bar's completion
        aligned = pd.merge_asof(
            m1_prepped.sort_values("m1_completion"),
            m5_prepped.sort_values("m5_completion"),
            left_on="m1_completion",
            right_on="m5_completion",
            direction="backward",
        )
        
        # Restore original M1 order
        aligned = aligned.sort_values("_m1_pos").reset_index(drop=True)
        
        # Rename signal columns with prefix
        rename_map = {c: f"m5_signal_{c}" for c in sig_cols}
        aligned = aligned.rename(columns=rename_map)
        
        # Forward-fill signal columns within each M5 bar if requested
        if forward_fill_within_m5 and "m5_signal_m5_completion" in aligned.columns:
            # Group by M5 completion timestamp and forward-fill
            aligned[sig_cols_prefixed := [f"m5_signal_{c}" for c in sig_cols]] = (
                aligned.groupby("m5_signal_m5_completion")[sig_cols_prefixed]
                .ffill()
                .reset_index(level=0, drop=True)
            )
        
        # Compute entry bar index (signal occurs at M5 close -> entry at NEXT M1 open)
        # The signal is available at m5_signal_m5_completion
        # Entry happens at the next M1 bar after that completion
        aligned["signal_available"] = ~aligned["m5_signal_entry_long"].isna() & (
            aligned["m5_signal_entry_long"] | aligned["m5_signal_entry_short"]
        )
        
        # Mark signal bar and entry bar
        aligned["signal_bar_index"] = -1
        aligned["entry_bar_index"] = -1
        
        signal_mask = aligned["signal_available"]
        if signal_mask.any():
            signal_indices = np.where(signal_mask)[0]
            aligned.loc[signal_mask, "signal_bar_index"] = signal_indices
            # Entry is at NEXT M1 bar
            entry_indices = signal_indices + 1
            entry_indices = np.clip(entry_indices, 0, len(aligned) - 1)
            aligned.loc[signal_mask, "entry_bar_index"] = entry_indices
        
        # Compute fill prices for entry
        # Long: entry at next M1 open + spread
        # Short: entry at next M1 open (bid)
        aligned["entry_fill_price_long"] = np.nan
        aligned["entry_fill_price_short"] = np.nan
        
        # For bars that are entry bars, compute fill price from NEXT bar's open
        entry_bars = aligned["entry_bar_index"] >= 0
        if entry_bars.any():
            # We need to look at the NEXT bar's open for fill
            # This is a bit tricky - the entry happens at the open of the entry_bar
            # So we shift the open column by -1 to get "next bar's open"
            next_open = aligned["open"].shift(-1)
            next_spread = aligned["spread"].shift(-1) if "spread" in aligned.columns else 0
            
            aligned.loc[entry_bars, "entry_fill_price_long"] = (
                next_open[entry_bars] + next_spread[entry_bars]
            )
            aligned.loc[entry_bars, "entry_fill_price_short"] = next_open[entry_bars]
        
        # Compute stop prices from M5 signal stop_distance
        if "m5_signal_stop_distance" in aligned.columns:
            stop_dist = aligned["m5_signal_stop_distance"]
            
            # For long entry at entry_fill_price_long, stop = entry - stop_distance
            aligned["stop_price_long"] = np.where(
                np.isfinite(aligned["entry_fill_price_long"]),
                aligned["entry_fill_price_long"] - stop_dist,
                np.nan
            )
            # For short entry at entry_fill_price_short, stop = entry + stop_distance
            aligned["stop_price_short"] = np.where(
                np.isfinite(aligned["entry_fill_price_short"]),
                aligned["entry_fill_price_short"] + stop_dist,
                np.nan
            )
        
        # Compute take-profit prices (using donchian midpoint as reference)
        if "m5_signal_donchian_mid" in aligned.columns:
            donchian_mid = aligned["m5_signal_donchian_mid"]
            
            # Long TP at donchian midpoint (exit when close < mid)
            # Short TP at donchian midpoint (exit when close > mid)
            aligned["tp_price_long"] = donchian_mid
            aligned["tp_price_short"] = donchian_mid
        
        # Clean up internal columns (keep completion timestamps for validation)
        drop_cols = ["_m1_pos"]
        aligned = aligned.drop(columns=[c for c in drop_cols if c in aligned.columns])
        
        return aligned
    
    def check_no_lookahead(
        self,
        aligned: pd.DataFrame,
    ) -> Dict[str, Any]:
        """
        Verify no look-ahead bias in alignment.
        
        Checks:
        1. No future M5 signal data in current M1 bar
        2. Signal completion <= M1 completion for all rows
        3. Entry bar index > signal bar index
        """
        results = {
            "passed": True,
            "checks": {},
        }
        
        # Check 1: signal completion <= M1 completion (if both present)
        if "m5_signal_m5_completion" in aligned.columns and "m1_completion" in aligned.columns:
            violations = aligned["m5_signal_m5_completion"] > aligned["m1_completion"]
            n_violations = int(violations.sum())
            results["checks"]["signal_completion_before_m1_completion"] = {
                "passed": n_violations == 0,
                "violations": n_violations,
            }
            if n_violations > 0:
                results["passed"] = False
        
        # Check 2: entry bar > signal bar
        if "signal_bar_index" in aligned.columns and "entry_bar_index" in aligned.columns:
            valid = aligned["signal_bar_index"] >= 0
            if valid.any():
                violations = aligned.loc[valid, "entry_bar_index"] <= aligned.loc[valid, "signal_bar_index"]
                n_violations = int(violations.sum())
                results["checks"]["entry_after_signal"] = {
                    "passed": n_violations == 0,
                    "violations": n_violations,
                }
                if n_violations > 0:
                    results["passed"] = False
        
        # Check 3: No NaN signal columns before first M5 signal
        sig_cols = [c for c in aligned.columns if c.startswith("m5_signal_")]
        if sig_cols:
            # Find first row with non-NaN signal
            first_signal = aligned[sig_cols].notna().any(axis=1).idxmax()
            # All rows before first_signal should have NaN signals (or be properly aligned)
            # This is more of a sanity check
            results["checks"]["first_signal_row"] = {"row": int(first_signal)}
        
        return results
    
    def compute_holding_duration(
        self,
        entry_bar: int,
        exit_bar: int,
        timeframe_minutes: int = M1_MINUTES,
    ) -> float:
        """Compute holding duration in minutes."""
        return (exit_bar - entry_bar) * timeframe_minutes


def create_aligned_execution_frame(
    m5_signals: pd.DataFrame,
    m1_execution: pd.DataFrame,
    max_holding_bars_m1: int = 6,
) -> pd.DataFrame:
    """
    Convenience function to create fully aligned execution frame.
    
    This is the main entry point for backtester integration.
    """
    config = AlignmentConfig(max_holding_bars_m1=max_holding_bars_m1)
    aligner = M5ToM1Alignment(config)
    
    aligned = aligner.align_signals_to_execution(m5_signals, m1_execution)
    
    # Add max holding bars from M5 signals (or default)
    if "m5_signal_max_holding_bars" in aligned.columns:
        aligned["max_holding_bars_m1"] = aligned["m5_signal_max_holding_bars"]
    else:
        aligned["max_holding_bars_m1"] = max_holding_bars_m1
    
    return aligned


__all__ = [
    "M5ToM1Alignment",
    "AlignmentConfig",
    "create_aligned_execution_frame",
]