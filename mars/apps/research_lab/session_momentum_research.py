"""
M.A.R.S. Session Momentum IS Research Pipeline: XAU-SESSION-MOM-001

In-Sample research with:
- Chronological train/val/test splits (70/15/15)
- One-factor-at-a-time parameter sensitivity (no grid search)
- Predeclared baselines (Buy-and-Hold, Flat, Random Signal)
- Full metrics suite per spec
- Frozen baseline = Paper 12 config
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yaml

from mars.apps.backtester.session_momentum_backtest import (
    SessionMomentumBacktester,
    BacktestResult,
    CostModel,
    ExecutionModel,
)
from mars.libs.data.loaders import load_ohlcv_parquet
from mars.libs.evaluation.metrics import regression_metrics
from mars.libs.evaluation.report import write_text_report
from mars.libs.evaluation.splits import time_series_split, TimeSeriesSplitResult
from mars.libs.risk.contract_aware import InstrumentSpec
from mars.libs.strategies.xau_session_momentum import SessionMomentumParams
from mars.libs.utils.paths import ProjectPaths
from mars.research.experiment import ExperimentLog, ExperimentRecord


# ============================================================================
# Research Configuration
# ============================================================================

@dataclass(frozen=True)
class ResearchConfig:
    """Immutable research configuration."""

    # Data
    symbol: str = "XAUUSDm"
    m5_path: str = "data/processed/xauusdm/m5/v1.2.0/data.parquet"
    h1_path: str = "data/processed/xauusdm/h1/v1.2.0/data.parquet"

    # Splits (chronological, by session index)
    train_ratio: float = 0.70
    val_ratio: float = 0.15
    test_ratio: float = 0.15

    # Baseline params (Paper 12 config = frozen baseline)
    baseline_params: SessionMomentumParams = field(default_factory=lambda: SessionMomentumParams(
        signal_mode="direction",
        threshold=0.0,
        risk_fraction=0.01,
        sl_points=200,
        spread_multiplier=1.0,
        commission_per_lot=0.0,
        slippage_points=0.0,
        block_fomc=False,
        block_high_vol=False,
        block_high_spread=False,
        starting_equity=10000.0,
    ))

    # Sensitivity grid (one-factor-at-a-time from baseline)
    sensitivity_grid: Dict[str, List[Any]] = field(default_factory=lambda: {
        "sl_points": [200, 300, 500],
        "spread_multiplier": [1.0, 1.5, 2.0],
        "risk_fraction": [0.01],  # Fixed per programme
        "signal_mode": ["direction"],  # Fixed per Paper 12
        "threshold": [0.0],  # Fixed per Paper 12
        "block_fomc": [False, True],
        "block_high_vol": [False, True],
        "block_high_spread": [False, True],
    })

    # Output
    output_dir: str = "reports/programme_01/session_momentum_001/is"
    experiment_log_root: str = "research/experiment_logs"
    hypothesis_id: str = "CSM-001"
    seed: int = 42


# ============================================================================
# Metrics Computation
# ============================================================================

def compute_trade_metrics(trades: pd.DataFrame, equity: float = 10000.0) -> Dict[str, Any]:
    """Compute comprehensive trade-level metrics matching spec Section 11."""
    if len(trades) == 0:
        return {"error": "No trades executed"}

    gross_pnls = trades["gross_pnl"].values
    net_pnls = trades["net_pnl"].values
    returns_gross = gross_pnls / equity
    returns_net = net_pnls / equity

    n_trades = len(trades)
    n_wins_gross = (gross_pnls > 0).sum()
    n_wins_net = (net_pnls > 0).sum()
    win_rate_gross = n_wins_gross / n_trades
    win_rate_net = n_wins_net / n_trades

    expectancy_gross = gross_pnls.mean()
    expectancy_net = net_pnls.mean()

    gross_profit = gross_pnls[gross_pnls > 0].sum()
    gross_loss = -gross_pnls[gross_pnls < 0].sum()
    profit_factor_gross = gross_profit / gross_loss if gross_loss > 0 else np.inf

    net_profit = net_pnls[net_pnls > 0].sum()
    net_loss = -net_pnls[net_pnls < 0].sum()
    profit_factor_net = net_profit / net_loss if net_loss > 0 else np.inf

    # Average R-multiple
    r_multiples = trades["r_multiple"].values
    avg_r_multiple = float(r_multiples.mean())

    # Holding period distribution
    holding_minutes = trades["holding_minutes"].values
    holding_sessions = holding_minutes / 60.0 / 8.0  # Approx sessions (8h avg)

    return {
        "n_trades": int(n_trades),
        "n_wins_gross": int(n_wins_gross),
        "n_wins_net": int(n_wins_net),
        "win_rate_gross": float(win_rate_gross),
        "win_rate_net": float(win_rate_net),
        "expectancy_gross_usd": float(expectancy_gross),
        "expectancy_net_usd": float(expectancy_net),
        "expectancy_gross_pct": float(expectancy_gross / equity),
        "expectancy_net_pct": float(expectancy_net / equity),
        "profit_factor_gross": float(profit_factor_gross),
        "profit_factor_net": float(profit_factor_net),
        "avg_r_multiple": avg_r_multiple,
        "avg_holding_minutes": float(holding_minutes.mean()),
        "avg_holding_sessions": float(holding_sessions.mean()),
        "gross_profit_usd": float(gross_profit),
        "gross_loss_usd": float(gross_loss),
        "net_profit_usd": float(net_profit),
        "net_loss_usd": float(net_loss),
    }


def compute_equity_metrics(equity_curve: pd.Series, starting_equity: float = 10000.0) -> Dict[str, Any]:
    """Compute equity curve metrics matching spec Section 11.2."""
    if len(equity_curve) < 2:
        return {"error": "Insufficient equity curve data"}

    returns = equity_curve.pct_change().dropna()
    if len(returns) == 0:
        return {"error": "No returns in equity curve"}

    cum_return = (equity_curve.iloc[-1] - starting_equity) / starting_equity

    # Annualized (assuming ~252 trading days * 3 sessions = 756 sessions/year)
    # But equity_curve is per M5 bar, so use trading days
    n_days = (equity_curve.index[-1] - equity_curve.index[0]).days
    if n_days > 0:
        years = n_days / 365.25
        ann_return = (1 + cum_return) ** (1 / years) - 1 if years > 0 else 0
    else:
        ann_return = 0.0

    ann_vol = returns.std() * np.sqrt(252 * 288)  # 288 M5 bars per day
    sharpe = ann_return / ann_vol if ann_vol > 0 else 0.0

    # Max drawdown
    cum_curve = equity_curve / starting_equity
    peak = cum_curve.expanding().max()
    dd = (cum_curve - peak) / peak
    max_dd = float(dd.min())
    max_dd_usd = float((dd * starting_equity).min())

    # Max DD duration (in bars)
    dd_duration = (dd < 0).astype(int)
    dd_groups = (dd_duration.diff() != 0).cumsum()
    max_dd_bars = int(dd_duration.groupby(dd_groups).sum().max()) if len(dd_groups) > 0 else 0

    # Calmar
    calmar = ann_return / abs(max_dd) if max_dd != 0 else 0.0

    return {
        "total_return": float(cum_return),
        "annualized_return": float(ann_return),
        "annualized_vol": float(ann_vol),
        "sharpe": float(sharpe),
        "max_drawdown": float(max_dd),
        "max_drawdown_usd": float(max_dd_usd),
        "max_drawdown_duration_bars": max_dd_bars,
        "calmar": float(calmar),
    }


def compute_session_breakdown(trades: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Break down performance by session type and year (spec Section 11.3)."""
    if len(trades) == 0:
        return pd.DataFrame(), pd.DataFrame()

    trade_df = trades.copy()
    trade_df["year"] = pd.to_datetime(trade_df["entry_time"]).dt.year
    trade_df["entry_session"] = trade_df["entry_session"].astype(str)

    # By session transition (Asia->Europe, Europe->US, US->Asia)
    # We need to infer the transition from entry_session
    session_map = {"asia": "Asia->Europe", "europe": "Europe->US", "us": "US->Asia"}
    trade_df["transition"] = trade_df["entry_session"].map(session_map)

    by_session = trade_df.groupby("transition").agg(
        n_trades=("net_pnl", "count"),
        win_rate=("net_pnl", lambda x: (x > 0).mean()),
        avg_pnl=("net_pnl", "mean"),
        total_pnl=("net_pnl", "sum"),
        avg_r=("r_multiple", "mean"),
    ).round(4)

    by_year = trade_df.groupby("year").agg(
        n_trades=("net_pnl", "count"),
        win_rate=("net_pnl", lambda x: (x > 0).mean()),
        avg_pnl=("net_pnl", "mean"),
        total_pnl=("net_pnl", "sum"),
        avg_r=("r_multiple", "mean"),
    ).round(4)

    return by_session, by_year


