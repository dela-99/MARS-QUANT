"""
Focused tests for MA-TSM-001 VectorBT implementation.

Tests verify:
- Signal timing and no lookahead
- SMA calculation correctness
- Entry/exit alignment (next bar open execution)
- Cost application
- Position sizing
- Missing data handling
- Reproducibility
- Split determinism
"""

import pytest
import pandas as pd
import numpy as np
import vectorbt as vbt

from mars.apps.research_lab.ma_tsm_001 import (
    load_and_validate_data,
    compute_sma_signals,
    run_vectorbt_portfolio,
    compute_metrics,
    compute_benchmarks,
    MATSMConfig,
    CostModel,
    ProjectPaths,
)
from mars.libs.evaluation.splits import time_series_split


class TestSignalTimingNoLookahead:
    """Verify signals use only information available before entry."""

    @pytest.fixture(scope="class")
    def config(cls):
        return MATSMConfig(
            symbol="XAUUSD",
            timeframe="h1",
            data_path=None,
            sma_period=200,
            position_size_pct=1.0,
            max_leverage=1.0,
            cost_model=CostModel(spread_pips=1.0, commission_per_lot=0.5, slippage_pips=0.5),
            train_ratio=0.7,
            val_ratio=0.15,
            test_ratio=0.15,
            seed=42,
        )

    @pytest.fixture(scope="class")
    def sample_data(cls, config):
        paths = ProjectPaths.from_root()
        return load_and_validate_data(config, paths).head(5000)  # Small sample

    def test_sma_uses_prior_bars_only(self, sample_data):
        """SMA at bar i must use only close[i-sma_period : i-1]."""
        df = compute_sma_signals(sample_data, 55)

        # For each bar after warmup, SMA should equal rolling mean of PRIOR closes
        for i in range(55, min(len(df), 100)):
            sma_expected = sample_data["close"].iloc[i-55:i].mean()
            assert abs(df["sma"].iloc[i] - sma_expected) < 1e-10, \
                f"SMA at {i} uses lookahead: {df['sma'].iloc[i]} != {sma_expected}"

    def test_first_bars_have_nan_sma(self, sample_data):
        """First sma_period bars should have NaN SMA."""
        df = compute_sma_signals(sample_data, 55)
        assert df["sma"].iloc[:54].isna().all()

    def test_entry_signal_no_lookahead(self, sample_data):
        """Entry signal at bar i uses SMA from bars i-55 to i-1 (shifted)."""
        df = compute_sma_signals(sample_data, 55)

        # Entry signal should only be 1 where close > sma (both at same index i)
        # sma at i is mean of close[i-55:i-1] — no lookahead
        for i in range(55, min(len(df), 200)):
            if df["entry_signal"].iloc[i] == 1:
                assert df["close"].iloc[i] > df["sma"].iloc[i]
            if df["exit_signal"].iloc[i] == 1:
                assert df["close"].iloc[i] < df["sma"].iloc[i]

    def test_no_signal_before_warmup(self, sample_data):
        """No entry/exit signals before SMA warmup completes."""
        df = compute_sma_signals(sample_data, 55)
        assert df["entry_signal"].iloc[:54].sum() == 0
        assert df["exit_signal"].iloc[:54].sum() == 0


class TestSMAComputation:
    """Verify SMA indicator calculation correctness."""

    def test_sma_constant_series(self):
        """SMA of constant series equals the constant."""
        dates = pd.date_range("2020-01-01", periods=300, freq="h", tz="UTC")
        df = pd.DataFrame({"close": [100.0] * 300}, index=dates)
        df["open"] = 100.0
        df["high"] = 100.0
        df["low"] = 100.0
        df["volume"] = 1000.0

        out = compute_sma_signals(df, 50)
        # After warmup, SMA should be 100
        assert np.allclose(out["sma"].iloc[50:], 100.0, atol=1e-10)

    def test_sma_linear_series(self):
        """SMA of linearly increasing series matches manual calculation."""
        dates = pd.date_range("2020-01-01", periods=300, freq="h", tz="UTC")
        closes = np.arange(100.0, 400.0, 1.0)
        df = pd.DataFrame({"close": closes}, index=dates)
        df["open"] = closes
        df["high"] = closes
        df["low"] = closes
        df["volume"] = 1000.0

        out = compute_sma_signals(df, 50)
        # Verify at a specific point
        i = 100
        expected = closes[i-50:i].mean()
        assert abs(out["sma"].iloc[i] - expected) < 1e-10

    def test_sma_shifted_correctly(self):
        """SMA must be shifted by 1 to avoid lookahead."""
        dates = pd.date_range("2020-01-01", periods=300, freq="h", tz="UTC")
        closes = np.random.default_rng(42).uniform(100, 200, 300)
        df = pd.DataFrame({"close": closes}, index=dates)
        df["open"] = closes
        df["high"] = closes
        df["low"] = closes
        df["volume"] = 1000.0

        out = compute_sma_signals(df, 20)

        # sma[i] should equal mean of close[i-20:i] (shifted by 1 from rolling)
        for i in range(20, 50):
            expected = df["close"].shift(1).rolling(20).mean().iloc[i]
            assert abs(out["sma"].iloc[i] - expected) < 1e-10


