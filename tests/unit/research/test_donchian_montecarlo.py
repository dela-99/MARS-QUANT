"""Unit tests for DONCHIAN-001 Monte Carlo robustness analysis."""
import numpy as np
import pytest
from mars.apps.research_lab.donchian_montecarlo import (
    TradeSequence,
    MonteCarloConfig,
    SimulationResults,
    load_oos_trades,
    compute_equity_curve,
    compute_max_drawdown,
    compute_sharpe,
    compute_profit_factor,
    compute_max_losing_streak,
    compute_worst_trade,
    compute_autocorrelation,
    simulate_equity_metrics,
    run_iid_bootstrap,
    run_randomized_sequence,
    run_block_bootstrap,
    run_monte_carlo_analysis,
)


class TestTradeSequence:
    """Tests for TradeSequence dataclass."""

    def test_trade_sequence_creation(self):
        pnl = np.array([100, -50, 200, 30])  # 3 positive, 1 negative
        returns = np.array([0.01, -0.005, 0.02, 0.003])
        timestamps = np.array([1, 2, 3, 4], dtype='datetime64[ns]')
        window_ids = np.array([1, 1, 2, 2])
        
        trades = TradeSequence(pnl=pnl, returns=returns, timestamps=timestamps, window_ids=window_ids)
        
        assert trades.n_trades == 4
        assert trades.expectancy == np.mean(pnl)
        assert trades.win_rate == 0.75  # 3 of 4 positive

    def test_trade_sequence_all_losing(self):
        pnl = np.array([-100, -50, -200])
        returns = np.array([-0.01, -0.005, -0.02])
        timestamps = np.array([1, 2, 3], dtype='datetime64[ns]')
        window_ids = np.array([1, 1, 1])
        
        trades = TradeSequence(pnl=pnl, returns=returns, timestamps=timestamps, window_ids=window_ids)
        
        assert trades.expectancy < 0
        assert trades.win_rate == 0.0


class TestMonteCarloConfig:
    """Tests for MonteCarloConfig."""

    def test_default_config(self):
        config = MonteCarloConfig()
        assert config.n_simulations == 10_000
        assert config.seed == 42
        assert config.block_length == 10
        assert config.capital == 100_000
        assert config.confidence_levels == (0.05, 0.25, 0.5, 0.75, 0.95)

    def test_custom_config(self):
        config = MonteCarloConfig(n_simulations=1000, seed=123, block_length=5, capital=50_000)
        assert config.n_simulations == 1000
        assert config.seed == 123
        assert config.block_length == 5
        assert config.capital == 50_000


class TestUtilityFunctions:
    """Tests for utility functions."""

    def test_compute_equity_curve(self):
        pnl = np.array([100, -50, 200, -30])
        capital = 1000
        equity = compute_equity_curve(pnl, capital)
        
        assert len(equity) == 4
        assert equity[0] == 1100
        assert equity[-1] == 1220

    def test_compute_max_drawdown(self):
        # Equity curve with clear peak and trough
        equity = np.array([1000, 1100, 1050, 1200, 1000, 1300])
        dd = compute_max_drawdown(equity)
        
        # Max DD from 1200 to 1000 = -16.67%
        assert -0.17 < dd < -0.16

    def test_compute_max_drawdown_no_drawdown(self):
        equity = np.array([1000, 1100, 1200, 1300])
        dd = compute_max_drawdown(equity)
        assert dd == 0.0

    def test_compute_profit_factor(self):
        pnl = np.array([100, 200, -50, -30, 150])
        pf = compute_profit_factor(pnl)
        
        gross_profit = 100 + 200 + 150  # 450
        gross_loss = 50 + 30  # 80
        expected = 450 / 80  # 5.625
        assert abs(pf - expected) < 1e-6

    def test_compute_profit_factor_no_losses(self):
        pnl = np.array([100, 200, 150])
        pf = compute_profit_factor(pnl)
        assert pf == np.inf

    def test_compute_profit_factor_no_wins(self):
        pnl = np.array([-100, -200, -50])
        pf = compute_profit_factor(pnl)
        assert pf == 0.0

    def test_compute_max_losing_streak(self):
        pnl = np.array([100, -50, -30, 200, -10, -20, -30, 50])
        streak = compute_max_losing_streak(pnl)
        assert streak == 3  # -10, -20, -30

    def test_compute_max_losing_streak_all_wins(self):
        pnl = np.array([100, 200, 300])
        streak = compute_max_losing_streak(pnl)
        assert streak == 0

    def test_compute_max_losing_streak_all_losses(self):
        pnl = np.array([-100, -200, -50])
        streak = compute_max_losing_streak(pnl)
        assert streak == 3

    def test_compute_worst_trade(self):
        pnl = np.array([100, -500, 200, -100])
        worst = compute_worst_trade(pnl)
        assert worst == -500

    def test_compute_autocorrelation(self):
        # Create a TradeSequence with known lag-1 autocorrelation
        np.random.seed(42)
        n = 1000
        x = np.random.randn(n)
        # Create AR(1) process with phi=0.5
        y = np.zeros(n)
        y[0] = x[0]
        for i in range(1, n):
            y[i] = 0.5 * y[i-1] + x[i]
        
        pnl = y * 100  # Convert to PnL
        returns = y / 100  # Returns as fraction
        # Use hourly timestamps to avoid day overflow
        timestamps = np.array([np.datetime64('2020-01-01') + np.timedelta64(i, 'h') for i in range(n)])
        window_ids = np.ones(n, dtype=int)
        trades = TradeSequence(pnl=pnl, returns=returns, timestamps=timestamps, window_ids=window_ids)
        
        acf = compute_autocorrelation(trades, max_lag=5)
        # Lag-1 ACF should be ~0.5
        assert 0.4 < acf[1] < 0.6

    def test_simulate_equity_metrics(self):
        pnl = np.array([100, -50, 200, -30, 150, -20])
        timestamps = np.array(['2020-01-01', '2020-01-02', '2020-01-03', '2020-01-04', '2020-01-05', '2020-01-06'], dtype='datetime64[D]')
        capital = 1000
        
        metrics = simulate_equity_metrics(pnl, timestamps, capital)
        
        assert 'cumulative_return' in metrics
        assert 'max_drawdown' in metrics
        assert 'sharpe' in metrics
        assert 'profit_factor' in metrics
        assert 'max_losing_streak' in metrics
        assert 'worst_trade' in metrics
        assert 'recovery_time' in metrics
        assert 'final_equity' in metrics
        
        assert metrics['cumulative_return'] > 0
        assert metrics['max_drawdown'] <= 0
        assert metrics['final_equity'] > capital


