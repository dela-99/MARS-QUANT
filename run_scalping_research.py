#!/usr/bin/env python
"""
XAU-SCALPING-DONCHIAN-001 Executable Demonstration (Assignment 22).

Runs the complete in-sample research pipeline for the short-horizon scalping
architecture recovered from Version 1 (XAU-MTF-DONCHIAN-001).

Usage:
    python run_scalping_research.py

Outputs:
    reports/assignment22/xau_scalping_donchian_is_research.json
    reports/assignment22/XAU_SCALPING_DONCHIAN_IS_RESEARCH_REPORT.md

This script:
1. Loads M5 v1.2.0 and H1 v1.2.0 data (M1 not required for M5 execution mode)
2. Runs baseline (Version 1 equivalent: M5 execution, 30-min max hold)
3. Runs current configuration
4. Executes parameter comparison (one-factor-at-a-time)
5. Runs cost sensitivity analysis
6. Performs $30 account feasibility analysis with Exness XAUUSDm specs
7. Generates comprehensive report
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from mars.apps.research_lab.xau_scalping_donchian_research import (
    ResearchConfig,
    run_full_research,
    ScalpingDonchianParams,
)
from mars.libs.risk.contract_aware import InstrumentSpec
from mars.apps.backtester.xau_scalping_donchian_backtest import CostModel, ExecutionModel


def main():
    print("=" * 70)
    print("XAU-SCALPING-DONCHIAN-001 In-Sample Research (Assignment 22)")
    print("=" * 70)
    print()

    # Configuration
    repo_root = PROJECT_ROOT
    output_dir = repo_root / "reports" / "assignment22"

    # Strategy parameters (baseline = Version 1 equivalent)
    params = ScalpingDonchianParams(
        # Version 1 base parameters (preserved from Assignment 14)
        donchian_lookback=20,
        ema_period=50,
        ema_slope_bars=5,
        atr_period=14,
        atr_stop_multiplier=2.0,
        risk_fraction=0.01,
        starting_equity=10_000.0,      # Research equity (preserved for reproducibility)
        allow_short=True,
        allow_long=True,

        # Assignment 22 scalping extensions
        execution_timeframe="M5",       # M5 execution (M1 not available yet)
        max_holding_bars=6,             # 6 M5 bars = 30 minutes max hold
        max_holding_minutes=30,         # Explicit 30-minute cap
        use_m1_context=False,           # M1 data not available
        m1_donchian_lookback=20,
        m1_atr_period=14,
        m1_atr_stop_multiplier=2.0,

        # $30 Account parameters (Exness XAUUSDm verified)
        account_equity_usd=30.0,
        leverage=2000,
        min_lot=0.01,
        max_lot=200.0,
        lot_step=0.01,
        contract_size=100.0,
        point_size=0.001,
        pip_size=0.01,
    )

    # Instrument spec (Exness XAUUSDm verified)
    spec = InstrumentSpec(
        symbol="XAUUSDm",
        contract_size=100.0,
        pip_size=0.01,
        point_size=0.001,
        quote_currency="USD",
        volume_min=0.01,
        volume_max=200.0,
        volume_step=0.01,
        volume_spec_source="mt5.live",
        spec_source="mt5.live",
    )

    # Cost model (observed spread only by default)
    cost_model = CostModel(
        spread_multiplier=1.0,
        commission_per_lot_round_trip=0.0,
        slippage_points=0.0,
        swap_per_lot_night=0.0,
        use_observed_spread=True,
        fallback_spread_points=200.0,
        cost_source="observed_bar_spread",
    )

    # Execution model
    execution_model = ExecutionModel(
        entry_fill="next_bar_open",
        stop_fill="gap_aware_conservative",
        same_bar_priority="worst_price",
        exit_fill="next_bar_open",
        time_exit_fill="next_bar_open",
        reversal_policy="opposite_signal_ignored",
    )

    # Research config
    config = ResearchConfig(
        repo_root=repo_root,
        params=params,
        spec=spec,
        cost_model=cost_model,
        execution_model=execution_model,
        m1_path="data/processed/xauusdm/m1/v1.2.0/data.parquet",
        m5_path="data/processed/xauusdm/m5/v1.2.0/data.parquet",
        h1_path="data/processed/xauusdm/h1/v1.2.0/data.parquet",
    )

    print(f"Repository root: {repo_root}")
    print(f"Output directory: {output_dir}")
    print(f"Execution timeframe: {params.execution_timeframe}")
    print(f"Max holding: {params.max_holding_bars} bars ({params.max_holding_minutes} min)")
    print(f"Account equity: ${params.account_equity_usd}")
    print(f"Risk per trade: {params.risk_fraction * 100}%")
    print(f"Min lot: {params.min_lot}")
    print(f"Leverage: 1:{params.leverage}")
    print()

    # Run full research
    try:
        report = run_full_research(repo_root, output_dir, config)
        print()
        print("=" * 70)
        print("RESEARCH COMPLETE")
        print("=" * 70)
        print()
        print("Key Results:")
        print(f"  Baseline (V1 equiv) Net P&L: ${report['baseline_metrics']['net_pnl_usd']:.2f}")
        print(f"  Baseline Expectancy: ${report['baseline_metrics']['expectancy_usd']:.4f}/trade")
        print(f"  Baseline Sharpe: {report['baseline_metrics']['sharpe']:.4f}")
        print(f"  Baseline Max DD: {report['baseline_metrics']['max_drawdown_pct']:.2%}")
        print()
        print(f"  Current Config Net P&L: ${report['current_metrics']['net_pnl_usd']:.2f}")
        print(f"  Current Expectancy: ${report['current_metrics']['expectancy_usd']:.4f}/trade")
        print(f"  Current Sharpe: {report['current_metrics']['sharpe']:.4f}")
        print(f"  Current Max DD: {report['current_metrics']['max_drawdown_pct']:.2%}")
        print()
        print("  $30 Account Feasibility:")
        feas = report["account_feasibility_30usd"]
        print(f"    Feasible: {feas['feasible']}")
        print(f"    Min Risk/Trade: ${feas['min_risk_per_trade_usd']:.2f}")
        print(f"    Conclusion: {feas['conclusion']}")
        print()
        print(f"Reports written to: {output_dir}")
        print("  - xau_scalping_donchian_is_research.json")
        print("  - XAU_SCALPING_DONCHIAN_IS_RESEARCH_REPORT.md")
        return 0

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())