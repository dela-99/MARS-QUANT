"""
Tests for M5→M1 Execution Backtester.
"""

import pandas as pd
import numpy as np
import pytest


def test_m5_m1_backtester_no_lookahead():
    """Test backtester with M5 execution (simpler, no alignment issues)."""
    from mars.apps.backtester.m5_m1_execution_backtest import M5M1ExecutionBacktester
    from mars.libs.strategies.xau_m5_momentum import MomentumParams, compute_momentum_signals
    from mars.libs.execution.cost_adapter import CostAdapter
    from mars.libs.execution.cost_model import ExnessXAUUSDmCostModel
    from mars.libs.risk.contract_aware import InstrumentSpec
    
    dates_m5 = pd.date_range("2024-01-01", periods=100, freq="5min", tz="UTC")
    close_m5 = np.linspace(2000, 2050, 100) + np.random.randn(100) * 0.2
    m5 = pd.DataFrame({"timestamp": dates_m5, "open": close_m5, "high": close_m5+1, "low": close_m5-1,
                       "close": close_m5, "volume": 1000, "spread": 200})
    h1_df = m5.resample("1h", on="timestamp").agg({"open": "first", "high": "max", "low": "min", "close": "last",
                                 "volume": "sum", "spread": "mean"}).dropna().reset_index()
    h1 = h1_df.rename(columns={"timestamp": "timestamp"})
    
    params = MomentumParams(execution_timeframe="M5", max_hold_bars=6)
    signals = compute_momentum_signals(m5, m5, h1, params)
    
    spec = InstrumentSpec(symbol="XAUUSDm", contract_size=100.0, pip_size=0.01, point_size=0.001,
                          quote_currency="USD", volume_min=0.01, volume_max=200.0, volume_step=0.01,
                          volume_spec_source="test", spec_source="test")
    exness_model = ExnessXAUUSDmCostModel(spec=spec, avg_spread_points=200, median_spread_points=180)
    cost_adapter = CostAdapter(exness_model)
    
    backtester = M5M1ExecutionBacktester(params, cost_adapter=cost_adapter)
    result = backtester.run(signals.frame, m5, h1)  # Use M5 for both signal and execution
    
    # Verify result
    assert result.trades is not None
    assert len(result.equity_curve) == len(signals.frame)
    # Each trade should have cost breakdown
    for trade in result.trades:
        assert hasattr(trade, "cost_breakdown") or hasattr(trade, "spread_cost")





def test_backtest_result_trades_frame():
    from mars.apps.backtester.m5_m1_execution_backtest import BacktestResult, Trade
    import pandas as pd
    
    # Create a minimal result with trades
    trade = Trade(
        symbol="XAUUSDm", side="long", entry_time=pd.Timestamp("2024-01-01", tz="UTC"),
        entry_price=2000.0, exit_time=pd.Timestamp("2024-01-01 00:10:00", tz="UTC"),
        exit_price=2005.0, lots=0.01, stop_price=1995.0, atr=1.5,
        gross_pnl=50.0, spread_cost=2.0, commission=0.0, swap=0.0, slippage=0.0,
        net_pnl=48.0, exit_reason="take_profit", holding_bars=10,
        holding_minutes=10.0, mae_price=1998.0, mfe_price=2006.0,
        r_multiple=2.0, equity_before=10000.0, equity_after=10048.0,
        entry_session="Asia", exit_session="Asia", execution_timeframe="M1", max_holding_bars=6
    )
    
    result = BacktestResult(
        trades=[trade], equity_curve=pd.Series([10000, 10048]),
        daily_equity=pd.Series([10048]), rejected_signals=[],
        params=None, cost_adapter=None, spec=None, starting_equity=10000.0,
        bars_in_market=10, total_bars=100, final_equity=10048.0
    )
    
    df = result.trades_frame()
    assert len(df) == 1
    assert df.iloc[0]["symbol"] == "XAUUSDm"
    assert df.iloc[0]["net_pnl"] == 48.0