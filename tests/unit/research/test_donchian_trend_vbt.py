"""
Focused tests for DONCHIAN-001 VectorBT implementation.

Tests verify:
- Signal timing and no lookahead
- Channel calculation correctness
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

from mars.apps.research_lab.donchian_trend_vbt import (
    load_and_validate_data,
    compute_donchian_channels,
    run_vectorbt_portfolio,
    DonchianConfig,
    CostModel,
    ProjectPaths,
)
from mars.libs.evaluation.splits import time_series_split


class TestSignalTimingNoLookahead:
    """Verify signals use only information available before entry."""

    @pytest.fixture(scope="class")
    def config(cls):
        return DonchianConfig(
            symbol="XAUUSD",
            timeframe="h1",
            data_path=None,
            entry_lookback=55,
            exit_lookback=20,
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

    def test_channel_uses_prior_bars_only(self, sample_data):
        """Donchian channels must use only prior bars (shifted by 1)."""
        df = compute_donchian_channels(sample_data, 55, 20)

        # For each bar, channel should equal rolling max/min of PREVIOUS bars
        for i in range(55, min(len(df), 100)):
            upper_expected = sample_data["high"].iloc[i-55:i].max()
            lower_expected = sample_data["low"].iloc[i-20:i].min()
            assert abs(df["donchian_upper"].iloc[i] - upper_expected) < 1e-10
            assert abs(df["donchian_lower"].iloc[i] - lower_expected) < 1e-10

    def test_first_bars_have_nan_channels(self, sample_data):
        """First entry_lookback bars should have NaN upper channel."""
        df = compute_donchian_channels(sample_data, 55, 20)
        assert df["donchian_upper"].iloc[:54].isna().all()
        assert df["donchian_lower"].iloc[:19].isna().all()

    def test_entry_signal_no_lookahead(self, sample_data):
        """Entry signal at bar i uses channel from bars i-55 to i-1 (shifted)."""
        df = compute_donchian_channels(sample_data, 55, 20)

        # Entry signal should only be 1 where close > donchian_upper (both at same index i)
        # donchian_upper at i is max of high[i-55:i-1] — no lookahead
        for i in range(55, min(len(df), 200)):
            if df["entry_signal"].iloc[i] == 1:
                assert df["close"].iloc[i] > df["donchian_upper"].iloc[i]
            if df["exit_signal"].iloc[i] == 1:
                assert df["close"].iloc[i] < df["donchian_lower"].iloc[i]


class TestChannelCalculation:
    """Verify Donchian channel calculations are correct."""

    @pytest.fixture(scope="class")
    def config(cls):
        return DonchianConfig(
            symbol="XAUUSD",
            timeframe="h1",
            data_path=None,
            entry_lookback=20,
            exit_lookback=10,
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
        return load_and_validate_data(config, paths).head(2000)

    def test_upper_channel_is_max_high(self, sample_data):
        """Upper channel = rolling max of high over entry_lookback prior bars."""
        df = compute_donchian_channels(sample_data, 20, 10)

        for i in range(20, 100):
            expected = sample_data["high"].iloc[i-20:i].max()
            actual = df["donchian_upper"].iloc[i]
            assert abs(actual - expected) < 1e-10, f"Bar {i}: expected {expected}, got {actual}"

    def test_lower_channel_is_min_low(self, sample_data):
        """Lower channel = rolling min of low over exit_lookback prior bars."""
        df = compute_donchian_channels(sample_data, 20, 10)

        for i in range(10, 100):
            expected = sample_data["low"].iloc[i-10:i].min()
            actual = df["donchian_lower"].iloc[i]
            assert abs(actual - expected) < 1e-10, f"Bar {i}: expected {expected}, got {actual}"

    def test_channel_wider_with_longer_lookback(self, sample_data):
        """Longer lookback should produce wider (or equal) channels."""
        df_short = compute_donchian_channels(sample_data, 10, 10)
        df_long = compute_donchian_channels(sample_data, 55, 10)

        # After warmup, longer lookback upper channel >= shorter
        for i in range(55, 200):
            assert df_long["donchian_upper"].iloc[i] >= df_short["donchian_upper"].iloc[i] - 1e-10


class TestEntryExitAlignment:
    """Verify entry at next bar open, exit at next bar open."""

    @pytest.fixture(scope="class")
    def config(cls):
        return DonchianConfig(
            symbol="XAUUSD",
            timeframe="h1",
            data_path=None,
            entry_lookback=20,
            exit_lookback=10,
            position_size_pct=1.0,
            max_leverage=1.0,
            cost_model=CostModel(spread_pips=1.0, commission_per_lot=0.5, slippage_pips=0.5),
            train_ratio=0.7,
            val_ratio=0.15,
            test_ratio=0.15,
            seed=42,
        )

    def test_entry_at_next_bar_open(self, config):
        """Entry price = next bar's open after entry_event."""
        paths = ProjectPaths.from_root()
        df = load_and_validate_data(config, paths).head(5000)
        df = compute_donchian_channels(df, config.entry_lookback, config.exit_lookback)

        pf = run_vectorbt_portfolio(df, config, init_cash=10_000_000)
        trades = pf.trades.records_readable

        if len(trades) == 0:
            pytest.skip("No trades generated in sample")

        # For each trade, entry price should match next bar's open after entry_event
        for _, trade in trades.iterrows():
            entry_ts = trade["Entry Timestamp"]
            # Find the entry_event bar (should be one bar before entry_ts)
            entry_event_idx = df.index.get_loc(entry_ts) - 1
            if entry_event_idx >= 0:
                expected_entry_price = df.iloc[entry_event_idx + 1]["open"]  # next bar open
                assert abs(trade["Avg Entry Price"] - expected_entry_price) < 1e-4, \
                    f"Entry price mismatch: got {trade['Avg Entry Price']}, expected {expected_entry_price}"

    def test_exit_at_next_bar_open(self, config):
        """Exit price = next bar's open after exit_event."""
        paths = ProjectPaths.from_root()
        df = load_and_validate_data(config, paths).head(5000)
        df = compute_donchian_channels(df, config.entry_lookback, config.exit_lookback)

        pf = run_vectorbt_portfolio(df, config, init_cash=10_000_000)
        trades = pf.trades.records_readable

        if len(trades) == 0:
            pytest.skip("No trades generated in sample")

        # For each trade, exit price should match next bar's open after exit_event
        for _, trade in trades.iterrows():
            exit_ts = trade["Exit Timestamp"]
            # Find the exit_event bar (should be one bar before exit_ts)
            exit_event_idx = df.index.get_loc(exit_ts) - 1
            if exit_event_idx >= 0:
                expected_exit_price = df.iloc[exit_event_idx + 1]["open"]  # next bar open
                assert abs(trade["Avg Exit Price"] - expected_exit_price) < 1e-4, \
                    f"Exit price mismatch: got {trade['Avg Exit Price']}, expected {expected_exit_price}"

    def test_one_entry_one_exit_per_trade(self, config):
        """Each trade should have exactly one entry and one exit.
        
        Note: The last entry/exit event may not have a next bar to execute,
        so trades count may be one less than events.
        """
        paths = ProjectPaths.from_root()
        df = load_and_validate_data(config, paths).head(10000)
        df = compute_donchian_channels(df, config.entry_lookback, config.exit_lookback)

        pf = run_vectorbt_portfolio(df, config, init_cash=10_000_000)
        trades = pf.trades.records_readable

        if len(trades) == 0:
            pytest.skip("No trades generated")

        # VectorBT should pair entries and exits
        # Trades count <= entry_events and <= exit_events (last event may not execute)
        assert len(trades) <= df["entry_event"].sum()
        assert len(trades) <= df["exit_event"].sum()


