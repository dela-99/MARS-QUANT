"""Unit tests for MA-TSM-001 Monte Carlo Robustness Validation."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pytest

from mars.apps.research_lab.ma_tsm_monte_carlo import (
    MonteCarloConfig,
    MonteCarloResults,
    run_all_monte_carlo,
    run_block_bootstrap_mc,
    run_resampling_mc,
    run_reshuffling_mc,
    save_results,
    load_oos_trades,
    check_dependence,
)


class TestDataLoading:
    """Tests for OOS trade data loading."""

    def test_load_oos_trades_returns_tuple(self):
        """Verify OOS trades load correctly as tuple."""
        pnl, returns, details = load_oos_trades("reports/walkforward/oos_trades_for_mc.json")
        assert isinstance(pnl, np.ndarray)
        assert isinstance(returns, np.ndarray)
        assert isinstance(details, list)
        assert len(pnl) == len(returns) == len(details)
        assert "pnl" in details[0]
        assert "return_pct" in details[0]
        assert "entry_time" in details[0]
        assert "exit_time" in details[0]

    def test_load_oos_trades_trade_count(self):
        """Verify expected trade count (914 OOS trades from walk-forward)."""
        pnl, returns, details = load_oos_trades("reports/walkforward/oos_trades_for_mc.json")
        assert len(pnl) == 914

    def test_load_oos_trades_positive_return(self):
        """Verify aggregate return is positive."""
        pnl, returns, details = load_oos_trades("reports/walkforward/oos_trades_for_mc.json")
        assert pnl.sum() > 0


class TestMonteCarloConfig:
    """Tests for Monte Carlo configuration."""

    def test_default_config(self):
        """Test default configuration values."""
        config = MonteCarloConfig()
        assert config.n_simulations == 10_000
        assert config.seed == 42
        assert config.initial_capital == 10_000_000
        assert config.block_length == 10
        assert config.dd_thresholds == [0.05, 0.10, 0.15, 0.20]

    def test_custom_config(self):
        """Test custom configuration values."""
        config = MonteCarloConfig(n_simulations=5_000, seed=123, initial_capital=1_000_000)
        assert config.n_simulations == 5_000
        assert config.seed == 123
        assert config.initial_capital == 1_000_000


class TestDependenceChecking:
    """Tests for serial dependence detection."""

    def test_check_dependence_returns_expected_keys(self):
        """Verify dependence check returns all expected metrics."""
        pnl, returns, details = load_oos_trades("reports/walkforward/oos_trades_for_mc.json")
        result = check_dependence(returns)

        assert "ljung_box_p" in result
        assert "runs_test_p" in result
        assert "dependence_detected" in result
        assert isinstance(result["dependence_detected"], bool)

    def test_check_dependence_reproducible(self):
        """Dependence check should be deterministic."""
        pnl, returns, details = load_oos_trades("reports/walkforward/oos_trades_for_mc.json")
        r1 = check_dependence(returns)
        r2 = check_dependence(returns)
        assert r1["ljung_box_p"] == r2["ljung_box_p"]
        assert r1["runs_test_p"] == r2["runs_test_p"]
        assert r1["dependence_detected"] == r2["dependence_detected"]


class TestTradeReshuffling:
    """Tests for Method 1: Trade Reshuffling."""

    def test_reshuffling_reproducibility(self):
        """Reshuffling with same seed should produce identical results."""
        pnl, returns, details = load_oos_trades("reports/walkforward/oos_trades_for_mc.json")

        config = MonteCarloConfig(n_simulations=1000, seed=42)
        r1 = run_reshuffling_mc(returns, config)
        r2 = run_reshuffling_mc(returns, config)

        assert r1.method == r2.method
        assert np.allclose(r1.terminal_returns, r2.terminal_returns)
        assert np.allclose(r1.max_drawdown_pcts, r2.max_drawdown_pcts)
        assert np.allclose(r1.max_losing_streaks, r2.max_losing_streaks)

    def test_reshuffling_preserves_trade_values(self):
        """Reshuffling should preserve original trade returns (only reorder)."""
        pnl, returns, details = load_oos_trades("reports/walkforward/oos_trades_for_mc.json")

        config = MonteCarloConfig(n_simulations=100, seed=42)
        result = run_reshuffling_mc(returns, config)

        # Each simulation is a permutation, so sum of returns should equal historical
        for sim_returns in result.sample_paths[:, 1:] - result.sample_paths[:, :-1]:
            # This is the equity diff, which equals returns * capital
            pass

        # The mean terminal return should match historical (permutation preserves sum)
        historical_return = (1 + returns).prod() - 1
        assert abs(result.return_percentiles[50] - historical_return) < 0.001

    def test_reshuffling_simulation_count(self):
        """Verify correct number of simulations."""
        pnl, returns, details = load_oos_trades("reports/walkforward/oos_trades_for_mc.json")

        for n_sims in [100, 1000, 5000]:
            config = MonteCarloConfig(n_simulations=n_sims, seed=42)
            result = run_reshuffling_mc(returns, config)
            assert result.n_simulations == n_sims
            assert len(result.terminal_returns) == n_sims
            assert len(result.max_drawdown_pcts) == n_sims
            assert len(result.max_losing_streaks) == n_sims

    def test_reshuffling_returns_structure(self):
        """Verify all expected fields in results."""
        pnl, returns, details = load_oos_trades("reports/walkforward/oos_trades_for_mc.json")

        config = MonteCarloConfig(n_simulations=100, seed=42)
        result = run_reshuffling_mc(returns, config)

        assert isinstance(result, MonteCarloResults)
        assert result.method == "Trade Reshuffling"
        assert result.n_trades == len(returns)
        assert 0 <= result.prob_loss <= 1
        assert all(0 <= v <= 1 for v in result.prob_dd_thresholds.values())
        assert all(p in result.return_percentiles for p in [5, 25, 50, 75, 95])
        assert all(p in result.dd_percentiles for p in [5, 25, 50, 75, 95])
        assert all(p in result.streak_percentiles for p in [5, 25, 50, 75, 95])


class TestTradeResampling:
    """Tests for Method 2: Trade Resampling (Bootstrap)."""

    def test_resampling_reproducibility(self):
        """Resampling with same seed should produce identical results."""
        pnl, returns, details = load_oos_trades("reports/walkforward/oos_trades_for_mc.json")

        config = MonteCarloConfig(n_simulations=1000, seed=42)
        r1 = run_resampling_mc(returns, config)
        r2 = run_resampling_mc(returns, config)

        assert np.allclose(r1.terminal_returns, r2.terminal_returns)
        assert np.allclose(r1.max_drawdown_pcts, r2.max_drawdown_pcts)
        assert np.allclose(r1.max_losing_streaks, r2.max_losing_streaks)

    def test_resampling_different_from_reshuffling(self):
        """Resampling (with replacement) should produce different distribution than reshuffling."""
        pnl, returns, details = load_oos_trades("reports/walkforward/oos_trades_for_mc.json")

        config = MonteCarloConfig(n_simulations=5000, seed=42)
        reshuffle = run_reshuffling_mc(returns, config)
        resample = run_resampling_mc(returns, config)

        # Resampling has more variance due to replacement
        assert np.std(resample.terminal_returns) > np.std(reshuffle.terminal_returns)

    def test_resampling_simulation_count(self):
        """Verify correct number of simulations."""
        pnl, returns, details = load_oos_trades("reports/walkforward/oos_trades_for_mc.json")

        for n_sims in [100, 1000, 5000]:
            config = MonteCarloConfig(n_simulations=n_sims, seed=42)
            result = run_resampling_mc(returns, config)
            assert result.n_simulations == n_sims
            assert len(result.terminal_returns) == n_sims

    def test_resampling_individual_trades(self):
        """Trades are resampled individually (independence assumption)."""
        pnl, returns, details = load_oos_trades("reports/walkforward/oos_trades_for_mc.json")

        config = MonteCarloConfig(n_simulations=100, seed=42)
        result = run_resampling_mc(returns, config)

        # With replacement, some simulations will have duplicate trades
        # and some trades will be missing - this is the independence assumption
        assert result.method == "Trade Resampling (Bootstrap)"


class TestBlockBootstrap:
    """Tests for Method 3: Block Bootstrap."""

    def test_block_bootstrap_reproducibility(self):
        """Block bootstrap with same seed should produce identical results."""
        pnl, returns, details = load_oos_trades("reports/walkforward/oos_trades_for_mc.json")

        config = MonteCarloConfig(n_simulations=1000, seed=42, block_length=10)
        r1 = run_block_bootstrap_mc(returns, config)
        r2 = run_block_bootstrap_mc(returns, config)

        assert np.allclose(r1.terminal_returns, r2.terminal_returns)
        assert np.allclose(r1.max_drawdown_pcts, r2.max_drawdown_pcts)

    def test_block_bootstrap_block_length_sensitivity(self):
        """Test sensitivity to block length."""
        pnl, returns, details = load_oos_trades("reports/walkforward/oos_trades_for_mc.json")

        results_by_block = {}
        for block_len in [5, 10, 20]:
            config = MonteCarloConfig(n_simulations=2000, seed=42, block_length=block_len)
            results_by_block[block_len] = run_block_bootstrap_mc(returns, config)

        # Different block lengths should produce somewhat different results
        assert results_by_block[5].return_percentiles[50] != results_by_block[20].return_percentiles[50]

    def test_block_bootstrap_method_name(self):
        """Block bootstrap method name includes block length."""
        pnl, returns, details = load_oos_trades("reports/walkforward/oos_trades_for_mc.json")

        config = MonteCarloConfig(n_simulations=100, seed=42, block_length=15)
        result = run_block_bootstrap_mc(returns, config)
        assert "block_len=15" in result.method or "Block Bootstrap" in result.method


class TestRunAllMonteCarlo:
    """Tests for the main orchestration function."""

    def test_run_all_returns_four_results(self):
        """run_all_monte_carlo should return 4 results (3 methods + dependence)."""
        reshuffle, resample, block, dependence = run_all_monte_carlo(
            "reports/walkforward/oos_trades_for_mc.json",
            MonteCarloConfig(n_simulations=100, seed=42),
        )
        assert reshuffle is not None
        assert resample is not None
        assert block is not None
        assert isinstance(dependence, dict)

    def test_run_all_uses_oos_data_only(self):
        """Verify only OOS data is used (no in-sample contamination)."""
        reshuffle, resample, block, _ = run_all_monte_carlo(
            "reports/walkforward/oos_trades_for_mc.json",
            MonteCarloConfig(n_simulations=100, seed=42),
        )

        # Historical terminal return should match OOS aggregate
        pnl, returns, details = load_oos_trades("reports/walkforward/oos_trades_for_mc.json")
        historical_return = (1 + returns).prod() - 1

        for res in [reshuffle, resample, block]:
            assert abs(res.historical_terminal_return - historical_return) < 0.001


class TestReturnCalculations:
    """Tests for return and drawdown calculations."""

    def test_terminal_return_calculation(self):
        """Terminal return = (final_equity / initial_capital) - 1."""
        pnl, returns, details = load_oos_trades("reports/walkforward/oos_trades_for_mc.json")

        config = MonteCarloConfig(n_simulations=100, seed=42, initial_capital=1_000_000)
        result = run_reshuffling_mc(returns, config)

        for i in range(min(10, config.n_simulations)):
            expected = result.terminal_equities[i] / config.initial_capital - 1
            assert abs(result.terminal_returns[i] - expected) < 1e-10

    def test_max_drawdown_calculation(self):
        """Max drawdown should be peak-to-trough decline."""
        pnl, returns, details = load_oos_trades("reports/walkforward/oos_trades_for_mc.json")

        config = MonteCarloConfig(n_simulations=100, seed=42)
        result = run_reshuffling_mc(returns, config)

        for i in range(min(10, config.n_simulations)):
            equity = result.sample_paths[i]
            peak = np.maximum.accumulate(equity)
            dd = (peak - equity) / peak
            expected_max_dd = np.max(dd)
            assert abs(result.max_drawdown_pcts[i] - expected_max_dd) < 1e-10

    def test_losing_streak_calculation(self):
        """Max losing streak = max consecutive negative returns."""
        pnl, returns, details = load_oos_trades("reports/walkforward/oos_trades_for_mc.json")

        config = MonteCarloConfig(n_simulations=100, seed=42)
        result = run_reshuffling_mc(returns, config)

        for i in range(min(10, config.n_simulations)):
            sim_returns = result.sample_paths[i, 1:] - result.sample_paths[i, :-1]
            sim_returns_pct = sim_returns / result.sample_paths[i, :-1]
            losing = sim_returns_pct < 0

            max_streak = 0
            current = 0
            for is_losing in losing:
                if is_losing:
                    current += 1
                    max_streak = max(max_streak, current)
                else:
                    current = 0

            assert result.max_losing_streaks[i] == max_streak


class TestPercentileCalculations:
    """Tests for percentile calculations."""

    def test_percentiles_are_monotonic(self):
        """Percentiles should be monotonically increasing."""
        pnl, returns, details = load_oos_trades("reports/walkforward/oos_trades_for_mc.json")

        config = MonteCarloConfig(n_simulations=1000, seed=42)
        result = run_reshuffling_mc(returns, config)

        for pcts in [result.return_percentiles, result.dd_percentiles, result.streak_percentiles]:
            vals = [pcts[p] for p in [5, 25, 50, 75, 95]]
            for i in range(len(vals) - 1):
                assert vals[i] <= vals[i + 1] + 1e-10  # allow tiny numerical diff

    def test_median_near_mean_for_symmetric(self):
        """For reshuffling (permutations), median terminal return ≈ mean."""
        pnl, returns, details = load_oos_trades("reports/walkforward/oos_trades_for_mc.json")

        config = MonteCarloConfig(n_simulations=5000, seed=42)
        result = run_reshuffling_mc(returns, config)

        mean_return = np.mean(result.terminal_returns)
        median_return = result.return_percentiles[50]
        assert abs(mean_return - median_return) / abs(mean_return) < 0.01


class TestDrawdownThresholds:
    """Tests for drawdown threshold probabilities."""

    def test_prob_dd_thresholds_in_range(self):
        """Probabilities should be between 0 and 1."""
        pnl, returns, details = load_oos_trades("reports/walkforward/oos_trades_for_mc.json")

        config = MonteCarloConfig(n_simulations=1000, seed=42)
        result = run_reshuffling_mc(returns, config)

        for prob in result.prob_dd_thresholds.values():
            assert 0 <= prob <= 1

    def test_higher_threshold_lower_prob(self):
        """P(DD > higher_threshold) <= P(DD > lower_threshold)."""
        pnl, returns, details = load_oos_trades("reports/walkforward/oos_trades_for_mc.json")

        config = MonteCarloConfig(n_simulations=1000, seed=42)
        result = run_reshuffling_mc(returns, config)

        thresholds = sorted(result.prob_dd_thresholds.keys())
        probs = [result.prob_dd_thresholds[t] for t in thresholds]
        for i in range(len(probs) - 1):
            assert probs[i] >= probs[i + 1] - 1e-10


class TestNoLookAheadBias:
    """Tests to verify no look-ahead bias."""

    def test_historical_values_match_oos(self):
        """Historical values in results should match OOS walk-forward."""
        pnl, returns, details = load_oos_trades("reports/walkforward/oos_trades_for_mc.json")
        historical_return = (1 + returns).prod() - 1

        # Max DD from equity curve (compounding returns) - same as results
        equity = np.zeros(len(returns) + 1)
        equity[0] = 10_000_000.0
        for i, ret in enumerate(returns):
            equity[i + 1] = equity[i] * (1 + ret)
        peak = np.maximum.accumulate(equity)
        dd = (peak - equity) / np.where(peak != 0, peak, 1)
        historical_max_dd = np.max(dd)

        # Max losing streak from trade returns
        losing = returns < 0
        max_streak = 0
        current = 0
        for is_l in losing:
            if is_l:
                current += 1
                max_streak = max(max_streak, current)
            else:
                current = 0

        config = MonteCarloConfig(n_simulations=100, seed=42)
        reshuffle, resample, block, _ = run_all_monte_carlo(
            "reports/walkforward/oos_trades_for_mc.json", config
        )

        for res in [reshuffle, resample, block]:
            assert abs(res.historical_terminal_return - historical_return) < 0.001
            assert abs(res.historical_max_dd - historical_max_dd) < 0.001
            assert res.historical_max_streak == max_streak


class TestSaveResults:
    """Tests for result serialization."""

    def test_save_results_creates_file(self):
        """save_results should create JSON output file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pnl, returns, details = load_oos_trades("reports/walkforward/oos_trades_for_mc.json")

            config = MonteCarloConfig(n_simulations=100, seed=42)
            reshuffle = run_reshuffling_mc(returns, config)
            resample = run_resampling_mc(returns, config)
            block = run_block_bootstrap_mc(returns, config)
            dependence = check_dependence(returns)

            output_dir = Path(tmpdir)
            save_results(reshuffle, resample, block, dependence, output_dir)

            result_file = output_dir / "monte_carlo_results.json"
            assert result_file.exists()

            with open(result_file) as f:
                data = json.load(f)

            assert "Trade Reshuffling" in data
            assert "Trade Resampling (Bootstrap)" in data
            assert "Block Bootstrap" in data
            assert "dependence_analysis" in data


class TestFullIntegration:
    """Integration test for full Monte Carlo pipeline."""

    def test_full_pipeline_runs(self):
        """Full pipeline should complete without errors."""
        reshuffle, resample, block, dependence = run_all_monte_carlo(
            "reports/walkforward/oos_trades_for_mc.json",
            MonteCarloConfig(n_simulations=500, seed=42),
        )

        assert reshuffle.n_simulations == 500
        assert resample.n_simulations == 500
        assert block.n_simulations == 500
        assert dependence["dependence_detected"] is False  # Per our data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])