def compute_exposure_turnover(trades: pd.DataFrame, equity_curve: pd.Series, equity: float = 10000.0) -> Dict[str, float]:
    """Compute exposure and turnover metrics (spec Section 11.4)."""
    if len(trades) == 0:
        return {"exposure": 0.0, "turnover": 0.0, "avg_leverage": 0.0}

    # Exposure: fraction of bars in market
    total_bars = len(equity_curve)
    bars_in_market = trades["bars_in_market"].sum()
    exposure = bars_in_market / total_bars if total_bars > 0 else 0.0

    # Turnover: sum of |Δposition| / equity
    # Each trade opens and closes = 2 * position_size per trade
    # But we track lots per trade
    total_lots_traded = trades["lots"].sum() * 2  # entry + exit
    avg_position_usd = trades["lots"].mean() * 100.0 * equity  # approx
    turnover = float(total_lots_traded)  # Simplified

    # Average leverage
    avg_leverage = float(trades["lots"].mean() * 100.0 / equity * 100.0)  # Notional / equity

    return {
        "exposure": float(exposure),
        "turnover": turnover,
        "avg_leverage": avg_leverage,
    }


def compute_baselines(m5: pd.DataFrame, split: TimeSeriesSplitResult, equity: float = 10000.0) -> Dict[str, Any]:
    """Compute predeclared baselines: Buy-and-Hold, Flat, Random Signal."""
    # Split the M5 data
    test_m5 = m5.iloc[split.test_idx]

    # Buy-and-Hold: long from first test open to last test close
    first_open = test_m5["open"].iloc[0]
    last_close = test_m5["close"].iloc[-1]
    bh_return = (last_close - first_open) / first_open
    bh_equity = equity * (1 + bh_return)

    # Flat: zero return
    flat_equity = equity

    # Random Signal baseline requires Monte Carlo - placeholder for now
    return {
        "buy_and_hold": {
            "return": float(bh_return),
            "final_equity": float(bh_equity),
        },
        "flat": {
            "return": 0.0,
            "final_equity": float(flat_equity),
        },
        "random_signal": {
            "note": "Requires Monte Carlo reshuffle - see session_momentum_montecarlo.py",
        },
    }


