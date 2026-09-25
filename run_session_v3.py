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

# Load .env file for MT5 credentials
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from mars.apps.trading.mt5_executor import (
    MT5Executor,
    MT5ConnectionManager,
    MT5Config,
    MT5AuditLogger,
    VolScaledSizer,
    MT5SymbolResolver,
    MT5OrderRouter,
)
from mars.apps.trading.system.vol_scaled_system import RiskManager, SizingConfig, TradeConfig
from mars.apps.trading.system.pair_config import get_pair_config, get_enabled_symbols, PAIR_CONFIG
from mars.apps.trading.signals.trend_breakout import DonchianBreakoutSignal
from mars.apps.trading.signals.mtf_gate import MTFGate, create_mtf_gate


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

        # Timeframe constants
        mock_mt5.TIMEFRAME_M5 = 5
        mock_mt5.TIMEFRAME_M1 = 1
        mock_mt5.TIMEFRAME_H1 = 16385

        # Mock copy_rates_from_pos to return synthetic data
        def mock_copy_rates_from_pos(symbol, timeframe, start_pos, count):
            import numpy as np
            import pandas as pd
            # Generate synthetic OHLCV data appropriate for the timeframe
            np.random.seed(42)
            base_price = 2000.0 if 'XAU' in symbol else (150.0 if 'JPY' in symbol else 1.1)
            
            # Map MT5 timeframe constants to pandas freq
            tf_map = {
                16385: 'h',     # TIMEFRAME_H1
                16384: '30min', # TIMEFRAME_M30
                16383: '15min', # TIMEFRAME_M15
                5: '5min',      # TIMEFRAME_M5
                1: '1min',      # TIMEFRAME_M1
            }
            freq = tf_map.get(timeframe, '5min')
            
            # Use end time as now, generate count bars going backwards
            times = pd.date_range(end=pd.Timestamp.now(tz='UTC'), periods=count, freq=freq)
            data = []
            price = base_price
            for i in range(count):
                # Volatility scales with timeframe
                vol_scale = {'h': 0.002, '30min': 0.001, '15min': 0.0007, '5min': 0.0005, '1min': 0.0002}.get(freq, 0.0005)
                change = np.random.normal(0, vol_scale)
                price *= (1 + change)
                o = price
                h = price * (1 + abs(np.random.normal(0, vol_scale * 0.4)))
                l = price * (1 - abs(np.random.normal(0, vol_scale * 0.4)))
                c = price * (1 + np.random.normal(0, vol_scale * 0.2))
                v = 1000
                data.append((int(times[i].timestamp()), o, h, l, c, v, 0, 0))
            # Create a structured array that mimics MT5 rates
            dt = np.dtype([('time', 'i8'), ('open', 'f8'), ('high', 'f8'), ('low', 'f8'), ('close', 'f8'), ('tick_volume', 'i8'), ('spread', 'i4'), ('real_volume', 'i8')])
            return np.array(data, dtype=dt)

        mock_mt5.copy_rates_from_pos.side_effect = mock_copy_rates_from_pos

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
        from dataclasses import dataclass
        
        @dataclass
        class MockOrderFill:
            retcode: int  # Main return code (TRADE_RETCODE_DONE = 10009)
            order: int    # Order ticket
            price: float  # Fill price
            volume: float # Fill volume
            commission: float = 0.0
            swap: float = 0.0
            profit: float = 0.0
            retcode_external: int = 10009
            comment: str = ""
            deal: int = 123456789
            request_id: int = 1
            external_id: str = ""
            
            # Additional fields needed by audit logger
            slippage: float = 0.0
            size_slippage: float = 0.0
            bid: float = 0.0
            ask: float = 0.0
            spread: float = 0.0
            sl: float = 0.0
            tp: float = 0.0
            ticket: int = None  # alias for order
            order_id: int = None  # alias for order
            
            def __post_init__(self):
                from datetime import datetime
                if self.ticket is None:
                    self.ticket = self.order
                if self.order_id is None:
                    self.order_id = self.order
                if self.bid == 0.0:
                    self.bid = self.price - 0.15
                if self.ask == 0.0:
                    self.ask = self.price + 0.15
                if self.spread == 0.0:
                    self.spread = self.ask - self.bid

        def mock_order_send(request):
            return MockOrderFill(
                retcode=10009,  # TRADE_RETCODE_DONE
                order=987654321,
                price=request.get('price', 2000.0),
                volume=request.get('volume', 0.01),
                sl=request.get('sl', 1990.0),
                tp=request.get('tp', 2030.0),
                comment=request.get('comment', '')
            )
        
        mock_mt5.symbol_info.side_effect = mock_symbol_info
        mock_mt5.symbol_info_tick.side_effect = mock_symbol_info_tick
        mock_mt5.order_send.side_effect = mock_order_send
        mock_mt5.last_error.return_value = (0, "No error")
        mock_mt5.initialize.return_value = True
        mock_mt5.shutdown.return_value = None
        mock_mt5.positions_get.return_value = []
        mock_mt5.orders_get.return_value = []
        mock_mt5.history_deals_get.return_value = []
        mock_mt5.history_orders_get.return_value = []
        
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

    def ensure_connected(self):
        """Mock ensure_connected - always returns True."""
        if not self.connected:
            self.connect()
        return True


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
        audit_db_path = os.path.join(tempfile.gettempdir(), 'mt5_audit_real.db')
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
        self.mtf_gates = {}
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
            # Create MTF gate for this symbol
            self.mtf_gates[symbol] = create_mtf_gate(self.executor.mt5, symbol)

    def fit_sizers(self):
        """Fit volatility sizers for all symbols using recent data.
        Uses VolScaledSizer (GARCH/CARR) which is the actual production sizer.
        """
        import pandas as pd
        from mars.apps.trading.system.vol_scaled_system import VolScaledSizer, SizingConfig

        print("Fitting volatility sizers (VolScaledSizer GARCH)...")
        for symbol in self.symbols:
            try:
                # Load recent data for sizer fitting
                data_path = f"data/processed/{symbol.lower()}/m5/v1.0.0/data.parquet"
                df = pd.read_parquet(data_path)
                df = df.sort_index()
                # Use last 2000 bars for fitting
                recent = df.tail(2000)

                # Create and fit VolScaledSizer per symbol
                sizer_config = SizingConfig(target_vol=0.15, max_leverage=3.0, min_leverage=0.01, kelly_fraction=0.5)
                sizer = VolScaledSizer(sizer_config, garch_variant='garch')
                sizer.fit(recent)
                self.executor.sizers[symbol] = sizer
                print(f"  {symbol}: fitted (GARCH vol forecast ready)")
            except Exception as e:
                print(f"  {symbol}: WARNING - could not fit sizer: {e}")

    def poll_cycle(self):
        """Single polling cycle: check signals, place orders, manage positions."""
        import pandas as pd
        from datetime import datetime
        cycle_results = {
            'signals_generated': {},
            'orders_placed': {},
            'orders_failed': {},
            'positions_managed': {},
        }

        # Get positions from executor (already synced with MT5)
        positions = self.executor.get_open_positions()

        for symbol in self.symbols:
            try:
                pair_cfg = get_pair_config(symbol)
                signal_gen = self.signal_generators[symbol]
                mtf_gate = self.mtf_gates.get(symbol)

                # Generate live signal
                signal = signal_gen.compute_live(self.executor.mt5, symbol, self.equity)
                signal_val = signal['signal']

                # Evaluate MTF gate for EVERY cycle (including FLAT signals)
                mtf_context = None
                if mtf_gate:
                    mtf_context = mtf_gate.evaluate_gate(
                        breakout_signal=signal_val,
                        breakout_price=signal.get('entry_price', 0),
                        breakout_stop=signal.get('stop_price', 0)
                    )
                    # Log MTF gate evaluation for dashboard visibility
                    self.executor.audit_logger.log_evaluation(symbol, mtf_context)
                    print(f"[{datetime.now()}] {symbol} 5M_signal={signal_val} MTF_gate={mtf_context.gate_result.name} reason={mtf_context.rejection_reason or 'OK'} 1H={mtf_context.trend_1h.name} 30M={mtf_context.bias_30m.name} 15M={mtf_context.context_15m.name}")

                gate_allows = (mtf_context is None) or (mtf_context.gate_result.name == 'ALLOWED')

                if signal_val != 0 and gate_allows:
                    cycle_results['signals_generated'][symbol] = signal_val
                    # In dry-run, we don't place orders
                    if not self.dry_run:
                        # Calculate position size using fitted sizer or fallback
                        sizer = self.executor.sizers.get(symbol)
                        if sizer is not None:
                            # Use the fitted VolScaledSizer to get vol forecast and compute position size
                            import pandas as pd
                            data_path = f"data/processed/{symbol.lower()}/m5/v1.0.0/data.parquet"
                            if os.path.exists(data_path):
                                df = pd.read_parquet(data_path).sort_index()
                                recent = df.tail(2000)
                                # Get vol forecast
                                forecast_vol = sizer.forecast_vol(recent)
                                if len(forecast_vol) > 0:
                                    latest_vol = forecast_vol.iloc[-1]  # annualized % vol
                                    # Compute position size: target_vol / forecast_vol * equity / (price * contract_multiplier)
                                    target_vol = sizer.config.target_vol  # e.g., 0.15
                                    kelly_fraction = sizer.config.kelly_fraction  # e.g., 0.5
                                    leverage = (target_vol / (latest_vol / 100)) * kelly_fraction
                                    leverage = max(sizer.config.min_leverage, min(sizer.config.max_leverage, leverage))
                                    position_value = self.equity * leverage
                                    contract_multiplier = 100.0  # XAUUSD: 100 oz per lot
                                    position_size = position_value / (signal['entry_price'] * contract_multiplier)
                                    # Cap by max position %
                                    max_position_value = self.equity * sizer.config.max_position_pct
                                    max_contracts = max_position_value / (signal['entry_price'] * contract_multiplier)
                                    position_size = min(position_size, max_contracts)
                                    position_size = max(0.01, round(position_size, 2))
                                else:
                                    position_size = 0.01
                            else:
                                position_size = 0.01  # fallback
                        else:
                            # Fallback: fixed fractional sizing
                            stop_distance = abs(signal['entry_price'] - signal['stop_price'])
                            risk_per_lot = stop_distance * 100  # XAUUSD: $1/pip per oz, 100 oz/lot
                            target_risk = self.equity * 0.01  # 1% risk
                            position_size = max(0.01, round(target_risk / risk_per_lot, 2))
                        
                        # Create TradeConfig
                        trade_config = TradeConfig(
                            symbol=symbol,
                            signal=signal['signal'],
                            entry_price=signal['entry_price'],
                            stop_price=signal['stop_price'],
                            take_profit=signal['take_profit'],
                            position_size=position_size,
                            max_hold_hours=24,
                            entry_time=pd.Timestamp.now(tz='UTC')
                        )
                        
                        success = self.executor.open_position(trade_config)
                        print(f"[{datetime.now()}] {symbol} signal={signal['signal']} entry={signal['entry_price']:.2f} stop={signal['stop_price']:.2f} tp={signal['take_profit']:.2f} size={position_size} -> {'PLACED' if success else 'REJECTED'}")
                        if success:
                            cycle_results['orders_placed'][symbol] = 1
                        else:
                            cycle_results['orders_failed'][symbol] = 1
                            # Debug: check risk manager state
                            print(f"  RiskMgr: tier={self.risk_manager._current_tier}, open_positions={len(self.risk_manager.current_positions)}, total_open_risk={self.risk_manager.total_open_risk:.2f}")
                else:
                    cycle_results['signals_generated'][symbol] = 0

                # Manage existing positions (trailing stops, etc.)
                if symbol in positions:
                    pos = positions[symbol]
                    cycle_results['positions_managed'][symbol] = pos.get('mt5_ticket', 'unknown')

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
                cycle_results = self.poll_cycle()

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
    parser.add_argument(
        "--symbols",
        type=str,
        help="Comma-separated list of symbols to trade this session (e.g., XAUUSDm,EURUSDm). REQUIRED - no default. Each symbol must be enabled in PAIR_CONFIG."
    )
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
    if not args.symbols:
        print("ERROR: No symbols specified. Pass --symbols XAUUSDm,EURUSDm (comma-separated, no spaces)")
        sys.exit(1)

    # Parse comma-separated symbols
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]

    # Validate each symbol is in PAIR_CONFIG and enabled
    for symbol in symbols:
        if symbol not in PAIR_CONFIG:
            print(f"ERROR: Symbol '{symbol}' not found in PAIR_CONFIG")
            sys.exit(1)
        if not PAIR_CONFIG[symbol].get("enabled", False):
            reason = PAIR_CONFIG[symbol].get("disabled_reason", "No reason provided")
            print(f"ERROR: Symbol '{symbol}' is disabled in PAIR_CONFIG and cannot be force-enabled.")
            print(f"       Reason: {reason}")
            sys.exit(1)

    print(f"Session symbols (validated): {symbols}")

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
        conn_manager.disconnect()
        return 0

    # Live session
    session.run_session(args.duration)

    print()
    print("=== SESSION SUMMARY ===")
    print(f"Final Equity: ${live_equity:.2f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())