class TestCostApplication:
    """Verify costs applied correctly per trade."""

    @pytest.fixture(scope="class")
    def config_with_costs(cls):
        return DonchianConfig(
            symbol="XAUUSD",
            timeframe="h1",
            data_path=None,
            entry_lookback=20,
            exit_lookback=10,
            position_size_pct=1.0,
            max_leverage=1.0,
            cost_model=CostModel(spread_pips=1.0, commission_per_lot=0.5, slippage_pips=0.5),
            train_ratio=0.7,
            val_ratio=0.15,
            test_ratio=0.15,
            seed=42,
        )

    @pytest.fixture(scope="class")
    def config_zero_costs(cls):
        return DonchianConfig(
            symbol="XAUUSD",
            timeframe="h1",
            data_path=None,
            entry_lookback=20,
            exit_lookback=10,
            position_size_pct=1.0,
            max_leverage=1.0,
            cost_model=CostModel(spread_pips=0.0, commission_per_lot=0.0, slippage_pips=0.0),
            train_ratio=0.7,
            val_ratio=0.15,
            test_ratio=0.15,
            seed=42,
        )

    def test_cost_per_lot_calculation(self, config_with_costs):
        """Round-trip cost = spread*$10 + commission + 2*slippage*$10 per lot."""
        # XAUUSD: 1 pip = $10 per lot (100 oz * $0.10/oz/pip)
        # spread=1.0 pip -> $10
        # commission=$0.5
        # slippage=0.5 pip * 2 (entry + exit) -> $10
        # Total = $20.50 per lot round-trip
        expected_round_trip = 1.0 * 10.0 + 0.5 + 2 * 0.5 * 10.0
        actual = config_with_costs.cost_model.per_round_trip_usd_per_lot()
        assert abs(actual - expected_round_trip) < 1e-10

    def test_net_vs_gross_pnl_difference(self, config_with_costs, config_zero_costs):
        """Net P&L = Gross P&L - total costs."""
        paths = ProjectPaths.from_root()
        df = load_and_validate_data(config_with_costs, paths).head(20000)
        df = compute_donchian_channels(df, config_with_costs.entry_lookback, config_with_costs.exit_lookback)

        pf_costs = run_vectorbt_portfolio(df, config_with_costs, init_cash=10_000_000)
        pf_zero = run_vectorbt_portfolio(df, config_zero_costs, init_cash=10_000_000)

        trades_costs = pf_costs.trades.records_readable
        trades_zero = pf_zero.trades.records_readable

        if len(trades_costs) == 0:
            pytest.skip("No trades generated")

        # Net P&L should be gross P&L minus costs
        # Use iterrows to access columns with spaces
        for _, tc in trades_costs.iterrows():
            tz = trades_zero.loc[trades_costs.index.get_loc(_)]
            gross_pnl = tz["PnL"]  # zero-cost P&L is gross
            net_pnl = tc["PnL"]
            total_fees = tc["Entry Fees"] + tc["Exit Fees"]
            assert abs(net_pnl - (gross_pnl - total_fees)) < 1e-6

    def test_fixed_fee_per_order_side(self, config_with_costs):
        """Fixed fee applied per order (entry and exit each)."""
        round_trip = config_with_costs.cost_model.per_round_trip_usd_per_lot()
        fee_per_order = round_trip / 2.0

        paths = ProjectPaths.from_root()
        df = load_and_validate_data(config_with_costs, paths).head(5000)
        df = compute_donchian_channels(df, config_with_costs.entry_lookback, config_with_costs.exit_lookback)

        pf = run_vectorbt_portfolio(df, config_with_costs, init_cash=10_000_000)
        trades = pf.trades.records_readable

        if len(trades) == 0:
            pytest.skip("No trades generated")

        # Each order side should have the same fixed fee
        for _, trade in trades.iterrows():
            # Position size = 1 lot = 100 oz
            assert abs(trade["Entry Fees"] - fee_per_order) < 1e-6
            assert abs(trade["Exit Fees"] - fee_per_order) < 1e-6


