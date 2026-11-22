#!/usr/bin/env python3
"""
Tests for MA-TSM-001 Paper Trading System
"""

import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
import pandas as pd
import numpy as np

from mars.apps.research_lab.ma_tsm_paper_trading import (
    MATSM001FrozenSpec,
    FROZEN_SPEC,
    PaperTradingConfig,
    MATSM001SignalGenerator,
    ForwardTestProtocol,
    FORWARD_TEST_PROTOCOL,
    analyze_30usd_capital_constraint,
)


class TestFrozenSpec:
    """Test that frozen strategy specification is truly immutable."""

    def test_frozen_spec_immutable(self):
        """Verify FROZEN_SPEC cannot be modified."""
        spec = FROZEN_SPEC
        
        # Dataclass with frozen=True should raise FrozenInstanceError
        with pytest.raises(AttributeError):
            spec.sma_period = 100
        
        with pytest.raises(AttributeError):
            spec.symbol = "BTCUSD"
        
        with pytest.raises(AttributeError):
            spec.position_size_lots = 2.0

    def test_frozen_spec_values(self):
        """Verify frozen spec has correct values."""
        assert FROZEN_SPEC.strategy_id == "MA-TSM-001"
        assert FROZEN_SPEC.symbol == "XAUUSD"
        assert FROZEN_SPEC.mt5_symbol == "XAUUSDm"
        assert FROZEN_SPEC.timeframe == "h1"
        assert FROZEN_SPEC.sma_period == 200
        assert FROZEN_SPEC.position_size_lots == 1.0
        assert FROZEN_SPEC.contract_size == 100.0
        assert FROZEN_SPEC.execution_price == "next_bar_open"

    def test_frozen_spec_to_dict(self):
        """Verify frozen spec can be serialized."""
        d = FROZEN_SPEC.to_dict()
        assert isinstance(d, dict)
        assert d['strategy_id'] == "MA-TSM-001"
        assert d['sma_period'] == 200


class TestSignalGenerator:
    """Test signal generation matches backtest logic exactly."""

    @pytest.fixture
    def sample_h1_data(self):
        """Create sample H1 data with known SMA crossover."""
        dates = pd.date_range('2024-01-01', periods=250, freq='h', tz='UTC')
        np.random.seed(42)
        # Create price that crosses SMA at known point
        close = 2000 + np.cumsum(np.random.randn(250) * 0.5)
        # Force a crossover around bar 200
        close[190:210] = np.linspace(1990, 2010, 20)
        
        df = pd.DataFrame({
            'open': close + np.random.randn(250) * 0.1,
            'high': close + np.abs(np.random.randn(250)) * 0.5,
            'low': close - np.abs(np.random.randn(250)) * 0.5,
            'close': close,
            'volume': np.random.randint(100, 1000, 250)
        }, index=dates)
        return df

    def test_signal_generator_initialization(self):
        """Test signal generator initializes correctly."""
        generator = MATSM001SignalGenerator(FROZEN_SPEC)
        assert generator.config == FROZEN_SPEC
        assert generator.min_bars_for_sma == 205  # 200 + 5
        assert generator.last_signal == 0
        assert generator.last_bar_time is None

    def test_signal_generator_update_data(self, sample_h1_data):
        """Test data buffer update."""
        generator = MATSM001SignalGenerator(FROZEN_SPEC)
        generator.update_data(sample_h1_data)
        
        assert generator.data_buffer is not None
        assert len(generator.data_buffer) == len(sample_h1_data)

    def test_signal_generator_compute_signals(self, sample_h1_data):
        """Test signal computation produces expected columns."""
        generator = MATSM001SignalGenerator(FROZEN_SPEC)
        generator.update_data(sample_h1_data)
        signals_df = generator.compute_signals()
        
        assert not signals_df.empty
        assert 'sma' in signals_df.columns
        assert 'entry_signal' in signals_df.columns
        assert 'exit_signal' in signals_df.columns
        assert 'position' in signals_df.columns

    def test_signal_generator_no_lookahead(self, sample_h1_data):
        """Verify signals use shift(1) - no lookahead bias."""
        generator = MATSM001SignalGenerator(FROZEN_SPEC)
        generator.update_data(sample_h1_data)
        signals_df = generator.compute_signals()
        
        # Check that entry_signal at index i uses data from i-1
        # entry_signal = (close > sma) & (close.shift(1) <= sma.shift(1))
        # This means signal at bar i depends on close[i] and close[i-1]
        # The signal is GENERATED at bar i close, for execution at bar i+1 open
        for i in range(1, min(10, len(signals_df))):
            close_now = signals_df['close'].iloc[i]
            sma_now = signals_df['sma'].iloc[i]
            close_prev = signals_df['close'].iloc[i-1]
            sma_prev = signals_df['sma'].iloc[i-1]
            
            expected_entry = (close_now > sma_now) and (close_prev <= sma_prev)
            actual_entry = bool(signals_df['entry_signal'].iloc[i])
            assert actual_entry == expected_entry, f"Mismatch at index {i}"

    def test_get_latest_signal_new_bar_only(self, sample_h1_data):
        """Test that get_latest_signal only returns signal for new completed bar."""
        generator = MATSM001SignalGenerator(FROZEN_SPEC)
        generator.update_data(sample_h1_data)
        
        # First call - should get signal for last completed bar
        signal1 = generator.get_latest_signal()
        
        # Second call immediately - should return empty (same bar)
        signal2 = generator.get_latest_signal()
        
        assert signal2 == {}, "Should not return signal for already-processed bar"
        
        # Verify signal structure if present
        if signal1:
            assert 'signal' in signal1
            assert 'bar_time' in signal1
            assert 'close' in signal1
            assert 'sma' in signal1
            assert 'position' in signal1
            assert signal1['signal'] in (1, -1)


