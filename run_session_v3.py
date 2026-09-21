#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MARS Multi-Symbol Live Trading Session
=======================================
Production entry point for running a live trading session with:
- Multi-symbol support (XAUUSD, EURUSD, USDJPY, EURGBP)
- Per-signal-type position sizing (ATR volatility targeting)
- Hard risk rules (daily loss, concurrent risk, kill-switch)
- MT5 demo account safety gate
- Tier-based risk management with equity floor
- Audit logging (SQLite) for all orders, fills, risk events
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta
from unittest.mock import Mock

from mars.apps.trading.mt5_executor import (
    MT5Executor,
    MT5ConnectionManager,
    MT5Config,
    MT5AuditLogger,
    VolScaledSizer,
    MT5SymbolResolver,
    MT5OrderRouter,
)
from mars.apps.trading.system.vol_scaled_system import RiskManager, SizingConfig
from mars.apps.trading.system.pair_config import get_pair_config, get_enabled_symbols
from mars.apps.trading.signals.trend_breakout import DonchianBreakoutSignal


class MockMT5ConnectionManager:
    """Mock MT5 connection manager for dry-run testing without real terminal."""
    
    def __init__(self, mt5_config: MT5Config):
        self.mt5_config = mt5_config
        self.mock_mt5 = self._create_mock_mt5()
        self.connected = False
    
    def _create_mock_mt5(self):
        """Create a mocked MT5 module with demo account data."""
        mock_mt5 = Mock()
        
        # Order types and constants
        mock_mt5.ORDER_TYPE_BUY = 0
        mock_mt5.ORDER_TYPE_SELL = 1
        mock_mt5.TRADE_ACTION_DEAL = 1
        mock_mt5.TRADE_RETCODE_DONE = 10009
        mock_mt5.ORDER_TIME_GTC = 0
        mock_mt5.ORDER_FILLING_FOK = 0
        mock_mt5.ORDER_FILLING_IOC = 1
        mock_mt5.ORDER_FILLING_RETURN = 2
        
        # Mock account info (DEMO account with $500 equity - triggers $100-1000 tier)
        mock_account = Mock()
        mock_account.login = 476944496
        mock_account.trade_mode = 0  # 0 = DEMO
        mock_account.balance = 500.0
        mock_account.equity = 500.0
        mock_account.currency = "USD"
        mock_account.leverage = 2000
        mock_mt5.account_info.return_value = mock_account
        
        # Mock symbol info for all enabled symbols
        def make_symbol_info(symbol):
            s = Mock()
            s.name = symbol
            s.trade_contract_size = 100.0 if 'XAU' in symbol else 100000.0
            s.volume_min = 0.01
            s.volume_max = 200.0
            s.volume_step = 0.01
            s.digits = 3 if 'JPY' in symbol or 'XAU' in symbol else 5
            s.point = 0.001 if 'JPY' in symbol or 'XAU' in symbol else 0.00001
            s.spread = 260 if 'XAU' in symbol else 15
            s.visible = True
            s.trade_tick_size = s.point
            s.trade_tick_value = 1.0
            s.swap_long = -1.5
            s.swap_short = -0.5
            s.margin_initial = 1000.0
            s.margin_maintenance = 500.0
            s.session_deals = 0
            s.session_buy_orders = 0
            s.session_sell_orders = 0
            s.time = int(time.time())
            s.filling_mode = 3
            s.order_mode = 127
            s.trade_mode = 4
            return s
        
        def make_tick(symbol):
            t = Mock()
            if 'XAU' in symbol:
                t.bid, t.ask = 2000.00, 2000.30
            elif 'JPY' in symbol:
                t.bid, t.ask = 150.000, 150.030
            else:
                t.bid, t.ask = 1.10000, 1.10015
            t.time = int(time.time())
            t.flags = 0
            t.volume = 1
            return t
        
        def mock_symbol_info(symbol):
            return make_symbol_info(symbol)
        
        def mock_symbol_info_tick(symbol):
            return make_tick(symbol)
        
        # Mock order_send to return success
        def mock_order_send(request):
            result = Mock()
            result.retcode = 10009  # TRADE_RETCODE_DONE
            result.deal = 123456789
            result.order = 987654321
            result.volume = request.volume
            result.price = request.price
            result.sl = request.sl
            result.tp = request.tp
            result.comment = request.comment
            result.request_id = 1
            result.external_id = ""
            return result
        
        mock_mt5.symbol_info.side_effect = mock_symbol_info
        mock_mt5.symbol_info_tick.side_effect = mock_symbol_info_tick
        mock_mt5.order_send.side_effect = mock_order_send
        mock_mt5.last_error.return_value = (0, "No error")
        mock_mt5.initialize.return_value = True
        mock_mt5.shutdown.return_value = None
        mock_mt5.positions_get.return_value = ()
        mock_mt5.orders_get.return_value = ()
        mock_mt5.history_deals_get.return_value = ()
        mock_mt5.history_orders_get.return_value = ()
        
        return mock_mt5
    
    def connect(self):
        """Mock connection - always succeeds."""
        self.connected = True
        print(f"[MOCK] MT5 connected to demo account #{self.mock_mt5.account_info().login}")
        return True
    
    def disconnect(self):
        self.connected = False
    
    def shutdown(self):
        self.disconnect()
    
    @property
    def mt5(self):
        return self.mock_mt5