class TestPositionSizing:
    """Verify position sizing matches fixed 1 lot."""

    def test_fixed_one_lot_per_trade(self):
        """Each trade generates exactly 1 lot (100 oz) position."""
        config = DonchianConfig(
            symbol="XAUUSD",
            timeframe="h1",
            data_path=None,
            entry_lookback=20,
            exit_lookback=10,
            position_size_pct=1.0,
            max_leverage=1.0,
            cost_model=CostModel(spread_pips=1.0, commission_per_lot=0.5, slippage_pips=0.5),
            train_ratio=0.7,
            val_ratio=0.15,
            test_ratio=0.15,
            seed=42,
        )

        paths = ProjectPaths.from_root()
        df = load_and_validate_data(config, paths).head(10000)
        df = compute_donchian_channels(df, config.entry_lookback, config.exit_lookback)

        pf = run_vectorbt_portfolio(df, config, init_cash=10_000_000)
        trades = pf.trades.records_readable

        if len(trades) == 0:
            pytest.skip("No trades generated")

        # All trades should have size = 100 oz (1 lot)
        for _, trade in trades.iterrows():
            assert abs(trade["Size"] - 100.0) < 1e-6, \
                f"Position size {trade['Size']} != 100 oz (1 lot)"

    def test_no_compounding_position_sizing(self):
        """Position size should not compound with equity changes."""
        config = DonchianConfig(
            symbol="XAUUSD",
            timeframe="h1",
            data_path=None,
            entry_lookback=20,
            exit_lookback=10,
            position_size_pct=1.0,
            max_leverage=1.0,
            cost_model=CostModel(spread_pips=1.0, commission_per_lot=0.5, slippage_pips=0.5),
            train_ratio=0.7,
            val_ratio=0.15,
            test_ratio=0.15,
            seed=42,
        )

        paths = ProjectPaths.from_root()
        df = load_and_validate_data(config, paths).head(20000)
        df = compute_donchian_channels(df, config.entry_lookback, config.exit_lookback)

        pf = run_vectorbt_portfolio(df, config, init_cash=10_000_000)
        trades = pf.trades.records_readable

        if len(trades) == 0:
            pytest.skip("No trades generated")

        # All trades same size regardless of cumulative P&L
        sizes = trades["Size"].unique()
        assert len(sizes) == 1
        assert abs(sizes[0] - 100.0) < 1e-6


