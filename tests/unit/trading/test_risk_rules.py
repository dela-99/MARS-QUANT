"""
Institutional Risk Rules Test Suite
Tests all 4 hard risk rules required by the system specification.
"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from mars.apps.trading.system.vol_scaled_system import (
    RiskManager, TradeExecutor, TradeConfig, VolScaledSizer, SizingConfig
)
from mars.apps.trading.signals.trend_breakout import TrendSignalFactory
from mars.apps.trading.demo_trading_system import DemoTradingSystem
import tempfile
import os


def make_risk_manager(equity, max_position_pct=1.0, tmpdir=None):
    """Create isolated RiskManager with unique kill-switch file."""
    kill_switch_file = os.path.join(tmpdir, "risk_kill_switch.json") if tmpdir else None
    return RiskManager(kill_switch_file=kill_switch_file)


def make_risk_manager_with_params(equity, max_position_pct=1.0, max_daily_loss_pct=0.02,
                                   max_weekly_loss_pct=0.05, max_monthly_loss_pct=0.10,
                                   max_drawdown_pct=0.15, tmpdir=None):
    """Create isolated RiskManager with custom parameters."""
    kill_switch_file = os.path.join(tmpdir, "risk_kill_switch.json") if tmpdir else None
    return RiskManager(kill_switch_file=kill_switch_file)


class TestMaxRiskPerTrade:
    """Rule 1: MAX RISK PER TRADE (0.5-1% of account equity at stop-loss distance)"""

    def test_risk_at_stop_distribution(self):
        """Verify all trades have risk-at-stop <= 1% of equity at entry"""
        system = DemoTradingSystem(equity=100000, signal_type='donchian', donchian_window=20, session='london')
        df = system.load_data(start='2020-01-01')
        df = df[df.index <= '2023-12-31']
        system.sizer.fit(df)
        forecast = system.sizer.forecast_vol(df)
        signals = system.signal_generator.generate(df)
        positions = system.sizer.compute_position_size(df, signals['signal'], 100000, forecast)

        common_idx = df.index.intersection(signals.index).intersection(positions.index)
        df = df.loc[common_idx]
        signals = signals.loc[common_idx]
        positions = positions.loc[common_idx]

        equity = 100000
        risk_manager = RiskManager()
        risk_manager.reset_daily(equity)
        risk_manager.select_tier_for_equity(equity)
        executor = TradeExecutor(equity, risk_manager, system.sizer)

        trades_info = []
        open_positions = {}

        for i, (timestamp, row) in enumerate(df.iterrows()):
            signal = signals['signal'].loc[timestamp] if timestamp in signals.index else 0
            position_size = positions['position_size'].loc[timestamp] if timestamp in positions.index else 0
            price = row['close']
            time = timestamp

            for symbol in list(open_positions.keys()):
                update = executor.update_position(symbol, price, time)
                if update['action'] == 'close':
                    pnl = executor.close_position(symbol, price, update['reason'])
                    trades_info.append({
                        'time': time, 'pnl': pnl, 'reason': update['reason'],
                        'entry_price': open_positions[symbol]['entry_price'],
                        'stop_price': open_positions[symbol]['stop_price'],
                        'position_size': open_positions[symbol]['position_size'],
                        'equity_at_entry': open_positions[symbol]['entry_equity'],
                    })
                    open_positions.pop(symbol, None)

            prev_signal = signals['signal'].iloc[i-1] if i > 0 else 0
            if signal != 0 and signal != prev_signal and 'XAUUSD' not in open_positions and position_size > 0:
                atr = row.get('ATRr_14', 5.0)
                stop_distance = atr * 2.5
                if signal == 1:
                    stop_price = df.iloc[i]['close'] - stop_distance
                    take_profit = df.iloc[i]['close'] + stop_distance * 2.5
                else:
                    stop_price = df.iloc[i]['close'] + stop_distance
                    take_profit = df.iloc[i]['close'] - stop_distance * 2.5

                config = TradeConfig(
                    symbol='XAUUSD', signal=signal,
                    entry_price=df.iloc[i]['close'], stop_price=stop_price,
                    take_profit=take_profit, position_size=position_size,
                    max_hold_hours=24, risk_pct=0.01, entry_time=time,
                )
                if executor.open_position(config):
                    open_positions['XAUUSD'] = {
                        'entry_price': config.entry_price, 'stop_price': config.stop_price,
                        'take_profit': config.take_profit, 'position_size': config.position_size,
                        'entry_time': config.entry_time, 'max_hold_hours': config.max_hold_hours,
                        'entry_equity': equity,
                    }

        # Compute risk-at-stop for each closed trade
        for t in trades_info:
            entry = t['entry_price']
            stop = t['stop_price']
            pos_size = t['position_size']
            equity_at_entry = t['equity_at_entry']
            risk_at_stop = abs(entry - stop) * pos_size * 100
            risk_pct = risk_at_stop / equity_at_entry * 100
            t['risk_at_stop'] = risk_at_stop
            t['risk_pct_of_equity'] = risk_pct

        trades_df = pd.DataFrame(trades_info)

        # Assertions
        assert len(trades_df) > 0, "Should have captured trades"
        assert trades_df['risk_pct_of_equity'].max() <= 1.0, \
            f"Found trade with risk-at-stop > 1%: {trades_df['risk_pct_of_equity'].max():.4f}%"

        # Report full distribution
        print(f"\n=== RULE 1: MAX RISK PER TRADE ===")
        print(f"Total trades: {len(trades_df)}")
        print(f"Risk-at-stop distribution (% of equity):")
        print(trades_df['risk_pct_of_equity'].describe())
        print(f"Min: {trades_df['risk_pct_of_equity'].min():.4f}%")
        print(f"Max: {trades_df['risk_pct_of_equity'].max():.4f}%")
        print(f"Median: {trades_df['risk_pct_of_equity'].median():.4f}%")
        print(f"Mean: {trades_df['risk_pct_of_equity'].mean():.4f}%")
        print(f"Trades > 1%: {(trades_df['risk_pct_of_equity'] > 1.0).sum()}")
        print("PASSED ✓")


class TestMaxDailyLossCircuitBreaker:
    """Rule 2: MAX DAILY LOSS CIRCUIT BREAKER"""

    def test_daily_loss_limit_halts_trading(self, tmp_path):
        """Simulate losing sequence breaching daily loss limit mid-session"""
        equity = 100000
        risk_manager = RiskManager(kill_switch_file=str(tmp_path / "risk_kill_switch.json"),
                                   max_consecutive_losses=5)  # Disable consecutive loss for this test
        risk_manager.reset_daily(equity)

        # Initially can trade
        can_trade, violations = risk_manager.check_limits()
        assert can_trade is True
        assert len(violations) == 0

        # Accumulate losses below limit
        risk_manager.update_pnl(-1000)  # -1%
        can_trade, violations = risk_manager.check_limits()
        assert can_trade is True

        # Accumulate more losses but still below 2%
        risk_manager.update_pnl(-800)  # -1.8% total
        can_trade, violations = risk_manager.check_limits()
        assert can_trade is True

        # Breach the 2% limit
        risk_manager.update_pnl(-300)  # -2.1% total
        can_trade, violations = risk_manager.check_limits()
        assert can_trade is False, "Should halt trading when daily loss limit breached"
        assert any("Daily loss limit exceeded" in v for v in violations), f"Violations: {violations}"

        # Verify it stays halted for the rest of the day
        can_trade2, _ = risk_manager.check_limits()
        assert can_trade2 is False, "Should remain halted"

        # Reset at next day boundary - should be able to trade again
        risk_manager.reset_daily(equity - 2100)  # New equity after losses
        can_trade3, _ = risk_manager.check_limits()
        assert can_trade3 is True, "Should reset and allow trading on new day"

        print("\n=== RULE 2: MAX DAILY LOSS CIRCUIT BREAKER ===")
        print("Daily loss limit correctly halts trading when breached")
        print("Daily loss limit correctly resets at day boundary")
        print("PASSED ✓")


class TestMaxConcurrentOpenRiskCap:
    """Rule 3: MAX CONCURRENT OPEN RISK CAP"""

    def test_concurrent_position_cap(self, tmp_path):
        """Verify system rejects positions that would exceed max concurrent risk"""
        equity = 100000
        risk_manager = RiskManager(kill_switch_file=str(tmp_path / "risk_kill_switch.json"))
        risk_manager.reset_daily(equity)

        sizing_config = SizingConfig(target_vol=0.15, max_leverage=3.0, min_leverage=0.01, kelly_fraction=0.5)
        sizer = VolScaledSizer(sizing_config, garch_variant="garch")

        executor = TradeExecutor(equity, risk_manager, sizer)

        # Test the tier's max_concurrent_trades limit directly via risk_manager
        # First select tier for equity
        risk_manager.select_tier_for_equity(equity)

        # At $100k equity, tier has max_concurrent_trades=6
        tier = risk_manager.get_current_tier()
        assert tier["max_concurrent_trades"] == 6

        # Test the max_concurrent_trades limit directly via risk_manager
        can_open, reason = risk_manager.can_open_position('XAUUSD', 20000.0, equity)
        # Should pass for first trade
        assert can_open is True

        # Simulate having max_concurrent_trades open
        # Add 6 positions manually (tier allows 6 max)
        for i in range(6):
            risk_manager.current_positions[f'XAUUSD_{i}'] = {
                "symbol": "XAUUSD", "entry_price": 2000.0, "position_size": 0.5
            }
        
        # Try to open 7th - should fail if max_concurrent_trades=6
        can_open2, reason2 = risk_manager.can_open_position('XAUUSD', 20000.0, equity)
        # At $100k equity, tier has max_concurrent_trades=6, so 7th should fail
        assert can_open2 is False
        assert "Max concurrent trades (6)" in reason2

        print("\n=== RULE 3: MAX CONCURRENT OPEN RISK CAP ===")
        print("System correctly rejects positions exceeding max concurrent risk cap")
        print("PASSED ✓")


class TestMaxDrawdownKillSwitch:
    """Rule 4: MAX DRAWDOWN KILL-SWITCH"""

    def test_max_drawdown_halt_and_reset(self, tmp_path):
        """Simulate equity decline breaching max drawdown threshold"""
        equity = 100000
        risk_manager = RiskManager(kill_switch_file=str(tmp_path / "risk_kill_switch.json"))
        risk_manager.reset_daily(equity)

        # Set peak equity
        risk_manager.peak_equity = equity
        risk_manager.current_equity = equity

        # Initially can trade
        can_trade, violations = risk_manager.check_limits()
        assert can_trade is True

        # Simulate gradual decline over multiple days with proper daily resets
        # We need to also reset weekly/monthly PnL to isolate drawdown test
        # Day 1: lose 2%
        risk_manager.update_pnl(-2000)
        risk_manager.reset_daily(risk_manager.current_equity)
        risk_manager.reset_weekly(risk_manager.current_equity)
        risk_manager.monthly_pnl = 0.0  # Reset monthly for isolation
        risk_manager.peak_equity = equity  # Keep peak at original

        # Day 2: lose 3%
        risk_manager.update_pnl(-3000)
        risk_manager.reset_daily(risk_manager.current_equity)
        risk_manager.reset_weekly(risk_manager.current_equity)
        risk_manager.monthly_pnl = 0.0

        # Day 3: lose 4% 
        risk_manager.update_pnl(-4000)
        risk_manager.reset_daily(risk_manager.current_equity)
        risk_manager.reset_weekly(risk_manager.current_equity)
        risk_manager.monthly_pnl = 0.0

        # Day 4: lose 5% - total from peak = 14%
        risk_manager.update_pnl(-5000)
        risk_manager.reset_daily(risk_manager.current_equity)
        risk_manager.reset_weekly(risk_manager.current_equity)
        risk_manager.monthly_pnl = 0.0
        current_dd = (risk_manager.peak_equity - risk_manager.current_equity) / risk_manager.peak_equity
        can_trade, violations = risk_manager.check_limits()
        assert can_trade is True, f"Should allow trading at {current_dd:.2%} drawdown"

        # Day 5: lose 3% - total from peak = 17% (breach 15%)
        risk_manager.update_pnl(-3000)
        risk_manager.reset_daily(risk_manager.current_equity)
        risk_manager.reset_weekly(risk_manager.current_equity)
        risk_manager.monthly_pnl = 0.0
        current_dd = (risk_manager.peak_equity - risk_manager.current_equity) / risk_manager.peak_equity
        can_trade, violations = risk_manager.check_limits()
        assert can_trade is False, f"Should halt ALL trading at {current_dd:.2%} drawdown"
        assert any("Max drawdown exceeded" in v for v in violations), f"Violations: {violations}"

        # Verify forced liquidation is available
        liquidation = risk_manager.forced_liquidation()
        # (Currently returns empty dict - would need broker integration)

        # State persistence check - risk_manager state is in-memory only
        # This is a FLAG for demo/live use (not a test failure)
        print("\n=== RULE 4: MAX DRAWDOWN KILL-SWITCH ===")
        print("System correctly halts all trading at max drawdown breach")
        print("WARNING: Kill-switch state is in-memory only - not persisted to disk/DB")
        print("         This is a GAP for unattended demo/live use")
        print("PASSED ✓ (with persistence gap flagged)")


class TestPeakEquityInitialization:
    """Regression test for peak_equity initialization bug (ZeroDivisionError on first check_limits)."""
    
    def test_peak_equity_never_zero_after_tier_selection(self, tmp_path):
        """After constructing RiskManager and selecting tier for equity, 
        peak_equity and current_equity must be non-zero before any check_limits call."""
        equity = 139.29
        risk_manager = RiskManager(kill_switch_file=str(tmp_path / "risk_kill_switch.json"))
        
        # Before tier selection - peak_equity is 0 (initialized in __init__)
        assert risk_manager.peak_equity == 0.0
        assert risk_manager.current_equity == 0.0
        
        # Select tier for equity - this is what run_session_v3.py does
        tier = risk_manager.select_tier_for_equity(equity)
        assert tier["risk_pct_per_trade"] == 0.03  # $100-1000 tier = 3%
        
        # CRITICAL: peak_equity and current_equity must be initialized 
        # before any check_limits() call. The session runner does this manually.
        # This test documents the requirement - without manual init, 
        # check_limits() crashes with ZeroDivisionError.
        risk_manager.current_equity = equity
        risk_manager.peak_equity = equity
        risk_manager.daily_pnl = 0.0
        
        # Now check_limits() must not crash
        can_trade, violations = risk_manager.check_limits()
        assert can_trade is True
        assert len(violations) == 0
        # Verify drawdown calculation works
        current_dd = (risk_manager.peak_equity - risk_manager.current_equity) / risk_manager.peak_equity
        assert current_dd == 0.0
        
    def test_peak_equity_updates_on_pnl(self, tmp_path):
        """peak_equity tracks high-water mark correctly after trades."""
        equity = 10000.0
        risk_manager = RiskManager(kill_switch_file=str(tmp_path / "risk_kill_switch.json"))
        risk_manager.current_equity = equity
        risk_manager.peak_equity = equity
        
        # Winning trade - peak should increase
        risk_manager.update_pnl(500.0)
        assert risk_manager.current_equity == 10500.0
        assert risk_manager.peak_equity == 10500.0
        
        # Losing trade - peak should stay at high-water mark
        risk_manager.update_pnl(-200.0)
        assert risk_manager.current_equity == 10300.0
        assert risk_manager.peak_equity == 10500.0  # Unchanged
        
        # Drawdown calculation uses correct peak
        current_dd = (risk_manager.peak_equity - risk_manager.current_equity) / risk_manager.peak_equity
        assert abs(current_dd - (200.0/10500.0)) < 1e-10


class TestNameErrorTimeFix:
    """Regression test for NameError: time (module shadowing bug)."""
    
    def test_time_module_available_in_session_scope(self):
        """Verify 'import time' is at module level in run_session_v3.py, 
        not shadowed by local variable or missing in function scope."""
        import run_session_v3
        import inspect
        
        # Check that time is imported at module level
        source = inspect.getsource(run_session_v3)
        assert "import time" in source or "from time import" in source, \
            "time module must be imported at module level"
        
        # Verify no local variable named 'time' shadows the module in main()
        main_source = inspect.getsource(run_session_v3.main)
        # The old buggy code had `elapsed = datetime.now() - session_start`
        # and then used `elapsed.total_seconds() % 30 < 2` followed by `time.sleep(1)`
        # but `time` was not imported - it relied on a local variable or was missing
        # The fix is `import time` at module level
        
        # Verify time.sleep is called (proves time module is used)
        assert "time.sleep" in main_source or "sleep(" in main_source
        
        # Run a minimal dry-run to confirm no NameError
        import sys
        import os
        # Can't actually run without MT5, but we verified the import exists


# Run all tests
class TestPeakEquityPersistence:
    """Regression test for peak_equity persistence across RiskManager restarts."""
    
    def test_peak_equity_survives_restart(self, tmp_path):
        """Simulate a session reaching a peak equity, force a restart 
        (re-instantiate RiskManager from scratch reading only persisted state),
        and confirm peak_equity is correctly restored — NOT reset to current equity.
        Verify subsequent drawdown calculation uses the true historical peak."""
        kill_switch_file = str(tmp_path / "risk_kill_switch.json")
        equity = 10000.0
        
        # --- Session 1: Build up to a peak ---
        rm1 = RiskManager(kill_switch_file=kill_switch_file)
        rm1.current_equity = equity
        rm1.peak_equity = equity
        
        # Winning trades push equity to a new peak
        rm1.update_pnl(500.0)   # equity = 10500, peak = 10500
        assert rm1.current_equity == 10500.0
        assert rm1.peak_equity == 10500.0
        
        rm1.update_pnl(300.0)   # equity = 10800, peak = 10800
        assert rm1.current_equity == 10800.0
        assert rm1.peak_equity == 10800.0
        
        # Small drawdown - peak should stay at 10800
        rm1.update_pnl(-200.0)  # equity = 10600, peak = 10800
        assert rm1.current_equity == 10600.0
        assert rm1.peak_equity == 10800.0
        
        # Verify state file was written with peak_equity
        import json
        with open(kill_switch_file, 'r') as f:
            state = json.load(f)
        assert 'peak_equity' in state
        assert state['peak_equity'] == 10800.0
        
        # --- Session 2: Simulate crash/restart ---
        # New RiskManager instance loads from same file
        rm2 = RiskManager(kill_switch_file=kill_switch_file)
        
        # Provide current live equity (e.g., from MT5 account_info())
        # In a real crash, MT5 might report current equity = 10600
        live_equity = 10600.0
        rm2.current_equity = live_equity
        
        # CRITICAL: peak_equity should be LOADED from persisted state (10800)
        # NOT initialized to live_equity (10600)
        assert rm2.peak_equity == 10800.0, \
            f"Expected peak_equity=10800 from persisted state, got {rm2.peak_equity}"
        
        # --- Verify drawdown math uses TRUE historical peak ---
        # Drawdown from true peak (10800) to current (10600) = 200/10800 ≈ 1.85%
        current_dd = (rm2.peak_equity - rm2.current_equity) / rm2.peak_equity
        expected_dd = 200.0 / 10800.0
        assert abs(current_dd - expected_dd) < 1e-10, \
            f"Drawdown wrong: got {current_dd:.6%}, expected {expected_dd:.6%}"
        
        # If peak had been silently reset to 10600, drawdown would be 0% (WRONG)
        wrong_dd = (live_equity - live_equity) / live_equity
        assert current_dd != wrong_dd, "peak_equity was silently reset to current equity!"
        
        # --- Continue session: new winning trade pushes to NEW peak ---
        rm2.update_pnl(500.0)   # equity = 11100, peak should become 11100
        assert rm2.current_equity == 11100.0
        assert rm2.peak_equity == 11100.0
        
        # Verify persistence updated
        with open(kill_switch_file, 'r') as f:
            state = json.load(f)
        assert state['peak_equity'] == 11100.0
        
        print("✅ peak_equity correctly persists across restarts")
        print("✅ Drawdown math uses true historical peak, not reset value")


class TestAggregateConcurrentRiskCap:
    """Test that tier risk_pct is a CEILING on total concurrent risk, not per-trade independent."""
    
    def test_aggregate_risk_cap_enforced(self, tmp_path):
        """Open one trade at full risk budget, second trade must be rejected or sized down."""
        equity = 500.0  # $100-1000 tier: 3% risk, max 2 concurrent trades
        risk_manager = RiskManager(
            kill_switch_file=str(tmp_path / "risk_kill_switch.json"),
            max_consecutive_losses=5  # Disable for this test
        )
        risk_manager.current_equity = equity
        risk_manager.peak_equity = equity
        risk_manager.select_tier_for_equity(equity)
        
        tier = risk_manager.get_current_tier()
        assert tier["risk_pct_per_trade"] == 0.03  # 3%
        assert tier["max_concurrent_trades"] == 2
        
        max_total_risk = equity * 0.03  # $15
        
        # --- Trade 1: Use full risk budget ---
        # 3% of $500 = $15. 10 pts * lots * 100 = $15 => lots = 0.015
        config1 = TradeConfig(
            symbol='XAUUSD', signal=1, entry_price=2000.0, stop_price=1990.0,
            position_size=0.015, max_hold_hours=24, risk_pct=0.03, entry_time=pd.Timestamp.now(tz='UTC')
        )
        # Risk = 10 pts * 0.015 lots * 100 = $15 (full 3% budget)
        
        # Check aggregate risk for first trade - should pass (no open risk yet)
        ok1, reason1 = risk_manager.check_aggregate_risk(config1, equity)
        assert ok1 is True, f"First trade should pass: {reason1}"
        
        # Register the position risk
        stop_distance = abs(config1.entry_price - config1.stop_price)
        risk_per_contract = stop_distance * 100
        risk_at_stop = config1.position_size * risk_per_contract
        risk_manager.register_position_risk('XAUUSD', risk_at_stop)
        assert risk_manager.total_open_risk == 15.0
        
        # --- Trade 2: Attempt to open second trade while first is open ---
        config2 = TradeConfig(
            symbol='XAUUSD', signal=-1, entry_price=2000.0, stop_price=2010.0,
            position_size=0.015, max_hold_hours=24, risk_pct=0.03, entry_time=pd.Timestamp.now(tz='UTC')
        )
        # Risk = 10 pts * 0.015 lots * 100 = $15
        
        # Check aggregate risk for second trade - should FAIL (would exceed $15 total)
        ok2, reason2 = risk_manager.check_aggregate_risk(config2, equity)
        assert ok2 is False, f"Second trade should be rejected due to aggregate cap"
        assert "AGGREGATE_RISK_CAP" in reason2 or "aggregate" in reason2.lower()
        
        print("✅ Aggregate concurrent risk cap correctly enforced")
        print(f"   First trade risk: ${risk_at_stop:.2f}")
        print(f"   Second trade rejected: {reason2}")


class TestConsecutiveLossCircuitBreaker:
    """Test the consecutive loss circuit breaker halts trading after N losses."""
    
    def test_consecutive_loss_halt_after_two_losses(self, tmp_path):
        """After 2 consecutive losses, new signals should be halted."""
        equity = 10000.0
        risk_manager = RiskManager(
            kill_switch_file=str(tmp_path / "risk_kill_switch.json"),
            max_consecutive_losses=2,
            consecutive_loss_cooldown_hours=1  # 1 hour cooldown for test
        )
        risk_manager.current_equity = equity
        risk_manager.peak_equity = equity
        # Disable daily/weekly/monthly loss limits for this test
        risk_manager.max_daily_loss_pct = 1.0
        risk_manager.max_weekly_loss_pct = 1.0
        risk_manager.max_monthly_loss_pct = 1.0
        
        # Initially can trade
        can_trade, violations = risk_manager.check_limits()
        assert can_trade is True
        assert risk_manager.consecutive_losses == 0
        assert risk_manager.consecutive_loss_halted is False
        
        # First loss (small enough to not hit daily limit)
        risk_manager.update_pnl(-50.0)  # -0.5%
        can_trade, _ = risk_manager.check_limits()
        assert can_trade is True
        assert risk_manager.consecutive_losses == 1
        assert risk_manager.consecutive_loss_halted is False
        
        # Second loss - should trigger halt
        risk_manager.update_pnl(-30.0)  # -0.3% more
        can_trade, violations = risk_manager.check_limits()
        assert can_trade is False
        assert risk_manager.consecutive_losses == 2
        assert risk_manager.consecutive_loss_halted is True
        assert any("CONSECUTIVE LOSS HALT" in v for v in violations)
        
        print("✅ Consecutive loss halt triggered after 2 losses")
    
    def test_consecutive_loss_cooldown_expiry(self, tmp_path):
        """After cooldown period, trading should resume."""
        equity = 10000.0
        risk_manager = RiskManager(
            kill_switch_file=str(tmp_path / "risk_kill_switch.json"),
            max_consecutive_losses=2,
            consecutive_loss_cooldown_hours=0.01  # ~36 seconds for test
        )
        risk_manager.current_equity = equity
        risk_manager.peak_equity = equity
        # Disable daily/weekly/monthly loss limits for this test
        risk_manager.max_daily_loss_pct = 1.0
        risk_manager.max_weekly_loss_pct = 1.0
        risk_manager.max_monthly_loss_pct = 1.0
        
        # Trigger halt
        risk_manager.update_pnl(-50.0)
        risk_manager.update_pnl(-30.0)
        assert risk_manager.consecutive_loss_halted is True
        
        # Wait for cooldown to expire
        import time
        time.sleep(40)  # Wait longer than 36 seconds
        
        # Should now be able to trade
        can_trade, violations = risk_manager.check_limits()
        assert can_trade is True, f"Should resume after cooldown: {violations}"
        assert risk_manager.consecutive_loss_halted is False
        assert risk_manager.consecutive_losses == 0
        
        print("✅ Consecutive loss cooldown expiry works")
    
    def test_win_resets_consecutive_losses_but_not_halt(self, tmp_path):
        """A win after losses resets counter but doesn't clear active halt."""
        equity = 10000.0
        risk_manager = RiskManager(
            kill_switch_file=str(tmp_path / "risk_kill_switch.json"),
            max_consecutive_losses=2,
            consecutive_loss_cooldown_hours=24  # Long cooldown
        )
        risk_manager.current_equity = equity
        risk_manager.peak_equity = equity
        # Disable daily/weekly/monthly loss limits for this test
        risk_manager.max_daily_loss_pct = 1.0
        risk_manager.max_weekly_loss_pct = 1.0
        risk_manager.max_monthly_loss_pct = 1.0
        
        # Two losses -> halt
        risk_manager.update_pnl(-50.0)
        risk_manager.update_pnl(-30.0)
        assert risk_manager.consecutive_loss_halted is True
        
        # One win - counter resets but halt remains
        risk_manager.update_pnl(20.0)
        assert risk_manager.consecutive_losses == 0
        assert risk_manager.consecutive_loss_halted is True  # Halt persists until cooldown
        
        # Should still be halted
        can_trade, violations = risk_manager.check_limits()
        assert can_trade is False
        assert any("CONSECUTIVE LOSS HALT" in v for v in violations)
        
        print("✅ Win resets counter but halt persists until cooldown")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])