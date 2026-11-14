"""
Tests for Cross-Session Momentum Experiment (CSM-001)

Validates:
- Signal timing (no look-ahead bias)
- Session boundary correctness
- Look-ahead prevention
- Data integrity
"""

from __future__ import annotations

from datetime import time, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mars.apps.research_lab.cross_session_momentum import (
    SESSION_BOUNDARIES_UTC,
    SESSION_ORDER,
    SESSION_TRANSITIONS,
    CostModel,
    ExperimentConfig,
    assign_session_labels,
    compute_session_returns,
    generate_signals,
    load_and_validate_data,
    run_experiment,
    simulate_trades,
)
from mars.libs.utils.paths import ProjectPaths


class TestSessionBoundaries:
    """Test session assignment and boundary logic."""
    
    def test_session_boundaries_utc_fixed(self):
        """Verify session boundaries are fixed UTC (no DST)."""
        assert SESSION_BOUNDARIES_UTC["asia"] == (time(0, 0, tzinfo=timezone.utc), time(8, 0, tzinfo=timezone.utc))
        assert SESSION_BOUNDARIES_UTC["europe"] == (time(8, 0, tzinfo=timezone.utc), time(14, 30, tzinfo=timezone.utc))
        assert SESSION_BOUNDARIES_UTC["us"] == (time(14, 30, tzinfo=timezone.utc), time(23, 59, 59, 999999, tzinfo=timezone.utc))
    
    def test_session_order(self):
        """Session order is Asia -> Europe -> US."""
        assert SESSION_ORDER == ["asia", "europe", "us"]
    
    def test_session_transitions(self):
        """Session transitions wrap correctly."""
        assert SESSION_TRANSITIONS["asia"] == "europe"
        assert SESSION_TRANSITIONS["europe"] == "us"
        assert SESSION_TRANSITIONS["us"] == "asia"
    
    def test_assign_session_labels(self):
        """Test session label assignment at boundaries."""
        # Create test timestamps at session boundaries
        timestamps = pd.DatetimeIndex([
            "2024-01-01 00:00:00+00:00",  # Asia open
            "2024-01-01 07:55:00+00:00",  # Asia close
            "2024-01-01 08:00:00+00:00",  # Europe open
            "2024-01-01 14:25:00+00:00",  # Europe close
            "2024-01-01 14:30:00+00:00",  # US open
            "2024-01-01 23:55:00+00:00",  # US close
        ], tz="UTC")
        
        df = pd.DataFrame(
            {"open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 1000},
            index=timestamps,
        )
        
        result = assign_session_labels(df)
        
        assert result.loc[timestamps[0], "session"] == "asia"
        assert result.loc[timestamps[1], "session"] == "asia"
        assert result.loc[timestamps[2], "session"] == "europe"
        assert result.loc[timestamps[3], "session"] == "europe"
        assert result.loc[timestamps[4], "session"] == "us"
        assert result.loc[timestamps[5], "session"] == "us"
    
    def test_compute_session_returns(self):
        """Test session return computation."""
        # Create 2 days of M5 data with known prices
        timestamps = pd.DatetimeIndex([
            # Day 1 Asia
            "2024-01-01 00:00:00+00:00",
            "2024-01-01 00:05:00+00:00",
            "2024-01-01 07:55:00+00:00",
            # Day 1 Europe
            "2024-01-01 08:00:00+00:00",
            "2024-01-01 14:25:00+00:00",
            # Day 1 US
            "2024-01-01 14:30:00+00:00",
            "2024-01-01 23:55:00+00:00",
            # Day 2 Asia
            "2024-01-02 00:00:00+00:00",
            "2024-01-02 07:55:00+00:00",
        ], tz="UTC")
        
        # Prices: Asia day 1: 100 -> 102 (+2%), Europe: 102 -> 101 (-1%), US: 101 -> 103 (+2%)
        prices = [100, 101, 102, 102, 101, 101, 103, 103, 104]
        
        df = pd.DataFrame(
            {
                "open": prices,
                "high": [p + 0.5 for p in prices],
                "low": [p - 0.5 for p in prices],
                "close": prices,
                "volume": [1000] * len(prices),
            },
            index=timestamps,
        )
        
        session_bars = compute_session_returns(df)
        
        assert len(session_bars) == 4  # 2 days * 2 sessions (last day only Asia)
        # Check Day 1 Asia return
        asia_d1 = session_bars[(session_bars["date"] == pd.Timestamp("2024-01-01").date()) & (session_bars["session"] == "asia")]
        assert len(asia_d1) == 1
        # Return = (102 - 100) / 100 = 0.02
        assert abs(asia_d1["session_return"].values[0] - 0.02) < 1e-6
        
        # Check Day 1 Europe return
        eur_d1 = session_bars[(session_bars["date"] == pd.Timestamp("2024-01-01").date()) & (session_bars["session"] == "europe")]
        assert len(eur_d1) == 1
        # Return = (101 - 102) / 102 = -0.0098
        assert abs(eur_d1["session_return"].values[0] - (-1/102)) < 1e-6


class TestSignalTimingNoLookahead:
    """Critical tests: signal must not use future data."""
    
    def test_signal_uses_previous_session_only(self):
        """Signal for session N uses only session N-1 data."""
        # Create 3 sessions with known returns
        timestamps = pd.DatetimeIndex([
            "2024-01-01 00:00:00+00:00",  # Asia open
            "2024-01-01 07:55:00+00:00",  # Asia close
            "2024-01-01 08:00:00+00:00",  # Europe open
            "2024-01-01 14:25:00+00:00",  # Europe close
            "2024-01-01 14:30:00+00:00",  # US open
            "2024-01-01 23:55:00+00:00",  # US close
        ], tz="UTC")
        
        # Asia: +1%, Europe: -1%, US: +1%
        prices = [100, 101, 101, 100, 100, 101]
        
        df = pd.DataFrame(
            {"open": prices, "high": [p+1 for p in prices], "low": [p-1 for p in prices], "close": prices, "volume": [1000]*6},
            index=timestamps,
        )
        
        session_bars = compute_session_returns(df)
        session_bars = generate_signals(session_bars, signal_mode="direction")
        
        # Session 0 (Asia): no previous session -> signal = 0
        assert session_bars.iloc[0]["signal"] == 0
        
        # Session 1 (Europe): signal based on Asia return (+1% -> long)
        assert session_bars.iloc[1]["signal"] == 1
        
        # Session 2 (US): signal based on Europe return (-1% -> flat)
        assert session_bars.iloc[2]["signal"] == 0
        
        # Verify signal references previous session
        assert session_bars.iloc[1]["prev_session_return"] == session_bars.iloc[0]["session_return"]
        assert session_bars.iloc[2]["prev_session_return"] == session_bars.iloc[1]["session_return"]
    
    def test_signal_observable_at_session_open(self):
        """Signal becomes observable at the OPEN of the target session."""
        # This test verifies the signal for session N is available at session N open
        # (i.e., after session N-1 close)
        timestamps = pd.DatetimeIndex([
            "2024-01-01 00:00:00+00:00", "2024-01-01 07:55:00+00:00",  # Asia
            "2024-01-01 08:00:00+00:00", "2024-01-01 14:25:00+00:00",  # Europe
        ], tz="UTC")
        
        prices = [100, 101, 101, 102]  # Asia +1%, Europe +1%
        
        df = pd.DataFrame(
            {"open": prices, "high": [p+1 for p in prices], "low": [p-1 for p in prices], "close": prices, "volume": [1000]*4},
            index=timestamps,
        )
        
        session_bars = compute_session_returns(df)
        session_bars = generate_signals(session_bars, signal_mode="direction")
        
        # Europe session signal (based on Asia) should be available at Europe open (08:00)
        # This is the key no-look-ahead check: we don't use Europe's close to trade Europe
        europe_row = session_bars[session_bars["session"] == "europe"].iloc[0]
        assert europe_row["signal"] == 1  # Based on Asia's +1%
        # The signal uses prev_session_return (Asia), not current session's return
        assert europe_row["prev_session_return"] > 0
        assert europe_row["session_return"] > 0  # Europe also positive, but signal doesn't use this


class TestDataIntegrity:
    """Test data loading and validation."""
    
    def test_load_m5_data(self):
        """Verify M5 data loads correctly."""
        paths = ProjectPaths.from_root()
        data_path = paths.processed_data / "xauusd" / "m5" / "v1.0.0" / "data.parquet"
        
        if not data_path.exists():
            pytest.skip("M5 data not available")
        
        df = load_and_validate_data(ExperimentConfig(timeframe="m5"), paths)
        
        assert len(df) > 100000  # Should have substantial data
        assert df.index.tz is not None
        assert str(df.index.tz) == "UTC"
        assert all(c in df.columns for c in ["open", "high", "low", "close", "volume"])
        assert not df[["open", "high", "low", "close"]].isna().any().any()
    
    def test_no_duplicate_timestamps(self):
        """Verify no duplicate timestamps in data."""
        paths = ProjectPaths.from_root()
        data_path = paths.processed_data / "xauusd" / "m5" / "v1.0.0" / "data.parquet"
        
        if not data_path.exists():
            pytest.skip("M5 data not available")
        
        df = load_and_validate_data(ExperimentConfig(timeframe="m5"), paths)
        
        assert not df.index.duplicated().any()


class TestCostModel:
    """Test transaction cost calculations."""
    
    def test_cost_model_zero(self):
        """Zero cost model returns zero."""
        cm = CostModel(spread_pips=0, commission_per_lot=0, slippage_pips=0)
        assert cm.per_round_trip_usd_per_lot() == 0.0
    
    def test_cost_model_calculation(self):
        """Test cost calculation with known values."""
        # 1 pip = $10 per lot on XAUUSD (100 oz * $0.01)
        # spread=1 pip, commission=$0.5, slippage=0.5 pip/side
        cm = CostModel(spread_pips=1.0, commission_per_lot=0.5, slippage_pips=0.5)
        cost = cm.per_round_trip_usd_per_lot()
        # spread: 1 * 10 = $10
        # slippage: 2 * 0.5 * 10 = $10 (entry + exit)
        # commission: $0.5
        # total: $20.50
        assert abs(cost - 20.50) < 0.01


class TestExperimentConfig:
    """Test experiment configuration."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = ExperimentConfig()
        
        assert config.symbol == "XAUUSD"
        assert config.timeframe == "m5"
        assert config.sessions == ("asia", "europe", "us")
        assert config.signal_mode == "direction"
        assert config.position_size_pct == 1.0
        assert config.max_leverage == 1.0
        assert config.train_ratio == 0.70
        assert config.val_ratio == 0.15
        assert config.test_ratio == 0.15
    
    def test_split_ratios_sum_to_one(self):
        """Split ratios must sum to 1.0."""
        config = ExperimentConfig(train_ratio=0.6, val_ratio=0.2, test_ratio=0.2)
        assert abs(config.train_ratio + config.val_ratio + config.test_ratio - 1.0) < 1e-6


class TestSimulation:
    """Test trade simulation logic."""
    
    def test_simulate_trades_basic(self):
        """Test basic trade simulation."""
        # Create session bars with signals
        session_bars = pd.DataFrame({
            "session_start": pd.to_datetime([
                "2024-01-01 00:00:00+00:00",
                "2024-01-01 08:00:00+00:00",
                "2024-01-01 14:30:00+00:00",
            ], utc=True),
            "session": ["asia", "europe", "us"],
            "session_open": [100.0, 101.0, 100.5],
            "session_close": [101.0, 100.5, 102.0],
            "signal": [0, 1, 1],  # Flat Asia, Long Europe, Long US
            "session": ["asia", "europe", "us"],
        })
        
        config = ExperimentConfig(position_size_pct=1.0, cost_model=CostModel())
        df_bars = pd.DataFrame()  # Not used in current implementation
        
        trades = simulate_trades(session_bars, config, df_bars)
        
        # Asia: signal=0 -> no trade
        assert trades.iloc[0]["is_trade"] == False
        assert trades.iloc[0]["net_pnl"] == 0
        
        # Europe: signal=1, entry=101, exit=100.5 -> loss
        assert trades.iloc[1]["is_trade"] == True
        assert trades.iloc[1]["entry_price"] == 101.0
        assert trades.iloc[1]["exit_price"] == 100.5
        # P&L = (100.5 - 101) * 1 * 100 = -$50 per lot
        
        # US: signal=1, entry=100.5, exit=102 -> profit
        assert trades.iloc[2]["is_trade"] == True
        assert trades.iloc[2]["entry_price"] == 100.5
        assert trades.iloc[2]["exit_price"] == 102.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])