"""
Tests for Cost Adapter - bridges Assignment 23's ExnessXAUUSDmCostModel to backtester.
"""

from pathlib import Path
import pytest


def test_cost_adapter_delegates_to_exness_model():
    from mars.libs.execution.cost_adapter import CostAdapter
    from mars.libs.execution.cost_model import ExnessXAUUSDmCostModel, CostBreakdown
    from mars.libs.risk.contract_aware import InstrumentSpec
    
    spec = InstrumentSpec(
        symbol="XAUUSDm", contract_size=100.0, pip_size=0.01, point_size=0.001,
        quote_currency="USD", volume_min=0.01, volume_max=200.0, volume_step=0.01,
        volume_spec_source="test", spec_source="test"
    )
    exness_model = ExnessXAUUSDmCostModel(
        spec=spec, avg_spread_points=200, median_spread_points=180,
        commission_per_lot_round_trip_usd=0.0, swap_long_points=-10.0,
        swap_short_points=-5.0, slippage_points_per_fill=0.0,
        fallback_spread_points=200.0
    )
    adapter = CostAdapter(exness_model)
    
    # Calculate cost for a trade
    breakdown = adapter.calculate_trade_cost(
        lots=0.01, entry_spread_points=200, exit_spread_points=180,
        hold_nights=0, side="long", entry_price=2000.0
    )
    
    assert isinstance(breakdown, CostBreakdown)
    assert breakdown.spread_cost_usd > 0
    assert breakdown.commission_usd == 0.0  # Exness raw spread
    assert breakdown.spread_source == "observed"
    assert breakdown.total_usd == breakdown.spread_cost_usd + breakdown.swap_usd + breakdown.slippage_usd


def test_cost_adapter_no_double_counting():
    """Verify spread is charged once per round trip, not twice."""
    from mars.libs.execution.cost_adapter import CostAdapter
    from mars.libs.execution.cost_model import ExnessXAUUSDmCostModel
    from mars.libs.risk.contract_aware import InstrumentSpec
    
    spec = InstrumentSpec(symbol="XAUUSDm", contract_size=100.0, pip_size=0.01, point_size=0.001,
                          quote_currency="USD", volume_min=0.01, volume_max=200.0, volume_step=0.01,
                          volume_spec_source="test", spec_source="test")
    exness_model = ExnessXAUUSDmCostModel(spec=spec, avg_spread_points=200, median_spread_points=200)
    adapter = CostAdapter(exness_model)
    
    # Round trip: entry spread + exit spread = 400 points total
    b = adapter.calculate_trade_cost(0.01, 200, 200, 0, "long", 2000.0)
    
    # Spread cost should be (200+200) * point_value * lots
    point_value = 100.0 * 0.001  # contract_size * point_size = $0.10 per point per lot
    expected_spread = 400 * point_value * 0.01  # = $0.40
    assert abs(b.spread_cost_usd - expected_spread) < 0.001


def test_cost_adapter_to_simple_cost_model():
    from mars.libs.execution.cost_adapter import CostAdapter
    from mars.libs.execution.cost_model import ExnessXAUUSDmCostModel
    from mars.libs.risk.contract_aware import InstrumentSpec
    from mars.apps.backtester.xau_scalping_donchian_backtest import CostModel as BacktestCostModel
    
    spec = InstrumentSpec(symbol="XAUUSDm", contract_size=100.0, pip_size=0.01, point_size=0.001,
                          quote_currency="USD", volume_min=0.01, volume_max=200.0, volume_step=0.01,
                          volume_spec_source="test", spec_source="test")
    exness_model = ExnessXAUUSDmCostModel(spec=spec, avg_spread_points=200, median_spread_points=180)
    adapter = CostAdapter(exness_model)
    
    simple_model = adapter.to_simple_cost_model()
    
    assert isinstance(simple_model, BacktestCostModel)
    assert simple_model.cost_source == "exness_xauusdm_detailed"
    assert simple_model.use_observed_spread == True


def test_cost_adapter_to_execution_model():
    from mars.libs.execution.cost_adapter import CostAdapter
    from mars.libs.execution.cost_model import ExnessXAUUSDmCostModel
    from mars.libs.risk.contract_aware import InstrumentSpec
    from mars.apps.backtester.xau_scalping_donchian_backtest import ExecutionModel
    
    spec = InstrumentSpec(symbol="XAUUSDm", contract_size=100.0, pip_size=0.01, point_size=0.001,
                          quote_currency="USD", volume_min=0.01, volume_max=200.0, volume_step=0.01,
                          volume_spec_source="test", spec_source="test")
    exness_model = ExnessXAUUSDmCostModel(spec=spec, avg_spread_points=200, median_spread_points=180)
    adapter = CostAdapter(exness_model)
    
    exec_model = adapter.to_execution_model()
    
    assert isinstance(exec_model, ExecutionModel)
    assert exec_model.entry_fill == "next_bar_open"
    assert exec_model.stop_fill == "gap_aware_conservative"
    assert exec_model.same_bar_priority == "worst_price"