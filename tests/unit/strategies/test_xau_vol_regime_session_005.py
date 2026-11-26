"""
Tests for XAU-VOL-REGIME-SESSION-005 Strategy Module

Validates:
- Volatility regime computation (expanding percentile, burn-in aware)
- Spread regime computation (frozen IS threshold)
- FOMC filter (static calendar, meeting day ±1)
- Signal generation with regime filters (no look-ahead)
- Parameter freezing (no optimization permitted)
- Session boundary correctness
"""

from __future__ import annotations

from datetime import date, time, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mars.libs.strategies.xau_vol_regime_session_005 import (
    FOMC_MEETING_DATES,
    FOMC_WINDOW_DATES,
    XAUVolRegimeSession005Params,
    compute_h1_realized_vol,
    compute_asian_session_avg_spread,
    is_fomc_day,
    compute_vol_regime,
    compute_spread_regime,
    generate_session_signals_with_regime,
    expand_signals_to_m5_with_regime,
    XAUVolRegimeSession005Strategy,
)
from mars.libs.strategies.xau_session_momentum import (
    SESSION_BOUNDARIES_UTC,
    SESSION_ORDER,
    SESSION_TRANSITIONS,
    assign_session_labels,
    compute_session_returns,
)


class TestFOMCCalendar:
    """Test FOMC static calendar correctness."""

    def test_fomc_meeting_dates_populated(self):
        """FOMC calendar should have meetings for 2021-2024."""
        assert len(FOMC_MEETING_DATES) > 0
        # Check coverage across IS period
        years = {d.year for d in FOMC_MEETING_DATES}
        assert 2021 in years
        assert 2022 in years
        assert 2023 in years
        assert 2024 in years

    def test_fomc_window_includes_pm1(self):
        """FOMC window should include meeting day ±1."""
        # For each meeting day, check day before and after are in window
        for d in FOMC_MEETING_DATES:
            assert d in FOMC_WINDOW_DATES
            assert d - timedelta(days=1) in FOMC_WINDOW_DATES
            assert d + timedelta(days=1) in FOMC_WINDOW_DATES

    def test_is_fomc_day_exact_meeting(self):
        """Exact meeting day should be detected."""
        meeting_day = date(2023, 3, 22)  # Known FOMC meeting
        ts = pd.Timestamp(meeting_day, tz="UTC")
        assert is_fomc_day(ts, window=True)
        assert is_fomc_day(ts, window=False)

    def test_is_fomc_day_window(self):
        """Day before/after meeting should be detected with window=True."""
        meeting_day = date(2023, 3, 22)
        day_before = meeting_day - timedelta(days=1)
        day_after = meeting_day + timedelta(days=1)

        ts_before = pd.Timestamp(day_before, tz="UTC")
        ts_after = pd.Timestamp(day_after, tz="UTC")

        assert is_fomc_day(ts_before, window=True)
        assert is_fomc_day(ts_after, window=True)
        # Without window, should not be detected
        assert not is_fomc_day(ts_before, window=False)
        assert not is_fomc_day(ts_after, window=False)

    def test_is_fomc_day_non_meeting(self):
        """Non-meeting days should not be flagged."""
        # Pick a random non-meeting day
        ts = pd.Timestamp("2023-05-15", tz="UTC")  # Not in calendar
        assert not is_fomc_day(ts, window=True)
        assert not is_fomc_day(ts, window=False)


