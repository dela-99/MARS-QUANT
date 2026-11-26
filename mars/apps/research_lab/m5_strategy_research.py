"""
Unified Research Runner for M5 Strategies with M1 Execution.

Orchestrates all 5 strategies across dev/validation/holdout periods
with strict chronological separation.
"""

from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
import json

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from mars.apps.research_lab.m5_data_loader import load_verified_m1_m5_h1
from mars.apps.backtester.m5_m1_execution_backtest import M5M1ExecutionBacktester, BacktestResult
from mars.libs.execution.cost_adapter import CostAdapter
from mars.libs.execution.cost_model import ExnessXAUUSDmCostModel
from mars.libs.risk.contract_aware import InstrumentSpec
from mars.libs.risk.feasibility import AccountFeasibilityAnalyzer
from mars.libs.strategies.xau_m5_momentum import MomentumParams, compute_momentum_signals, XauM5MomentumStrategy
from mars.libs.strategies.xau_m5_pullback import PullbackParams, compute_pullback_signals, XauM5PullbackStrategy
from mars.libs.strategies.xau_m5_vol_expansion import VolExpansionParams, compute_vol_expansion_signals, XauM5VolExpansionStrategy
from mars.libs.strategies.xau_m5_failed_breakout import FailedBreakoutParams, compute_failed_breakout_signals, XauM5FailedBreakoutStrategy
from mars.libs.strategies.xau_m5_displacement_mr import DisplacementMRParams, compute_displacement_mr_signals, XauM5DisplacementMRStrategy


STRATEGY_REGISTRY = {
    "momentum": {
        "params_cls": MomentumParams,
        "compute_signals": compute_momentum_signals,
        "strategy_cls": XauM5MomentumStrategy,
        "default_params": {"execution_timeframe": "M5", "max_hold_bars": 6},
    },
    "pullback": {
        "params_cls": PullbackParams,
        "compute_signals": compute_pullback_signals,
        "strategy_cls": XauM5PullbackStrategy,
        "default_params": {"execution_timeframe": "M5", "max_hold_bars": 12},
    },
    "vol_expansion": {
        "params_cls": VolExpansionParams,
        "compute_signals": compute_vol_expansion_signals,
        "strategy_cls": XauM5VolExpansionStrategy,
        "default_params": {"execution_timeframe": "M5", "max_hold_bars": 6},
    },
    "failed_breakout": {
        "params_cls": FailedBreakoutParams,
        "compute_signals": compute_failed_breakout_signals,
        "strategy_cls": XauM5FailedBreakoutStrategy,
        "default_params": {"execution_timeframe": "M5", "max_hold_bars": 3},
    },
    "displacement_mr": {
        "params_cls": DisplacementMRParams,
        "compute_signals": compute_displacement_mr_signals,
        "strategy_cls": XauM5DisplacementMRStrategy,
        "default_params": {"execution_timeframe": "M5", "max_hold_bars": 6},
    },
}


