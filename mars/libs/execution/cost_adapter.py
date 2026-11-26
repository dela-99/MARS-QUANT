"""
Cost Adapter - Bridges Assignment 23's ExnessXAUUSDmCostModel to Backtester.

Prevents double-counting: ExnessXAUUSDmCostModel is the SINGLE
authoritative cost calculator. This adapter only translates interfaces.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Optional

from mars.libs.execution.cost_model import ExnessXAUUSDmCostModel, CostBreakdown
from mars.libs.risk.contract_aware import InstrumentSpec


class CostAdapter:
    """
    Adapter bridging Assignment 23's detailed ExnessXAUUSDmCostModel
    to the backtester's simpler CostModel/ExecutionModel.
    
    Prevents double-counting: ExnessXAUUSDmCostModel is the SINGLE
    authoritative cost calculator. This adapter only translates interfaces.
    """
    
    def __init__(self, exness_model: ExnessXAUUSDmCostModel):
        self.exness_model = exness_model
    
    def calculate_trade_cost(
        self,
        lots: float,
        entry_spread_points: float,
        exit_spread_points: float,
        hold_nights: int,
        side: str,
        entry_price: float = 0.0,
    ) -> CostBreakdown:
        """Delegate to ExnessXAUUSDmCostModel for itemized cost breakdown."""
        return self.exness_model.calculate_round_trip_cost(
            lots=lots,
            entry_spread_points=entry_spread_points,
            exit_spread_points=exit_spread_points,
            hold_nights=hold_nights,
            side=side,
            entry_price=entry_price,
        )
    
    def to_simple_cost_model(self):
        """
        Create a backtester-compatible CostModel with equivalent parameters.
        Only for UI/compatibility — actual costs calculated via ExnessXAUUSDmCostModel.
        """
        # Import here to avoid circular dependency
        from mars.apps.backtester.xau_scalping_donchian_backtest import CostModel as BacktestCostModel
        
        return BacktestCostModel(
            spread_multiplier=1.0,
            commission_per_lot_round_trip=self.exness_model.commission_per_lot_round_trip_usd,
            slippage_points=self.exness_model.slippage_points_per_fill,
            swap_per_lot_night=0.0,  # Swap handled per-trade by Exness model
            use_observed_spread=True,
            fallback_spread_points=self.exness_model.fallback_spread_points,
            cost_source="exness_xauusdm_detailed",
        )
    
    def to_execution_model(self):
        """Create execution model matching our conventions."""
        # Import here to avoid circular dependency
        from mars.apps.backtester.xau_scalping_donchian_backtest import ExecutionModel
        
        return ExecutionModel(
            entry_fill="next_bar_open",
            stop_fill="gap_aware_conservative",
            same_bar_priority="worst_price",
            exit_fill="next_bar_open",
            time_exit_fill="next_bar_open",
            reversal_policy="opposite_signal_ignored",
        )


__all__ = ["CostAdapter"]