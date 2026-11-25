"""
Assignment 14 — full research run for XAU-MTF-DONCHIAN-001.

Pipeline (Assignment 14, sections E, F, G, H):

  1. Load the versioned Exness XAUUSDm datasets (M5 v1.2.0 / H1 v1.2.0).
  2. In-sample baseline over 2021-07-16 -> 2024-12-31.
  3. Predeclared, one-factor-at-a-time parameter comparison on the in-sample
     window (Donchian lookback, then ATR stop multiplier).
  4. Freeze one configuration on in-sample evidence only.
  5. Run the frozen configuration on the untouched out-of-sample window
     (2025-01-01 -> last verified observation) exactly once.
  6. Gross/net reporting, cost sensitivity, benchmark and no-trade baseline.
  7. Monte Carlo (reshuffle + resample) on the OOS trade series.
  8. Write machine-readable ledgers, metrics and markdown reports.

Usage:
    python research/assignment14/run_assignment14.py [--out-dir reports/assignment14]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mars.apps.backtester.mtf_donchian_backtest import CostModel, ExecutionModel  # noqa: E402
from mars.apps.research_lab.xau_mtf_donchian_001 import (  # noqa: E402
    BASELINE_ATR_MULTIPLIER,
    BASELINE_DONCHIAN_LOOKBACK,
    IS_END,
    IS_START,
    OOS_START,
    PREDECLARED_ATR_MULTIPLIERS,
    PREDECLARED_DONCHIAN_LOOKBACKS,
    ResearchConfig,
    benchmark_buy_and_hold,
    compute_metrics,
    cost_sensitivity,
    exit_reason_breakdown,
    load_dataset,
    parameter_comparison,
    run_window,
    session_breakdown,
    structural_ablation,
    yearly_breakdown,
)
from mars.apps.research_lab.xau_mtf_donchian_montecarlo import (  # noqa: E402
    MonteCarloConfig,
    plot_fan_and_distributions,
    summarise as mc_summarise,
)
from mars.libs.risk.contract_aware import InstrumentSpec  # noqa: E402
from mars.libs.strategies.xau_mtf_donchian import MtfDonchianParams  # noqa: E402

#: Instrument specification used for the research run.
#:
#: ``contract_size`` (100 oz/lot) and ``pip_size`` (0.01) come from the
#: repository's offline symbol configuration (``run_multi_pair_backtest.SYMBOL_CONFIGS``).
#: ``point_size`` (0.001) is the tick size implied by the 3-decimal XAUUSDm
#: quote used by the project's own MT5 mock symbol.
#:
#: The volume constraints are the project's offline defaults and are **not**
#: live-verified: the MT5 terminal cannot be connected because the Exness demo
#: credentials were rotated (Assignment 13 blocker).  They are flagged
#: ``unverified_offline_default`` in every run record.
INSTRUMENT = InstrumentSpec(
    symbol="XAUUSDm",
    contract_size=100.0,
    pip_size=0.01,
    point_size=0.001,
    quote_currency="USD",
    volume_min=0.01,
    volume_max=200.0,
    volume_step=0.01,
    volume_spec_source="unverified_offline_default",
    spec_source="pair_config.offline",
)

BASE_PARAMS = MtfDonchianParams(
    donchian_lookback=BASELINE_DONCHIAN_LOOKBACK,
    ema_period=50,
    ema_slope_bars=5,
    atr_period=14,
    atr_stop_multiplier=BASELINE_ATR_MULTIPLIER,
    risk_fraction=0.01,
    starting_equity=10_000.0,
)


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, pd.Timestamp):
        return str(obj)
    if isinstance(obj, float) and not np.isfinite(obj):
        return str(obj)
    return obj


def select_frozen_config(comparison: pd.DataFrame) -> Dict[str, Any]:
    """
    Select one configuration from the in-sample comparison.

    Selection rule (fixed before the run, applied mechanically):
      1. candidates must have a positive in-sample net P&L;
      2. among those, take the highest expectancy per trade (``expectancy_usd``);
      3. if no candidate is profitable, freeze the **baseline** configuration
         and record that no candidate survived the profitability filter.

    The out-of-sample window is never consulted by this function.
    """
    rows = comparison.to_dict("records")
    profitable = [r for r in rows if r["net_pnl_usd"] > 0 and r["expectancy_usd"] > 0]
    if not profitable:
        return {
            "donchian_lookback": BASELINE_DONCHIAN_LOOKBACK,
            "atr_stop_multiplier": BASELINE_ATR_MULTIPLIER,
            "selection_basis": "no candidate passed the in-sample profitability filter; "
                               "the baseline configuration is frozen unchanged",
            "selected_from": "baseline",
        }
    best = max(profitable, key=lambda r: r["expectancy_usd"])
    return {
        "donchian_lookback": int(best["value"]) if best["factor"] == "donchian_lookback"
        else BASELINE_DONCHIAN_LOOKBACK,
        "atr_stop_multiplier": float(best["value"]) if best["factor"] == "atr_stop_multiplier"
        else BASELINE_ATR_MULTIPLIER,
        "selection_basis": f"highest in-sample expectancy per trade among profitable "
                           f"candidates ({best['factor']}={best['value']}, "
                           f"expectancy ${best['expectancy_usd']:.2f}/trade)",
        "selected_from": f"{best['factor']}={best['value']}",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="reports/assignment14")
    ap.add_argument("--n-simulations", type=int, default=2000)
    args = ap.parse_args()

    out_dir = ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc)

    print("=" * 100)
    print("ASSIGNMENT 14 — XAU-MTF-DONCHIAN-001 RESEARCH RUN")
    print("=" *100)

    m5, h1 = load_dataset(ROOT)
    print(f"data: M5 {len(m5):,} bars {m5.index[0]} -> {m5.index[-1]}")
    print(f"      H1 {len(h1):,} bars {h1.index[0]} -> {h1.index[-1]}")

    cfg = ResearchConfig(repo_root=ROOT, params=BASE_PARAMS, spec=INSTRUMENT,
                          cost_model=CostModel(), execution_model=ExecutionModel())

    # ------------------------------------------------------------------
    # 1. In-sample baseline
    # ------------------------------------------------------------------
    print("\n[1/8] in-sample baseline")
    t0 = time.time()
    is_res = run_window(cfg, m5, h1, IS_START, IS_END)
    is_metrics = compute_metrics(is_res)
    print(f"      {time.time() - t0:.1f}s  trades={is_metrics['trade_count']}  "
          f"net=${is_metrics['net_pnl_usd']:,.2f}  PF={is_metrics['profit_factor']:.3f}  "
          f"Sharpe={is_metrics['sharpe']:.3f}")

    # ------------------------------------------------------------------
    # 2. Predeclared parameter comparison (in-sample only)
    # ------------------------------------------------------------------
    print("\n[2/8] predeclared parameter comparison (in-sample only)")
    comparison = parameter_comparison(cfg, m5, h1, IS_START, IS_END)
    print(comparison.to_string(index=False))

    # ------------------------------------------------------------------
    # 3. Freeze one configuration on in-sample evidence
    # ------------------------------------------------------------------
    frozen = select_frozen_config(comparison)
    print(f"\n[3/8] frozen configuration: {frozen}")

    # ------------------------------------------------------------------
    # 4. Out-of-sample run of the frozen configuration (once)
    # ------------------------------------------------------------------
    print("\n[4/8] out-of-sample run (frozen configuration, run once)")
    frozen_params = MtfDonchianParams(
        donchian_lookback=int(frozen["donchian_lookback"]),
        ema_period=BASE_PARAMS.ema_period,
        ema_slope_bars=BASE_PARAMS.ema_slope_bars,
        atr_period=BASE_PARAMS.atr_period,
        atr_stop_multiplier=float(frozen["atr_stop_multiplier"]),
        risk_fraction=BASE_PARAMS.risk_fraction,
        starting_equity=BASE_PARAMS.starting_equity,
    )
    frozen_cfg = ResearchConfig(repo_root=ROOT, params=frozen_params, spec=INSTRUMENT,
                                 cost_model=CostModel(), execution_model=ExecutionModel())
    oos_res = run_window(frozen_cfg, m5, h1, OOS_START, None)
    oos_metrics = compute_metrics(oos_res)
    print(f"      trades={oos_metrics['trade_count']}  net=${oos_metrics['net_pnl_usd']:,.2f}  "
          f"PF={oos_metrics['profit_factor']:.3f}  Sharpe={oos_metrics['sharpe']:.3f}  "
          f"maxDD={oos_metrics['max_drawdown_pct']:.2%}")

    # ------------------------------------------------------------------
    # 5. Baselines
    # ------------------------------------------------------------------
    print("\n[5/8] benchmarks and no-trade baseline")
    oos_m5, oos_h1 = m5[m5.index >= OOS_START], h1[h1.index >= OOS_START]
    bnh = benchmark_buy_and_hold(oos_m5, INSTRUMENT, frozen_params.starting_equity)
    no_trade = {"name": "no_trade", "net_pnl_usd": 0.0, "net_return": 0.0,
                "sharpe": 0.0, "max_drawdown_pct": 0.0}
    print(f"      buy & hold: net=${bnh['net_pnl_usd']:,.2f} ({bnh['net_return']:.2%})  "
          f"Sharpe={bnh['sharpe']:.3f}")
    print(f"      no trade:   net=$0.00 (0.00%)")

    # ------------------------------------------------------------------
    # 6. Cost sensitivity
    # ------------------------------------------------------------------
    print("\n[6/8] cost sensitivity (frozen configuration, OOS)")
    costs = cost_sensitivity(frozen_cfg, m5, h1, OOS_START, None)
    print(costs.to_string(index=False))

    print("\n[6b/8] in-sample structural ablation (diagnostic only, not for selection)")
    ablation = structural_ablation(frozen_cfg, m5, h1, IS_START, IS_END)
    print(ablation.to_string(index=False))

    # ------------------------------------------------------------------
    # 7. Monte Carlo
    # ------------------------------------------------------------------
    print("\n[7/8] Monte Carlo on the OOS trade series")
    oos_tf = oos_res.trades_frame()
    mc_ran = False
    mc_summary: Dict[str, Any] = {}
    mc_charts: Dict[str, str] = {}
    if len(oos_tf) >= 20:
        mc_cfg = MonteCarloConfig(n_simulations=args.n_simulations)
        mc_summary = mc_summarise(
            oos_tf["net_pnl"].to_numpy(dtype=float),
            frozen_params.starting_equity,
            mc_cfg,
        )
        mc_charts = plot_fan_and_distributions(
            mc_summary, out_dir, label="XAU-MTF-DONCHIAN-001 (OOS)",
            threshold=frozen_params.starting_equity,
        )
        mc_ran = True
        print(f"      reshuffle: mean terminal ${mc_summary['reshuffle']['terminal_equity_mean']:,.2f}, "
              f"maxDD p05 ${mc_summary['reshuffle']['max_drawdown_p05']:,.2f}")
        print(f"      resample:  mean terminal ${mc_summary['resample']['terminal_equity_mean']:,.2f}, "
              f"p05 ${mc_summary['resample']['terminal_equity_p05']:,.2f}")
    else:
        print(f"      SKIPPED: only {len(oos_tf)} OOS trades (need >= 20 for a credible series)")

    # ------------------------------------------------------------------
    # 8. Write artifacts
    # ------------------------------------------------------------------
    print("\n[8/8] writing artifacts")
    ledger_dir = out_dir / "ledger"
    ledger_dir.mkdir(parents=True, exist_ok=True)

    is_res.trades_frame().to_csv(ledger_dir / "trades_in_sample.csv", index=False)
    oos_tf.to_csv(ledger_dir / "trades_out_of_sample.csv", index=False)
    comparison.to_csv(ledger_dir / "parameter_comparison_in_sample.csv", index=False)
    costs.to_csv(ledger_dir / "cost_sensitivity_out_of_sample.csv", index=False)
    is_res.equity_curve.to_csv(ledger_dir / "equity_curve_in_sample.csv")
    oos_res.equity_curve.to_csv(ledger_dir / "equity_curve_out_of_sample.csv")
    yearly_breakdown(oos_res).to_csv(ledger_dir / "yearly_out_of_sample.csv")
    session_breakdown(oos_res).to_csv(ledger_dir / "session_out_of_sample.csv")
    exit_reason_breakdown(oos_res).to_csv(ledger_dir / "exit_reasons_out_of_sample.csv")
    yearly_breakdown(is_res).to_csv(ledger_dir / "yearly_in_sample.csv")
    session_breakdown(is_res).to_csv(ledger_dir / "session_in_sample.csv")
    exit_reason_breakdown(is_res).to_csv(ledger_dir / "exit_reasons_in_sample.csv")

    payload = {
        "run": {
            "strategy_id": "XAU-MTF-DONCHIAN-001",
            "started_utc": started.isoformat(),
            "finished_utc": datetime.now(timezone.utc).isoformat(),
            "command": "python research/assignment14/run_assignment14.py",
            "git_commit": None,      # filled in by the caller / report
        },
        "data": {
            "m5": "data/processed/xauusdm/m5/v1.2.0/data.parquet",
            "m5_rows": int(len(m5)),
            "m5_range": [str(m5.index[0]), str(m5.index[-1])],
            "h1": "data/processed/xauusdm/h1/v1.2.0/data.parquet",
            "h1_rows": int(len(h1)),
            "h1_range": [str(h1.index[0]), str(h1.index[-1])],
        },
        "configuration": frozen_cfg.to_dict(),
        "frozen_selection": frozen,
        "in_sample": {
            "window": [str(IS_START), str(IS_END)],
            "metrics": is_metrics,
            "yearly": yearly_breakdown(is_res).to_dict("index"),
            "session": session_breakdown(is_res).to_dict("index"),
            "exit_reasons": exit_reason_breakdown(is_res).to_dict("index"),
        },
        "out_of_sample": {
            "window": [str(OOS_START), str(m5.index[-1])],
            "metrics": oos_metrics,
            "yearly": yearly_breakdown(oos_res).to_dict("index"),
            "session": session_breakdown(oos_res).to_dict("index"),
            "exit_reasons": exit_reason_breakdown(oos_res).to_dict("index"),
        },
        "parameter_comparison_in_sample": comparison.to_dict("records"),
        "cost_sensitivity_out_of_sample": costs.to_dict("records"),
        "baselines": {"buy_and_hold": bnh, "no_trade": no_trade},
        "monte_carlo": (_jsonable({k: v for k, v in mc_summary.items() if k != "_paths"})
                        if mc_ran else {"status": "not_run",
                                        "reason": f"only {len(oos_tf)} OOS trades"}),
        "monte_carlo_charts": mc_charts,
        "rejected_signal_counts": {
            "in_sample": int(len(is_res.rejected_signals)),
            "out_of_sample": int(len(oos_res.rejected_signals)),
        },
    }
    with (out_dir / "assignment14_results.json").open("w", encoding="utf-8") as fh:
        json.dump(_jsonable(payload), fh, indent=2)

    print(f"      artifacts written to {out_dir}")
    print("\nDONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
