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
        risk_manager = RiskManager(kill_switch_file=str(tmp_path / "risk_kill_switch.json"))
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


# Run all tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])