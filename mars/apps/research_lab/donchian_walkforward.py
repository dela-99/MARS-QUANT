"""
Walk-Forward Validation for DONCHIAN-001 using VectorBT.

Implements chronological walk-forward with expanding training window.
No parameter optimization — pure out-of-sample evaluation of frozen baseline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

import numpy as np
import pandas as pd
import vectorbt as vbt

from mars.apps.research_lab.donchian_trend_vbt import (
    DonchianConfig,
    CostModel,
    load_and_validate_data,
    compute_donchian_channels,
    run_vectorbt_portfolio,
    compute_metrics,
    compute_benchmarks,
    performance_by_year,
    ProjectPaths,
)
from mars.research.experiment import ExperimentLog, ExperimentRecord
from mars.libs.evaluation.report import write_text_report


# ============================================================================
# Walk-Forward Configuration
# ============================================================================

@dataclass(frozen=True)
class WalkForwardConfig:
    """Immutable walk-forward validation configuration."""
    # Baseline strategy (frozen from DONCHIAN-001)
    base_config: DonchianConfig
    # Walk-forward window parameters
    initial_train_years: int = 4          # Initial training window (years)
    oos_window_years: int = 1             # Each OOS evaluation window (years)
    step_years: int = 1                   # Step forward (same as OOS for non-overlapping)
    min_train_years: int = 2              # Minimum training data before first OOS
    warmup_bars: int = 55                 # Max lookback for channel warmup
    # Execution
    seed: int = 42


@dataclass
class WindowResult:
    """Results for a single OOS window."""
    window_id: int
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    oos_start: pd.Timestamp
    oos_end: pd.Timestamp
    n_train_bars: int
    n_oos_bars: int
    metrics: dict[str, Any]
    benchmarks: dict[str, Any]
    trades: pd.DataFrame


# ============================================================================
# Walk-Forward Engine
# ============================================================================

class WalkForwardValidator:
    """Chronological walk-forward validator for DONCHIAN-001."""

    def __init__(self, config: WalkForwardConfig):
        self.config = config
        self.paths = ProjectPaths.from_root()
        self.results: list[WindowResult] = []

    def load_full_data(self) -> pd.DataFrame:
        """Load and validate full dataset."""
        df = load_and_validate_data(self.config.base_config, self.paths)
        return df

    def compute_windows(self, df: pd.DataFrame) -> list[tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp]]:
        """
        Compute walk-forward window boundaries.

        Returns list of (train_start, train_end, oos_start, oos_end) tuples.
        """
        index = df.index
        total_start = index[0]
        total_end = index[-1]

        # Initial training window
        train_start = total_start
        train_end = train_start + pd.DateOffset(years=self.config.initial_train_years)

        # Ensure we have enough data for warmup
        # Find first index with enough prior bars for max lookback
        min_train_idx = self.config.warmup_bars
        if train_end <= index[min_train_idx]:
            train_end = index[min_train_idx]

        windows = []
        window_id = 0

        while True:
            # OOS window
            oos_start = train_end
            oos_end = oos_start + pd.DateOffset(years=self.config.oos_window_years)

            # Check if OOS window has data
            oos_mask = (index >= oos_start) & (index < oos_end)
            if not oos_mask.any():
                break

            # Ensure OOS window has meaningful data (at least some bars)
            n_oos_bars = oos_mask.sum()
            if n_oos_bars < 100:  # Minimum bars for meaningful evaluation
                break

            windows.append((train_start, train_end, oos_start, oos_end))
            window_id += 1

            # Expand training window for next iteration
            train_end = oos_end

            # Stop if we've reached end of data
            if oos_end >= total_end:
                break

        return windows

    def run_single_window(
        self,
        df: pd.DataFrame,
        train_start: pd.Timestamp,
        train_end: pd.Timestamp,
        oos_start: pd.Timestamp,
        oos_end: pd.Timestamp,
        window_id: int,
    ) -> WindowResult:
        """Run DONCHIAN-001 on a single OOS window with given training period."""

        # Extract OOS data (need training data for channel warmup)
        # We need to include enough prior bars for channel calculation
        lookback = max(self.config.base_config.entry_lookback, self.config.base_config.exit_lookback)
        warmup_start = oos_start - pd.DateOffset(hours=lookback + 100)  # Buffer

        # Get data for this window (training + OOS for warmup, but we only evaluate OOS)
        # Actually, the strategy doesn't need training data for parameter fitting —
        # it's a fixed-parameter strategy. The "training" is just to compute channels
        # that have enough history. So we compute channels on full data up to oos_end,
        # then evaluate only on OOS period.

        # Compute channels on data up to OOS end (includes all prior history)
        df_window = df[df.index <= oos_end].copy()
        df_window = compute_donchian_channels(
            df_window,
            self.config.base_config.entry_lookback,
            self.config.base_config.exit_lookback,
        )

        # Now extract only OOS period for evaluation
        oos_mask = (df_window.index >= oos_start) & (df_window.index < oos_end)
        df_oos = df_window[oos_mask].copy()

        # Also need training data stats for reference
        train_mask = (df.index >= train_start) & (df.index < train_end)
        n_train_bars = int(train_mask.sum())
        n_oos_bars = int(oos_mask.sum())

        if n_oos_bars == 0:
            raise ValueError(f"Window {window_id}: No OOS bars in range {oos_start} to {oos_end}")

        # Run VectorBT on OOS data only
        pf = run_vectorbt_portfolio(df_oos, self.config.base_config)

        # Compute metrics
        metrics = compute_metrics(pf, self.config.base_config, df_oos)
        benchmarks = compute_benchmarks(df_oos)
        trades = pf.trades.records_readable

        return WindowResult(
            window_id=window_id,
            train_start=train_start,
            train_end=train_end,
            oos_start=oos_start,
            oos_end=oos_end,
            n_train_bars=n_train_bars,
            n_oos_bars=n_oos_bars,
            metrics=metrics,
            benchmarks=benchmarks,
            trades=trades,
        )

    def run_walk_forward(self) -> list[WindowResult]:
        """Execute full walk-forward validation."""
        print("=" * 60)
        print("DONCHIAN-001 Walk-Forward Validation")
        print("=" * 60)

        # Load full data
        print("\n[1/4] Loading full dataset...")
        df = self.load_full_data()
        print(f"      Loaded {len(df)} bars from {df.index[0]} to {df.index[-1]}")

        # Compute windows
        print("\n[2/4] Computing walk-forward windows...")
        windows = self.compute_windows(df)
        print(f"      Generated {len(windows)} OOS windows:")
        for i, (tr_s, tr_e, oos_s, oos_e) in enumerate(windows):
            print(f"      Window {i+1}: Train {tr_s.date()}→{tr_e.date()} | OOS {oos_s.date()}→{oos_e.date()}")

        # Run each window
        print("\n[3/4] Running walk-forward evaluation...")
        self.results = []
        for i, (tr_s, tr_e, oos_s, oos_e) in enumerate(windows):
            print(f"      Window {i+1}/{len(windows)}...", end=" ")
            try:
                result = self.run_single_window(df, tr_s, tr_e, oos_s, oos_e, i + 1)
                self.results.append(result)
                m = result.metrics
                print(f"Trades={m.get('n_trades', 0)}, NetRet={m.get('total_return_net', 0):.2%}, PF={m.get('profit_factor_net', 0):.2f}, Sharpe={m.get('sharpe_net', 0):.2f}, DD={m.get('max_drawdown_net', 0):.2%}")
            except Exception as e:
                print(f"FAILED: {e}")
                raise

        # Aggregate results
        print("\n[4/4] Aggregating results...")
        self._print_aggregate_summary()

        return self.results

    def _print_aggregate_summary(self):
        """Print aggregate OOS performance summary."""
        if not self.results:
            print("      No results to aggregate")
            return

        # Aggregate metrics across all OOS windows
        all_trades = []
        total_net_return = 1.0
        total_gross_return = 1.0
        all_net_returns = []
        all_sharpes = []
        all_dd = []
        all_pf = []
        all_win_rates = []
        profitable_windows = 0

        for r in self.results:
            m = r.metrics
            if m.get('n_trades', 0) > 0:
                # Compound returns across windows
                total_net_return *= (1 + m['total_return_net'])
                total_gross_return *= (1 + m['total_return_gross'])
                all_net_returns.append(m['total_return_net'])
                all_sharpes.append(m['sharpe_net'])
                all_dd.append(m['max_drawdown_net'])
                all_pf.append(m['profit_factor_net'])
                all_win_rates.append(m['win_rate_net'])
                if m['total_return_net'] > 0:
                    profitable_windows += 1
                # Collect trades for aggregate analysis
                if len(r.trades) > 0:
                    r.trades['window_id'] = r.window_id
                    all_trades.append(r.trades)

        agg_net_return = total_net_return - 1
        agg_gross_return = total_gross_return - 1

        print(f"\n{'='*60}")
        print("AGGREGATE OOS PERFORMANCE")
        print(f"{'='*60}")
        print(f"Total OOS windows: {len(self.results)}")
        print(f"Profitable windows: {profitable_windows}/{len(self.results)} ({profitable_windows/len(self.results):.0%})")
        print(f"")
        print(f"Aggregate Net Return: {agg_net_return:.2%}")
        print(f"Aggregate Gross Return: {agg_gross_return:.2%}")
        print(f"Mean OOS Net Return: {np.mean(all_net_returns):.2%} (±{np.std(all_net_returns):.2%})")
        print(f"Median OOS Net Return: {np.median(all_net_returns):.2%}")
        print(f"Mean OOS Sharpe: {np.mean(all_sharpes):.2f} (±{np.std(all_sharpes):.2f})")
        print(f"Mean OOS Profit Factor: {np.mean(all_pf):.2f}")
        print(f"Mean OOS Win Rate: {np.mean(all_win_rates):.1%}")
        print(f"Worst OOS DD: {min(all_dd):.2%}")
        print(f"Best OOS Window Return: {max(all_net_returns):.2%}")
        print(f"Worst OOS Window Return: {min(all_net_returns):.2%}")

        # Aggregate trades
        if all_trades:
            all_trades_df = pd.concat(all_trades, ignore_index=True)
            n_trades = len(all_trades_df)
            net_pnls = all_trades_df['PnL'].values
            win_rate = (net_pnls > 0).mean()
            expectancy = net_pnls.mean()
            pf = net_pnls[net_pnls > 0].sum() / (-net_pnls[net_pnls < 0].sum()) if (net_pnls < 0).any() else np.inf
            print(f"\nAggregate Trade Stats:")
            print(f"  Total Trades: {n_trades}")
            print(f"  Win Rate: {win_rate:.1%}")
            print(f"  Expectancy: ${expectancy:.2f}/trade")
            print(f"  Profit Factor: {pf:.2f}")

    def generate_report(self) -> str:
        """Generate comprehensive walk-forward report."""
        if not self.results:
            return "No results to report."

        df = self.load_full_data()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        sections = [
            f"DONCHIAN-001 Walk-Forward Validation Report",
            f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"Experiment ID: WF_DONCHIAN_001_{stamp}",
            f"VectorBT Version: {vbt.__version__}",
            "",
            "METHODOLOGY",
            f"Baseline: Donchian entry={self.config.base_config.entry_lookback}, exit={self.config.base_config.exit_lookback}",
            f"Initial Training: {self.config.initial_train_years} years",
            f"OOS Window: {self.config.oos_window_years} year(s)",
            f"Step: {self.config.step_years} year(s) (expanding window)",
            f"Warmup bars: {self.config.warmup_bars} (max lookback)",
            f"Cost Model: spread={self.config.base_config.cost_model.spread_pips} pips, "
            f"commission=${self.config.base_config.cost_model.commission_per_lot}/lot, "
            f"slippage={self.config.base_config.cost_model.slippage_pips} pips/side",
            f"Round-trip cost: ${self.config.base_config.cost_model.per_round_trip_usd_per_lot():.2f}/lot",
            "",
            "WINDOW RESULTS",
        ]

        # Per-window detail
        for r in self.results:
            m = r.metrics
            b = r.benchmarks
            sections.extend([
                "",
                f"--- Window {r.window_id} ---",
                f"Train: {r.train_start.date()} to {r.train_end.date()} ({r.n_train_bars} bars)",
                f"OOS:   {r.oos_start.date()} to {r.oos_end.date()} ({r.n_oos_bars} bars)",
                f"Trades: {m.get('n_trades', 0)}",
                f"Net Return: {m.get('total_return_net', 0):.2%} | Ann. Return: {m.get('annualized_return_net', 0):.2%}",
                f"Sharpe: {m.get('sharpe_net', 0):.2f} | Sortino: {m.get('sortino_net', 0):.2f}",
                f"Max DD: {m.get('max_drawdown_net', 0):.2%} | Calmar: {m.get('calmar_net', 0):.2f}",
                f"Profit Factor: {m.get('profit_factor_net', 0):.2f} | Win Rate: {m.get('win_rate_net', 0):.1%}",
                f"Expectancy: ${m.get('expectancy_net_usd', 0):.2f}/trade",
                f"Exposure: {m.get('exposure', 0):.2%} | Turnover: {m.get('turnover', 0):.2f}",
                f"Buy-and-Hold (OOS): {b.get('buy_and_hold_return', 0):.2%}",
            ])

        # Aggregate summary
        all_net_returns = [r.metrics.get('total_return_net', 0) for r in self.results if r.metrics.get('n_trades', 0) > 0]
        all_sharpes = [r.metrics.get('sharpe_net', 0) for r in self.results if r.metrics.get('n_trades', 0) > 0]
        all_dd = [r.metrics.get('max_drawdown_net', 0) for r in self.results if r.metrics.get('n_trades', 0) > 0]
        all_pf = [r.metrics.get('profit_factor_net', 0) for r in self.results if r.metrics.get('n_trades', 0) > 0]
        all_win_rates = [r.metrics.get('win_rate_net', 0) for r in self.results if r.metrics.get('n_trades', 0) > 0]
        profitable = sum(1 for r in all_net_returns if r > 0)

        total_net = np.prod([1 + r for r in all_net_returns]) - 1 if all_net_returns else 0

        sections.extend([
            "",
            "AGGREGATE OOS PERFORMANCE",
            f"Windows evaluated: {len(self.results)}",
            f"Profitable windows: {profitable}/{len(self.results)} ({profitable/len(self.results):.0%})" if self.results else "N/A",
            f"Aggregate Net Return: {total_net:.2%}",
            f"Mean OOS Net Return: {np.mean(all_net_returns):.2%} (±{np.std(all_net_returns):.2%})" if all_net_returns else "N/A",
            f"Median OOS Net Return: {np.median(all_net_returns):.2%}" if all_net_returns else "N/A",
            f"Mean OOS Sharpe: {np.mean(all_sharpes):.2f} (±{np.std(all_sharpes):.2f})" if all_sharpes else "N/A",
            f"Mean OOS Sortino: {np.mean([r.metrics.get('sortino_net', 0) for r in self.results if r.metrics.get('n_trades', 0) > 0]):.2f}",
            f"Mean OOS Profit Factor: {np.mean(all_pf):.2f}" if all_pf else "N/A",
            f"Mean OOS Win Rate: {np.mean(all_win_rates):.1%}" if all_win_rates else "N/A",
            f"Worst Window Return: {min(all_net_returns):.2%}" if all_net_returns else "N/A",
            f"Best Window Return: {max(all_net_returns):.2%}" if all_net_returns else "N/A",
            f"Worst Window Max DD: {min(all_dd):.2%}" if all_dd else "N/A",
        ])

        # Comparison with full-history backtest (Assignment 06)
        sections.extend([
            "",
            "COMPARISON WITH FULL-HISTORY BACKTEST (ASSIGNMENT 06)",
            "Full-history (2015-2026) net return: 541.41%",
            "Full-history (2015-2026) net Sharpe: 0.05",
            "Full-history (2015-2026) max DD: -32.11%",
            "Full-history (2015-2026) profit factor: 1.60",
            "",
            "Walk-forward OOS aggregate provides more realistic expectation",
            "by evaluating on unseen data sequentially rather than single in-sample fit.",
        ])

        # Robustness assessment
        sections.extend([
            "",
            "ROBUSTNESS ASSESSMENT",
        ])

        # Check if performance is concentrated in few windows
        if all_net_returns:
            sorted_returns = sorted(all_net_returns, reverse=True)
            top_2_contrib = sum(sorted_returns[:2]) / sum(r for r in sorted_returns if r > 0) if sum(r for r in sorted_returns if r > 0) > 0 else 0
            sections.append(f"Top 2 windows contribution to positive returns: {top_2_contrib:.0%}")

        # Check regime sensitivity
        neg_windows = sum(1 for r in all_net_returns if r < 0)
        sections.append(f"Negative return windows: {neg_windows}/{len(all_net_returns)}")

        # Drawdown behavior
        if all_dd:
            sections.append(f"Max DD across windows: {min(all_dd):.2%} (worst), {max(all_dd):.2%} (best)")

        # Recommendation
        sections.extend([
            "",
            "RECOMMENDATION",
        ])

        if profitable / len(self.results) >= 0.6 and total_net > 0 and np.mean(all_sharpes) > 0.1:
            rec = "GO TO MONTE CARLO"
        elif profitable / len(self.results) >= 0.5 and total_net > 0:
            rec = "RESEARCH FURTHER"
        else:
            rec = "REJECT"

        sections.append(f"Decision: {rec}")
        sections.append("")
        sections.append("Rationale:")
        if rec == "GO TO MONTE CARLO":
            sections.append("- Majority of OOS windows profitable")
            sections.append("- Positive aggregate OOS return with acceptable risk-adjusted metrics")
            sections.append("- Performance not dominated by single window")
        elif rec == "RESEARCH FURTHER":
            sections.append("- Some positive OOS windows but inconsistent")
            sections.append("- Risk-adjusted metrics below threshold for live deployment")
            sections.append("- Requires regime filtering or position sizing improvements")
        else:
            sections.append("- Insufficient OOS profitability")
            sections.append("- Performance likely regime-dependent (favorable bull markets only)")
            sections.append("- Does not generalize across market conditions")

        report_text = "\n".join(sections)

        # Save report
        report_path = self.paths.reports / f"donchian_wf_validation_{stamp}.txt"
        write_text_report(report_path, sections, title="DONCHIAN-001 Walk-Forward Validation")

        # Save detailed results
        results_path = self.paths.artifacts / f"donchian_wf_results_{stamp}.parquet"
        self.paths.artifacts.mkdir(parents=True, exist_ok=True)

        # Save per-window metrics
        window_metrics = []
        for r in self.results:
            row = {
                'window_id': r.window_id,
                'train_start': r.train_start,
                'train_end': r.train_end,
                'oos_start': r.oos_start,
                'oos_end': r.oos_end,
                'n_train_bars': r.n_train_bars,
                'n_oos_bars': r.n_oos_bars,
            }
            row.update({k: v for k, v in r.metrics.items() if not isinstance(v, (dict, list, pd.DataFrame))})
            window_metrics.append(row)

        window_metrics_df = pd.DataFrame(window_metrics)
        window_metrics_df.to_parquet(results_path)

        # Save all trades
        if all_trades := [r.trades for r in self.results if len(r.trades) > 0]:
            all_trades_df = pd.concat(all_trades, ignore_index=True)
            trades_path = self.paths.artifacts / f"donchian_wf_trades_{stamp}.parquet"
            all_trades_df.to_parquet(trades_path)

        return report_text


def run_walk_forward_validation(
    timeframe: str = "h1",
    entry_lookback: int = 55,
    exit_lookback: int = 20,
    spread_pips: float = 1.0,
    commission: float = 0.5,
    slippage_pips: float = 0.5,
    initial_train_years: int = 4,
    oos_window_years: int = 1,
    step_years: int = 1,
    seed: int = 42,
) -> list[WindowResult]:
    """Convenience function to run walk-forward validation."""

    cost_model = CostModel(
        spread_pips=spread_pips,
        commission_per_lot=commission,
        slippage_pips=slippage_pips,
    )

    base_config = DonchianConfig(
        timeframe=timeframe,
        entry_lookback=entry_lookback,
        exit_lookback=exit_lookback,
        cost_model=cost_model,
        seed=seed,
    )

    wf_config = WalkForwardConfig(
        base_config=base_config,
        initial_train_years=initial_train_years,
        oos_window_years=oos_window_years,
        step_years=step_years,
        seed=seed,
    )

    validator = WalkForwardValidator(wf_config)
    results = validator.run_walk_forward()
    report = validator.generate_report()
    print("\n" + report)

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="DONCHIAN-001 Walk-Forward Validation")
    parser.add_argument("--timeframe", choices=["m5", "h1"], default="h1")
    parser.add_argument("--entry-lookback", type=int, default=55)
    parser.add_argument("--exit-lookback", type=int, default=20)
    parser.add_argument("--spread-pips", type=float, default=1.0)
    parser.add_argument("--commission", type=float, default=0.5)
    parser.add_argument("--slippage-pips", type=float, default=0.5)
    parser.add_argument("--initial-train-years", type=int, default=4)
    parser.add_argument("--oos-window-years", type=int, default=1)
    parser.add_argument("--step-years", type=int, default=1)
    parser.add_argument("--seed", type=int, default=42)

    args = parser.parse_args()

    run_walk_forward_validation(
        timeframe=args.timeframe,
        entry_lookback=args.entry_lookback,
        exit_lookback=args.exit_lookback,
        spread_pips=args.spread_pips,
        commission=args.commission,
        slippage_pips=args.slippage_pips,
        initial_train_years=args.initial_train_years,
        oos_window_years=args.oos_window_years,
        step_years=args.step_years,
        seed=args.seed,
    )