class TestEntryExitAlignment:
    """Verify entry/exit execution at next bar open."""

    def test_entry_execution_next_open(self):
        """Entry should execute at NEXT bar's open, not signal bar close."""
        dates = pd.date_range("2020-01-01", periods=100, freq="h", tz="UTC")
        # Create a clear SMA cross
        closes = np.ones(100) * 100.0
        closes[50:] = 110.0  # Cross above SMA
        df = pd.DataFrame({"close": closes}, index=dates)
        df["open"] = closes + 0.5  # Open slightly above close
        df["high"] = closes + 1.0
        df["low"] = closes - 1.0
        df["volume"] = 1000.0

        out = compute_sma_signals(df, 20)
        # Find entry event
        entry_idx = out[out["entry_event"] == 1].index[0]
        entry_loc = out.index.get_loc(entry_idx)
        next_idx = out.index[entry_loc + 1]

        config = MATSMConfig(position_size_pct=1.0, sma_period=20)
        pf = run_vectorbt_portfolio(out, config)

        trades = pf.trades.records_readable
        if len(trades) > 0:
            # Entry price should be next bar's OPEN
            assert abs(trades.iloc[0]["Avg Entry Price"] - out.loc[next_idx, "open"]) < 1e-6

    def test_exit_execution_next_open(self):
        """Exit should execute at NEXT bar's open after exit signal."""
        dates = pd.date_range("2020-01-01", periods=100, freq="h", tz="UTC")
        closes = np.ones(100) * 110.0
        closes[50:] = 100.0  # Cross below SMA
        df = pd.DataFrame({"close": closes}, index=dates)
        df["open"] = closes - 0.5
        df["high"] = closes + 1.0
        df["low"] = closes - 1.0
        df["volume"] = 1000.0

        out = compute_sma_signals(df, 20)
        exit_mask = out["exit_event"] == 1
        if exit_mask.any():
            exit_idx = out[exit_mask].index[0]
            exit_loc = out.index.get_loc(exit_idx)
            next_idx = out.index[exit_loc + 1]

            config = MATSMConfig(position_size_pct=1.0, sma_period=20)
            pf = run_vectorbt_portfolio(out, config)

            trades = pf.trades.records_readable
            if len(trades) > 0:
                # Exit price should be next bar's OPEN
                assert abs(trades.iloc[0]["Avg Exit Price"] - out.loc[next_idx, "open"]) < 1e-6