def run_single_backtest(
    m5: pd.DataFrame,
    h1: pd.DataFrame,
    params: SessionMomentumParams,
    spec: InstrumentSpec,
    cost_model: CostModel,
    execution_model: ExecutionModel,
) -> BacktestResult:
    """Run a single backtest with given parameters."""
    backtester = SessionMomentumBacktester(
        params=params,
        spec=spec,
        cost_model=cost_model,
        execution_model=execution_model,
    )
    return backtester.run(m5, h1)


# ============================================================================
# IS Research Pipeline
# ============================================================================

def run_is_research(config: Optional[ResearchConfig] = None) -> Dict[str, Any]:
    """Execute the full IS research pipeline."""
    config = config or ResearchConfig()
    paths = ProjectPaths.from_root()

    print("=" * 70)
    print("M.A.R.S. Session Momentum IS Research: XAU-SESSION-MOM-001")
    print("=" * 70)

    # --- 1. Load data ---
    print("\n[1/7] Loading M5 and H1 data...")
    m5 = load_ohlcv_parquet(paths.root / config.m5_path)
    h1 = load_ohlcv_parquet(paths.root / config.h1_path)
    print(f"      M5: {len(m5)} bars, {m5['timestamp'].min()} to {m5['timestamp'].max()}")
    print(f"      H1: {len(h1)} bars, {h1['timestamp'].min()} to {h1['timestamp'].max()}")

    # --- 2. Compute session-level data for splitting ---
    from mars.libs.strategies.xau_session_momentum import compute_session_returns, assign_session_labels
    session_bars = compute_session_returns(m5.set_index("timestamp"))
    print(f"      {len(session_bars)} sessions from {session_bars['session_start'].min()} to {session_bars['session_start'].max()}")

    # --- 3. Chronological split by session index ---
    print("\n[2/7] Applying chronological train/val/test split (70/15/15)...")
    split = time_series_split(
        session_bars.index,
        train_ratio=config.train_ratio,
        val_ratio=config.val_ratio,
        test_ratio=config.test_ratio,
    )
    print(split.describe())

    # Map session splits back to M5 bar indices using timestamp index
    m5_indexed = m5.set_index("timestamp")
    m5_sessions = assign_session_labels(m5_indexed)

    # Create mapping from (date, session) to M5 timestamps
    session_to_timestamps = m5_sessions.groupby(["date", "session"]).apply(
        lambda x: x.index.tolist()
    )

    train_timestamps = []
    val_timestamps = []
    test_timestamps = []

    for idx in split.train_idx:
        session_row = session_bars.iloc[idx]
        key = (session_row["date"], session_row["session"])
        if key in session_to_timestamps.index:
            train_timestamps.extend(session_to_timestamps[key])
    for idx in split.val_idx:
        session_row = session_bars.iloc[idx]
        key = (session_row["date"], session_row["session"])
        if key in session_to_timestamps.index:
            val_timestamps.extend(session_to_timestamps[key])
    for idx in split.test_idx:
        session_row = session_bars.iloc[idx]
        key = (session_row["date"], session_row["session"])
        if key in session_to_timestamps.index:
            test_timestamps.extend(session_to_timestamps[key])

    train_m5 = m5_indexed.loc[train_timestamps].reset_index()
    val_m5 = m5_indexed.loc[val_timestamps].reset_index()
    test_m5 = m5_indexed.loc[test_timestamps].reset_index()

    # Split H1 by session date range (not exact timestamp matching)
    # H1 is resampled from M5, so sessions align by date boundaries
    train_dates = set(pd.to_datetime(train_timestamps).date)
    val_dates = set(pd.to_datetime(val_timestamps).date)
    test_dates = set(pd.to_datetime(test_timestamps).date)

    h1["date"] = h1["timestamp"].dt.date
    train_h1 = h1[h1["date"].isin(train_dates)].drop(columns=["date"]).reset_index(drop=True)
    val_h1 = h1[h1["date"].isin(val_dates)].drop(columns=["date"]).reset_index(drop=True)
    test_h1 = h1[h1["date"].isin(test_dates)].drop(columns=["date"]).reset_index(drop=True)

    print(f"      Train: {len(train_m5)} M5 bars, {len(train_h1)} H1 bars")
    print(f"      Val:   {len(val_m5)} M5 bars, {len(val_h1)} H1 bars")
    print(f"      Test:  {len(test_m5)} M5 bars, {len(test_h1)} H1 bars")

    # --- 4. Instrument spec & cost/execution models ---
    print("\n[3/7] Setting up instrument spec and cost/execution models...")
    spec = InstrumentSpec(
        symbol="XAUUSDm",
        contract_size=100.0,
        pip_size=0.01,
        point_size=0.001,
        quote_currency="USD",
        volume_min=0.01,
        volume_max=200.0,
        volume_step=0.01,
        volume_spec_source="pair_config.offline",
        spec_source="pair_config.offline",
    )
    cost_model = CostModel(
        spread_multiplier=config.baseline_params.spread_multiplier,
        commission_per_lot_round_trip=config.baseline_params.commission_per_lot,
        slippage_points=config.baseline_params.slippage_points,
        use_observed_spread=True,
        fallback_spread_points=200.0,
    )
    execution_model = ExecutionModel()

    # --- 5. Run baseline on train (frozen Paper 12 config) ---
    print("\n[4/7] Running baseline (Paper 12 config) on TRAIN...")
    baseline_result = run_single_backtest(
        train_m5, train_h1, config.baseline_params, spec, cost_model, execution_model
    )
    baseline_metrics = compute_full_metrics(baseline_result, config.baseline_params.starting_equity)
    print(f"      Trades: {baseline_metrics['trade_metrics']['n_trades']}")
    print(f"      Net Expectancy: ${baseline_metrics['trade_metrics']['expectancy_net_usd']:.2f}")
    print(f"      Net Profit Factor: {baseline_metrics['trade_metrics']['profit_factor_net']:.2f}")
    print(f"      Net Sharpe: {baseline_metrics['equity_metrics']['sharpe']:.2f}")
    print(f"      Max DD: {baseline_metrics['equity_metrics']['max_drawdown']:.2%}")

    # --- 6. One-factor-at-a-time sensitivity on validation ---
    print("\n[5/7] Running one-factor-at-a-time sensitivity on VALIDATION...")
    sensitivity_results = run_sensitivity_analysis(
        val_m5, val_h1, config.baseline_params, config.sensitivity_grid,
        spec, cost_model, execution_model
    )

    # --- 7. Run baseline on test (OOS) ---
    print("\n[6/7] Running baseline on TEST (OOS)...")
    test_result = run_single_backtest(
        test_m5, test_h1, config.baseline_params, spec, cost_model, execution_model
    )
    test_metrics = compute_full_metrics(test_result, config.baseline_params.starting_equity)
    print(f"      Trades: {test_metrics['trade_metrics']['n_trades']}")
    print(f"      Net Expectancy: ${test_metrics['trade_metrics']['expectancy_net_usd']:.2f}")
    print(f"      Net Profit Factor: {test_metrics['trade_metrics']['profit_factor_net']:.2f}")
    print(f"      Net Sharpe: {test_metrics['equity_metrics']['sharpe']:.2f}")
    print(f"      Max DD: {test_metrics['equity_metrics']['max_drawdown']:.2%}")

    # --- 8. Baselines ---
    print("\n[7/7] Computing predeclared baselines...")
    baselines = compute_baselines(m5, split, config.baseline_params.starting_equity)

    # --- 9. Compile results ---
    results = {
        "strategy_id": "XAU-SESSION-MOM-001",
        "hypothesis_id": config.hypothesis_id,
        "data_version": "M5 v1.2.0 / H1 v1.2.0",
        "split": {
            "train_ratio": config.train_ratio,
            "val_ratio": config.val_ratio,
            "test_ratio": config.test_ratio,
            "train_sessions": len(split.train_idx),
            "val_sessions": len(split.val_idx),
            "test_sessions": len(split.test_idx),
        },
        "baseline_params": config.baseline_params.to_dict(),
        "train_metrics": baseline_metrics,
        "val_sensitivity": sensitivity_results,
        "test_metrics": test_metrics,
        "baselines": baselines,
        "falsification_check": check_falsification_criteria(test_metrics),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Save artifacts
    save_results(results, config.output_dir)

    # Log experiment
    log_experiment(results, config)

    print("\n" + "=" * 70)
    print("IS RESEARCH COMPLETE")
    print("=" * 70)
    print(f"Results saved to: {config.output_dir}")

    return results


def compute_full_metrics(result: BacktestResult, equity: float) -> Dict[str, Any]:
    """Compute all metrics for a backtest result."""
    trades_df = result.trades_frame()
    trade_metrics = compute_trade_metrics(trades_df, equity)
    equity_metrics = compute_equity_metrics(result.equity_curve, equity)
    by_session, by_year = compute_session_breakdown(trades_df)
    exposure_metrics = compute_exposure_turnover(trades_df, result.equity_curve, equity)

    return {
        "trade_metrics": trade_metrics,
        "equity_metrics": equity_metrics,
        "by_session": by_session.to_dict() if not by_session.empty else {},
        "by_year": by_year.to_dict() if not by_year.empty else {},
        "exposure_metrics": exposure_metrics,
        "rejected_signals": len(result.rejected_signals),
        "run_record": result.run_record(),
    }


def run_sensitivity_analysis(
    m5: pd.DataFrame,
    h1: pd.DataFrame,
    baseline: SessionMomentumParams,
    grid: Dict[str, List[Any]],
    spec: InstrumentSpec,
    cost_model: CostModel,
    execution_model: ExecutionModel,
) -> Dict[str, Any]:
    """One-factor-at-a-time sensitivity from baseline."""
    results = {}
    baseline_dict = baseline.to_dict()

    for param_name, values in grid.items():
        if param_name not in baseline_dict:
            continue

        baseline_value = baseline_dict[param_name]
        param_results = []

        for value in values:
            if value == baseline_value:
                # Use baseline result (already computed if we cached it)
                # For simplicity, re-run
                pass

            # Create modified params
            param_dict = baseline_dict.copy()
            param_dict[param_name] = value
            params = SessionMomentumParams(**param_dict)

            # Update cost model if spread_multiplier changed
            cm = CostModel(
                spread_multiplier=params.spread_multiplier,
                commission_per_lot_round_trip=params.commission_per_lot,
                slippage_points=params.slippage_points,
            )

            result = run_single_backtest(m5, h1, params, spec, cm, execution_model)
            metrics = compute_full_metrics(result, baseline.starting_equity)

            param_results.append({
                "value": value,
                "n_trades": metrics["trade_metrics"]["n_trades"],
                "expectancy_net_usd": metrics["trade_metrics"]["expectancy_net_usd"],
                "profit_factor_net": metrics["trade_metrics"]["profit_factor_net"],
                "sharpe": metrics["equity_metrics"]["sharpe"],
                "max_drawdown": metrics["equity_metrics"]["max_drawdown"],
            })

        results[param_name] = {
            "baseline_value": baseline_value,
            "results": param_results,
        }

    return results


def check_falsification_criteria(metrics: Dict[str, Any]) -> Dict[str, Any]:
    """Check predeclared falsification criteria (spec Section 13)."""
    trade_m = metrics.get("trade_metrics", {})
    equity_m = metrics.get("equity_metrics", {})

    checks = {
        "net_expectancy_positive": trade_m.get("expectancy_net_usd", -1) > 0,
        "net_profit_factor_gt_1": trade_m.get("profit_factor_net", 0) > 1.0,
        "net_sharpe_positive": equity_m.get("sharpe", -1) > 0,
        "max_drawdown_lt_20pct": abs(equity_m.get("max_drawdown", 1)) < 0.20,
        "trade_count_ge_30": trade_m.get("n_trades", 0) >= 30,
    }

    all_pass = all(checks.values())

    return {
        "checks": checks,
        "all_pass": all_pass,
        "verdict": "ADVANCES" if all_pass else "REJECTED",
    }


def save_results(results: Dict[str, Any], output_dir: str) -> None:
    """Save results as JSON and human-readable report."""
    paths = ProjectPaths.from_root()
    out_path = paths.root / output_dir
    out_path.mkdir(parents=True, exist_ok=True)

    # JSON
    import json
    json_path = out_path / "is_results.json"
    # Convert non-serializable
    serializable = make_serializable(results)
    json_path.write_text(json.dumps(serializable, indent=2), encoding="utf-8")

    # Human-readable report
    report_path = out_path / "is_report.md"
    report = generate_report(results)
    report_path.write_text(report, encoding="utf-8")

    # Trade ledgers
    # Note: Would need to save from backtest results


def make_serializable(obj: Any) -> Any:
    """Convert numpy/pandas types to JSON-serializable."""
    if isinstance(obj, (np.integer, np.floating)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, pd.DataFrame):
        return obj.to_dict()
    if isinstance(obj, pd.Series):
        return obj.to_dict()
    if isinstance(obj, dict):
        return {k: make_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [make_serializable(v) for v in obj]
    if isinstance(obj, (datetime, pd.Timestamp)):
        return obj.isoformat()
    return obj


def generate_report(results: Dict[str, Any]) -> str:
    """Generate human-readable IS report."""
    lines = [
        "# M.A.R.S. Session Momentum IS Research Report",
        f"**Strategy:** XAU-SESSION-MOM-001",
        f"**Hypothesis:** {results['hypothesis_id']}",
        f"**Data:** {results['data_version']}",
        f"**Date:** {results['timestamp']}",
        "",
        "## Split",
        f"- Train: {results['split']['train_sessions']} sessions ({results['split']['train_ratio']:.0%})",
        f"- Val:   {results['split']['val_sessions']} sessions ({results['split']['val_ratio']:.0%})",
        f"- Test:  {results['split']['test_sessions']} sessions ({results['split']['test_ratio']:.0%})",
        "",
        "## Baseline Configuration (Paper 12 - Frozen)",
    ]
    for k, v in results["baseline_params"].items():
        lines.append(f"- {k}: {v}")

    lines.extend(["", "## Train Metrics (In-Sample)"])
    tm = results["train_metrics"]["trade_metrics"]
    em = results["train_metrics"]["equity_metrics"]
    lines.extend([
        f"- Trades: {tm.get('n_trades', 'N/A')}",
        f"- Win Rate (net): {tm.get('win_rate_net', 0):.1%}",
        f"- Expectancy (net): ${tm.get('expectancy_net_usd', 0):.2f}",
        f"- Profit Factor (net): {tm.get('profit_factor_net', 0):.2f}",
        f"- Sharpe: {em.get('sharpe', 0):.2f}",
        f"- Max DD: {em.get('max_drawdown', 0):.2%}",
    ])

    lines.extend(["", "## Validation Sensitivity (One-Factor-at-a-Time)"])
    for param, data in results["val_sensitivity"].items():
        lines.append(f"\n### {param} (baseline: {data['baseline_value']})")
        for r in data["results"]:
            lines.append(
                f"- {param}={r['value']}: trades={r['n_trades']}, "
                f"expectancy=${r['expectancy_net_usd']:.2f}, PF={r['profit_factor_net']:.2f}, "
                f"Sharpe={r['sharpe']:.2f}, MaxDD={r['max_drawdown']:.2%}"
            )

    lines.extend(["", "## Test Metrics (Out-of-Sample)"])
    tm = results["test_metrics"]["trade_metrics"]
    em = results["test_metrics"]["equity_metrics"]
    lines.extend([
        f"- Trades: {tm.get('n_trades', 'N/A')}",
        f"- Win Rate (net): {tm.get('win_rate_net', 0):.1%}",
        f"- Expectancy (net): ${tm.get('expectancy_net_usd', 0):.2f}",
        f"- Profit Factor (net): {tm.get('profit_factor_net', 0):.2f}",
        f"- Sharpe: {em.get('sharpe', 0):.2f}",
        f"- Max DD: {em.get('max_drawdown', 0):.2%}",
    ])

    lines.extend(["", "## Baselines"])
    for name, data in results["baselines"].items():
        ret = data.get('return', 'N/A')
        eq = data.get('final_equity', 'N/A')
        if isinstance(ret, (int, float)):
            ret_str = f"{ret:.2%}"
        else:
            ret_str = str(ret)
        if isinstance(eq, (int, float)):
            eq_str = f"{eq:.2f}"
        else:
            eq_str = str(eq)
        lines.append(f"- {name}: return={ret_str}, equity={eq_str}")

    lines.extend(["", "## Falsification Criteria (Pre-Registered)"])
    fc = results["falsification_check"]
    for check, passed in fc["checks"].items():
        status = "✅ PASS" if passed else "❌ FAIL"
        lines.append(f"- {check}: {status}")
    lines.append(f"\n**Overall Verdict: {fc['verdict']}**")

    return "\n".join(lines)


def log_experiment(results: Dict[str, Any], config: ResearchConfig) -> None:
    """Log experiment to experiment registry."""
    exp_log = ExperimentLog(
        hypothesis_root=ProjectPaths.from_root().root / "research" / "hypotheses"
    )
    exp = ExperimentRecord(
        hypothesis_id=config.hypothesis_id,
        name="XAU-SESSION-MOM-001 IS Research",
        description="In-sample research for Asian-Session Momentum Continuation",
        dataset_ids=[config.m5_path, config.h1_path],
        parameters={
            "baseline_params": config.baseline_params.to_dict(),
            "sensitivity_grid": {k: str(v) for k, v in config.sensitivity_grid.items()},
        },
        metrics={
            "train": results["train_metrics"],
            "test": results["test_metrics"],
            "falsification": results["falsification_check"],
        },
        seed=config.seed,
    )
    exp_log.write(exp)
    print(f"Experiment logged: {exp.experiment_id}")


# ============================================================================
# CLI Entry Point
# ============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run XAU-SESSION-MOM-001 IS Research")
    parser.add_argument("--phase", choices=["is", "oos"], default="is")
    parser.add_argument("--config", type=str, default="configs/session_momentum_001.yaml")
    parser.add_argument("--frozen", action="store_true", help="Use frozen config for OOS")
    args = parser.parse_args()

    if args.phase == "is":
        run_is_research()
    else:
        print("OOS phase not yet implemented - use frozen config from IS")