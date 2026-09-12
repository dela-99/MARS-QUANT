"""
Tests for Task 2: Consolidated Per-Trade and Concurrent Risk Limits
Verifies both limits are enforced from RiskManager (single source of truth).
"""
import pytest
import pandas as pd
import tempfile
import os
from mars.apps.trading.system.vol_scaled_system import (
    RiskManager, TradeExecutor, TradeConfig, VolScaledSizer, SizingConfig
)


def make_risk_manager(equity, tmpdir=None):
    """Create isolated RiskManager with unique kill-switch file."""
    kill_switch_file = os.path.join(tmpdir, "risk_kill_switch.json") if tmpdir else None
    return RiskManager(kill_switch_file=kill_switch_file)


class TestConsolidatedRiskLimits:
    """Task 2: Both risk limits enforced from RiskManager (single source of truth)."""

    def test_per_trade_risk_limit_enforced_via_risk_manager(self, tmp_path):
        """Verify tier's per-trade risk limit is enforced by RiskManager, not executor."""
        equity = 100000
        tmpdir = str(tmp_path)
        risk_manager = make_risk_manager(equity, tmpdir=tmpdir)
        risk_manager.reset_daily(equity)
        risk_manager.select_tier_for_equity(equity)
        risk_manager.peak_equity = equity
        risk_manager.current_equity = equity

        sizing_config = SizingConfig(target_vol=0.15, max_leverage=3.0, min_leverage=0.01, kelly_fraction=0.5)
        sizer = VolScaledSizer(sizing_config, garch_variant="garch")
        executor = TradeExecutor(equity, risk_manager, sizer)

        # At $100k equity, tier has risk_pct_per_trade=1%
        tier = risk_manager.get_current_tier()
        assert tier["risk_pct_per_trade"] == 0.01

        # Test 1: Trade that EXCEEDS tier's risk limit but UNDER ceiling -> ALLOWED with MIN_LOT_OVERRIDE
        # stop_distance = 50 points, risk_per_contract = 5000
        # position_size = 1.0 lot -> total_risk = 5000 (5% of 100k) -> under 15% ceiling
        config_exceeds_tier = TradeConfig(
            symbol='XAUUSD', signal=1, entry_price=2000.0, stop_price=1950.0,
            take_profit=2100.0, position_size=1.0, max_hold_hours=24,
            risk_pct=0.01, entry_time=pd.Timestamp('2024-01-01 10:00:00', tz='UTC')
        )

        success = executor.open_position(config_exceeds_tier)
        assert success is True, "Trade exceeding tier's per-trade risk but UNDER ceiling should be ALLOWED with MIN_LOT_OVERRIDE"

        # Test 2: Trade that EXCEEDS ceiling (15%) -> REJECTED
        # stop_distance = 200 points, risk_per_contract = 20000
        # position_size = 1.0 lot -> total_risk = 20000 (20% of 100k) -> exceeds 15% ceiling
        config_exceeds_ceiling = TradeConfig(
            symbol='XAUUSD', signal=1, entry_price=2000.0, stop_price=1800.0,
            take_profit=2300.0, position_size=1.0, max_hold_hours=24,
            risk_pct=0.01, entry_time=pd.Timestamp('2024-01-01 10:00:00', tz='UTC')
        )

        success = executor.open_position(config_exceeds_ceiling)
        assert success is False, "Trade exceeding ceiling (15%) should be REJECTED"

        # Test 3: Trade that PASSES tier's risk limit -> ALLOWED
        config_passes = TradeConfig(
            symbol='XAUUSD', signal=1, entry_price=2000.0, stop_price=1990.0,
            take_profit=2020.0, position_size=0.5, max_hold_hours=24,
            risk_pct=0.01, entry_time=pd.Timestamp('2024-01-01 10:00:00', tz='UTC')
        )

        success = executor.open_position(config_passes)
        assert success is True, "Trade within tier's per-trade risk should be allowed"
        assert 'XAUUSD' in executor.open_positions

        # Verify check_per_trade_risk method behavior
        # Trade under ceiling but over tier limit -> ALLOWED with MIN_LOT_OVERRIDE
        can_open, reason = risk_manager.check_per_trade_risk(config_exceeds_tier, equity)
        assert can_open is True, f"check_per_trade_risk should allow trade under ceiling, got: {reason}"
        assert "MIN_LOT_OVERRIDE" in reason

        # Trade exceeding ceiling -> REJECTED
        can_open2, reason2 = risk_manager.check_per_trade_risk(config_exceeds_ceiling, equity)
        assert can_open2 is False, f"check_per_trade_risk should reject trade exceeding ceiling, got: {reason2}"
        assert "exceeds" in reason2.lower() and "15%" in reason2

        # Trade within tier limit -> ALLOWED
        can_open2, reason2 = risk_manager.check_per_trade_risk(config_passes, equity)
        assert can_open2 is True
        assert reason2 == "OK"

        print("✅ Test 1 PASSED: Per-trade risk limit with MIN_LOT_OVERRIDE enforced by RiskManager")

    def test_concurrent_exposure_cap_enforced_via_risk_manager(self, tmp_path):
        """Verify tier's concurrent exposure cap is enforced by RiskManager."""
        equity = 100000
        tmpdir = str(tmp_path)
        risk_manager = make_risk_manager(equity, tmpdir=tmpdir)
        risk_manager.reset_daily(equity)
        risk_manager.select_tier_for_equity(equity)
        risk_manager.peak_equity = equity
        risk_manager.current_equity = equity

        sizing_config = SizingConfig(target_vol=0.15, max_leverage=3.0, min_leverage=0.01, kelly_fraction=0.5)
        sizer = VolScaledSizer(sizing_config, garch_variant="garch")
        executor = TradeExecutor(equity, risk_manager, sizer)

        # At $100k equity, tier has max_concurrent_trades=6
        tier = risk_manager.get_current_tier()
        assert tier["max_concurrent_trades"] == 6

        # Test 1: Position under cap should pass can_open_position
        can_open, reason = risk_manager.can_open_position('XAUUSD', 20000.0, equity)
        assert can_open is True
        assert reason == "OK"

        # Test 2: Simulate having max_concurrent_trades open
        # Add 6 positions manually
        for i in range(6):
            risk_manager.current_positions[f'XAUUSD_{i}'] = {
                "symbol": "XAUUSD", "entry_price": 2000.0, "position_size": 0.5
            }

        # Try to open 7th - should fail
        can_open2, reason2 = risk_manager.can_open_position('XAUUSD', 20000.0, equity)
        assert can_open2 is False
        assert "Max concurrent trades (6)" in reason2

        print("✅ Test 2 PASSED: Concurrent exposure cap enforced by RiskManager")

    def test_both_limits_jointly_enforced_single_config(self, tmp_path):
        """Verify both limits are enforced from single RiskManager config - no drift possible."""
        equity = 100000
        tmpdir = str(tmp_path)
        risk_manager = make_risk_manager(equity, tmpdir=tmpdir)
        risk_manager.reset_daily(equity)
        risk_manager.select_tier_for_equity(equity)
        risk_manager.peak_equity = equity
        risk_manager.current_equity = equity

        # Both limits defined in tier table - single source of truth
        tier = risk_manager.get_current_tier()
        assert tier["risk_pct_per_trade"] == 0.01  # 1% per trade
        assert tier["max_concurrent_trades"] == 6  # 6 trades max

        # Verify executor delegates BOTH checks to risk_manager
        sizing_config = SizingConfig(target_vol=0.15, max_leverage=3.0, min_leverage=0.01, kelly_fraction=0.5)
        sizer = VolScaledSizer(sizing_config, garch_variant="garch")
        executor = TradeExecutor(equity, risk_manager, sizer)

        # open_position calls both risk_manager methods
        import inspect
        source = inspect.getsource(executor.open_position)
        assert "risk_manager.can_open_position" in source
        assert "risk_manager.check_per_trade_risk" in source
        assert "0.01" not in source or "self.equity * 0.01" not in source, \
            "Hardcoded 1% found in executor - should use risk_manager config"

        print("✅ Test 3 PASSED: Both limits enforced from single RiskManager config")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])