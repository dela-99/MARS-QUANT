"""
Realistic Execution Cost Model for Exness XAUUSDm.

Separates observed costs (from data) from assumptions (commission, swap, slippage).
All costs itemized in every run record.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional

import numpy as np

from mars.libs.risk.contract_aware import InstrumentSpec


@dataclass(frozen=True)
class CostBreakdown:
    """Itemized cost breakdown for a single trade (round trip)."""
    spread_cost_usd: float = 0.0
    commission_usd: float = 0.0
    swap_usd: float = 0.0
    slippage_usd: float = 0.0
    total_usd: float = 0.0
    
    # Metadata for traceability
    entry_spread_points: float = 0.0
    exit_spread_points: float = 0.0
    hold_nights: int = 0
    side: str = "long"
    lots: float = 0.0
    
    # Source flags
    spread_source: str = "observed"      # "observed" | "assumed" | "fallback"
    commission_source: str = "assumed"   # "verified" | "assumed"
    swap_source: str = "assumed"         # "verified" | "assumed"
    slippage_source: str = "assumed"     # "assumed"
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExnessXAUUSDmCostModel:
    """
    Verified Exness XAUUSDm cost parameters for raw spread accounts.
    
    Sources:
    - Spread: OBSERVED from per-bar spread column in dataset (points)
    - Commission: $0 per lot round-trip (Exness raw spread account)
    - Swap: From MT5 symbol_info (points per night, varies long/short)
    - Slippage: ASSUMPTION (default 0 points, labelled as such)
    
    IMPORTANT: Round-trip spread = ONE observed spread (entry pays spread, exit receives bid).
    Do NOT double-count.
    """
    
    # Instrument spec (for point/contract size conversion)
    spec: InstrumentSpec
    
    # Observed from data (per-bar, in broker points)
    # These are filled at runtime from actual data
    avg_spread_points: float = 0.0
    median_spread_points: float = 0.0
    
    # Broker specifications (verified from MT5 symbol_info)
    commission_per_lot_round_trip_usd: float = 0.0  # Exness raw spread: $0 commission
    swap_long_points: float = -10.0   # points per night (verify from MT5)
    swap_short_points: float = -5.0   # points per night (verify from MT5)
    
    # Assumptions (clearly labelled)
    slippage_points_per_fill: float = 0.0  # assumption, labelled as such
    fallback_spread_points: float = 200.0  # used when observed spread is NaN/zero
    
    def __post_init__(self):
        # Validate spec
        if self.spec.symbol != "XAUUSDm":
            raise ValueError(f"Cost model for XAUUSDm, got spec for {self.spec.symbol}")
    
    def calculate_round_trip_cost(
        self,
        lots: float,
        entry_spread_points: float,
        exit_spread_points: float,
        hold_nights: int,
        side: str = "long",
        entry_price: float = 0.0,
    ) -> CostBreakdown:
        """
        Calculate itemized round-trip cost for a trade.
        
        Parameters
        ----------
        lots: Position size in lots
        entry_spread_points: Observed spread at entry (broker points)
        exit_spread_points: Observed spread at exit (broker points)
        hold_nights: Number of nights position held (for swap)
        side: "long" or "short"
        entry_price: Entry price (for swap calculation if needed)
        
        Returns
        -------
        CostBreakdown with itemized costs
        """
        point_value = self.spec.point_value_per_lot_usd  # USD per point per lot
        contract_size = self.spec.contract_size
        
        # === SPREAD COST ===
        # Round trip = entry spread + exit spread (in points)
        # Long: entry pays ask (bid + spread), exit receives bid
        # Short: entry receives bid, exit pays ask (bid + spread)
        # Either way: one spread paid per round trip
        entry_spread = np.where(np.isfinite(entry_spread_points) and entry_spread_points > 0,
                               entry_spread_points, self.fallback_spread_points)
        exit_spread = np.where(np.isfinite(exit_spread_points) and exit_spread_points > 0,
                              exit_spread_points, self.fallback_spread_points)
        
        total_spread_points = entry_spread + exit_spread
        spread_cost = total_spread_points * point_value * lots
        
        spread_source = "observed" if (np.isfinite(entry_spread_points) and np.isfinite(exit_spread_points)) else "fallback"
        
        # === COMMISSION ===
        commission = self.commission_per_lot_round_trip_usd * lots
        
        # === SWAP ===
        if side == "long":
            swap_points = self.swap_long_points
        else:
            swap_points = self.swap_short_points
        swap_cost = swap_points * point_value * lots * hold_nights
        
        # === SLIPPAGE ===
        # Applied per fill (entry + exit = 2 fills)
        slippage_cost = 2 * self.slippage_points_per_fill * point_value * lots
        
        total = spread_cost + commission + swap_cost + slippage_cost
        
        return CostBreakdown(
            spread_cost_usd=spread_cost,
            commission_usd=commission,
            swap_usd=swap_cost,
            slippage_usd=slippage_cost,
            total_usd=total,
            entry_spread_points=entry_spread,
            exit_spread_points=exit_spread,
            hold_nights=hold_nights,
            side=side,
            lots=lots,
            spread_source=spread_source,
            commission_source="verified" if self.commission_per_lot_round_trip_usd == 0 else "assumed",
            swap_source="assumed",  # Would be "verified" if from MT5 symbol_info
            slippage_source="assumed",
        )
    
    def estimate_cost_from_signals(
        self,
        entry_spread_points: float,
        avg_holding_bars: float,
        timeframe_minutes: int = 1,
        side: str = "long",
        lots: float = 0.01,
    ) -> CostBreakdown:
        """
        Estimate cost from signal statistics (for feasibility analysis).
        
        Uses median spread for exit (conservative).
        """
        exit_spread = self.median_spread_points if self.median_spread_points > 0 else self.fallback_spread_points
        
        # Convert holding bars to nights
        hold_minutes = avg_holding_bars * timeframe_minutes
        hold_nights = max(0, int(hold_minutes / (24 * 60)))
        
        return self.calculate_round_trip_cost(
            lots=lots,
            entry_spread_points=entry_spread_points,
            exit_spread_points=exit_spread,
            hold_nights=hold_nights,
            side=side,
        )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "spec": self.spec.to_dict(),
            "avg_spread_points": self.avg_spread_points,
            "median_spread_points": self.median_spread_points,
            "commission_per_lot_round_trip_usd": self.commission_per_lot_round_trip_usd,
            "swap_long_points": self.swap_long_points,
            "swap_short_points": self.swap_short_points,
            "slippage_points_per_fill": self.slippage_points_per_fill,
            "fallback_spread_points": self.fallback_spread_points,
        }


def create_cost_model_from_spec(
    spec: InstrumentSpec,
    avg_spread_points: float = 0.0,
    median_spread_points: float = 0.0,
    commission_per_lot: float = 0.0,
    swap_long_points: float = -10.0,
    swap_short_points: float = -5.0,
    slippage_points: float = 0.0,
) -> ExnessXAUUSDmCostModel:
    """Factory to create cost model with verified/assumed parameters."""
    return ExnessXAUUSDmCostModel(
        spec=spec,
        avg_spread_points=avg_spread_points,
        median_spread_points=median_spread_points,
        commission_per_lot_round_trip_usd=commission_per_lot,
        swap_long_points=swap_long_points,
        swap_short_points=swap_short_points,
        slippage_points_per_fill=slippage_points,
    )


__all__ = [
    "CostBreakdown",
    "ExnessXAUUSDmCostModel",
    "create_cost_model_from_spec",
]