def _slice_period(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    if len(df) == 0:
        return df
    return df[(df.index >= start) & (df.index < end)].copy()


def _choose_execution_data(m1: pd.DataFrame, m5: pd.DataFrame, period: str, coverage: Dict) -> pd.DataFrame:
    """Choose M1 or M5 for execution based on period and data availability."""
    mode = coverage["execution_mode"].get(period, "M1")
    if mode == "M1" and len(m1) > 0:
        return m1
    return m5


class M5StrategyResearch:
    """Unified research runner for all M5 strategies with M1 execution."""
    
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.m1, self.m5, self.h1, self.coverage = load_verified_m1_m5_h1(repo_root)
        self.spec = InstrumentSpec(
            symbol="XAUUSDm", contract_size=100.0, pip_size=0.01, point_size=0.001,
            quote_currency="USD", volume_min=0.01, volume_max=200.0, volume_step=0.01,
            volume_spec_source="mt5.live", spec_source="mt5.live",
        )
        self.exness_cost_model = ExnessXAUUSDmCostModel(
            spec=self.spec,
            avg_spread_points=float(self.m5["spread"].mean()) if "spread" in self.m5.columns else 200.0,
            median_spread_points=float(self.m5["spread"].median()) if "spread" in self.m5.columns else 180.0,
            commission_per_lot_round_trip_usd=0.0,
            swap_long_points=-10.0,
            swap_short_points=-5.0,
            slippage_points_per_fill=0.0,
            fallback_spread_points=200.0,
        )
        self.cost_adapter = CostAdapter(self.exness_cost_model)
        
        # Period boundaries
        self.periods = {
            "dev": (self.coverage["period_slices"]["dev_start"], self.coverage["period_slices"]["dev_end"]),
            "val": (self.coverage["period_slices"]["val_start"], self.coverage["period_slices"]["val_end"]),
            "holdout": (self.coverage["period_slices"]["holdout_start"], self.coverage["period_slices"]["holdout_end"]),
        }
    
    def run_single_strategy(
        self,
        strategy_name: str,
        period: Literal["dev", "val", "holdout"],
        max_bars: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Run one strategy on one period."""
        if strategy_name not in STRATEGY_REGISTRY:
            raise ValueError(f"Unknown strategy: {strategy_name}")
        
        reg = STRATEGY_REGISTRY[strategy_name]
        params = reg["params_cls"](**reg["default_params"])
        
        # Slice data
        start, end = self.periods[period]
        m1_s = _slice_period(self.m1, start, end)
        m5_s = _slice_period(self.m5, start, end)
        h1_s = _slice_period(self.h1, start, end)
        
        if max_bars:
            m1_s = m1_s.iloc[:max_bars]
            m5_s = m5_s.iloc[:max_bars]
            h1_s = h1_s.iloc[:max_bars]
        
        # Choose execution data
        exec_data = _choose_execution_data(m1_s, m5_s, period, self.coverage)
        ctx_data = m5_s  # Context is always M5
        
        # Compute signals on M5 context
        signals = reg["compute_signals"](exec_data, ctx_data, h1_s, params)
        
        # Run backtester
        backtester = M5M1ExecutionBacktester(
            params, spec=self.spec, cost_adapter=self.cost_adapter
        )
        result = backtester.run(signals.frame, exec_data, h1_s)
        
        # Compute metrics
        metrics = self._compute_metrics(result)
        
        # Feasibility
        feasibility = self._analyze_feasibility(result, params)
        
        return {
            "strategy": strategy_name,
            "period": period,
            "execution_mode": self.coverage["execution_mode"].get(period, "M1"),
            "trades": result.trades_frame().to_dict(orient="records"),
            "equity_curve": result.equity_curve.to_dict(),
            "metrics": metrics,
            "feasibility": feasibility.to_dict() if hasattr(feasibility, "to_dict") else feasibility,
            "rejected_signals": result.rejected_signals,
            "exit_breakdown": {
                "time_exits": result.time_exits,
                "stop_exits": result.stop_exits,
                "mid_exits": result.mid_exits,
                "end_of_data_exits": result.end_of_data_exits,
            },
        }
    
    def _compute_metrics(self, result: BacktestResult) -> Dict[str, Any]:
        """Compute full metrics from backtest result."""
        tf = result.trades_frame()
        equity = result.equity_curve
        starting = result.starting_equity
        final = result.final_equity
        
        if len(tf):
            net = tf["net_pnl"].to_numpy(dtype=float)
            wins = net[net > 0]
            losses = net[net <= 0]
            win_rate = float(len(wins) / len(net))
            gross_win = float(wins.sum()) if len(wins) else 0.0
            gross_loss = float(-losses.sum()) if len(losses) else 0.0
            expectancy = float(net.mean())
            avg_win = float(wins.mean()) if len(wins) else 0.0
            avg_loss = float(losses.mean()) if len(losses) else 0.0
            profit_factor = gross_win / gross_loss if gross_loss > 0 else float("inf") if gross_win > 0 else 0.0
            r = tf["r_multiple"].to_numpy(dtype=float)
            expectancy_r = float(r.mean()) if len(r) else 0.0
            total_commission = float(tf["commission"].sum())
            total_swap = float(tf["swap"].sum())
            total_slippage = float(tf["slippage"].sum())
            total_spread = float(tf["spread_cost"].sum())
            gross_pnl_total = float(tf["gross_pnl"].sum())
            net_pnl_total = float(net.sum())
            holding = tf["holding_minutes"].to_numpy(dtype=float)
        else:
            net = np.array([])
            win_rate = expectancy = avg_win = avg_loss = expectancy_r = 0.0
            gross_win = gross_loss = profit_factor = 0.0
            total_commission = total_swap = total_slippage = total_spread = 0.0
            gross_pnl_total = net_pnl_total = 0.0
            holding = np.array([])
        
        # Drawdown
        running_max = equity.cummax()
        dd = equity - running_max
        max_dd = float(dd.min()) if len(dd) else 0.0
        max_dd_pct = max_dd / float(equity[running_max.idxmax()]) if len(equity) and running_max.max() != 0 else 0.0
        
        # Sharpe
        daily = equity.resample("1D").last().ffill()
        rets = daily.pct_change().dropna()
        sharpe = float(rets.mean() / rets.std() * np.sqrt(252)) if len(rets) > 1 and rets.std() > 0 else 0.0
        
        return {
            "trade_count": int(len(tf)),
            "win_rate": win_rate,
            "avg_win_usd": avg_win,
            "avg_loss_usd": avg_loss,
            "expectancy_usd": expectancy,
            "expectancy_r": expectancy_r,
            "profit_factor": profit_factor,
            "gross_pnl_usd": gross_pnl_total,
            "net_pnl_usd": net_pnl_total,
            "net_return": net_pnl_total / starting if starting != 0 else 0.0,
            "max_drawdown_usd": max_dd,
            "max_drawdown_pct": max_dd_pct,
            "sharpe": sharpe,
            "avg_holding_minutes": float(holding.mean()) if len(holding) else 0.0,
            "median_holding_minutes": float(np.median(holding)) if len(holding) else 0.0,
            "total_commission_usd": total_commission,
            "total_swap_usd": total_swap,
            "total_slippage_usd": total_slippage,
            "total_spread_cost_usd": total_spread,
            "cost_breakdown": {
                "spread": total_spread,
                "commission": total_commission,
                "swap": total_swap,
                "slippage": total_slippage,
                "total": total_spread + total_commission + total_swap + total_slippage,
            },
        }
    
    def _analyze_feasibility(self, result: BacktestResult, params: Any) -> Any:
        """Run independent $30 feasibility analysis."""
        tf = result.trades_frame()
        if len(tf) == 0:
            avg_stop = getattr(params, "atr_stop_mult", 2.0) * 1.5  # rough estimate
            avg_spread = float(self.m5["spread"].mean()) if "spread" in self.m5.columns else 200.0
        else:
            avg_stop = float(tf["atr"].mean() * getattr(params, "atr_stop_mult", 2.0))
            avg_spread = float(tf["entry_spread_pts"].mean()) if "entry_spread_pts" in tf.columns else 200.0
        
        analyzer = AccountFeasibilityAnalyzer(
            spec=self.spec,
            equity_usd=30.0,
            risk_fraction=0.01,
            leverage=2000,
            avg_holding_bars=float(getattr(params, "max_hold_bars", 6)),
            timeframe_minutes=1,
        )
        return analyzer.analyze(avg_stop, avg_spread, entry_price=2000.0)
    
    def run_full_research(self, output_dir: Path) -> Dict[str, Any]:
        """Run all strategies on all periods and generate reports."""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        all_results = {}
        
        for strategy_name in STRATEGY_REGISTRY.keys():
            print(f"\n=== Running {strategy_name} ===")
            strategy_results = {}
            
            for period in ["dev", "val", "holdout"]:
                print(f"  Period: {period}")
                res = self.run_single_strategy(strategy_name, period)
                strategy_results[period] = res
                
                # Save trade ledger
                ledger_path = output_dir / f"{strategy_name}_{period}_trades.csv"
                pd.DataFrame(res["trades"]).to_csv(ledger_path, index=False)
            
            all_results[strategy_name] = strategy_results
        
        # Generate decision report
        self._generate_decision_report(all_results, output_dir)
        
        # Save equity curves
        self._plot_equity_curves(all_results, output_dir)
        
        # Save JSON summary
        with open(output_dir / "m5_strategy_research_results.json", "w") as f:
            json.dump(all_results, f, indent=2, default=str)
        
        return all_results
    
    def _generate_decision_report(self, results: Dict, output_dir: Path):
        """Generate markdown decision report."""
        lines = [
            "# M5 Strategy Research — Decision Report",
            "",
            f"**Generated**: {pd.Timestamp.now(tz='UTC').isoformat()}",
            f"**Data Coverage**: M1 true bars 2021-2026 ({self.coverage['m1_total_bars']:,} bars)",
            f"**M1 Daily Bar Years (excluded from M1 exec)**: {self.coverage['m1_daily_years']}",
            "",
            "## Executive Summary",
            "",
        ]
        
        # Summary table
        lines.append("| Strategy | Dev Net P&L | Val Net P&L | Holdout Net P&L | Dev PF | Val PF | Holdout PF | Feasible $30 | Min Equity |")
        lines.append("|----------|-------------|-------------|-----------------|--------|--------|------------|--------------|------------|")
        
        for strategy_name, strategy_results in results.items():
            dev = strategy_results["dev"]["metrics"]
            val = strategy_results["val"]["metrics"]
            holdout = strategy_results["holdout"]["metrics"]
            dev_feas = strategy_results["dev"]["feasibility"]
            val_feas = strategy_results["val"]["feasibility"]
            holdout_feas = strategy_results["holdout"]["feasibility"]
            
            feasible_any = any(f.get("feasible", False) for f in [dev_feas, val_feas, holdout_feas])
            min_equity = min(
                f.get("min_equity_required_usd", float("inf")) 
                for f in [dev_feas, val_feas, holdout_feas]
            )
            
            lines.append(
                f"| {strategy_name} | ${dev['net_pnl_usd']:.2f} | ${val['net_pnl_usd']:.2f} | "
                f"${holdout['net_pnl_usd']:.2f} | {dev['profit_factor']:.2f} | "
                f"{val['profit_factor']:.2f} | {holdout['profit_factor']:.2f} | "
                f"{'✅' if feasible_any else '❌'} | ${min_equity:.0f} |"
            )
        
        lines.extend(["", "## Detailed Results by Strategy", ""])
        
        for strategy_name, strategy_results in results.items():
            lines.append(f"### {strategy_name.upper()}")
            lines.append("")
            
            for period in ["dev", "val", "holdout"]:
                res = strategy_results[period]
                m = res["metrics"]
                f = res["feasibility"]
                
                lines.append(f"#### {period.capitalize()} Period ({res['execution_mode']} execution)")
                lines.append(f"- **Trades**: {m['trade_count']}")
                lines.append(f"- **Win Rate**: {m['win_rate']:.1%}")
                lines.append(f"- **Expectancy**: ${m['expectancy_usd']:.2f} ({m['expectancy_r']:.2f}R)")
                lines.append(f"- **Profit Factor**: {m['profit_factor']:.2f}")
                lines.append(f"- **Net P&L**: ${m['net_pnl_usd']:.2f} ({m['net_return']:.2%})")
                lines.append(f"- **Max Drawdown**: ${m['max_drawdown_usd']:.2f} ({m['max_drawdown_pct']:.2%})")
                lines.append(f"- **Sharpe**: {m['sharpe']:.2f}")
                lines.append(f"- **Avg Holding**: {m['avg_holding_minutes']:.1f} min")
                lines.append(f"- **Costs**: Spread ${m['total_spread_cost_usd']:.2f}, "
                           f"Comm ${m['total_commission_usd']:.2f}, "
                           f"Swap ${m['total_swap_usd']:.2f}, "
                           f"Slip ${m['total_slippage_usd']:.2f}")
                lines.append(f"- **$30 Feasible**: {'✅' if f.get('feasible', False) else '❌'} — "
                           f"Min equity ${f.get('min_equity_required_usd', 0):.0f}")
                if not f.get('feasible', True):
                    lines.append(f"  - Reason: {f.get('rejection_reason', 'N/A')}")
                lines.append("")
        
        lines.extend([
            "## Conclusion",
            "",
            "### Candidates Surviving All Periods (After Costs):",
        ])
        
        survivors = []
        for strategy_name, strategy_results in results.items():
            dev_ok = strategy_results["dev"]["metrics"]["net_pnl_usd"] > 0
            val_ok = strategy_results["val"]["metrics"]["net_pnl_usd"] > 0
            holdout_ok = strategy_results["holdout"]["metrics"]["net_pnl_usd"] > 0
            if dev_ok and val_ok and holdout_ok:
                survivors.append(strategy_name)
        
        if survivors:
            for s in survivors:
                lines.append(f"- **{s}**: Positive net P&L on dev, validation, AND holdout")
        else:
            lines.append("**NONE** — No strategy demonstrates credible performance after costs across all independent periods.")
        
        lines.extend([
            "",
            "### Rejected Candidates:",
        ])
        for strategy_name in results:
            if strategy_name not in survivors:
                lines.append(f"- **{strategy_name}**: Failed on at least one period")
        
        with open(output_dir / "M5_STRATEGY_RESEARCH_DECISION_REPORT.md", "w") as f:
            f.write("\n".join(lines))
    
    def _plot_equity_curves(self, results: Dict, output_dir: Path):
        """Generate equity curve and drawdown charts."""
        for strategy_name, strategy_results in results.items():
            fig, axes = plt.subplots(3, 2, figsize=(14, 10))
            fig.suptitle(f"{strategy_name.upper()} — Equity Curves & Drawdowns")
            
            for idx, period in enumerate(["dev", "val", "holdout"]):
                res = strategy_results[period]
                equity = pd.Series(res["equity_curve"])
                equity.index = pd.DatetimeIndex(equity.index)
                
                # Equity curve
                ax = axes[idx, 0]
                equity.plot(ax=ax, color="blue", linewidth=0.8)
                ax.set_title(f"{period.capitalize()} Equity Curve")
                ax.set_ylabel("Equity ($)")
                ax.grid(True, alpha=0.3)
                
                # Drawdown
                ax = axes[idx, 1]
                running_max = equity.cummax()
                dd = (equity - running_max) / running_max * 100
                dd.plot(ax=ax, color="red", linewidth=0.8)
                ax.fill_between(dd.index, dd, 0, color="red", alpha=0.1)
                ax.set_title(f"{period.capitalize()} Drawdown %")
                ax.set_ylabel("Drawdown (%)")
                ax.grid(True, alpha=0.3)
            
            plt.tight_layout()
            plt.savefig(output_dir / f"{strategy_name}_equity_drawdown.png", dpi=150)
            plt.close()


__all__ = ["M5StrategyResearch", "STRATEGY_REGISTRY"]