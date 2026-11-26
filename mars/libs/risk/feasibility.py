"""
Independent $30 Account Feasibility Calculator.

Verifies Assignment 22 minimum-risk calculation using actual symbol metadata.
Does NOT weaken risk limits to accommodate the $30 account.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

from mars.libs.risk.contract_aware import InstrumentSpec, floor_to_step


@dataclass(frozen=True)
class FeasibilityResult:
    """Result of $30 account feasibility analysis."""
    
    # Input parameters
    equity_usd: float
    risk_fraction: float
    risk_budget_usd: float
    
    # Symbol specs
    min_lot: float
    max_lot: float
    lot_step: float
    contract_size: float
    point_size: float
    pip_size: float
    leverage: int
    
    # Derived calculations
    avg_stop_distance_price: float
    avg_spread_points: float
    risk_per_lot_usd: float
    lots_exact: float
    lots_floored: float
    
    # Feasibility verdict
    feasible: bool
    rejection_reason: Optional[str] = None
    
    # Risk at minimum lot
    risk_at_min_lot_usd: float = 0.0
    risk_at_min_lot_multiple_of_budget: float = 0.0
    
    # Margin calculations
    entry_price: float = 0.0
    margin_required_usd: float = 0.0
    free_margin_after_entry_usd: float = 0.0
    margin_level_pct: float = 0.0
    
    # Cost per trade at min lot
    spread_cost_per_trade_usd: float = 0.0
    commission_per_trade_usd: float = 0.0
    swap_estimate_per_trade_usd: float = 0.0
    total_cost_per_trade_usd: float = 0.0
    
    # Summary
    min_equity_required_usd: float = 0.0
    summary: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def __str__(self) -> str:
        lines = [
            f"=== $30 Account Feasibility Analysis ===",
            f"Equity: ${self.equity_usd:.2f} | Risk: {self.risk_fraction*100:.1f}% | Budget: ${self.risk_budget_usd:.2f}",
            f"",
            f"Symbol Specs:",
            f"  Min Lot: {self.min_lot} | Max Lot: {self.max_lot} | Step: {self.lot_step}",
            f"  Contract Size: {self.contract_size} | Point: {self.point_size} | Pip: {self.pip_size}",
            f"  Leverage: 1:{self.leverage}",
            f"",
            f"Trade Parameters:",
            f"  Avg Stop Distance: {self.avg_stop_distance_price:.5f} price units",
            f"  Avg Spread: {self.avg_spread_points:.1f} points",
            f"",
            f"Risk Calculation:",
            f"  Risk per Lot: ${self.risk_per_lot_usd:.2f}",
            f"  Exact Lots for 1% Risk: {self.lots_exact:.6f}",
            f"  Floored Lots: {self.lots_floored:.6f}",
            f"",
            f"Feasibility: {'✅ FEASIBLE' if self.feasible else '❌ INFEASIBLE'}",
        ]
        if self.rejection_reason:
            lines.append(f"  Reason: {self.rejection_reason}")
        lines.extend([
            f"  Risk at Min Lot (0.01): ${self.risk_at_min_lot_usd:.2f} ({self.risk_at_min_lot_multiple_of_budget:.1f}x budget)",
            f"",
            f"Margin at Min Lot (entry @ {self.entry_price:.2f}):",
            f"  Required: ${self.margin_required_usd:.2f}",
            f"  Free After Entry: ${self.free_margin_after_entry_usd:.2f}",
            f"  Margin Level: {self.margin_level_pct:.1f}%",
            f"",
            f"Cost per Trade at Min Lot:",
            f"  Spread: ${self.spread_cost_per_trade_usd:.4f}",
            f"  Commission: ${self.commission_per_trade_usd:.4f}",
            f"  Swap Estimate: ${self.swap_estimate_per_trade_usd:.4f}",
            f"  Total: ${self.total_cost_per_trade_usd:.4f}",
            f"",
            f"Minimum Equity Required for 1% Risk at Min Lot: ${self.min_equity_required_usd:.2f}",
            f"",
            f"Summary: {self.summary}",
        ])
        return "\n".join(lines)


class AccountFeasibilityAnalyzer:
    """
    Independent verification of account feasibility for a given strategy.
    
    Uses the SAME risk engine logic as ContractAwareFixedFractionalRisk to determine
    if min lot (0.01) breaches the 1% risk budget.
    """
    
    def __init__(
        self,
        spec: InstrumentSpec,
        equity_usd: float = 30.0,
        risk_fraction: float = 0.01,
        leverage: int = 2000,
        commission_per_lot: float = 0.0,
        swap_long_points: float = -10.0,
        swap_short_points: float = -5.0,
        avg_holding_bars: float = 6.0,
        timeframe_minutes: int = 5,
    ):
        self.spec = spec
        self.equity_usd = equity_usd
        self.risk_fraction = risk_fraction
        self.leverage = leverage
        self.commission_per_lot = commission_per_lot
        self.swap_long_points = swap_long_points
        self.swap_short_points = swap_short_points
        self.avg_holding_bars = avg_holding_bars
        self.timeframe_minutes = timeframe_minutes
        
        self.risk_budget_usd = equity_usd * risk_fraction
    
    def analyze(
        self,
        avg_stop_distance_price: float,
        avg_spread_points: float,
        entry_price: float = 2000.0,
        side: str = "long",
    ) -> FeasibilityResult:
        """
        Analyze whether the strategy is executable at the given account size.
        
        Parameters
        ----------
        avg_stop_distance_price: Average stop distance in price units (from backtester signals)
        avg_spread_points: Average spread in broker points (from dataset)
        entry_price: Estimated entry price for margin calculation
        side: "long" or "short" (affects swap)
        
        Returns
        -------
        FeasibilityResult with complete analysis
        """
        # Risk per lot = stop_distance * contract_size * quote_to_usd
        # For XAUUSDm: quote_currency = USD, so quote_to_usd = 1.0
        risk_per_lot_usd = avg_stop_distance_price * self.spec.contract_size * 1.0
        
        # Exact lots needed for 1% risk
        lots_exact = self.risk_budget_usd / risk_per_lot_usd if risk_per_lot_usd > 0 else 0.0
        
        # Floor to broker step
        lots_floored = floor_to_step(lots_exact, self.spec.volume_step)
        
        # Check min lot constraint
        if lots_floored < self.spec.volume_min - 1e-12:
            # Min lot breaches risk budget
            risk_at_min = self.spec.volume_min * risk_per_lot_usd
            feasible = False
            rejection_reason = (
                f"min volume breach: {self.spec.volume_min} lots risks "
                f"${risk_at_min:.2f} > budget ${self.risk_budget_usd:.2f}"
            )
        else:
            feasible = True
            risk_at_min = self.spec.volume_min * risk_per_lot_usd
            rejection_reason = None
        
        risk_at_min_lot_multiple = risk_at_min / self.risk_budget_usd if self.risk_budget_usd > 0 else 0.0
        
        # Margin calculation
        # Margin = (entry_price * contract_size * lots) / leverage
        margin_required = (entry_price * self.spec.contract_size * self.spec.volume_min) / self.leverage
        free_margin_after = self.equity_usd - margin_required
        margin_level = (self.equity_usd / margin_required * 100) if margin_required > 0 else float('inf')
        
        # Cost per trade at min lot
        point_value = self.spec.point_value_per_lot_usd
        spread_cost = avg_spread_points * point_value * self.spec.volume_min
        commission_cost = self.commission_per_lot * self.spec.volume_min
        
        # Swap estimate (rough: assume avg holding crosses 1 night per 24h)
        hold_minutes = self.avg_holding_bars * self.timeframe_minutes
        hold_nights = max(0, int(hold_minutes / (24 * 60)))
        if side == "long":
            swap_points = self.swap_long_points
        else:
            swap_points = self.swap_short_points
        swap_cost = swap_points * point_value * self.spec.volume_min * hold_nights
        
        total_cost = spread_cost + commission_cost + swap_cost
        
        # Minimum equity required to trade at min lot within 1% risk
        min_equity_required = risk_at_min / self.risk_fraction if self.risk_fraction > 0 else 0.0
        
        # Summary
        if feasible:
            summary = (
                f"Strategy executable at ${self.equity_usd:.2f}. "
                f"Min lot risk (${risk_at_min:.2f}) within budget (${self.risk_budget_usd:.2f})."
            )
        else:
            summary = (
                f"Strategy INFEASIBLE at ${self.equity_usd:.2f}. "
                f"Min lot risk (${risk_at_min:.2f}) exceeds budget (${self.risk_budget_usd:.2f}) by "
                f"{risk_at_min_lot_multiple:.1f}x. "
                f"Minimum equity required: ${min_equity_required:.2f}."
            )
        
        return FeasibilityResult(
            equity_usd=self.equity_usd,
            risk_fraction=self.risk_fraction,
            risk_budget_usd=self.risk_budget_usd,
            min_lot=self.spec.volume_min,
            max_lot=self.spec.volume_max,
            lot_step=self.spec.volume_step,
            contract_size=self.spec.contract_size,
            point_size=self.spec.point_size,
            pip_size=self.spec.pip_size,
            leverage=self.leverage,
            avg_stop_distance_price=avg_stop_distance_price,
            avg_spread_points=avg_spread_points,
            risk_per_lot_usd=risk_per_lot_usd,
            lots_exact=lots_exact,
            lots_floored=lots_floored,
            feasible=feasible,
            rejection_reason=rejection_reason,
            risk_at_min_lot_usd=risk_at_min,
            risk_at_min_lot_multiple_of_budget=risk_at_min_lot_multiple,
            entry_price=entry_price,
            margin_required_usd=margin_required,
            free_margin_after_entry_usd=free_margin_after,
            margin_level_pct=margin_level,
            spread_cost_per_trade_usd=spread_cost,
            commission_per_trade_usd=commission_cost,
            swap_estimate_per_trade_usd=swap_cost,
            total_cost_per_trade_usd=total_cost,
            min_equity_required_usd=min_equity_required,
            summary=summary,
        )
    
    def find_minimum_viable_equity(
        self,
        avg_stop_distance_price: float,
        target_risk_multiple: float = 1.0,
    ) -> float:
        """
        Find minimum equity required so that min lot risks <= target_risk_multiple * risk_fraction.
        
        Default target_risk_multiple=1.0 means min lot risk == risk budget.
        """
        risk_per_lot = avg_stop_distance_price * self.spec.contract_size
        risk_at_min = self.spec.volume_min * risk_per_lot
        required_budget = risk_at_min / target_risk_multiple
        return required_budget / self.risk_fraction


__all__ = [
    "FeasibilityResult",
    "AccountFeasibilityAnalyzer",
]