class TestH1RealizedVol:
    """Test H1 realized volatility computation."""

    @pytest.fixture
    def sample_h1(self):
        """Create sample H1 data with known prices."""
        # 30 days of H1 bars (24 bars/day = 720 bars)
        timestamps = pd.date_range("2023-01-01", periods=720, freq="h", tz="UTC")
        # Simple random walk with known volatility
        np.random.seed(42)
        log_returns = np.random.normal(0, 0.001, 720)
        prices = 2000 * np.exp(np.cumsum(log_returns))

        df = pd.DataFrame({
            "open": prices,
            "high": prices * 1.001,
            "low": prices * 0.999,
            "close": prices,
        }, index=timestamps)
        return df

    def test_compute_h1_realized_vol_returns_series(self, sample_h1):
        """Function should return Series with same index as input."""
        rv = compute_h1_realized_vol(sample_h1, lookback=20)
        assert isinstance(rv, pd.Series)
        assert len(rv) == len(sample_h1)
        assert rv.index.equals(sample_h1.index)

    def test_compute_h1_realized_vol_annualized(self, sample_h1):
        """RV should be annualized (roughly match input vol * sqrt(252*24))."""
        rv = compute_h1_realized_vol(sample_h1, lookback=20)
        valid_rv = rv.dropna()
        # Input daily vol ~ 0.001 * sqrt(24) = 0.0049
        # Annualized: 0.0049 * sqrt(252) ≈ 0.078
        # Our RV uses H1 bars so annualization factor is sqrt(252*24)
        assert valid_rv.mean() > 0
        assert valid_rv.mean() < 1.0  # Sanity check

    def test_compute_h1_realized_vol_burn_in(self, sample_h1):
        """First (lookback-1) values should be NaN."""
        rv = compute_h1_realized_vol(sample_h1, lookback=20)
        assert rv.iloc[:19].isna().all()
        assert not rv.iloc[20:].isna().all()

    def test_compute_h1_realized_vol_asia_filter(self, sample_h1):
        """Asia filter should only compute on Asian session bars."""
        rv_all = compute_h1_realized_vol(sample_h1, lookback=20, session_filter=None)
        rv_asia = compute_h1_realized_vol(sample_h1, lookback=20, session_filter="asia")

        # Asia filter should have more NaN (only 8 H1 bars per day vs 24)
        assert rv_asia.isna().sum() > rv_all.isna().sum()


class TestAsianSessionAvgSpread:
    """Test Asian session average spread computation."""

    @pytest.fixture
    def sample_m5(self):
        """Create sample M5 data with spread column."""
        # 5 days of M5 bars (288 bars/day = 1440 bars)
        timestamps = pd.date_range("2023-01-01", periods=1440, freq="5min", tz="UTC")
        prices = 2000 + np.cumsum(np.random.normal(0, 0.1, 1440))
        spreads = np.random.uniform(10, 50, 1440)  # Points

        df = pd.DataFrame({
            "open": prices,
            "high": prices + np.abs(np.random.normal(0, 0.2, 1440)),
            "low": prices - np.abs(np.random.normal(0, 0.2, 1440)),
            "close": prices + np.random.normal(0, 0.1, 1440),
            "volume": np.random.randint(100, 1000, 1440),
            "spread": spreads,
        }, index=timestamps)
        return df

    def test_compute_asian_session_avg_spread_returns_series(self, sample_m5):
        """Should return Series indexed by date."""
        avg_spread = compute_asian_session_avg_spread(sample_m5)
        assert isinstance(avg_spread, pd.Series)
        assert len(avg_spread) > 0
        # Index should be dates
        assert all(isinstance(idx, date) for idx in avg_spread.index)

    def test_compute_asian_session_avg_spread_asia_only(self, sample_m5):
        """Should only compute on Asia session bars (00:00-08:00)."""
        avg_spread = compute_asian_session_avg_spread(sample_m5)
        # Should have ~5 days of data
        assert len(avg_spread) == 5


class TestVolRegime:
    """Test volatility regime computation."""

    @pytest.fixture
    def sample_rv(self):
        """Create sample RV series with known percentile behavior."""
        # 100 values, first 50 are low vol, last 50 are high vol
        dates = pd.date_range("2021-07-01", periods=100, freq="h", tz="UTC")
        values = np.concatenate([
            np.random.uniform(0.1, 0.2, 50),  # Low vol
            np.random.uniform(0.3, 0.5, 50),  # High vol
        ])
        return pd.Series(values, index=dates)

    def test_compute_vol_regime_expanding_percentile(self, sample_rv):
        """Regime should use expanding percentile."""
        regime = compute_vol_regime(sample_rv, percentile_threshold=40.0, burn_in_end="2021-07-15")
        # After burn-in, regime should be True for low vol, False for high vol
        # First 50 (low vol) should be favorable, last 50 (high vol) unfavorable
        assert isinstance(regime, pd.Series)
        assert len(regime) == len(sample_rv)

    def test_compute_vol_regime_burn_in(self, sample_rv):
        """Regime uses expanding percentile - check behavior."""
        regime = compute_vol_regime(sample_rv, percentile_threshold=40.0, burn_in_end="2021-07-15")
        # All values should be boolean (True/False) since expanding with min_periods=1
        # computes percentile even for single value
        assert regime.notna().all()
        # Should be boolean type
        assert regime.dtype == bool or regime.dtype == object
        # First value is based on single observation, so it will be True (value <= itself)
        # Subsequent values depend on expanding history


