"""
Tests for Task 1: Kill-Switch State Persistence
"""
import pytest
import os
import json
from mars.apps.trading.system.vol_scaled_system import RiskManager


class TestKillSwitchPersistence:
    """Task 1: Kill-switch state survives process restart and requires manual reset."""

    def test_kill_switch_survives_restart(self, tmp_path):
        """Trigger kill-switch, restart RiskManager, verify it stays halted."""
        kill_switch_file = str(tmp_path / "risk_kill_switch.json")

        equity = 100000
        risk_manager = RiskManager(kill_switch_file=kill_switch_file)
        risk_manager.reset_daily(equity)
        risk_manager.peak_equity = equity
        risk_manager.current_equity = equity

        # Trigger kill-switch by breaching drawdown
        risk_manager.update_pnl(-20000)  # 20% loss
        risk_manager.reset_daily(risk_manager.current_equity)
        current_dd = (risk_manager.peak_equity - risk_manager.current_equity) / risk_manager.peak_equity
        can_trade, violations = risk_manager.check_limits()

        assert can_trade is False
        assert risk_manager.kill_switch_halted is True
        assert risk_manager.kill_switch_drawdown_at_trigger == pytest.approx(0.20)

        # Verify state file was created
        assert os.path.exists(risk_manager.KILL_SWITCH_FILE)
        with open(risk_manager.KILL_SWITCH_FILE) as f:
            state = json.load(f)
        assert state['halted'] is True
        assert state['drawdown_at_trigger'] == pytest.approx(0.20)
        assert state['requires_manual_reset'] is True

        # --- SIMULATE PROCESS RESTART ---
        # Create new RiskManager instance (fresh process) with same file
        risk_manager2 = RiskManager(kill_switch_file=risk_manager.KILL_SWITCH_FILE)
        risk_manager2.reset_daily(equity)
        risk_manager2.peak_equity = equity
        risk_manager2.current_equity = equity

        # Verify state was loaded
        assert risk_manager2.kill_switch_halted is True
        assert risk_manager2.kill_switch_drawdown_at_trigger == pytest.approx(0.20)
        assert risk_manager2.kill_switch_requires_manual_reset is True

        # System must still be halted - no auto-resume
        can_trade, violations = risk_manager2.check_limits()
        assert can_trade is False
        assert any("KILL-SWITCH ACTIVE" in v for v in violations)

        # Try to open position - must be rejected
        can_open, reason = risk_manager2.can_open_position('XAUUSD', 10000, equity)
        assert can_open is False
        assert "KILL-SWITCH ACTIVE" in reason

        print("✅ Test 1 PASSED: Kill-switch survives restart, system stays halted")

    def test_manual_reset_clears_halt(self, tmp_path):
        """Manual reset clears halt and resumes trading."""
        kill_switch_file = str(tmp_path / "risk_kill_switch.json")

        equity = 100000
        risk_manager = RiskManager(kill_switch_file=kill_switch_file)
        risk_manager.reset_daily(equity)
        risk_manager.peak_equity = equity
        risk_manager.current_equity = equity

        # Trigger kill-switch
        risk_manager.update_pnl(-20000)
        risk_manager.reset_daily(risk_manager.current_equity)
        risk_manager.check_limits()

        assert risk_manager.kill_switch_halted is True

        # Manual reset (operator action)
        risk_manager.manual_reset_kill_switch()

        # Verify kill-switch cleared
        assert risk_manager.kill_switch_halted is False
        assert risk_manager.kill_switch_requires_manual_reset is False
        assert risk_manager.kill_switch_drawdown_at_trigger == 0.0
        assert risk_manager.kill_switch_triggered_at is None

        # Re-select tier for the session (reset_daily clears tier lock)
        risk_manager.reset_daily(risk_manager.current_equity)
        risk_manager.reset_weekly(risk_manager.current_equity)
        risk_manager.monthly_pnl = 0.0
        risk_manager.select_tier_for_equity(risk_manager.current_equity)

        # System should now allow trading
        can_trade, violations = risk_manager.check_limits()
        assert can_trade is True
        assert len(violations) == 0

        # Can open position
        can_open, reason = risk_manager.can_open_position('XAUUSD', 10000, equity)
        assert can_open is True
        assert reason == "OK"

        # Verify state persisted (file updated)
        with open(risk_manager.KILL_SWITCH_FILE) as f:
            state = json.load(f)
        assert state['halted'] is False
        assert state['requires_manual_reset'] is False

        print("✅ Test 2 PASSED: Manual reset clears halt, trading resumes")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])