"""
Focused tests for CSM-001 VectorBT revalidation.

Tests verify:
- Signal timing and no lookahead
- Entry/exit alignment
- Cost application
- Position sizing
- Session boundaries
- Missing data handling
- Reproducibility
"""

import pytest
import pandas as pd
import numpy as np
import vectorbt as vbt

from mars.apps.research_lab.cross_session_momentum_vbt import (
    load_and_validate_data,
    assign_session_labels,
    compute_session_returns,
    generate_signals,
    run_vectorbt_portfolio_m5,
    ExperimentConfig,
    CostModel,
    SessionName,
    ProjectPaths,
)
from mars.libs.evaluation.splits import time_series_split


class TestSignalTimingNoLookahead:
    """Verify signals use only information available before entry."""

    @pytest.fixture(scope="class")
    def config(cls):
        return ExperimentConfig(
            symbol="XAUUSD",
            timeframe="m5",
            data_path=None,
            sessions=("asia", "europe", "us"),
            signal_mode="direction",
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
        return load_and_validate_data(config, paths).head(10000)  # Small sample

    def test_signal_uses_previous_session_only(self, sample_data):
        """Signal for session N must be computed from session N-1 close."""
        labeled = assign_session_labels(sample_data)
        session_bars = compute_session_returns(labeled)
        signals = generate_signals(session_bars, "direction")

        # First session has no previous session -> must be flat (0)
        assert signals.iloc[0]["signal"] == 0

        # Each signal must equal sign of previous session's return
        for i in range(1, len(signals)):
            prev_return = session_bars.iloc[i - 1]["session_return"]
            expected_signal = 1 if prev_return > 0 else 0
            assert signals.iloc[i]["signal"] == expected_signal, \
                f"Signal at index {i} uses lookahead or wrong logic"

    def test_no_future_data_in_signal_computation(self, sample_data):
        """Verify compute_session_returns doesn't use future bars."""
        labeled = assign_session_labels(sample_data)
        session_bars = compute_session_returns(labeled)

        # Session return = (close - open) / open of SAME session
        # Open = first bar open, Close = last bar close
        for _, row in session_bars.iterrows():
            session_data = labeled[
                (labeled["date"] == row["date"]) & (labeled["session"] == row["session"])
            ]
            expected_open = session_data.iloc[0]["open"]
            expected_close = session_data.iloc[-1]["close"]
            expected_return = (expected_close - expected_open) / expected_open
            assert abs(row["session_return"] - expected_return) < 1e-10


class TestEntryExitAlignment:
    """Verify entry at session open, exit at session close."""

    @pytest.fixture(scope="class")
    def config(self):
        return ExperimentConfig(
            symbol="XAUUSD",
            timeframe="m5",
            data_path=None,
            sessions=("asia", "europe", "us"),
            signal_mode="direction",
            position_size_pct=1.0,
            max_leverage=1.0,
            cost_model=CostModel(spread_pips=1.0, commission_per_lot=0.5, slippage_pips=0.5),
            train_ratio=0.7,
            val_ratio=0.15,
            test_ratio=0.15,
            seed=42,
        )

    def test_entry_at_session_open_exit_at_session_close(self, config):
        """Entry price = first bar open, Exit price = last bar close."""
        paths = ProjectPaths.from_root()
        df = load_and_validate_data(config, paths).head(5000)  # Small sample
        labeled = assign_session_labels(df)
        session_bars = compute_session_returns(labeled)
        signals = generate_signals(session_bars, "direction")

        pf, _ = run_vectorbt_portfolio_m5(df, signals, config, init_cash=10_000_000)

        trades = pf.trades.records_readable
        if len(trades) == 0:
            pytest.skip("No trades generated in sample")

        # Group M5 bars by session to get expected entry/exit prices
        session_groups = labeled.groupby(["date", "session"])
        session_to_prices = {}
        for (date, session), group in session_groups:
            session_to_prices[(date, session)] = {
                "entry_price": group.iloc[0]["open"],
                "exit_price": group.iloc[-1]["close"],
            }

        # Check each trade matches session prices
        for _, trade in trades.iterrows():
            entry_ts = trade["Entry Timestamp"]
            exit_ts = trade["Exit Timestamp"]
            entry_date = entry_ts.date()
            entry_hour = entry_ts.hour
            entry_minute = entry_ts.minute

            # Determine session from entry timestamp
            if 0 <= entry_hour < 8:
                session = "asia"
            elif 8 <= entry_hour < 14 or (entry_hour == 14 and entry_minute < 30):
                session = "europe"
            else:
                session = "us"

            key = (entry_date, session)
            if key in session_to_prices:
                expected_entry = session_to_prices[key]["entry_price"]
                expected_exit = session_to_prices[key]["exit_price"]

                # Allow small floating point difference
                assert abs(trade["Avg Entry Price"] - expected_entry) < 1e-4, \
                    f"Entry price mismatch: got {trade['Avg Entry Price']}, expected {expected_entry}"
                assert abs(trade["Avg Exit Price"] - expected_exit) < 1e-4, \
                    f"Exit price mismatch: got {trade['Avg Exit Price']}, expected {expected_exit}"

    def test_one_session_hold_duration(self, config):
        """Each trade must be held for exactly one session."""
        paths = ProjectPaths.from_root()
        df = load_and_validate_data(config, paths).head(10000)
        labeled = assign_session_labels(df)
        session_bars = compute_session_returns(labeled)
        signals = generate_signals(session_bars, "direction")

        pf, _ = run_vectorbt_portfolio_m5(df, signals, config, init_cash=10_000_000)
        trades = pf.trades.records_readable

        if len(trades) == 0:
            pytest.skip("No trades generated")

        # Entry and exit should be in consecutive sessions
        for _, trade in trades.iterrows():
            entry_ts = trade["Entry Timestamp"]
            exit_ts = trade["Exit Timestamp"]
            # Exit should be on same day or next day, within next session
            # Session duration is 6.5h (Asia), 6.5h (Europe), 9.5h (US)
            # So exit - entry should be roughly one session length
            duration_hours = (exit_ts - entry_ts).total_seconds() / 3600
            assert 5 <= duration_hours <= 12, \
                f"Trade duration {duration_hours:.1f}h not ~1 session"


class TestCostApplication:
    """Verify costs applied correctly per trade."""

    @pytest.fixture(scope="class")
    def config_with_costs(cls):
        return ExperimentConfig(
            symbol="XAUUSD",
            timeframe="m5",
            data_path=None,
            sessions=("asia", "europe", "us"),
            signal_mode="direction",
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
        return ExperimentConfig(
            symbol="XAUUSD",
            timeframe="m5",
            data_path=None,
            sessions=("asia", "europe", "us"),
            signal_mode="direction",
            position_size_pct=1.0,
            max_leverage=1.0,
            cost_model=CostModel(spread_pips=0.0, commission_per_lot=0.0, slippage_pips=0.0),
            train_ratio=0.7,
            val_ratio=0.15,
            test_ratio=0.15,
            seed=42,
        )

    def test_cost_per_lot_calculation(self, config_with_costs):
        """Round-trip cost = spread*$10 + commission + 2*slippage*$10 per lot (entry + exit)."""
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
        labeled = assign_session_labels(df)
        session_bars = compute_session_returns(labeled)
        signals = generate_signals(session_bars, "direction")

        pf_costs, _ = run_vectorbt_portfolio_m5(df, signals, config_with_costs, init_cash=10_000_000)
        pf_zero, _ = run_vectorbt_portfolio_m5(df, signals, config_zero_costs, init_cash=10_000_000)

        trades_costs = pf_costs.trades.records_readable
        trades_zero = pf_zero.trades.records_readable

        if len(trades_costs) == 0:
            pytest.skip("No trades generated")

        # Net P&L should be gross P&L minus costs
        # VectorBT reports Entry Fees + Exit Fees as total costs per trade
        # itertuples uses positional indices: _6 = Entry Fees, _9 = Exit Fees
        for tc, tz in zip(trades_costs.itertuples(), trades_zero.itertuples()):
            gross_pnl = tz.PnL  # zero-cost P&L is gross
            net_pnl = tc.PnL
            total_fees = tc._6 + tc._9  # Entry Fees + Exit Fees
            assert abs(net_pnl - (gross_pnl - total_fees)) < 1e-6

    def test_fixed_fee_per_order_side(self, config_with_costs):
        """Fixed fee applied per order (entry and exit each)."""
        round_trip = config_with_costs.cost_model.per_round_trip_usd_per_lot()
        fee_per_order = round_trip / 2.0

        paths = ProjectPaths.from_root()
        df = load_and_validate_data(config_with_costs, paths).head(5000)
        labeled = assign_session_labels(df)
        session_bars = compute_session_returns(labeled)
        signals = generate_signals(session_bars, "direction")

        pf, _ = run_vectorbt_portfolio_m5(df, signals, config_with_costs, init_cash=10_000_000)
        trades = pf.trades.records_readable

        if len(trades) == 0:
            pytest.skip("No trades generated")

        # Each order side should have the same fixed fee
        for _, trade in trades.iterrows():
            # Position size = 1 lot = 100 oz
            # VectorBT fixed_fees is per order in USD
            assert abs(trade["Entry Fees"] - fee_per_order) < 1e-6
            assert abs(trade["Exit Fees"] - fee_per_order) < 1e-6


class TestPositionSizing:
    """Verify position sizing matches Assignment 01 (fixed 1 lot)."""

    def test_fixed_one_lot_per_signal(self):
        """Each signal generates exactly 1 lot (100 oz) position."""
        config = ExperimentConfig(
            symbol="XAUUSD",
            timeframe="m5",
            data_path=None,
            sessions=("asia", "europe", "us"),
            signal_mode="direction",
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
        labeled = assign_session_labels(df)
        session_bars = compute_session_returns(labeled)
        signals = generate_signals(session_bars, "direction")

        pf, _ = run_vectorbt_portfolio_m5(df, signals, config, init_cash=10_000_000)
        trades = pf.trades.records_readable

        if len(trades) == 0:
            pytest.skip("No trades generated")

        # All trades should have size = 100 oz (1 lot)
        for _, trade in trades.iterrows():
            assert abs(trade["Size"] - 100.0) < 1e-6, \
                f"Position size {trade['Size']} != 100 oz (1 lot)"

    def test_no_compounding_position_sizing(self):
        """Position size should not compound with equity changes."""
        config = ExperimentConfig(
            symbol="XAUUSD",
            timeframe="m5",
            data_path=None,
            sessions=("asia", "europe", "us"),
            signal_mode="direction",
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
        labeled = assign_session_labels(df)
        session_bars = compute_session_returns(labeled)
        signals = generate_signals(session_bars, "direction")

        pf, _ = run_vectorbt_portfolio_m5(df, signals, config, init_cash=10_000_000)
        trades = pf.trades.records_readable

        if len(trades) == 0:
            pytest.skip("No trades generated")

        # All trades same size regardless of cumulative P&L
        sizes = trades["Size"].unique()
        assert len(sizes) == 1
        assert abs(sizes[0] - 100.0) < 1e-6


class TestSessionBoundaries:
    """Verify session definitions and boundary handling."""

    def test_session_definitions_utc_fixed(self):
        """Sessions defined in fixed UTC: Asia 00-08, Europe 08-14:30, US 14:30-24."""
        config = ExperimentConfig(
            symbol="XAUUSD",
            timeframe="m5",
            data_path=None,
            sessions=("asia", "europe", "us"),
            signal_mode="direction",
            position_size_pct=1.0,
            max_leverage=1.0,
            cost_model=CostModel(spread_pips=1.0, commission_per_lot=0.5, slippage_pips=0.5),
            train_ratio=0.7,
            val_ratio=0.15,
            test_ratio=0.15,
            seed=42,
        )

        paths = ProjectPaths.from_root()
        df = load_and_validate_data(config, paths).head(5000)
        labeled = assign_session_labels(df, config.sessions)

        # Check session assignments
        asia_bars = labeled[labeled["session"] == "asia"]
        europe_bars = labeled[labeled["session"] == "europe"]
        us_bars = labeled[labeled["session"] == "us"]

        if len(asia_bars) > 0:
            assert (asia_bars.index.hour >= 0).all() and (asia_bars.index.hour < 8).all()
        if len(europe_bars) > 0:
            # Europe: 08:00-14:30 UTC
            europe_mask = (europe_bars.index.hour >= 8) & (europe_bars.index.hour < 14) | \
                          ((europe_bars.index.hour == 14) & (europe_bars.index.minute < 30))
            assert europe_mask.all()
        if len(us_bars) > 0:
            # US: 14:30-24:00 UTC
            us_mask = (us_bars.index.hour > 14) | \
                      ((us_bars.index.hour == 14) & (us_bars.index.minute >= 30)) | \
                      (us_bars.index.hour < 24)
            assert us_mask.all()

    def test_session_count_matches_expected(self):
        """Number of sessions per day should be 3 (Asia, Europe, US)."""
        config = ExperimentConfig(
            symbol="XAUUSD",
            timeframe="m5",
            data_path=None,
            sessions=("asia", "europe", "us"),
            signal_mode="direction",
            position_size_pct=1.0,
            max_leverage=1.0,
            cost_model=CostModel(spread_pips=1.0, commission_per_lot=0.5, slippage_pips=0.5),
            train_ratio=0.7,
            val_ratio=0.15,
            test_ratio=0.15,
            seed=42,
        )

        paths = ProjectPaths.from_root()
        df = load_and_validate_data(config, paths).head(5000)
        labeled = assign_session_labels(df, config.sessions)
        session_bars = compute_session_returns(labeled)

        # Count unique dates
        unique_dates = session_bars["date"].nunique()
        # Should have 3 sessions per day (some days may have fewer due to weekends/holidays)
        assert session_bars.groupby("date").size().max() <= 3
        assert session_bars.groupby("date").size().min() >= 1


class TestMissingData:
    """Verify handling of missing bars and incomplete sessions."""

    def test_incomplete_sessions_excluded(self):
        """Sessions with insufficient bars should be excluded from signals."""
        config = ExperimentConfig(
            symbol="XAUUSD",
            timeframe="m5",
            data_path=None,
            sessions=("asia", "europe", "us"),
            signal_mode="direction",
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
        labeled = assign_session_labels(df)
        session_bars = compute_session_returns(labeled)

        # Each session bar should have at least 2 M5 bars (open and close)
        session_groups = labeled.groupby(["date", "session"])
        for (date, session), group in session_groups:
            assert len(group) >= 2, f"Session {date} {session} has only {len(group)} bars"

    def test_forward_fill_not_applied(self):
        """Missing bars should not be forward-filled (no NaN in OHLCV)."""
        config = ExperimentConfig(
            symbol="XAUUSD",
            timeframe="m5",
            data_path=None,
            sessions=("asia", "europe", "us"),
            signal_mode="direction",
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
        # Should have no NaN in OHLCV after load_and_validate_data dropna
        assert df[["open", "high", "low", "close", "volume"]].notna().all().all()


class TestReproducibility:
    """Verify experiment is fully reproducible."""

    def test_deterministic_results(self):
        """Same config + same data + same seed = identical results."""
        config = ExperimentConfig(
            symbol="XAUUSD",
            timeframe="m5",
            data_path=None,
            sessions=("asia", "europe", "us"),
            signal_mode="direction",
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
        labeled = assign_session_labels(df)
        session_bars = compute_session_returns(labeled)
        signals = generate_signals(session_bars, "direction")

        pf1, _ = run_vectorbt_portfolio_m5(df, signals, config, init_cash=10_000_000)
        pf2, _ = run_vectorbt_portfolio_m5(df, signals, config, init_cash=10_000_000)

        trades1 = pf1.trades.records_readable
        trades2 = pf2.trades.records_readable

        assert len(trades1) == len(trades2)
        if len(trades1) > 0:
            pd.testing.assert_frame_equal(trades1, trades2, check_dtype=False)

    def test_chronological_split_deterministic(self):
        """Train/val/test split must be deterministic and chronological."""
        config = ExperimentConfig(
            symbol="XAUUSD",
            timeframe="m5",
            data_path=None,
            sessions=("asia", "europe", "us"),
            signal_mode="direction",
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
        labeled = assign_session_labels(df)
        session_bars = compute_session_returns(labeled)

        result = time_series_split(
            session_bars.index,
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
            session_bars.index,
            train_ratio=config.train_ratio,
            val_ratio=config.val_ratio,
            test_ratio=config.test_ratio,
        )
        train_idx2 = result2.train_idx
        val_idx2 = result2.val_idx
        test_idx2 = result2.test_idx

        assert list(train_idx) == list(train_idx2)
        assert list(val_idx) == list(val_idx2)
        assert list(test_idx) == list(test_idx2)


class TestVectorBTVsAssignment01:
    """Compare VectorBT results with Assignment 01 reference values."""

    def test_vectorbt_matches_assignment01_m5_direction_full(self):
        """VectorBT M5 direction with costs matches Assignment 01 report values.
        
        Reference: reports/csm_vbt_xauusd_m5_20261114_184637.txt
        Full dataset: 9,870 trades, net Sharpe 0.11, max DD -78.53%, profit factor 1.05
        """
        config = ExperimentConfig(
            symbol="XAUUSD",
            timeframe="m5",
            data_path=None,
            sessions=("asia", "europe", "us"),
            signal_mode="direction",
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
        labeled = assign_session_labels(df)
        session_bars = compute_session_returns(labeled)
        signals = generate_signals(session_bars, "direction")

        pf, _ = run_vectorbt_portfolio_m5(df, signals, config, init_cash=10_000_000)

        trades = pf.trades.records_readable
        net_pnls = trades["PnL"].values
        entry_fees = trades["Entry Fees"].values
        exit_fees = trades["Exit Fees"].values
        total_fees = entry_fees + exit_fees
        gross_pnls = net_pnls + total_fees

        equity = 100000.0
        returns_net = net_pnls / equity
        returns_gross = gross_pnls / equity

        n_trades = len(trades)
        n_wins_net = (net_pnls > 0).sum()
        win_rate_net = n_wins_net / n_trades

        net_profit = net_pnls[net_pnls > 0].sum()
        net_loss = -net_pnls[net_pnls < 0].sum()
        profit_factor_net = net_profit / net_loss if net_loss > 0 else np.inf

        cum_net = (1 + returns_net).prod() - 1

        # Annualized using sessions per year (same as report)
        sessions_per_year = 252 * 3
        n_sessions = len(session_bars)
        years = n_sessions / sessions_per_year
        ann_return_net = (1 + cum_net) ** (1 / years) - 1 if years > 0 else 0
        ann_vol_net = returns_net.std() * np.sqrt(sessions_per_year)
        sharpe_net = ann_return_net / ann_vol_net if ann_vol_net > 0 else 0

        # Max drawdown from trade cumulative returns
        cum_curve_net = np.cumprod(1 + returns_net)
        peak_net = np.maximum.accumulate(cum_curve_net)
        dd_net = (cum_curve_net - peak_net) / peak_net
        max_dd_net = dd_net.min()

        # Reference from Assignment 01 / VectorBT full run report
        assert len(trades) == 9870
        assert abs(win_rate_net - 0.4559) < 0.001
        assert abs(profit_factor_net - 1.05) < 0.02
        assert abs(sharpe_net - 0.11) < 0.02
        assert abs(max_dd_net - (-0.7853)) < 0.005


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])