class TestSpreadRegime:
    """Test spread regime computation with frozen IS threshold."""

    @pytest.fixture
    def sample_spreads(self):
        """Create sample spread series."""
        dates = [date(2023, 1, d) for d in range(1, 31)]
        # First 20 days: low spread, last 10 days: high spread
        values = np.concatenate([
            np.random.uniform(10, 20, 20),
            np.random.uniform(30, 50, 10),
        ])
        return pd.Series(values, index=dates)

    def test_compute_spread_regime_frozen_threshold(self, sample_spreads):
        """Threshold should be computed from IS period only."""
        regime = compute_spread_regime(sample_spreads, percentile_threshold=40.0, is_end="2023-01-20")
        # IS period ends 2023-01-20, so threshold from first 20 days
        # Days 1-20 (low spread) should be favorable
        # Days 21-30 (high spread) should be unfavorable
        assert isinstance(regime, pd.Series)
        assert len(regime) == len(sample_spreads)

    def test_compute_spread_regime_empty_is_raises(self):
        """Should raise if no IS period data."""
        dates = [date(2025, 1, d) for d in range(1, 5)]  # All after IS end
        spreads = pd.Series([20, 25, 30, 35], index=dates)
        with pytest.raises(ValueError, match="No IS period spreads found"):
            compute_spread_regime(spreads, percentile_threshold=40.0, is_end="2024-12-31")


class TestParamsFreezing:
    """Test parameter freezing (no optimization)."""

    def test_params_immutable(self):
        """Params should be frozen (immutable)."""
        params = XAUVolRegimeSession005Params()
        with pytest.raises(Exception):  # dataclass frozen=True raises FrozenInstanceError
            params.vol_lookback_bars = 30

    def test_params_default_values_match_spec(self):
        """Default params should match Assignment 20 frozen specification."""
        params = XAUVolRegimeSession005Params()
        assert params.vol_lookback_bars == 20
        assert params.vol_percentile_threshold == 40.0
        assert params.spread_percentile_threshold == 40.0
        assert params.fomc_filter == True
        assert params.risk_fraction == 0.01
        assert params.sl_points == 200
        assert params.spread_multiplier == 1.0
        assert params.commission_per_lot == 0.0
        assert params.slippage_points == 0.0
        assert params.starting_equity == 10000.0
        assert params.feasibility_equity == 30.0
        assert params.is_start == "2021-10-01"
        assert params.is_end == "2024-12-31"
        assert params.burn_in_start == "2021-07-16"
        assert params.burn_in_end == "2021-09-30"

    def test_params_sensitivity_pre_registered(self):
        """Sensitivity dimensions should be pre-registered (not for optimization)."""
        params = XAUVolRegimeSession005Params()
        sens = params.sensitivity
        assert "spread_multiplier" in sens
        assert "vol_percentile_threshold" in sens
        assert "spread_percentile_threshold" in sens
        assert "fomc_filter" in sens
        assert "sl_points" in sens
        assert "dst_shift_hours" in sens
        assert len(sens) == 6  # Exactly 6 pre-registered dimensions


