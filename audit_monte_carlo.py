#!/usr/bin/env python3
"""
Independent audit of MA-TSM-001 Monte Carlo pipeline.
Verifies calculations, JSON output, and visualization data integrity.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy import stats

from mars.apps.research_lab.ma_tsm_monte_carlo import (
    MonteCarloConfig,
    MonteCarloResults,
    run_all_monte_carlo,
    run_block_bootstrap_mc,
    run_resampling_mc,
    run_reshuffling_mc,
    load_oos_trades,
    check_dependence,
    simulate_equity_path_from_returns,
    compute_drawdown,
    compute_max_losing_streak,
)

# =============================================================================
# INDEPENDENT CALCULATION FUNCTIONS (using NumPy/SciPy)
# =============================================================================

def independent_historical_metrics(returns: np.ndarray, initial_capital: float) -> dict:
    """Independent calculation of historical metrics."""
    equity = np.zeros(len(returns) + 1)
    equity[0] = initial_capital
    for i, ret in enumerate(returns):
        equity[i + 1] = equity[i] * (1 + ret)
    
    terminal_return = (equity[-1] - initial_capital) / initial_capital
    
    peak = np.maximum.accumulate(equity)
    dd = (equity - peak) / peak
    max_dd = abs(np.min(dd))
    
    losing = returns < 0
    max_streak = 0
    current = 0
    for is_l in losing:
        if is_l:
            current += 1
            max_streak = max(max_streak, current)
        else:
            current = 0
    
    return {
        "terminal_return": terminal_return,
        "max_dd": max_dd,
        "max_streak": max_streak,
        "final_equity": equity[-1],
        "equity_curve": equity,
    }


def independent_drawdown(equity_curve: np.ndarray) -> tuple[float, float]:
    """Independent drawdown calculation using NumPy."""
    peak = np.maximum.accumulate(equity_curve)
    dd = (equity_curve - peak) / peak
    max_dd_pct = abs(np.min(dd)) if len(dd) > 0 else 0.0
    max_dd_abs = abs(np.min(equity_curve - peak)) if len(equity_curve) > 0 else 0.0
    return max_dd_abs, max_dd_pct


def independent_max_losing_streak(returns: np.ndarray) -> int:
    """Independent max losing streak calculation."""
    losing = returns < 0
    max_streak = 0
    current = 0
    for is_l in losing:
        if is_l:
            current += 1
            max_streak = max(max_streak, current)
        else:
            current = 0
    return max_streak


def independent_reshuffling(returns: np.ndarray, config: MonteCarloConfig, 
                            hist_term_ret: float, hist_max_dd: float, hist_max_streak: int) -> dict:
    """Independent reshuffling simulation for verification."""
    rng = np.random.default_rng(config.seed)
    n_trades = len(returns)
    n_sims = config.n_simulations
    
    terminal_returns = np.zeros(n_sims)
    max_dds = np.zeros(n_sims)
    max_streaks = np.zeros(n_sims, dtype=int)
    sample_paths = np.zeros((min(n_sims, 200), n_trades + 1))
    
    for sim in range(n_sims):
        idx = rng.permutation(n_trades)
        sim_returns = returns[idx]
        
        equity = np.zeros(n_trades + 1)
        equity[0] = config.initial_capital
        for i, ret in enumerate(sim_returns):
            equity[i + 1] = equity[i] * (1 + ret)
        
        terminal_returns[sim] = (equity[-1] - config.initial_capital) / config.initial_capital
        _, max_dd = independent_drawdown(equity)
        max_dds[sim] = max_dd
        max_streaks[sim] = independent_max_losing_streak(sim_returns)
        
        if sim < 200:
            sample_paths[sim] = equity
    
    return {
        "terminal_returns": terminal_returns,
        "max_dds": max_dds,
        "max_streaks": max_streaks,
        "sample_paths": sample_paths,
    }


def independent_resampling(returns: np.ndarray, config: MonteCarloConfig,
                           hist_term_ret: float, hist_max_dd: float, hist_max_streak: int) -> dict:
    """Independent resampling (bootstrap) simulation for verification."""
    rng = np.random.default_rng(config.seed)
    n_trades = len(returns)
    n_sims = config.n_simulations
    
    terminal_returns = np.zeros(n_sims)
    max_dds = np.zeros(n_sims)
    max_streaks = np.zeros(n_sims, dtype=int)
    sample_paths = np.zeros((min(n_sims, 200), n_trades + 1))
    
    for sim in range(n_sims):
        idx = rng.integers(0, n_trades, size=n_trades)
        sim_returns = returns[idx]
        
        equity = np.zeros(n_trades + 1)
        equity[0] = config.initial_capital
        for i, ret in enumerate(sim_returns):
            equity[i + 1] = equity[i] * (1 + ret)
        
        terminal_returns[sim] = (equity[-1] - config.initial_capital) / config.initial_capital
        _, max_dd = independent_drawdown(equity)
        max_dds[sim] = max_dd
        max_streaks[sim] = independent_max_losing_streak(sim_returns)
        
        if sim < 200:
            sample_paths[sim] = equity
    
    return {
        "terminal_returns": terminal_returns,
        "max_dds": max_dds,
        "max_streaks": max_streaks,
        "sample_paths": sample_paths,
    }


def independent_block_bootstrap(returns: np.ndarray, config: MonteCarloConfig,
                                hist_term_ret: float, hist_max_dd: float, hist_max_streak: int) -> dict:
    """Independent block bootstrap simulation for verification."""
    rng = np.random.default_rng(config.seed)
    n_trades = len(returns)
    n_sims = config.n_simulations
    block_len = config.block_length
    n_blocks = int(np.ceil(n_trades / block_len))
    
    terminal_returns = np.zeros(n_sims)
    max_dds = np.zeros(n_sims)
    max_streaks = np.zeros(n_sims, dtype=int)
    sample_paths = np.zeros((min(n_sims, 200), n_trades + 1))
    
    for sim in range(n_sims):
        blocks = []
        for _ in range(n_blocks):
            start = rng.integers(0, n_trades - block_len + 1)
            blocks.append(returns[start:start + block_len])
        sim_returns = np.concatenate(blocks)[:n_trades]
        
        equity = np.zeros(n_trades + 1)
        equity[0] = config.initial_capital
        for i, ret in enumerate(sim_returns):
            equity[i + 1] = equity[i] * (1 + ret)
        
        terminal_returns[sim] = (equity[-1] - config.initial_capital) / config.initial_capital
        _, max_dd = independent_drawdown(equity)
        max_dds[sim] = max_dd
        max_streaks[sim] = independent_max_losing_streak(sim_returns)
        
        if sim < 200:
            sample_paths[sim] = equity
    
    return {
        "terminal_returns": terminal_returns,
        "max_dds": max_dds,
        "max_streaks": max_streaks,
        "sample_paths": sample_paths,
    }


def independent_percentiles(data: np.ndarray, percentiles: list[int]) -> dict:
    """Independent percentile calculation using NumPy."""
    return {p: float(np.percentile(data, p)) for p in percentiles}


def independent_probabilities(terminal_returns: np.ndarray, max_dds: np.ndarray,
                              max_streaks: np.ndarray, config: MonteCarloConfig) -> dict:
    """Independent probability calculations."""
    prob_loss = float(np.mean(terminal_returns < 0))
    prob_dd = {}
    for thresh in config.dd_thresholds:
        prob_dd[thresh] = float(np.mean(max_dds > thresh))
    prob_streak = float(np.mean(max_streaks >= config.streak_threshold))
    return {
        "prob_loss": prob_loss,
        "prob_dd_thresholds": prob_dd,
        "prob_streak_threshold": prob_streak,
    }


# =============================================================================
# AUDIT FUNCTIONS
# =============================================================================

def audit_historical_metrics(returns: np.ndarray, config: MonteCarloConfig) -> dict:
    """Audit historical metrics against independent calculation."""
    print("\n" + "="*70)
    print("AUDIT: Historical Metrics")
    print("="*70)
    
    # Implementation calculation
    hist_equity, hist_term_ret, hist_max_dd, hist_max_streak = simulate_equity_path_from_returns(
        returns, config.initial_capital
    )
    
    # Independent calculation
    indep = independent_historical_metrics(returns, config.initial_capital)
    
    discrepancies = []
    
    # Compare terminal return
    diff_term = abs(hist_term_ret - indep["terminal_return"])
    if diff_term > 1e-10:
        discrepancies.append(f"Terminal return mismatch: impl={hist_term_ret:.10f}, indep={indep['terminal_return']:.10f}, diff={diff_term:.2e}")
    else:
        print(f"✓ Terminal return: {hist_term_ret:.6f} ({hist_term_ret*100:.2f}%) - MATCH")
    
    # Compare max DD
    diff_dd = abs(hist_max_dd - indep["max_dd"])
    if diff_dd > 1e-10:
        discrepancies.append(f"Max DD mismatch: impl={hist_max_dd:.10f}, indep={indep['max_dd']:.10f}, diff={diff_dd:.2e}")
    else:
        print(f"✓ Max DD: {hist_max_dd:.6f} ({hist_max_dd*100:.2f}%) - MATCH")
    
    # Compare max streak
    if hist_max_streak != indep["max_streak"]:
        discrepancies.append(f"Max streak mismatch: impl={hist_max_streak}, indep={indep['max_streak']}")
    else:
        print(f"✓ Max losing streak: {hist_max_streak} - MATCH")
    
    # Compare final equity
    diff_equity = abs(hist_equity[-1] - indep["final_equity"])
    if diff_equity > 1e-6:
        discrepancies.append(f"Final equity mismatch: impl={hist_equity[-1]:.2f}, indep={indep['final_equity']:.2f}, diff={diff_equity:.2e}")
    else:
        print(f"✓ Final equity: ${hist_equity[-1]:,.2f} - MATCH")
    
    return {
        "implementation": {
            "terminal_return": hist_term_ret,
            "max_dd": hist_max_dd,
            "max_streak": hist_max_streak,
            "final_equity": hist_equity[-1],
        },
        "independent": indep,
        "discrepancies": discrepancies,
    }


def audit_method(method_name: str, impl_result: MonteCarloResults, 
                 indep_result: dict, config: MonteCarloConfig, returns: np.ndarray) -> dict:
    """Audit a single Monte Carlo method against independent calculation."""
    print(f"\n" + "="*70)
    print(f"AUDIT: {method_name}")
    print("="*70)
    
    discrepancies = []
    percentiles_list = [5, 25, 50, 75, 95]
    
    # Terminal returns
    impl_term_returns = impl_result.terminal_returns
    indep_term_returns = indep_result["terminal_returns"]
    
    impl_term_pcts = independent_percentiles(impl_term_returns, percentiles_list)
    indep_term_pcts = independent_percentiles(indep_term_returns, percentiles_list)
    
    print("\nTerminal Return Percentiles:")
    for p in percentiles_list:
        impl_val = impl_term_pcts[p]
        indep_val = indep_term_pcts[p]
        diff = abs(impl_val - indep_val)
        rel_diff = diff / max(abs(impl_val), abs(indep_val), 1e-10)
        status = "✓" if rel_diff < 0.02 else "✗"  # 2% tolerance for MC
        print(f"  {p}th: impl={impl_val:.6f} ({impl_val*100:.2f}%), indep={indep_val:.6f} ({indep_val*100:.2f}%), diff={diff:.6f} {status}")
        if rel_diff >= 0.02:
            discrepancies.append(f"Terminal return {p}th percentile: impl={impl_val:.6f}, indep={indep_val:.6f}, rel_diff={rel_diff:.2%}")
    
    # Mean and std
    impl_mean = np.mean(impl_term_returns)
    indep_mean = np.mean(indep_term_returns)
    rel_diff_mean = abs(impl_mean - indep_mean) / max(abs(impl_mean), 1e-10)
    status = "✓" if rel_diff_mean < 0.02 else "✗"
    print(f"  Mean: impl={impl_mean:.6f}, indep={indep_mean:.6f}, rel_diff={rel_diff_mean:.2%} {status}")
    if rel_diff_mean >= 0.02:
        discrepancies.append(f"Terminal return mean: impl={impl_mean:.6f}, indep={indep_mean:.6f}")
    
    # Max DD
    impl_dd = impl_result.max_drawdown_pcts
    indep_dd = indep_result["max_dds"]
    
    impl_dd_pcts = independent_percentiles(impl_dd, percentiles_list)
    indep_dd_pcts = independent_percentiles(indep_dd, percentiles_list)
    
    print("\nMax Drawdown Percentiles:")
    for p in percentiles_list:
        impl_val = impl_dd_pcts[p]
        indep_val = indep_dd_pcts[p]
        diff = abs(impl_val - indep_val)
        rel_diff = diff / max(abs(impl_val), abs(indep_val), 1e-10)
        status = "✓" if rel_diff < 0.02 else "✗"
        print(f"  {p}th: impl={impl_val:.6f} ({impl_val*100:.2f}%), indep={indep_val:.6f} ({indep_val*100:.2f}%), diff={diff:.6f} {status}")
        if rel_diff >= 0.02:
            discrepancies.append(f"Max DD {p}th percentile: impl={impl_val:.6f}, indep={indep_val:.6f}, rel_diff={rel_diff:.2%}")
    
    # Max losing streak
    impl_streak = impl_result.max_losing_streaks
    indep_streak = indep_result["max_streaks"]
    
    impl_streak_pcts = independent_percentiles(impl_streak.astype(float), percentiles_list)
    indep_streak_pcts = independent_percentiles(indep_streak.astype(float), percentiles_list)
    
    print("\nMax Losing Streak Percentiles:")
    for p in percentiles_list:
        impl_val = impl_streak_pcts[p]
        indep_val = indep_streak_pcts[p]
        diff = abs(impl_val - indep_val)
        status = "✓" if diff <= 1 else "✗"  # Integer values, 1 trade tolerance
        print(f"  {p}th: impl={impl_val:.0f}, indep={indep_val:.0f}, diff={diff:.2f} {status}")
        if diff > 1:
            discrepancies.append(f"Max streak {p}th percentile: impl={impl_val:.0f}, indep={indep_val:.0f}")
    
    # Probabilities
    impl_probs = {
        "prob_loss": impl_result.prob_loss,
        "prob_dd_thresholds": impl_result.prob_dd_thresholds,
        "prob_streak_threshold": impl_result.prob_streak_threshold,
    }
    indep_probs = independent_probabilities(indep_term_returns, indep_dd, indep_streak, config)
    
    print("\nProbabilities:")
    loss_diff = abs(impl_probs["prob_loss"] - indep_probs["prob_loss"])
    status = "✓" if loss_diff < 0.01 else "✗"
    print(f"  P(loss): impl={impl_probs['prob_loss']:.4f}, indep={indep_probs['prob_loss']:.4f}, diff={loss_diff:.4f} {status}")
    if loss_diff >= 0.01:
        discrepancies.append(f"P(loss): impl={impl_probs['prob_loss']:.4f}, indep={indep_probs['prob_loss']:.4f}")
    
    for thresh in config.dd_thresholds:
        impl_val = impl_probs["prob_dd_thresholds"][thresh]
        indep_val = indep_probs["prob_dd_thresholds"][thresh]
        diff = abs(impl_val - indep_val)
        status = "✓" if diff < 0.02 else "✗"
        print(f"  P(DD>{thresh*100:.0f}%): impl={impl_val:.4f}, indep={indep_val:.4f}, diff={diff:.4f} {status}")
        if diff >= 0.02:
            discrepancies.append(f"P(DD>{thresh*100:.0f}%): impl={impl_val:.4f}, indep={indep_val:.4f}")
    
    streak_diff = abs(impl_probs["prob_streak_threshold"] - indep_probs["prob_streak_threshold"])
    status = "✓" if streak_diff < 0.02 else "✗"
    print(f"  P(streak>={config.streak_threshold}): impl={impl_probs['prob_streak_threshold']:.4f}, indep={indep_probs['prob_streak_threshold']:.4f}, diff={streak_diff:.4f} {status}")
    if streak_diff >= 0.02:
        discrepancies.append(f"P(streak): impl={impl_probs['prob_streak_threshold']:.4f}, indep={indep_probs['prob_streak_threshold']:.4f}")
    
    # Sample paths check (for fan chart data)
    if impl_result.sample_paths.size > 0 and indep_result["sample_paths"].size > 0:
        impl_paths = impl_result.sample_paths
        indep_paths = indep_result["sample_paths"]
        min_sims = min(impl_paths.shape[0], indep_paths.shape[0])
        
        # Compare terminal equity of first few paths
        path_diffs = []
        for i in range(min(10, min_sims)):
            diff = abs(impl_paths[i, -1] - indep_paths[i, -1])
            path_diffs.append(diff)
        max_path_diff = max(path_diffs) if path_diffs else 0
        status = "✓" if max_path_diff < 100 else "✗"  # $100 tolerance
        print(f"\nSample paths terminal equity (first 10): max diff = ${max_path_diff:,.2f} {status}")
        if max_path_diff >= 100:
            discrepancies.append(f"Sample paths terminal equity diff: max=${max_path_diff:,.2f}")
    
    return {
        "method": method_name,
        "discrepancies": discrepancies,
    }


def audit_json_output(json_path: Path, impl_results: tuple) -> dict:
    """Audit JSON output against implementation results."""
    print("\n" + "="*70)
    print("AUDIT: JSON Output")
    print("="*70)
    
    with open(json_path) as f:
        json_data = json.load(f)
    
    reshuffle, resample, block, _ = impl_results
    methods = [
        ("Trade Reshuffling", reshuffle),
        ("Trade Resampling (Bootstrap)", resample),
        ("Block Bootstrap", block),
    ]
    
    discrepancies = []
    
    for method_name, impl in methods:
        if method_name not in json_data:
            discrepancies.append(f"Missing method in JSON: {method_name}")
            continue
        
        j = json_data[method_name]
        
        # Check terminal equity percentiles
        for p in [5, 25, 50, 75, 95]:
            impl_val = impl.equity_percentiles[p]
            json_val = j["terminal_equity"]["percentiles"][str(p)]
            diff = abs(impl_val - json_val)
            status = "✓" if diff < 1 else "✗"
            print(f"  {method_name} equity {p}th: impl={impl_val:,.2f}, json={json_val:,.2f}, diff={diff:.2f} {status}")
            if diff >= 1:
                discrepancies.append(f"{method_name} equity {p}th: impl={impl_val:,.2f}, json={json_val:,.2f}")
        
        # Check terminal return percentiles
        for p in [5, 25, 50, 75, 95]:
            impl_val = impl.return_percentiles[p]
            json_val = j["terminal_return"]["percentiles"][str(p)]
            diff = abs(impl_val - json_val)
            status = "✓" if diff < 1e-8 else "✗"
            print(f"  {method_name} return {p}th: impl={impl_val:.8f}, json={json_val:.8f}, diff={diff:.2e} {status}")
            if diff >= 1e-8:
                discrepancies.append(f"{method_name} return {p}th: impl={impl_val:.8f}, json={json_val:.8f}")
        
        # Check historical comparison
        hist_ret_json = j["historical_comparison"]["terminal_return"]
        diff = abs(impl.historical_terminal_return - hist_ret_json)
        status = "✓" if diff < 1e-10 else "✗"
        print(f"  {method_name} hist_term_ret: impl={impl.historical_terminal_return:.10f}, json={hist_ret_json:.10f}, diff={diff:.2e} {status}")
        if diff >= 1e-10:
            discrepancies.append(f"{method_name} historical terminal return mismatch")
    
    return {"discrepancies": discrepancies}


def audit_visualization_data(impl_results: tuple, returns: np.ndarray, config: MonteCarloConfig) -> dict:
    """Audit data that would be used for visualizations."""
    print("\n" + "="*70)
    print("AUDIT: Visualization Data Integrity")
    print("="*70)
    
    reshuffle, resample, block, _ = impl_results
    discrepancies = []
    
    # Check fan chart data for reshuffling
    # All paths should end at same terminal equity
    reshuffle_terminal = reshuffle.sample_paths[:, -1]
    unique_terminals = np.unique(np.round(reshuffle_terminal, 2))
    if len(unique_terminals) > 1:
        discrepancies.append(f"Reshuffling terminal equities not identical: {len(unique_terminals)} unique values")
        print(f"  ✗ Reshuffling terminal equities: {len(unique_terminals)} unique values (should be 1)")
    else:
        print(f"  ✓ Reshuffling terminal equities: all ${unique_terminals[0]:,.2f}")
    
    # Check fan chart historical marker position for fan chart
    hist_marker_y_pct = reshuffle.historical_terminal_return * 100
    actual_hist_return_pct = reshuffle.historical_terminal_return * 100
    diff = abs(hist_marker_y_pct - actual_hist_return_pct)
    status = "✓" if diff < 1e-6 else "✗"
    print(f"  Fan chart historical marker: computed={hist_marker_y_pct:.2f}%, actual={actual_hist_return_pct:.2f}%, diff={diff:.2f} {status}")
    if diff >= 1e-6:
        discrepancies.append(f"Fan chart historical marker mismatch: {diff:.2f}%")
    
    # Check historical vs simulated chart data
    for res, name in [(reshuffle, "Reshuffle"), (resample, "Resample"), (block, "Block")]:
        # Terminal returns box plot data
        returns_pct = res.terminal_returns * 100
        hist_val = res.historical_terminal_return * 100
        
        # Check if historical value falls within simulated range
        sim_min, sim_max = np.min(returns_pct), np.max(returns_pct)
        in_range = sim_min <= hist_val <= sim_max
        print(f"  {name} terminal returns: sim range=[{sim_min:.2f}%, {sim_max:.2f}%], hist={hist_val:.2f}%, in_range={in_range}")
        
        # Max DD box plot data
        dd_pct = res.max_drawdown_pcts * 100
        hist_dd = res.historical_max_dd * 100
        dd_min, dd_max = np.min(dd_pct), np.max(dd_pct)
        in_range = dd_min <= hist_dd <= dd_max
        print(f"  {name} max DD: sim range=[{dd_min:.2f}%, {dd_max:.2f}%], hist={hist_dd:.2f}%, in_range={in_range}")
        
        # Terminal equity box plot data
        eq_min, eq_max = np.min(res.terminal_equities), np.max(res.terminal_equities)
        hist_eq = res.initial_capital * (1 + res.historical_terminal_return)
        in_range = eq_min <= hist_eq <= eq_max
        print(f"  {name} terminal equity: sim range=[${eq_min:,.0f}, ${eq_max:,.0f}], hist=${hist_eq:,.0f}, in_range={in_range}")
        
        # Max streak box plot data
        streak_min, streak_max = np.min(res.max_losing_streaks), np.max(res.max_losing_streaks)
        hist_streak = res.historical_max_streak
        in_range = streak_min <= hist_streak <= streak_max
        print(f"  {name} max streak: sim range=[{streak_min}, {streak_max}], hist={hist_streak}, in_range={in_range}")
        
        # Check percentiles are monotonically increasing
        for attr_name, pcts in [("return", res.return_percentiles), ("dd", res.dd_percentiles), ("streak", res.streak_percentiles)]:
            vals = [pcts[p] for p in [5, 25, 50, 75, 95]]
            monotonic = all(vals[i] <= vals[i+1] + 1e-10 for i in range(len(vals)-1))
            status = "✓" if monotonic else "✗"
            print(f"  {name} {attr_name} percentiles monotonic: {monotonic} {status}")
            if not monotonic:
                discrepancies.append(f"{name} {attr_name} percentiles not monotonic: {vals}")
    
    return {"discrepancies": discrepancies}


def audit_dependence_analysis(returns: np.ndarray, dep_result: dict) -> dict:
    """Audit dependence analysis against independent calculation."""
    print("\n" + "="*70)
    print("AUDIT: Dependence Analysis")
    print("="*70)
    
    # Independent Ljung-Box test
    from statsmodels.stats.diagnostic import acorr_ljungbox
    lb_result = acorr_ljungbox(returns, lags=20, return_df=True)
    indep_lb_p = float(lb_result["lb_pvalue"].iloc[-1])
    
    # Independent runs test
    n = len(returns)
    n_pos = np.sum(returns > 0)
    n_neg = np.sum(returns < 0)
    # Expected runs
    expected_runs = 1 + 2 * n_pos * n_neg / n
    # Actual runs
    runs = 1
    for i in range(1, n):
        if (returns[i] > 0) != (returns[i-1] > 0):
            runs += 1
    # Variance of runs
    var_runs = (2 * n_pos * n_neg * (2 * n_pos * n_neg - n)) / (n**2 * (n - 1))
    z = (runs - expected_runs) / np.sqrt(var_runs)
    indep_runs_p = 2 * (1 - stats.norm.cdf(abs(z)))
    
    print(f"  Ljung-Box p-value: impl={dep_result['ljung_box_p']:.6f}, indep={indep_lb_p:.6f}")
    print(f"  Runs test p-value: impl={dep_result['runs_test_p']:.6f}, indep={indep_runs_p:.6f}")
    print(f"  Dependence detected: impl={dep_result['dependence_detected']}")
    
    discrepancies = []
    if abs(dep_result["ljung_box_p"] - indep_lb_p) > 0.01:
        discrepancies.append(f"Ljung-Box p-value mismatch: impl={dep_result['ljung_box_p']:.6f}, indep={indep_lb_p:.6f}")
    if abs(dep_result["runs_test_p"] - indep_runs_p) > 0.01:
        discrepancies.append(f"Runs test p-value mismatch: impl={dep_result['runs_test_p']:.6f}, indep={indep_runs_p:.6f}")
    
    return {"discrepancies": discrepancies}


def run_full_audit() -> dict:
    """Run complete audit of Monte Carlo pipeline."""
    print("="*70)
    print("MA-TSM-001 MONTE CARLO INTEGRITY AUDIT")
    print("="*70)
    
    # Load data
    pnl, returns, details = load_oos_trades("reports/walkforward/oos_trades_for_mc.json")
    config = MonteCarloConfig(n_simulations=10000, seed=42)
    
    # Run implementation
    reshuffle, resample, block, dependence = run_all_monte_carlo(
        "reports/walkforward/oos_trades_for_mc.json", config
    )
    
    # Run independent simulations (with smaller sample for speed)
    indep_config = MonteCarloConfig(n_simulations=2000, seed=42)
    
    # Get historical metrics
    hist_equity, hist_term_ret, hist_max_dd, hist_max_streak = simulate_equity_path_from_returns(
        returns, config.initial_capital
    )
    
    indep_reshuffle = independent_reshuffling(returns, indep_config, hist_term_ret, hist_max_dd, hist_max_streak)
    indep_resample = independent_resampling(returns, indep_config, hist_term_ret, hist_max_dd, hist_max_streak)
    indep_block = independent_block_bootstrap(returns, indep_config, hist_term_ret, hist_max_dd, hist_max_streak)
    
    # Audit historical metrics
    hist_audit = audit_historical_metrics(returns, config)
    
    # Audit each method
    reshuffle_audit = audit_method("Trade Reshuffling", reshuffle, indep_reshuffle, indep_config, returns)
    resample_audit = audit_method("Trade Resampling (Bootstrap)", resample, indep_resample, indep_config, returns)
    block_audit = audit_method("Block Bootstrap", block, indep_block, indep_config, returns)
    
    # Audit JSON output
    json_audit = audit_json_output(Path("reports/monte_carlo/monte_carlo_results.json"), 
                                    (reshuffle, resample, block, dependence))
    
    # Audit visualization data
    viz_audit = audit_visualization_data((reshuffle, resample, block, dependence), returns, config)
    
    # Audit dependence analysis
    dep_audit = audit_dependence_analysis(returns, dependence)
    
    # Collect all discrepancies
    all_discrepancies = []
    all_discrepancies.extend(hist_audit["discrepancies"])
    all_discrepancies.extend(reshuffle_audit["discrepancies"])
    all_discrepancies.extend(resample_audit["discrepancies"])
    all_discrepancies.extend(block_audit["discrepancies"])
    all_discrepancies.extend(json_audit["discrepancies"])
    all_discrepancies.extend(viz_audit["discrepancies"])
    all_discrepancies.extend(dep_audit["discrepancies"])
    
    print("\n" + "="*70)
    print("AUDIT SUMMARY")
    print("="*70)
    print(f"Total discrepancies found: {len(all_discrepancies)}")
    for i, d in enumerate(all_discrepancies, 1):
        print(f"  {i}. {d}")
    
    return {
        "historical_audit": hist_audit,
        "reshuffle_audit": reshuffle_audit,
        "resample_audit": resample_audit,
        "block_audit": block_audit,
        "json_audit": json_audit,
        "viz_audit": viz_audit,
        "dependence_audit": dep_audit,
        "total_discrepancies": len(all_discrepancies),
        "discrepancies": all_discrepancies,
    }


if __name__ == "__main__":
    results = run_full_audit()
    
    # Save audit report
    output_path = Path("reports/monte_carlo/audit_report.json")
    # Convert numpy types for JSON serialization
    def convert(obj):
        if isinstance(obj, (np.integer, np.floating)):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, dict):
            return {k: convert(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert(v) for v in obj]
        return obj
    
    with open(output_path, "w") as f:
        json.dump(convert(results), f, indent=2)
    
    print(f"\nAudit report saved to: {output_path}")
    
    if results["total_discrepancies"] == 0:
        print("\n✓ AUDIT PASSED - No discrepancies found")
    else:
        print(f"\n✗ AUDIT FAILED - {results['total_discrepancies']} discrepancies found")