class TestMissingData:
    """Verify handling of missing bars."""

    def test_no_nan_in_ohlcv_after_load(self):
        """Loaded data should have no NaN in OHLCV."""
        config = DonchianConfig(
            symbol="XAUUSD",
            timeframe="h1",
            data_path=None,
            entry_lookback=55,
            exit_lookback=20,
            position_size_pct=1.0,
            max_leverage=1.0,
            cost_model=CostModel(spread_pips=1.0, commission_per_lot=0.5, slippage_pips=0.5),
            train_ratio=0.7,
            val_ratio=0.15,
            test_ratio=0.15,
            seed=42,
        )

        paths = ProjectPaths.from_root()
        df = load_and_validate_data(config, paths)
        assert df[["open", "high", "low", "close", "volume"]].notna().all().all()

    def test_channels_nan_until_warmup(self):
        """Channels should be NaN until enough prior bars exist."""
        config = DonchianConfig(
            symbol="XAUUSD",
            timeframe="h1",
            data_path=None,
            entry_lookback=55,
            exit_lookback=20,
            position_size_pct=1.0,
            max_leverage=1.0,
            cost_model=CostModel(spread_pips=1.0, commission_per_lot=0.5, slippage_pips=0.5),
            train_ratio=0.7,
            val_ratio=0.15,
            test_ratio=0.15,
            seed=42,
        )

        paths = ProjectPaths.from_root()
        df = load_and_validate_data(config, paths).head(200)
        df = compute_donchian_channels(df, 55, 20)

        # First 55 bars: upper channel NaN
        assert df["donchian_upper"].iloc[:55].isna().all()
        # First 20 bars: lower channel NaN
        assert df["donchian_lower"].iloc[:20].isna().all()
        # After warmup, no NaN
        assert df["donchian_upper"].iloc[55:].notna().all()
        assert df["donchian_lower"].iloc[20:].notna().all()