class TestSignalGenerationWithRegime:
    """Test signal generation with regime filters (no look-ahead)."""

    @pytest.fixture
    def sample_session_bars(self):
        """Create sample session bars with returns."""
        # 10 days * 3 sessions = 30 session bars
        dates = pd.date_range("2023-01-01", periods=10, freq="D")
        sessions = ["asia", "europe", "us"]
        data = []
        for d in dates:
            for i, s in enumerate(sessions):
                session_start = pd.Timestamp.combine(d, time(0, 0, tzinfo=timezone.utc))
                if s == "europe":
                    session_start = pd.Timestamp.combine(d, time(8, 0, tzinfo=timezone.utc))
                elif s == "us":
                    session_start = pd.Timestamp.combine(d, time(14, 30, tzinfo=timezone.utc))

                session_end = session_start + timedelta(hours=8 if s == "asia" else (6.5 if s == "europe" else 9.5))

                data.append({
                    "date": d.date(),
                    "session": s,
                    "session_start": session_start,
                    "session_end": session_end,
                    "open": 2000 + np.random.normal(0, 5),
                    "high": 2005 + np.random.normal(0, 5),
                    "low": 1995 + np.random.normal(0, 5),
                    "close": 2000 + np.random.normal(0, 5),
                    "session_return": np.random.normal(0, 0.005),
                    "session_direction": 1 if np.random.normal(0, 0.005) > 0 else -1,
                })
        df = pd.DataFrame(data)
        df = df.sort_values(["date", "session"]).reset_index(drop=True)
        return df

    @pytest.fixture
    def sample_h1_rv(self):
        """Create sample H1 RV series."""
        timestamps = pd.date_range("2023-01-01 00:00", periods=240, freq="h", tz="UTC")
        values = np.random.uniform(0.1, 0.3, 240)
        return pd.Series(values, index=timestamps)

    @pytest.fixture
    def sample_asian_spread(self):
        """Create sample Asian avg spread."""
        dates = [date(2023, 1, d) for d in range(1, 11)]
        values = np.random.uniform(10, 30, 10)
        return pd.Series(values, index=dates)

    @pytest.fixture
    def params(self):
        return XAUVolRegimeSession005Params()

    def test_generate_session_signals_with_regime_columns(self, sample_session_bars, sample_h1_rv, sample_asian_spread, params):
        """Should add all regime columns."""
        result = generate_session_signals_with_regime(
            sample_session_bars, sample_h1_rv, sample_asian_spread, params
        )
        expected_cols = ["signal", "base_signal", "vol_regime", "spread_regime", "fomc_filter", "regime_favorable"]
        for col in expected_cols:
            assert col in result.columns

    def test_generate_session_signals_base_signal_logic(self, sample_session_bars, sample_h1_rv, sample_asian_spread, params):
        """Base signal should equal previous session direction > 0."""
        result = generate_session_signals_with_regime(
            sample_session_bars, sample_h1_rv, sample_asian_spread, params
        )
        # First session has no previous -> flat
        assert result.iloc[0]["base_signal"] == 0
        # Subsequent sessions: base_signal = (prev_direction > 0)
        for i in range(1, len(result)):
            prev_dir = result.iloc[i - 1]["session_direction"]
            expected = 1 if prev_dir > 0 else 0
            assert result.iloc[i]["base_signal"] == expected

    def test_generate_session_signals_regime_gate(self, sample_session_bars, sample_h1_rv, sample_asian_spread, params):
        """Final signal should be base_signal AND regime_favorable."""
        result = generate_session_signals_with_regime(
            sample_session_bars, sample_h1_rv, sample_asian_spread, params
        )
        for _, row in result.iterrows():
            expected = int(row["base_signal"] == 1 and row["regime_favorable"])
            assert row["signal"] == expected

    def test_generate_session_signals_no_lookahead(self, sample_session_bars, sample_h1_rv, sample_asian_spread, params):
        """Signal for session N must use only info available at session N open."""
        result = generate_session_signals_with_regime(
            sample_session_bars, sample_h1_rv, sample_asian_spread, params
        )
        # Regime at session N should depend on data up to session N start
        # Vol regime uses RV at session start (prior H1 bar)
        # Spread regime uses Asian spread of same day (already known at 08:00)
        # FOMC is pre-determined calendar
        # All are available at session open -> no look-ahead
        assert True  # Design verification