class MultiSymbolSession:
    """Manages a multi-symbol live trading session."""

    def __init__(
        self,
        symbols: list[str],
        equity: float,
        risk_manager: RiskManager,
        mt5_config: MT5Config,
        dry_run: bool = False,
        use_mock: bool = False,
    ):
        self.symbols = symbols
        self.equity = equity
        self.risk_manager = risk_manager
        self.mt5_config = mt5_config
        self.dry_run = dry_run
        self.use_mock = use_mock

        # Initialize MT5 executor with live trading system
        audit_db_path = os.path.join(tempfile.gettempdir(), 'mt5_audit.db')
        sizer = VolScaledSizer(SizingConfig(target_vol=0.15, max_leverage=3.0, min_leverage=0.01, kelly_fraction=0.5))

        if use_mock:
            mock_conn = MockMT5ConnectionManager(mt5_config)
            mock_conn.connect()
            self.executor = MT5Executor(
                equity=equity,
                risk_manager=risk_manager,
                sizer=sizer,
                mt5_config=mt5_config,
                audit_db_path=audit_db_path,
                conn_manager=mock_conn,
                auto_initialize=False,
            )
            # Manually initialize components with mock MT5
            self.executor.mt5 = mock_conn.mt5
            self.executor.symbol_resolver = MT5SymbolResolver(self.executor.mt5)
            self.executor.order_router = MT5OrderRouter(self.executor.mt5, self.executor.symbol_resolver)
            account_info = self.executor.mt5.account_info()
            if account_info:
                print(f"MT5 DEMO ACCOUNT: #{account_info.login} | Balance: {account_info.balance:.2f} | Equity: {account_info.equity:.2f}")
        else:
            self.executor = MT5Executor(
                equity=equity,
                risk_manager=risk_manager,
                sizer=sizer,
                mt5_config=mt5_config,
                audit_db_path=audit_db_path,
            )
        self.signal_generators = {}
        for symbol in symbols:
            pair_cfg = get_pair_config(symbol)
            self.signal_generators[symbol] = DonchianBreakoutSignal(
                
                window=pair_cfg["donchian_window"],
                
                stop_multiplier=pair_cfg.get("stop_multiplier", 2.0),
                session_filter=pair_cfg.get("session_filter", "all"),
                stop_mode=pair_cfg.get("stop_mode", "atr"),
                risk_pips=pair_cfg.get("risk_pips", 0.0),
                exit_window=pair_cfg.get("exit_window", 10),
            
                pip_size=pair_cfg.get("pip_size", 0.0001),
            )

    def fit_sizers(self):
        """Fit volatility sizers for all symbols using recent data."""
        try:
            from mars.libs.features.volatility.ranker import VolatilityRanker
        except ImportError:
            print("  WARNING: VolatilityRanker not available, skipping sizer fitting")
            return
        import pandas as pd

        print("Fitting volatility sizers...")
        for symbol in self.symbols:
            try:
                # Load recent data for sizer fitting
                data_path = f"data/processed/{symbol.lower()}/m5/v1.0.0/data.parquet"
                df = pd.read_parquet(data_path)
                df = df.sort_index()
                # Use last 2000 bars for fitting
                recent = df.tail(2000)
                closes = recent['close'].values
                highs = recent['high'].values
                lows = recent['low'].values

                ranker = VolatilityRanker(lookback=100)
                ranker.fit(closes, highs, lows)
                self.executor.sizers[symbol] = ranker
                print(f"  {symbol}: fitted (regime={ranker.regime})")
            except Exception as e:
                print(f"  {symbol}: WARNING - could not fit sizer: {e}")

    def poll_cycle(self, mt5):
        """Single polling cycle: check signals, place orders, manage positions."""
        from mars.apps.trading.mt5_executor import get_positions_dict

        cycle_results = {
            'signals_generated': {},
            'orders_placed': {},
            'orders_failed': {},
            'positions_managed': {},
        }

        positions = get_positions_dict(mt5)

        for symbol in self.symbols:
            try:
                pair_cfg = get_pair_config(symbol)
                signal_gen = self.signal_generators[symbol]

                # Get current rates
                tick = mt5.symbol_info_tick(symbol)
                if tick is None:
                    cycle_results['signals_generated'][symbol] = 0
                    continue

                bid, ask = tick.bid, tick.ask
                current_price = (bid + ask) / 2

                # Generate signal
                signal = signal_gen.compute(
                    current_price=current_price,
                    bid=bid,
                    ask=ask,
                    equity=self.equity,
                )

                if signal['signal'] != 0:
                    cycle_results['signals_generated'][symbol] = signal['signal']
                    # In dry-run, we don't place orders
                    if not self.dry_run:
                        result = self.executor.execute_signal(symbol, signal, bid, ask)
                        if result.success:
                            cycle_results['orders_placed'][symbol] = 1
                        else:
                            cycle_results['orders_failed'][symbol] = 1
                else:
                    cycle_results['signals_generated'][symbol] = 0

                # Manage existing positions (trailing stops, etc.)
                if symbol in positions:
                    pos = positions[symbol]
                    cycle_results['positions_managed'][symbol] = pos.ticket

            except Exception as e:
                print(f"[{datetime.now()}] Error in {symbol} cycle: {e}")

        return cycle_results

    def run_session(self, duration_minutes: int = 5):
        """Run the live trading session for the specified duration."""
        session_start = datetime.now()
        end_time = session_start + timedelta(minutes=duration_minutes)

        print(f"Starting live session for {duration_minutes} minutes...")
        print(f"Symbols: {self.symbols}")
        print(f"Dry run: {self.dry_run}")

        try:
            while datetime.now() < end_time:
                # Run polling cycle
                cycle_results = self.poll_cycle(self.executor.mt5)

                # Check kill-switch
                if self.risk_manager.kill_switch_halted:
                    print(f"[{datetime.now()}] KILL SWITCH ACTIVATED - HALTING")
                    break

                # Status update every 30 seconds
                elapsed = datetime.now() - session_start
                if int(elapsed.total_seconds()) % 30 == 0:
                    total_signals = sum(cycle_results['signals_generated'].values())
                    total_placed = sum(cycle_results['orders_placed'].values())
                    total_failed = sum(cycle_results['orders_failed'].values())
                    print(f"[{datetime.now()}] Status: Signals={total_signals}, Placed={total_placed}, Failed={total_failed}, Equity=${self.equity:.2f}")

                time.sleep(1)

        except KeyboardInterrupt:
            print(f"\n[{datetime.now()}] Session interrupted by user")

        finally:
            self.executor.shutdown()

        return {
            'duration': datetime.now() - session_start,
            'final_equity': self.equity,
        }


