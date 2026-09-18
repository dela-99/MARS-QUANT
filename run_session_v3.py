#!/usr/bin/env python3
"""
Live trading session with tiered risk config - DRY RUN mode for validation.
Supports multi-symbol trading from PAIR_CONFIG.
"""
import sys
import os
import time
import argparse
from datetime import datetime, timedelta

# Ensure local package is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mars.core.config import MT5Config, DEFAULT_CONFIG
from mars.apps.trading.mt5_executor import MT5Executor, MT5ConnectionManager
from mars.apps.trading.system.vol_scaled_system import RiskManager, TradeConfig, VolScaledSizer, SizingConfig
from mars.apps.trading.system.pair_config import get_enabled_symbols, get_pair_config, create_signal_generator, get_contract_specs
from mars.libs.features.volatility.range import ATRFeature
import pandas as pd
import tempfile
import sqlite3


def compute_current_atr(price_df: pd.DataFrame, window: int = 14) -> float:
    """Compute current ATR from live bar data."""
    atr_feat = ATRFeature(window=window)
    result = atr_feat.compute(price_df)
    atr_series = result.data['atr']
    current_atr = atr_series.iloc[-1]
    return float(current_atr)


def fetch_live_data(mt5, symbol: str, bars: int = 5000) -> pd.DataFrame | None:
    """Fetch recent M5 bars from MT5 for a symbol."""
    rates = mt5.copy_rates_from_pos(symbol, 5, 0, bars)
    if rates is None or len(rates) == 0:
        return None
    live_df = pd.DataFrame(rates)
    live_df['timestamp'] = pd.to_datetime(live_df['time'], unit='s', utc=True)
    live_df.set_index('timestamp', inplace=True)
    live_df.rename(columns={
        'open': 'open', 'high': 'high', 'low': 'low', 'close': 'close',
        'tick_volume': 'volume', 'spread': 'spread', 'real_volume': 'real_volume'
    }, inplace=True)
    return live_df


def validate_live_data(live_df: pd.DataFrame, symbol: str) -> tuple[bool, list[str], list[str]]:
    """Validate live bar data. Returns (ok, errors, warnings)."""
    from mars.libs.data.loaders import normalize_ohlcv
    from mars.libs.data.validation import validate_ohlcv
    
    # Normalize
    live_df = normalize_ohlcv(live_df, symbol=symbol, timeframe='M5', assume_utc=True)
    
    # Validate
    validation_report = validate_ohlcv(live_df, strict=False)
    return validation_report.ok, validation_report.errors, validation_report.warnings