class TestBootstrapMethods:
    """Tests for bootstrap simulation methods."""

    def test_run_iid_bootstrap(self):
        # Small test dataset
        pnl = np.array([100, -50, 200, -30, 150, -20, 80, -40, 120, -60] * 3)  # 30 trades
        returns = pnl / 10000  # Dummy returns
        timestamps = np.array([f'2020-01-{i:02d}' for i in range(1, 31)], dtype='datetime64[D]')
        window_ids = np.array([1]*10 + [2]*10 + [3]*10)
        trades = TradeSequence(pnl=pnl, returns=returns, timestamps=timestamps, window_ids=window_ids)
        
        config = MonteCarloConfig(n_simulations=100, seed=42)
        results = run_iid_bootstrap(trades, config)
        
        assert results.method == "IID Bootstrap"
        assert results.n_simulations == 100
        assert len(results.cumulative_returns) == 100
        assert len(results.max_drawdowns) == 100
        assert len(results.sharpes) == 100
        assert 'cumulative_return' in results.percentiles
        assert 'max_drawdown' in results.percentiles
        assert 'sharpe' in results.percentiles

    def test_run_randomized_sequence(self):
        pnl = np.array([100, -50, 200, -30, 150, -20, 80, -40, 120, -60] * 3)
        returns = pnl / 10000
        timestamps = np.array([f'2020-01-{i:02d}' for i in range(1, 31)], dtype='datetime64[D]')
        window_ids = np.array([1]*10 + [2]*10 + [3]*10)
        trades = TradeSequence(pnl=pnl, returns=returns, timestamps=timestamps, window_ids=window_ids)
        
        config = MonteCarloConfig(n_simulations=100, seed=42)
        results = run_randomized_sequence(trades, config)
        
        assert results.method == "Randomized Sequence"
        assert results.n_simulations == 100
        # Randomized sequence has fixed cumulative return (same trades, different order)
        # But max drawdown varies
        assert np.all(results.cumulative_returns == results.cumulative_returns[0])

    def test_run_block_bootstrap(self):
        # Skip if arch not available
        try:
            from arch.bootstrap import StationaryBootstrap
        except ImportError:
            pytest.skip("arch package not available")
        
        pnl = np.array([100, -50, 200, -30, 150, -20, 80, -40, 120, -60] * 3)
        returns = pnl / 10000
        timestamps = np.array([f'2020-01-{i:02d}' for i in range(1, 31)], dtype='datetime64[D]')
        window_ids = np.array([1]*10 + [2]*10 + [3]*10)
        trades = TradeSequence(pnl=pnl, returns=returns, timestamps=timestamps, window_ids=window_ids)
        
        config = MonteCarloConfig(n_simulations=100, seed=42, block_length=5)
        results = run_block_bootstrap(trades, config)
        
        assert "Block Bootstrap" in results.method
        assert results.n_simulations == 100
        assert len(results.cumulative_returns) == 100