class TestCostApplication:
    """Verify transaction costs are applied correctly."""

    def test_cost_model_round_trip(self):
        """CostModel.per_round_trip_usd_per_lot should compute correctly."""
        # XAUUSD: 1 pip = $10/lot, 1 lot = 100 oz
        cm = CostModel(spread_pips=1.0, commission_per_lot=0.5, slippage_pips=0.5)
        # spread: 1 pip * $10 = $10
        # slippage: 2 * 0.5 pip * $10 = $10
        # commission: $0.5
        # total = $20.5
        assert abs(cm.per_round_trip_usd_per_lot() - 20.5) < 1e-10

    def test_zero_costs_no_fees(self):
        """Zero cost model should produce zero fees."""
        cm = CostModel(spread_pips=0.0, commission_per_lot=0.0, slippage_pips=0.0)
        assert cm.per_round_trip_usd_per_lot() == 0.0

    def test_costs_reduce_net_pnl(self):
        """Net P&L should be lower than gross P&L when costs applied."""
        dates = pd.date_range("2020-01-01", periods=300, freq="h", tz="UTC")
        closes = np.ones(300) * 100.0
        closes[100:200] = 110.0  # Trend up then down
        df = pd.DataFrame({"close": closes}, index=dates)
        df["open"] = closes
        df["high"] = closes + 1
        df["low"] = closes - 1
        df["volume"] = 1000.0

        config_zero = MATSMConfig(
            sma_period=20,
            cost_model=CostModel(spread_pips=0.0, commission_per_lot=0.0, slippage_pips=0.0)
        )
        config_cost = MATSMConfig(
            sma_period=20,
            cost_model=CostModel(spread_pips=1.0, commission_per_lot=0.5, slippage_pips=0.5)
        )

        out_zero = compute_sma_signals(df, 20)
        out_cost = compute_sma_signals(df, 20)

        pf_zero = run_vectorbt_portfolio(out_zero, config_zero)
        pf_cost = run_vectorbt_portfolio(out_cost, config_cost)

        trades_zero = pf_zero.trades.records_readable
        trades_cost = pf_cost.trades.records_readable

        if len(trades_zero) > 0 and len(trades_cost) > 0:
            # Net P&L with costs should be lower
            assert trades_cost["PnL"].sum() < trades_zero["PnL"].sum()


class TestPositionSizing:
    """Verify position sizing and leverage."""

    def test_fixed_position_size(self):
        """Position size should match config (1 lot = 100 oz)."""
        dates = pd.date_range("2020-01-01", periods=300, freq="h", tz="UTC")
        closes = np.ones(300) * 100.0
        closes[100:200] = 110.0
        df = pd.DataFrame({"close": closes}, index=dates)
        df["open"] = closes
        df["high"] = closes + 1
        df["low"] = closes - 1
        df["volume"] = 1000.0

        config = MATSMConfig(position_size_pct=1.0, sma_period=20, max_leverage=1.0)
        out = compute_sma_signals(df, 20)
        pf = run_vectorbt_portfolio(out, config)

        trades = pf.trades.records_readable
        if len(trades) > 0:
            # Size should be 100 oz (1 lot)
            assert np.allclose(trades["Size"], 100.0)

    def test_leverage_scaling(self):
        """Position size should scale with max_leverage."""
        dates = pd.date_range("2020-01-01", periods=300, freq="h", tz="UTC")
        closes = np.ones(300) * 100.0
        closes[100:200] = 110.0
        df = pd.DataFrame({"close": closes}, index=dates)
        df["open"] = closes
        df["high"] = closes + 1
        df["low"] = closes - 1
        df["volume"] = 1000.0

        config_1x = MATSMConfig(position_size_pct=1.0, sma_period=20, max_leverage=1.0)
        config_2x = MATSMConfig(position_size_pct=1.0, sma_period=20, max_leverage=2.0)

        out = compute_sma_signals(df, 20)
        pf_1x = run_vectorbt_portfolio(out, config_1x)
        pf_2x = run_vectorbt_portfolio(out, config_2x)

        trades_1x = pf_1x.trades.records_readable
        trades_2x = pf_2x.trades.records_readable

        if len(trades_1x) > 0 and len(trades_2x) > 0:
            assert np.allclose(trades_2x["Size"], 2 * trades_1x["Size"])


class TestMissingDataHandling:
    """Verify handling of missing/invalid data."""

    def test_nan_closes_excluded(self):
        """NaN close values should not break SMA calculation."""
        dates = pd.date_range("2020-01-01", periods=300, freq="h", tz="UTC")
        closes = np.ones(300) * 100.0
        closes[50] = np.nan
        df = pd.DataFrame({"close": closes}, index=dates)
        df["open"] = closes
        df["high"] = closes + 1
        df["low"] = closes - 1
        df["volume"] = 1000.0

        out = compute_sma_signals(df, 20)
        # Should not crash; NaN should propagate appropriately
        assert out["sma"].iloc[50:70].isna().any()