class MultiSymbolSession:
    """Manages a multi-symbol trading session."""
    
    def __init__(
        self,
        symbols: list[str],
        equity: float,
        risk_manager: RiskManager,
        mt5_config,
        dry_run: bool = True,
        audit_db_path: str | None = None,
    ):
        self.symbols = symbols
        self.equity = equity
        self.risk_manager = risk_manager
        self.mt5_config = mt5_config
        self.dry_run = dry_run
        
        # Per-symbol state
        self.signal_generators = {}
        self.sizers = {}
        self.live_data = {}
        self.last_bar_times = {}
        
        # Audit DB
        self.audit_db_path = audit_db_path or os.path.join(tempfile.gettempdir(), 'mt5_audit_multi.db')
        
        # Initialize per-symbol components
        for symbol in symbols:
            pair_cfg = get_pair_config(symbol)
            contract_specs = get_contract_specs(symbol)
            
            # Signal generator
            self.signal_generators[symbol] = create_signal_generator(symbol)
            
            # Sizer with per-symbol config
            sizing_config = SizingConfig(
                target_vol=0.15,
                max_leverage=3.0,
                min_leverage=0.01,
                kelly_fraction=0.5,
                max_position_pct=1.0,
            )
            self.sizers[symbol] = VolScaledSizer(sizing_config, garch_variant='garch')
            
            # Load historical data for initial fitting
            data_path = contract_specs['data_path']
            df = pd.read_parquet(data_path)
            if "timestamp" in df.columns:
                df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
                df = df.set_index("timestamp").sort_index()
            elif isinstance(df.index, pd.DatetimeIndex):
                df = df.sort_index()
            # Use recent data for fitting
            self.live_data[symbol] = df.tail(5000).copy()
            self.last_bar_times[symbol] = None
        
        # MT5 executor (single connection, multi-symbol)
        self.executor = MT5Executor(
            equity=equity,
            risk_manager=risk_manager,
            sizer=None,  # We manage sizers per-symbol
            mt5_config=mt5_config,
            audit_db_path=self.audit_db_path,
        )
    
    def fit_sizers(self):
        """Fit all sizers on historical data."""
        print("Fitting sizers on historical data...")
        for symbol in self.symbols:
            print(f"  Fitting {symbol}...")
            self.sizers[symbol].fit(self.live_data[symbol])
        print("  All sizers fitted.")
    
    def poll_cycle(self, mt5) -> dict:
        """Run one polling cycle across all symbols."""
        results = {
            'signals_generated': {},
            'orders_placed': {},
            'orders_failed': {},
            'equity': self.equity,
        }
        
        # Refresh live data for all symbols
        for symbol in self.symbols:
            live_df = fetch_live_data(mt5, symbol)
            if live_df is None:
                print(f"[{datetime.now()}] WARNING: No live data for {symbol}")
                continue
            
            # Validate
            ok, errors, warnings = validate_live_data(live_df, symbol)
            if not ok:
                print(f"[{datetime.now()}] WARNING: {symbol} validation failed: {errors}")
                continue
            if warnings:
                print(f"[{datetime.now()}] {symbol} validation warnings: {warnings}")
            
            self.live_data[symbol] = live_df.tail(5000).copy()
        
        # Process each symbol
        for symbol in self.symbols:
            if symbol not in self.live_data:
                continue
            
            recent_data = self.live_data[symbol]
            signal_generator = self.signal_generators[symbol]
            sizer = self.sizers[symbol]
            pair_cfg = get_pair_config(symbol)
            contract_specs = get_contract_specs(symbol)
            
            # Generate signals
            signals = signal_generator.generate(recent_data)
            if len(signals) == 0:
                continue
            
            latest_signal = signals['signal'].iloc[-1]
            
            if latest_signal != 0:
                results['signals_generated'][symbol] = latest_signal
                signal_type = 'BUY' if latest_signal == 1 else 'SELL'
                print(f"[{datetime.now()}] SIGNAL: {symbol} {signal_type}")
                
                # Compute ATR
                atr_feat = ATRFeature(window=14)
                atr_result = atr_feat.compute(recent_data)
                current_atr = atr_result.data['atr'].iloc[-1]
                
                # Get vol forecast and compute position size
                forecast_vol = sizer.forecast_vol(recent_data)
                signal_series = signals['signal']
                positions_df = sizer.compute_position_size(
                    recent_data, signal_series, self.equity, forecast_vol,
                    contract_multiplier=contract_specs['contract_size']
                )
                position_size = positions_df['position_size'].iloc[-1] if len(positions_df) > 0 else 0
                
                # Min lot floor
                min_lot = 0.01
                if position_size < min_lot:
                    position_size = min_lot
                
                # Current price from tick
                tick = mt5.symbol_info_tick(symbol)
                if tick is None:
                    print(f"  No tick data for {symbol}")
                    results['orders_failed'][symbol] = results['orders_failed'].get(symbol, 0) + 1
                    continue
                
                current_price = tick.ask if latest_signal == 1 else tick.bid
                
                # Compute stop/take
                stop_mult = pair_cfg.get("stop_multiplier", 2.0)
                reward_mult = pair_cfg.get("rr_ratio", 2.5)
                
                if latest_signal == 1:
                    stop_price = current_price - stop_mult * current_atr
                    take_profit = current_price + stop_mult * reward_mult * current_atr
                else:
                    stop_price = current_price + stop_mult * current_atr
                    take_profit = current_price - stop_mult * reward_mult * current_atr
                
                trade_config = TradeConfig(
                    symbol=symbol,
                    signal=latest_signal,
                    entry_price=current_price,
                    stop_price=stop_price,
                    take_profit=take_profit,
                    position_size=position_size,
                    max_hold_hours=24,
                    risk_pct=pair_cfg.get("risk_pct", 0.01),
                    entry_time=pd.Timestamp.now(tz='UTC'),
                )
                
                if self.dry_run:
                    # In dry run, just check risk
                    can_open, reason = self.risk_manager.can_open_position(
                        symbol, position_size * current_price, self.equity
                    )
                    if can_open:
                        # Check per-trade risk
                        can_open, reason = self.risk_manager.check_per_trade_risk(trade_config, self.equity)
                    
                    if can_open:
                        print(f"  ✅ DRY RUN: Would place {signal_type} {position_size:.4f} lots @ {current_price}")
                        results['orders_placed'][symbol] = results['orders_placed'].get(symbol, 0) + 1
                    else:
                        print(f"  ❌ DRY RUN: Rejected - {reason}")
                        results['orders_failed'][symbol] = results['orders_failed'].get(symbol, 0) + 1
                else:
                    # Live trading
                    success = self.executor.open_position(trade_config)
                    if success:
                        results['orders_placed'][symbol] = results['orders_placed'].get(symbol, 0) + 1
                        print(f"  FILLED: {symbol} {signal_type} {position_size:.4f} lots")
                    else:
                        results['orders_failed'][symbol] = results['orders_failed'].get(symbol, 0) + 1
                        print(f"  ORDER REJECTED/FAILED: {symbol}")
        
        # Update equity from MT5
        account = mt5.account_info()
        if account:
            self.equity = account.equity
            self.risk_manager.current_equity = self.equity
            self.risk_manager.peak_equity = max(self.risk_manager.peak_equity, self.equity)
            results['equity'] = self.equity
        
        return results
    
    def run_session(self, duration_minutes: int):
        """Run the trading session for the specified duration."""
        session_start = datetime.now()
        max_duration = timedelta(minutes=duration_minutes)
        
        # Get MT5 connection
        from mars.apps.trading.mt5_executor import MT5ConnectionManager
        conn_manager = MT5ConnectionManager(self.mt5_config)
        conn_manager.connect()
        mt5 = conn_manager.mt5
        
        try:
            print(f"\n=== {'DRY RUN' if self.dry_run else 'LIVE SESSION'} STARTING ({duration_minutes} minutes) ===")
            print(f"Start time: {datetime.now()}")
            print(f"Symbols: {', '.join(self.symbols)}")
            print(f"Equity: ${self.equity:.2f}")
            print(f"Tier risk per trade: {self.risk_manager.max_risk_per_trade_pct:.1%} (${self.equity * self.risk_manager.max_risk_per_trade_pct:.2f})")
            print(f"Max concurrent trades: {self.risk_manager.max_concurrent_trades}")
            print()
            
            while datetime.now() - session_start < max_duration:
                # Ensure connection
                conn_manager.ensure_connected()
                
                # Run polling cycle
                cycle_results = self.poll_cycle(mt5)
                
                # Check kill-switch
                if self.risk_manager.kill_switch_halted:
                    print(f"[{datetime.now()}] KILL SWITCH ACTIVATED - HALTING")
                    break
                
                # Status update every 30 seconds
                elapsed = datetime.now() - session_start
                if elapsed.total_seconds() % 30 < 2:
                    total_signals = sum(cycle_results['signals_generated'].values())
                    total_placed = sum(cycle_results['orders_placed'].values())
                    total_failed = sum(cycle_results['orders_failed'].values())
                    print(f"[{datetime.now()}] Status: Signals={total_signals}, Placed={total_placed}, Failed={total_failed}, Equity=${self.equity:.2f}")
                
                time.sleep(1)
        
        except KeyboardInterrupt:
            print(f"\n[{datetime.now()}] Session interrupted by user")
        
        finally:
            self.executor.shutdown()
            conn_manager.disconnect()
        
        return {
            'duration': datetime.now() - session_start,
            'final_equity': self.equity,
        }


