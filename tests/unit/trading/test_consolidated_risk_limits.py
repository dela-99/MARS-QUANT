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


def make_risk_manager(equity, max_position_pct=1.0, tmpdir=None):
    """Create isolated RiskManager with unique kill-switch file."""
    kill_switch_file = os.path.join(tmpdir, "risk_kill_switch.json") if tmpdir else None
    return RiskManager(
        max_daily_loss_pct=0.02, max_weekly_loss_pct=0.50,
        max_monthly_loss_pct=0.50, max_drawdown_pct=0.15,
        max_position_pct=max_position_pct, max_risk_per_trade_pct=0.01,
        kill_switch_file=os.path.join(tmpdir, "risk_kill_switch.json") if tmpdir else None,
    )


class TestConsolidatedRiskLimits:
    """Task 2: Both risk limits enforced from RiskManager (single source of truth)."""
    
    def test_per_trade_risk_limit_enforced_via_risk_manager(self, tmp_path):
        """Verify 1% per-trade risk limit is enforced by RiskManager, not executor."""
        equity = 100000
        tmpdir = str(tmp_path)
        risk_manager = make_risk_manager(equity, max_position_pct=1.0, tmpdir=tmpdir)
        risk_manager.reset_daily(equity)
        risk_manager.peak_equity = equity
        risk_manager.current_equity = equity
        
        sizing_config = SizingConfig(target_vol=0.15, max_leverage=3.0, min_leverage=0.01, kelly_fraction=0.5)
        sizer = VolScaledSizer(sizing_config, garch_variant="garch")
        executor = TradeExecutor(equity, risk_manager, sizer)
        
        # Test 1: Trade that EXCEEDS 1% per-trade risk should be rejected
        # stop_distance = 50 points, risk_per_contract = 5000
        # position_size = 1.0 lot -> total_risk = 5000 > 1000 (1% of 100k)
        config_exceeds = TradeConfig(
            symbol='XAUUSD', signal=1, entry_price=2000.0, stop_price=1950.0,
            take_profit=2100.0, position_size=1.0, max_hold_hours=24,
            risk_pct=0.01, entry_time=pd.Timestamp('2024-01-01 10:00:00', tz='UTC')
        )
        
        success = executor.open_position(config_exceeds)
        assert success is False, "Trade exceeding 1% per-trade risk should be rejected"
        
        # Test 2: Trade that PASSES 1% per-trade risk should be allowed
        # stop_distance = 10 points, risk_per_contract = 1000
        # position_size = 0.5 lots -> total_risk = 500 < 1000 (1% of 100k)
        config_passes = TradeConfig(
            symbol='XAUUSD', signal=1, entry_price=2000.0, stop_price=1990.0,
            take_profit=2020.0, position_size=0.5, max_hold_hours=24,
            risk_pct=0.01, entry_time=pd.Timestamp('2024-01-01 10:00:00', tz='UTC')
        )
        
        success = executor.open_position(config_passes)
        assert success is True, "Trade within 1% per-trade risk should be allowed"
        assert 'XAUUSD' in executor.open_positions
        
        # Verify the check_per_trade_risk method works correctly
        can_open, reason = risk_manager.check_per_trade_risk(config_exceeds, equity)
        assert can_open is False
        assert "exceeds max 1.0%" in reason
        
        can_open2, reason2 = risk_manager.check_per_trade_risk(config_passes, equity)
        assert can_open2 is True
        assert reason2 == "OK"
        
        print("✅ Test 1 PASSED: Per-trade risk limit (1%) enforced by RiskManager")
    
    def test_concurrent_exposure_cap_enforced_via_risk_manager(self, tmp_path):
        """Verify 30% concurrent exposure cap is enforced by RiskManager."""
        equity = 100000
        tmpdir = str(tmp_path)
        risk_manager = make_risk_manager(equity, max_position_pct=0.30, tmpdir=tmpdir)
        risk_manager.reset_daily(equity)
        risk_manager.peak_equity = equity
        risk_manager.current_equity = equity
        
        sizing_config = SizingConfig(target_vol=0.15, max_leverage=3.0, min_leverage=0.01, kelly_fraction=0.5)
        sizer = VolScaledSizer(sizing_config, garch_variant="garch")
        executor = TradeExecutor(equity, risk_manager, sizer)
        
        # Test 1: Position under 30% cap should pass can_open_position
        can_open, reason = risk_manager.can_open_position('XAUUSD', 20000.0, equity)
        assert can_open is True
        assert reason == "OK"
        
        # Test 2: Position over 30% cap should be rejected
        can_open2, reason2 = risk_manager.can_open_position('XAUUSD', 40000.0, equity)
        assert can_open2 is False
        assert "exceeds max 30.0% of equity" in reason2
        
        print("✅ Test 2 PASSED: Concurrent exposure cap (30%) enforced by RiskManager")
    
    def test_both_limits_jointly_enforced_single_config(self, tmp_path):
        """Verify both limits are enforced from single RiskManager config - no drift possible."""
        equity = 100000
        tmpdir = str(tmp_path)
        risk_manager = make_risk_manager(equity, max_position_pct=0.30, tmpdir=tmpdir)
        risk_manager.reset_daily(equity)
        risk_manager.peak_equity = equity
        risk_manager.current_equity = equity
        
        # Both limits defined in one place - single source of truth
        assert risk_manager.max_risk_per_trade_pct == 0.01  # 1% per trade
        assert risk_manager.max_position_pct == 0.30  # 30% concurrent
        
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