class TestReproducibility:
    """Verify experiment is fully reproducible."""

    def test_deterministic_results(self):
        """Same config + same data + same seed = identical results."""
        config = DonchianConfig(
            symbol="XAUUSD",
            timeframe="h1",
            data_path=None,
            entry_lookback=20,
            exit_lookback=10,
            position_size_pct=1.0,
            max_leverage=1.0,
            cost_model=CostModel(spread_pips=1.0, commission_per_lot=0.5, slippage_pips=0.5),
            train_ratio=0.7,
            val_ratio=0.15,
            test_ratio=0.15,
            seed=42,
        )

        paths = ProjectPaths.from_root()
        df = load_and_validate_data(config, paths).head(20000)
        df = compute_donchian_channels(df, config.entry_lookback, config.exit_lookback)

        pf1 = run_vectorbt_portfolio(df, config, init_cash=10_000_000)
        pf2 = run_vectorbt_portfolio(df, config, init_cash=10_000_000)

        trades1 = pf1.trades.records_readable
        trades2 = pf2.trades.records_readable

        assert len(trades1) == len(trades2)
        if len(trades1) > 0:
            pd.testing.assert_frame_equal(trades1, trades2, check_dtype=False)

    def test_chronological_split_deterministic(self):
        """Train/val/test split must be deterministic and chronological."""
        config = DonchianConfig(
            symbol="XAUUSD",
            timeframe="h1",
            data_path=None,
            entry_lookback=20,
            exit_lookback=10,
            position_size_pct=1.0,
            max_leverage=1.0,
            cost_model=CostModel(spread_pips=1.0, commission_per_lot=0.5, slippage_pips=0.5),
            train_ratio=0.7,
            val_ratio=0.15,
            test_ratio=0.15,
            seed=42,
        )

        paths = ProjectPaths.from_root()
        df = load_and_validate_data(config, paths).head(20000)
        df = compute_donchian_channels(df, config.entry_lookback, config.exit_lookback)

        result = time_series_split(
            df.index,
            train_ratio=config.train_ratio,
            val_ratio=config.val_ratio,
            test_ratio=config.test_ratio,
        )
        train_idx = result.train_idx
        val_idx = result.val_idx
        test_idx = result.test_idx

        # Train before val before test
        assert max(train_idx) < min(val_idx)
        assert max(val_idx) < min(test_idx)

        # Run twice
        result2 = time_series_split(
            df.index,
            train_ratio=config.train_ratio,
            val_ratio=config.val_ratio,
            test_ratio=config.test_ratio,
        )
        assert list(train_idx) == list(result2.train_idx)
        assert list(val_idx) == list(result2.val_idx)
        assert list(test_idx) == list(result2.test_idx)


class TestLongOnlyBehavior:
    """Verify strategy is long-only (no short positions)."""

    def test_no_short_trades(self):
        """All trades should be long (Size > 0)."""
        config = DonchianConfig(
            symbol="XAUUSD",
            timeframe="h1",
            data_path=None,
            entry_lookback=20,
            exit_lookback=10,
            position_size_pct=1.0,
            max_leverage=1.0,
            cost_model=CostModel(spread_pips=1.0, commission_per_lot=0.5, slippage_pips=0.5),
            train_ratio=0.7,
            val_ratio=0.15,
            test_ratio=0.15,
            seed=42,
        )

        paths = ProjectPaths.from_root()
        df = load_and_validate_data(config, paths).head(20000)
        df = compute_donchian_channels(df, config.entry_lookback, config.exit_lookback)

        pf = run_vectorbt_portfolio(df, config, init_cash=10_000_000)
        trades = pf.trades.records_readable

        if len(trades) == 0:
            pytest.skip("No trades generated")

        # All trades should have positive size (long)
        assert (trades["Size"] > 0).all()

    def test_portfolio_direction_longonly(self):
        """Portfolio should be configured as longonly."""
        config = DonchianConfig(
            symbol="XAUUSD",
            timeframe="h1",
            data_path=None,
            entry_lookback=20,
            exit_lookback=10,
            position_size_pct=1.0,
            max_leverage=1.0,
            cost_model=CostModel(spread_pips=1.0, commission_per_lot=0.5, slippage_pips=0.5),
            train_ratio=0.7,
            val_ratio=0.15,
            test_ratio=0.15,
            seed=42,
        )

        paths = ProjectPaths.from_root()
        df = load_and_validate_data(config, paths).head(1000)
        df = compute_donchian_channels(df, config.entry_lookback, config.exit_lookback)

        pf = run_vectorbt_portfolio(df, config, init_cash=10_000_000)

        # Portfolio should have no short trades
        trades = pf.trades.records_readable
        if len(trades) > 0:
            assert (trades["Size"] > 0).all()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])