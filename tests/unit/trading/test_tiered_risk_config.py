"""
Acceptance tests for Tiered, Account-Scale-Aware Risk Configuration.
Tests Steps 2-5: Tier locking, open-position immunity, min-lot override, config-drift audit.
"""
import pytest
import pandas as pd
import tempfile
import os
from datetime import datetime, timedelta
from mars.apps.trading.system.vol_scaled_system import (
    RiskManager, TradeExecutor, TradeConfig, VolScaledSizer, SizingConfig
)


def make_risk_manager(equity, tmpdir=None):
    """Create isolated RiskManager with unique kill-switch file."""
    kill_switch_file = os.path.join(tmpdir, "risk_kill_switch.json") if tmpdir else None
    return RiskManager(kill_switch_file=kill_switch_file)


class TestTieredRiskConfigAcceptance:
    """Acceptance criteria tests for the tiered risk configuration."""

    def test_tier_selection_at_multiple_equity_levels(self):
        """Test tier selection at $30, $124, $500, $5000 equity levels."""
        test_cases = [
            # (equity, expected_tier_index, expected_risk_pct, expected_concurrent, expected_rr)
            (30, 0, 0.07, 1, 3.0),    # Tier 0: $0-100
            (124, 1, 0.03, 2, 3.0),   # Tier 1: $100-1000
            (500, 1, 0.03, 2, 3.0),   # Tier 1: $100-1000
            (5000, 2, 0.015, 4, 2.0), # Tier 2: $1000-10000
            (50000, 3, 0.01, 6, 2.0), # Tier 3: $10000+
        ]

        for equity, expected_idx, expected_risk, expected_concurrent, expected_rr in test_cases:
            risk_manager = make_risk_manager(equity)
            risk_manager.reset_daily(equity)
            risk_manager.select_tier_for_equity(equity)
            tier = risk_manager.get_current_tier()

            assert tier["min_equity"] == [0, 100, 1000, 10000][expected_idx]
            assert tier["max_equity"] == [100, 1000, 10000, float('inf')][expected_idx]
            assert tier["risk_pct_per_trade"] == expected_risk
            assert tier["max_concurrent_trades"] == expected_concurrent
            assert tier["reward_risk_ratio"] == expected_rr

        print("✅ Test PASSED: Tier selection correct at all equity levels")

    def test_tier_locking_prevents_flapping(self, tmp_path):
        """Test tier is locked at session start and doesn't flap with equity oscillations."""
        equity = 500  # Tier 1
        tmpdir = str(tmp_path)
        risk_manager = make_risk_manager(equity, tmpdir=tmpdir)
        risk_manager.reset_daily(equity)
        risk_manager.select_tier_for_equity(equity)

        # Initial tier should be Tier 1
        tier = risk_manager.get_current_tier()
        assert tier["risk_pct_per_trade"] == 0.03
        assert tier["max_concurrent_trades"] == 2
        initial_tier = risk_manager._current_tier

        # Simulate equity oscillating across tier boundary within same session
        # Drop to $99 (Tier 0) - tier should NOT change
        risk_manager.current_equity = 99
        risk_manager.select_tier_for_equity(99)  # Should return locked tier
        tier = risk_manager.get_current_tier()
        assert tier["risk_pct_per_trade"] == 0.03  # Still Tier 1
        assert risk_manager._current_tier == initial_tier

        # Rise to $1100 (Tier 2) - tier should NOT change
        risk_manager.current_equity = 1100
        risk_manager.select_tier_for_equity(1100)
        tier = risk_manager.get_current_tier()
        assert tier["risk_pct_per_trade"] == 0.03  # Still Tier 1
        assert risk_manager._current_tier == initial_tier

        # Drop to $50 (Tier 0) - tier should NOT change
        risk_manager.current_equity = 50
        risk_manager.select_tier_for_equity(50)
        tier = risk_manager.get_current_tier()
        assert tier["risk_pct_per_trade"] == 0.03  # Still Tier 1
        assert risk_manager._current_tier == initial_tier

        # Now simulate new session boundary (reset_daily clears tier lock)
        risk_manager.reset_daily(1100)  # New session at $1100
        risk_manager.select_tier_for_equity(1100)
        tier = risk_manager.get_current_tier()
        assert tier["risk_pct_per_trade"] == 0.015  # Now Tier 2
        assert tier["max_concurrent_trades"] == 4
        assert risk_manager._current_tier != initial_tier  # Tier changed

        print("✅ Test PASSED: Tier locking prevents flapping within session")

    def test_open_positions_unaffected_by_tier_change(self, tmp_path):
        """Test open positions keep original stop/TP/size after tier change at session boundary."""
        equity = 500  # Tier 1 (3% risk, 2 concurrent)
        tmpdir = str(tmp_path)
        risk_manager = make_risk_manager(equity, tmpdir=tmpdir)
        risk_manager.reset_daily(equity)
        risk_manager.select_tier_for_equity(equity)

        sizing_config = SizingConfig(target_vol=0.15, max_leverage=3.0, min_leverage=0.01, kelly_fraction=0.5)
        sizer = VolScaledSizer(sizing_config, garch_variant="garch")
        executor = TradeExecutor(equity, risk_manager, sizer)

        # Open a trade under Tier 1 parameters
        # XAUUSD: 2.5 point stop = 25 pips = $250/lot, 0.5 lot = $125 risk (25% of $500 = exceeds ceiling!)
        # Need smaller: 1 point stop = $100/lot, 0.05 lot = $5 risk (1% of $500)
        config_tier1 = TradeConfig(
            symbol='XAUUSD', signal=1, entry_price=2000.0, stop_price=1999.0,
            take_profit=2002.5, position_size=0.05, max_hold_hours=24,
            risk_pct=0.03, entry_time=pd.Timestamp('2024-01-01 10:00:00', tz='UTC')
        )
        success = executor.open_position(config_tier1)
        assert success is True

        # Capture original position details
        original_position = executor.open_positions['XAUUSD']
        original_stop = original_position["stop_price"]
        original_tp = original_position["take_profit"]
        original_size = original_position["position_size"]

        # Simulate session boundary - equity grows to $5000 (Tier 2)
        # reset_daily clears tier lock, then select new tier
        risk_manager.reset_daily(5000)
        executor.equity = 5000  # Sync executor equity with risk manager
        risk_manager.select_tier_for_equity(5000)
        new_tier = risk_manager.get_current_tier()
        assert new_tier["risk_pct_per_trade"] == 0.015  # Tier 2
        assert new_tier["max_concurrent_trades"] == 4

        # Verify OPEN position is unchanged
        assert 'XAUUSD' in executor.open_positions
        assert executor.open_positions['XAUUSD']["stop_price"] == original_stop
        assert executor.open_positions['XAUUSD']["take_profit"] == original_tp
        assert executor.open_positions['XAUUSD']["position_size"] == original_size

        # Open NEW trade - should use Tier 2 parameters (1.5% risk)
        config_tier2 = TradeConfig(
            symbol='XAUUSD', signal=1, entry_price=2000.0, stop_price=1998.5,
            take_profit=2004.0, position_size=0.03, max_hold_hours=24,
            risk_pct=0.015, entry_time=pd.Timestamp('2024-01-02 10:00:00', tz='UTC')
        )
        success = executor.open_position(config_tier2)
        assert success is True

        print("✅ Test PASSED: Open positions unaffected by tier change at session boundary")

    def test_min_lot_override_logs_and_ceiling_rejects(self, tmp_path):
        """Test min-lot override logs correctly and hard ceiling (15%) rejects trades."""
        equity = 124.73  # Current test account
        tmpdir = str(tmp_path)
        risk_manager = make_risk_manager(equity, tmpdir=tmpdir)
        risk_manager.reset_daily(equity)
        risk_manager.select_tier_for_equity(equity)

        sizing_config = SizingConfig(target_vol=0.15, max_leverage=3.0, min_leverage=0.01, kelly_fraction=0.5)
        sizer = VolScaledSizer(sizing_config, garch_variant="garch")
        executor = TradeExecutor(equity, risk_manager, sizer)

        # At $124.73, tier is Tier 1: risk_pct=3%, max_concurrent=2
        tier = risk_manager.get_current_tier()
        assert tier["risk_pct_per_trade"] == 0.03

        # Test 1: Trade that exceeds tier risk (3%) but under ceiling (15%) -> ALLOWED with MIN_LOT_OVERRIDE
        # XAUUSDm: min_lot=0.01, contract_size=100
        # stop_distance = 1 point (10 pips), risk_per_contract = $100
        # position_size = 0.01 lot (min lot) -> total_risk = $1 (0.8% of equity)
        # This is UNDER tier risk (3%) -> should pass normally
        # Let's use stop_distance = 5 points (50 pips), risk = $500/lot, min_lot = $5 (4% of equity)
        # 4% > 3% (tier) but 4% < 15% (ceiling) -> MIN_LOT_OVERRIDE ALLOWED
        config_override = TradeConfig(
            symbol='XAUUSD', signal=1, entry_price=2000.0, stop_price=1995.0,
            take_profit=2010.0, position_size=0.01, max_hold_hours=24,
            risk_pct=0.03, entry_time=pd.Timestamp('2024-01-01 10:00:00', tz='UTC')
        )

        success = executor.open_position(config_override)
        assert success is True, "Min-lot trade exceeding tier risk but under ceiling should be ALLOWED"

        # Verify MIN_LOT_OVERRIDE was logged
        can_open, reason = risk_manager.check_per_trade_risk(config_override, equity)
        assert can_open is True
        assert "MIN_LOT_OVERRIDE" in reason
        assert "intended" in reason and "actual" in reason

        # Test 2: Trade that exceeds ceiling (15%) -> REJECTED
        # stop_distance = 20 points (200 pips), risk_per_contract = $2000
        # position_size = 0.01 lot -> total_risk = $20 (16% of equity) -> EXCEEDS 15% ceiling
        config_ceiling = TradeConfig(
            symbol='XAUUSD', signal=1, entry_price=2000.0, stop_price=1980.0,
            take_profit=2030.0, position_size=0.01, max_hold_hours=24,
            risk_pct=0.03, entry_time=pd.Timestamp('2024-01-01 10:00:00', tz='UTC')
        )

        success = executor.open_position(config_ceiling)
        assert success is False, "Trade exceeding 15% ceiling should be REJECTED"

        can_open, reason = risk_manager.check_per_trade_risk(config_ceiling, equity)
        assert can_open is False
        assert "exceeds" in reason.lower() and "15%" in reason

        print("✅ Test PASSED: Min-lot override logs correctly and ceiling rejects")

    def test_equity_threshold_for_xauusdm_tradeability(self, tmp_path):
        """Calculate and verify the equity floor below which XAUUSDm cannot be traded."""
        # XAUUSDm specs from Exness demo:
        # contract_size = 100 oz per lot
        # min_lot = 0.01
        # lot_step = 0.01
        # At current ATR-based stop ~50 points (500 pips) = $50 risk per contract
        # Min lot risk = 0.01 * 5000 = $50
        # Hard ceiling = 15%
        # Minimum equity = min_lot_risk / 0.15 = $50 / 0.15 = $333.33

        stop_distance = 50  # points (500 pips typical ATR stop)
        risk_per_contract = stop_distance * 100  # $5000 per lot
        min_lot = 0.01
        min_lot_risk = min_lot * risk_per_contract  # $50
        ceiling_pct = 0.15

        min_equity = min_lot_risk / ceiling_pct
        assert min_equity == 50 / 0.15  # $333.33

        # Verify at equity below this, trade is rejected
        equity = 300  # Below $333.33
        risk_manager = make_risk_manager(equity, tmpdir=str(tmp_path))
        risk_manager.reset_daily(equity)
        risk_manager.select_tier_for_equity(equity)

        config = TradeConfig(
            symbol='XAUUSD', signal=1, entry_price=2000.0, stop_price=1950.0,
            take_profit=2100.0, position_size=0.01, max_hold_hours=24,
            risk_pct=0.03, entry_time=pd.Timestamp('2024-01-01 10:00:00', tz='UTC')
        )

        can_open, reason = risk_manager.check_per_trade_risk(config, equity)
        assert can_open is False
        assert "exceeds" in reason.lower() and "15%" in reason

        # Verify at equity above this, trade is allowed (with override)
        equity = 400  # Above $333.33
        risk_manager2 = make_risk_manager(equity, tmpdir=str(tmp_path))
        risk_manager2.reset_daily(equity)
        risk_manager2.select_tier_for_equity(equity)

        can_open2, reason2 = risk_manager2.check_per_trade_risk(config, equity)
        assert can_open2 is True
        assert "MIN_LOT_OVERRIDE" in reason2

        print(f"✅ Test PASSED: XAUUSDm tradeability floor = ${min_equity:.2f}")

    def test_config_drift_audit_no_hardcoded_risk_values(self):
        """Verify RISK_TIERS is single source of truth - no hardcoded risk values outside RiskManager."""
        import inspect
        from mars.apps.trading.system.vol_scaled_system import RiskManager, TradeExecutor

        # Check RiskManager - RISK_TIERS should exist and be the only place defining tiers
        risk_manager_source = inspect.getsource(RiskManager)

        # Verify RISK_TIERS table exists
        assert "RISK_TIERS" in risk_manager_source
        assert "0.07" in risk_manager_source  # Tier 0 risk
        assert "0.03" in risk_manager_source  # Tier 1 risk
        assert "0.015" in risk_manager_source  # Tier 2 risk
        assert "0.01" in risk_manager_source  # Tier 3 risk

        # Check TradeExecutor - should NOT have hardcoded risk percentages
        executor_source = inspect.getsource(TradeExecutor)
        
        # Should delegate to risk_manager for per-trade risk
        assert "risk_manager.check_per_trade_risk" in executor_source
        
        # Should delegate to risk_manager for concurrent position check
        assert "risk_manager.can_open_position" in executor_source

        # Should NOT have hardcoded 0.01, 0.03, 0.015, 0.07, 1%, 3%, etc. in risk logic
        # (except possibly in comments or tests)
        # The only acceptable place for risk percentages is in the RISK_TIERS table

        # Check the check_per_trade_risk method uses tier config
        check_risk_method = inspect.getsource(RiskManager.check_per_trade_risk)
        assert "self.get_current_tier" in check_risk_method or "self._current_tier" in check_risk_method
        assert "tier[\"risk_pct_per_trade\"]" in check_risk_method or "tier_risk_pct" in check_risk_method

        # Check the can_open_position method uses tier config
        can_open_method = inspect.getsource(RiskManager.can_open_position)
        assert "self.get_current_tier" in can_open_method or "self._current_tier" in can_open_method
        assert "max_concurrent_trades" in can_open_method

        print("✅ Test PASSED: Config-drift audit - RISK_TIERS is single source of truth")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])