class TestCapitalConstraintAnalysis:
    """Test $30 capital constraint analysis."""

    def test_analysis_runs(self):
        """Verify analysis completes without error."""
        results = analyze_30usd_capital_constraint()
        assert isinstance(results, dict)
        assert 'equity_usd' in results
        assert results['equity_usd'] == 30.0

    def test_tier_0_limits(self):
        """Verify Tier 0 limits are correct."""
        results = analyze_30usd_capital_constraint()
        tier = results['tier_limits']
        assert tier['max_per_trade_risk_pct'] == 0.07
        assert tier['max_aggregate_risk_pct'] == 0.07
        assert tier['max_concurrent_trades'] == 1
        assert tier['max_risk_per_trade_usd'] == 2.10

    def test_backtest_impossible_at_30(self):
        """Verify backtest position size impossible at $30."""
        results = analyze_30usd_capital_constraint()
        feas = results['feasibility_analysis']['1_lot']
        assert feas['within_tier_limit'] == False
        # risk_pct_of_equity is ratio (risk_usd / equity), so $10,000 / $30 = 333.33x
        assert feas['risk_pct_of_equity'] > 10  # 33,333% = 333x equity

    def test_min_lot_catastrophic_impossible(self):
        """Verify min lot with catastrophic stop impossible at $30."""
        results = analyze_30usd_capital_constraint()
        feas = results['feasibility_analysis']['min_lot_catastrophic_stop']
        assert feas['within_tier_limit'] == False
        # $100 / $30 = 3.33x (333%) - exceeds 7% tier limit (0.07x)
        assert feas['risk_pct_of_equity'] > 0.07  # 333% > 7%

    def test_max_allowable_stop_at_min_lot(self):
        """Verify max allowable stop at min lot is ~210 pips."""
        results = analyze_30usd_capital_constraint()
        feas = results['feasibility_analysis']['min_lot_max_allowable_stop']
        assert feas['within_tier_limit'] == True
        assert abs(feas['max_stop_pips'] - 210) <= 5  # ~210 pips

    def test_typical_atr_stop_impossible(self):
        """Verify typical ATR stop impossible at $30 min lot."""
        results = analyze_30usd_capital_constraint()
        feas = results['feasibility_analysis']['min_lot_typical_atr_stop']
        assert feas['within_tier_limit'] == False
        # $7.50 / $30 = 0.25 (25%)
        assert feas['risk_pct_of_equity'] > 0.07  # 25% > 7%

    def test_overall_verdict_incompatible(self):
        """Verify overall verdict says INCOMPATIBLE."""
        results = analyze_30usd_capital_constraint()
        verdict = results['overall_verdict']
        assert verdict['can_trade_at_backtest_size'] == False
        assert verdict['can_trade_at_min_lot_with_strategy_stops'] == False
        assert 'INCOMPATIBLE' in verdict['strategy_compatibility']
        assert verdict['can_trade_at_min_lot_with_reduced_stops'] == True


class TestForwardTestProtocol:
    """Test forward test protocol is immutable and has correct values."""

    def test_protocol_immutable(self):
        """Verify protocol is frozen dataclass."""
        from dataclasses import FrozenInstanceError
        protocol = FORWARD_TEST_PROTOCOL
        
        with pytest.raises(FrozenInstanceError):
            protocol.min_trading_days = 10
        
        with pytest.raises(FrozenInstanceError):
            protocol.min_executed_trades = 5

    def test_protocol_key_thresholds(self):
        """Verify key acceptance thresholds."""
        assert FORWARD_TEST_PROTOCOL.min_trading_days == 60
        assert FORWARD_TEST_PROTOCOL.max_trading_days == 180
        assert FORWARD_TEST_PROTOCOL.min_executed_trades == 15
        assert FORWARD_TEST_PROTOCOL.target_executed_trades == 25
        assert FORWARD_TEST_PROTOCOL.required_uptime_pct == 95.0
        assert FORWARD_TEST_PROTOCOL.max_order_rejection_rate_pct == 5.0
        assert FORWARD_TEST_PROTOCOL.max_failed_order_rate_pct == 2.0
        assert FORWARD_TEST_PROTOCOL.max_slippage_pips == 3.0
        assert FORWARD_TEST_PROTOCOL.kill_switch_trigger_threshold == 0.15
        assert FORWARD_TEST_PROTOCOL.consecutive_loss_halt_threshold == 2

    def test_protocol_to_dict(self):
        """Verify protocol can be serialized."""
        d = FORWARD_TEST_PROTOCOL.to_dict()
        assert isinstance(d, dict)
        assert d['min_trading_days'] == 60
        assert d['min_executed_trades'] == 15


class TestPaperTradingConfig:
    """Test paper trading configuration."""

    def test_default_config(self):
        """Test default configuration values."""
        config = PaperTradingConfig()
        
        assert config.session_name == "ma_tsm_001_paper"
        assert config.account_number == 476944496
        assert config.initial_equity == 100000.0
        assert config.monitor_interval_seconds == 60
        assert config.heartbeat_log_interval_seconds == 300
        assert config.reconciliation_interval_seconds == 3600

    def test_custom_config(self):
        """Test custom configuration."""
        config = PaperTradingConfig(
            session_name="test_session",
            initial_equity=50000.0,
            monitor_interval_seconds=30,
        )
        
        assert config.session_name == "test_session"
        assert config.initial_equity == 50000.0
        assert config.monitor_interval_seconds == 30


if __name__ == "__main__":
    pytest.main([__file__, "-v"])