class TestSimulationResults:
    """Tests for SimulationResults dataclass."""

    def test_summarize(self):
        # Create mock results
        n = 1000
        cum_returns = np.random.normal(1.5, 0.5, n)
        max_dds = -np.abs(np.random.normal(0.2, 0.1, n))
        sharpes = np.random.normal(0.1, 0.05, n)
        profit_factors = np.abs(np.random.normal(1.6, 0.3, n))
        losing_streaks = np.random.randint(3, 10, n)
        worst_trade = -np.abs(np.random.normal(500, 200, n))
        recovery_times = np.random.randint(1, 20, n)
        final_equity = np.random.normal(200_000, 50_000, n)
        
        results = SimulationResults(
            method="Test",
            n_simulations=n,
            cumulative_returns=cum_returns,
            max_drawdowns=max_dds,
            sharpes=sharpes,
            profit_factors=profit_factors,
            losing_streaks=losing_streaks,
            worst_trade=worst_trade,
            recovery_times=recovery_times,
            final_equity=final_equity,
            percentiles={},
        )
        
        summary = results.summarize()
        
        assert 'cumulative_return' in summary
        assert 'max_drawdown' in summary
        assert 'sharpe' in summary
        assert 'profit_factor' in summary
        assert 'max_losing_streak' in summary
        assert 'worst_trade' in summary
        assert 'dd_exceedance' in summary
        assert 'prob_positive_expectancy' in summary
        assert 'prob_breakeven' in summary
        
        # DD exceedance should have non-zero values
        assert summary['dd_exceedance']['5%'] > 0
        assert summary['prob_positive_expectancy'] >= 0


class TestLoadOOSTrades:
    """Tests for loading OOS trade data."""

    def test_load_oos_trades(self):
        trades = load_oos_trades()
        
        assert isinstance(trades, TradeSequence)
        assert trades.n_trades == 285
        assert len(trades.timestamps) == 285
        assert len(trades.window_ids) == 285
        assert len(np.unique(trades.window_ids)) == 8
        assert trades.expectancy > 0
        assert 0 < trades.win_rate < 1


class TestReproducibility:
    """Tests for reproducibility with fixed seeds."""

    def test_iid_bootstrap_reproducible(self):
        pnl = np.array([100, -50, 200, -30, 150, -20, 80, -40, 120, -60] * 3)
        returns = pnl / 10000
        timestamps = np.array([f'2020-01-{i:02d}' for i in range(1, 31)], dtype='datetime64[D]')
        window_ids = np.array([1]*10 + [2]*10 + [3]*10)
        trades = TradeSequence(pnl=pnl, returns=returns, timestamps=timestamps, window_ids=window_ids)
        
        config1 = MonteCarloConfig(n_simulations=100, seed=42)
        config2 = MonteCarloConfig(n_simulations=100, seed=42)
        
        results1 = run_iid_bootstrap(trades, config1)
        results2 = run_iid_bootstrap(trades, config2)
        
        np.testing.assert_array_equal(results1.cumulative_returns, results2.cumulative_returns)
        np.testing.assert_array_equal(results1.max_drawdowns, results2.max_drawdowns)

    def test_randomized_sequence_reproducible(self):
        pnl = np.array([100, -50, 200, -30, 150, -20, 80, -40, 120, -60] * 3)
        returns = pnl / 10000
        timestamps = np.array([f'2020-01-{i:02d}' for i in range(1, 31)], dtype='datetime64[D]')
        window_ids = np.array([1]*10 + [2]*10 + [3]*10)
        trades = TradeSequence(pnl=pnl, returns=returns, timestamps=timestamps, window_ids=window_ids)
        
        config1 = MonteCarloConfig(n_simulations=100, seed=42)
        config2 = MonteCarloConfig(n_simulations=100, seed=42)
        
        results1 = run_randomized_sequence(trades, config1)
        results2 = run_randomized_sequence(trades, config2)
        
        np.testing.assert_array_equal(results1.max_drawdowns, results2.max_drawdowns)

    def test_different_seeds_produce_different_results(self):
        pnl = np.array([100, -50, 200, -30, 150, -20, 80, -40, 120, -60] * 3)
        returns = pnl / 10000
        timestamps = np.array([f'2020-01-{i:02d}' for i in range(1, 31)], dtype='datetime64[D]')
        window_ids = np.array([1]*10 + [2]*10 + [3]*10)
        trades = TradeSequence(pnl=pnl, returns=returns, timestamps=timestamps, window_ids=window_ids)
        
        config1 = MonteCarloConfig(n_simulations=100, seed=42)
        config2 = MonteCarloConfig(n_simulations=100, seed=123)
        
        results1 = run_iid_bootstrap(trades, config1)
        results2 = run_iid_bootstrap(trades, config2)
        
        # Results should differ with different seeds
        assert not np.array_equal(results1.cumulative_returns, results2.cumulative_returns)


class TestIntegration:
    """Integration tests for full Monte Carlo analysis."""

    def test_full_analysis_small(self):
        """Run full analysis with small number of simulations for speed."""
        config = MonteCarloConfig(n_simulations=100, seed=42, block_length=5)
        
        # This should not raise
        results = run_monte_carlo_analysis(n_simulations=100, seed=42, block_length=5)
        
        assert 'IID Bootstrap' in results
        assert 'Randomized Sequence' in results
        assert 'Block Bootstrap (b=5)' in results
        
        for name, result in results.items():
            assert result.n_simulations == 100
            assert len(result.cumulative_returns) == 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])