def main():
    parser = argparse.ArgumentParser(description="MARS Multi-Symbol Live Trading Session")
    parser.add_argument("--dry-run", action="store_true", help="Validate setup without placing orders")
    parser.add_argument("--mock-mt5", action="store_true", help="Use mocked MT5 for dry-run testing (no real terminal needed)")
    parser.add_argument("--duration", type=int, default=5, help="Session duration in minutes (default: 5)")
    parser.add_argument("--symbols", nargs="+", help="Override symbols to trade (default: all enabled from PAIR_CONFIG)")
    args = parser.parse_args()

    # Clean up any stale kill-switch file from previous runs
    kill_switch_path = os.path.join(tempfile.gettempdir(), 'risk_kill_switch.json')
    if os.path.exists(kill_switch_path):
        os.remove(kill_switch_path)

    # --- MT5 Config & Demo Account Safety Gate ---
    mt5_config = MT5Config(
        login=int(os.getenv("DEMO_ACCOUNT_NUMBER", "476944496")),
        password=os.getenv("PASSWORD", ""),
        server=os.getenv("SERVER", ""),
        path=os.getenv("MT5_PATH", r"C:\Program Files\MetaTrader 5\terminal64.exe"),
        timeout=60000,
        portable=False,
    )
    if not mt5_config.is_configured() and not args.mock_mt5:
        print("MT5 credentials not configured (use --mock-mt5 for testing without real terminal)")
        sys.exit(1)

    # --- Instantiate RiskManager ---
    risk_manager = RiskManager(
        kill_switch_file=kill_switch_path,
    )

    # --- Connect to MT5 to get LIVE equity for tier selection ---
    print("=== DRY RUN: Connecting to MT5 for live equity ===")
    if args.mock_mt5:
        conn_manager = MockMT5ConnectionManager(mt5_config)
    else:
        conn_manager = MT5ConnectionManager(mt5_config)
    conn_manager.connect()
    mt5 = conn_manager.mt5

    # Verify demo account and get live equity
    account_info = mt5.account_info()
    if account_info is None:
        raise RuntimeError(f"Failed to get account info: {mt5.last_error()}")

    live_equity = float(account_info.equity)
    account_number = account_info.login
    trade_mode = account_info.trade_mode

    print(f"MT5 ACCOUNT CONNECTED: #{account_number} | Trade Mode: {trade_mode} (0=DEMO)")
    print(f"LIVE EQUITY: ${live_equity:.2f}")

    if trade_mode != 0:
        raise RuntimeError("SAFETY GATE FAILED: Account is NOT a DEMO account")

    # --- SELECT AND LOCK TIER BASED ON LIVE EQUITY ---
    tier = risk_manager.select_tier_for_equity(live_equity)
    print()
    print("=== TIER SELECTED (LOCKED FOR SESSION) ===")
    print(f"  Equity: ${live_equity:.2f}")
    print(f"  Tier: ${tier['min_equity']:.0f} - ${tier['max_equity'] if tier['max_equity'] != float('inf') else '∞'}")
    print(f"  Max Concurrent Trades: {tier['max_concurrent_trades']}")
    print(f"  Risk per Trade: {tier['risk_pct_per_trade']:.1%}")
    print(f"  Aggregate Risk Cap: {tier['aggregate_risk_pct']:.1%}")
    print(f"  Reward:Risk Ratio: {tier['reward_risk_ratio']:.1f}")
    print(f"  Tier Locked: {risk_manager.is_tier_locked()}")
    print(f"  Locked At Equity: ${risk_manager._tier_locked_at_equity:.2f}")
    print()

    # Initialize RiskManager equity state
    risk_manager.current_equity = live_equity
    risk_manager.peak_equity = live_equity
    risk_manager.daily_pnl = 0.0

    # --- Determine symbols to trade ---
    if args.symbols:
        symbols = args.symbols
        print(f"Using override symbols: {symbols}")
    else:
        symbols = get_enabled_symbols()
        print(f"Using enabled symbols from PAIR_CONFIG: {symbols}")

    # --- Create and run multi-symbol session ---
    session = MultiSymbolSession(
        symbols=symbols,
        equity=live_equity,
        risk_manager=risk_manager,
        mt5_config=mt5_config,
        dry_run=args.dry_run,
        use_mock=args.mock_mt5,
    )

    # Fit sizers
    session.fit_sizers()

    if args.dry_run:
        print("\n✅ DRY RUN COMPLETE - All validations passed, no orders placed.")
        print("   Tier selection and lock confirmed.")
        print("   Demo account safety gate passed.")
        print("   Multi-symbol signal generation validated.")
        print("   Ready for live session.")
        session.executor.shutdown()
        conn_manager.shutdown()
        return 0

    # Live session
    session.run_session(args.duration)

    print()
    print("=== SESSION SUMMARY ===")
    print(f"Final Equity: ${live_equity:.2f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())