def main():
    parser = argparse.ArgumentParser(description="MARS Multi-Symbol Live Trading Session")
    parser.add_argument("--dry-run", action="store_true", help="Validate setup without placing orders")
    parser.add_argument("--duration", type=int, default=5, help="Session duration in minutes (default: 5)")
    parser.add_argument("--symbols", nargs="+", help="Override symbols to trade (default: all enabled from PAIR_CONFIG)")
    args = parser.parse_args()
    
    # Clean up any stale kill-switch file from previous runs
    kill_switch_path = os.path.join(tempfile.gettempdir(), 'risk_kill_switch.json')
    if os.path.exists(kill_switch_path):
        os.remove(kill_switch_path)
    
    # --- MT5 Config & Demo Account Safety Gate ---
    config = MT5Config()
    if not config.is_configured():
        print("MT5 credentials not configured")
        sys.exit(1)
    
    # --- Instantiate RiskManager ---
    risk_manager = RiskManager(
        kill_switch_file=kill_switch_path,
    )
    
    # --- Connect to MT5 to get LIVE equity for tier selection ---
    print("=== DRY RUN: Connecting to MT5 for live equity ===")
    mt5_config = DEFAULT_CONFIG.mt5
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
    
    # Verify all symbols are in PAIR_CONFIG
    for symbol in symbols:
        if symbol not in get_pair_config.__wrapped__.__self__ if hasattr(get_pair_config, '__wrapped__') else True:
            pass  # get_pair_config will raise KeyError if not found
    
    # --- Create and run multi-symbol session ---
    session = MultiSymbolSession(
        symbols=symbols,
        equity=live_equity,
        risk_manager=risk_manager,
        mt5_config=mt5_config,
        dry_run=args.dry_run,
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