class TestReproducibility:
    """Verify deterministic results with fixed seed."""

    @pytest.fixture
    def sample_data(self):
        config = MATSMConfig(sma_period=200, seed=42)
        paths = ProjectPaths.from_root()
        return load_and_validate_data(config, paths).head(2000)

    def test_deterministic_signals(self, sample_data):
        """Same input and config should produce identical signals."""
        out1 = compute_sma_signals(sample_data, 200)
        out2 = compute_sma_signals(sample_data, 200)
        pd.testing.assert_frame_equal(out1, out2)

    def test_deterministic_portfolio(self, sample_data):
        """Same config should produce identical portfolio results."""
        config = MATSMConfig(sma_period=200, seed=42)
        out1 = compute_sma_signals(sample_data, 200)
        out2 = compute_sma_signals(sample_data, 200)

        pf1 = run_vectorbt_portfolio(out1, config)
        pf2 = run_vectorbt_portfolio(out2, config)

        t1 = pf1.trades.records_readable
        t2 = pf2.trades.records_readable

        if len(t1) > 0:
            pd.testing.assert_frame_equal(t1, t2)


class TestSplitDeterminism:
    """Verify chronological splits are deterministic and non-overlapping."""

    @pytest.fixture
    def sample_data(self):
        config = MATSMConfig(sma_period=200, seed=42)
        paths = ProjectPaths.from_root()
        return load_and_validate_data(config, paths).head(2000)

    def test_split_chronological(self, sample_data):
        """Split indices should be chronological and non-overlapping."""
        split = time_series_split(
            sample_data.index,
            train_ratio=0.7,
            val_ratio=0.15,
            test_ratio=0.15,
        )
        assert split.train_idx[-1] < split.val_idx[0]
        assert split.val_idx[-1] < split.test_idx[0]

    def test_split_ratios(self, sample_data):
        """Split ratios should match approximately."""
        n = len(sample_data)
        split = time_series_split(
            sample_data.index,
            train_ratio=0.7,
            val_ratio=0.15,
            test_ratio=0.15,
        )
        assert abs(len(split.train_idx) / n - 0.7) < 0.02
        assert abs(len(split.val_idx) / n - 0.15) < 0.02
        assert abs(len(split.test_idx) / n - 0.15) < 0.02


class TestBenchmarkCalculation:
    """Verify buy-and-hold benchmark."""

    def test_buy_and_hold_positive_trend(self):
        """Buy-and-hold should be positive in upward trend."""
        dates = pd.date_range("2020-01-01", periods=100, freq="h", tz="UTC")
        closes = np.linspace(100.0, 200.0, 100)
        df = pd.DataFrame({"close": closes}, index=dates)
        df["open"] = closes
        df["high"] = closes + 1
        df["low"] = closes - 1
        df["volume"] = 1000.0

        bench = compute_benchmarks(df)
        assert bench["buy_and_hold_return"] > 0.9  # ~100% return

    def test_buy_and_hold_flat(self):
        """Buy-and-hold should be zero in flat market."""
        dates = pd.date_range("2020-01-01", periods=100, freq="h", tz="UTC")
        closes = np.ones(100) * 100.0
        df = pd.DataFrame({"close": closes}, index=dates)
        df["open"] = closes
        df["high"] = closes + 1
        df["low"] = closes - 1
        df["volume"] = 1000.0

        bench = compute_benchmarks(df)
        assert abs(bench["buy_and_hold_return"]) < 1e-10


class TestIntegration:
    """Integration test with real data sample."""

    def test_full_pipeline_real_data(self):
        """Run full pipeline on small real data sample."""
        config = MATSMConfig(
            symbol="XAUUSD",
            timeframe="h1",
            sma_period=200,
            position_size_pct=1.0,
            cost_model=CostModel(spread_pips=1.0, commission_per_lot=0.5, slippage_pips=0.5),
        )
        paths = ProjectPaths.from_root()
        df = load_and_validate_data(config, paths).head(2000)

        # Full pipeline
        df_sig = compute_sma_signals(df, config.sma_period)
        pf = run_vectorbt_portfolio(df_sig, config)
        metrics = compute_metrics(pf, config, df)

        assert "n_trades" in metrics
        assert metrics["n_trades"] >= 0
        assert "sharpe_net" in metrics


if __name__ == "__main__":
    pytest.main([__file__, "-v"])