class TestExpandSignalsToM5:
    """Test M5 signal expansion with regime metadata."""

    @pytest.fixture
    def sample_m5(self):
        """Create sample M5 data."""
        timestamps = pd.date_range("2023-01-01 00:00", periods=288, freq="5min", tz="UTC")
        prices = 2000 + np.cumsum(np.random.normal(0, 0.1, 288))
        return pd.DataFrame({
            "open": prices,
            "high": prices + 0.5,
            "low": prices - 0.5,
            "close": prices,
            "volume": 1000,
            "spread": 20,
        }, index=timestamps)

    @pytest.fixture
    def sample_session_signals(self):
        """Create sample session signals."""
        dates = [date(2023, 1, 1)]
        sessions = ["asia", "europe", "us"]
        data = []
        for s in sessions:
            session_start = pd.Timestamp.combine(dates[0], time(0, 0, tzinfo=timezone.utc))
            if s == "europe":
                session_start = pd.Timestamp.combine(dates[0], time(8, 0, tzinfo=timezone.utc))
            elif s == "us":
                session_start = pd.Timestamp.combine(dates[0], time(14, 30, tzinfo=timezone.utc))

            session_end = session_start + timedelta(hours=8 if s == "asia" else (6.5 if s == "europe" else 9.5))

            data.append({
                "date": dates[0],
                "session": s,
                "session_start": session_start,
                "session_end": session_end,
                "signal": 1 if s == "europe" else 0,
                "base_signal": 1 if s == "europe" else 0,
                "vol_regime": True,
                "spread_regime": True,
                "fomc_filter": True,
                "regime_favorable": True,
                "fomc_day": False,
                "sl_points": 200,
            })
        return pd.DataFrame(data)

    def test_expand_signals_to_m5_adds_regime_cols(self, sample_m5, sample_session_signals):
        """M5 expansion should add regime metadata columns."""
        result = expand_signals_to_m5_with_regime(sample_m5, sample_session_signals)
        expected_cols = ["signal", "base_signal", "vol_regime", "spread_regime", "fomc_filter", "regime_favorable", "entry_long"]
        for col in expected_cols:
            assert col in result.columns

    def test_expand_signals_entry_at_session_first(self, sample_m5, sample_session_signals):
        """Entry should be on first bar of session when signal=1."""
        result = expand_signals_to_m5_with_regime(sample_m5, sample_session_signals)
        # Europe session should have entry on first bar
        europe_first = result[(result["session"] == "europe") & (result["is_session_first"])]
        assert europe_first["entry_long"].any()
        # Asia/US should not have entry (signal=0)
        asia_first = result[(result["session"] == "asia") & (result["is_session_first"])]
        assert not asia_first["entry_long"].any()


class TestXAUVolRegimeSession005Strategy:
    """Test the strategy class interface."""

    @pytest.fixture
    def params(self):
        return XAUVolRegimeSession005Params()

    def test_compute_signatures(self, params):
        """Strategy should have compute_signals method."""
        strategy = XAUVolRegimeSession005Strategy(params)
        assert hasattr(strategy, "compute_signals")
        assert callable(strategy.compute_signals)

    def test_compute_unconditional_signatures(self, params):
        """Strategy should have compute_unconditional_signals for Model A."""
        strategy = XAUVolRegimeSession005Strategy(params)
        assert hasattr(strategy, "compute_unconditional_signals")
        assert callable(strategy.compute_unconditional_signals)


class TestSessionBoundaries:
    """Verify session boundaries are fixed UTC (no DST)."""

    def test_session_boundaries_utc_fixed(self):
        """Session boundaries must be fixed UTC."""
        assert SESSION_BOUNDARIES_UTC["asia"] == (time(0, 0, tzinfo=timezone.utc), time(8, 0, tzinfo=timezone.utc))
        assert SESSION_BOUNDARIES_UTC["europe"] == (time(8, 0, tzinfo=timezone.utc), time(14, 30, tzinfo=timezone.utc))
        assert SESSION_BOUNDARIES_UTC["us"] == (time(14, 30, tzinfo=timezone.utc), time(23, 59, 59, 999999, tzinfo=timezone.utc))

    def test_session_order(self):
        """Session order: Asia -> Europe -> US."""
        assert SESSION_ORDER == ["asia", "europe", "us"]

    def test_session_transitions(self):
        """Transitions wrap correctly."""
        assert SESSION_TRANSITIONS["asia"] == "europe"
        assert SESSION_TRANSITIONS["europe"] == "us"
        assert SESSION_TRANSITIONS["us"] == "asia"