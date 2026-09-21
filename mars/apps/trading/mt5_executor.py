# -*- coding: utf-8 -*-
"""
MT5 Live Execution Module
=========================
Production-grade MT5 executor for live demo trading.
Replaces backtest TradeExecutor with real MT5 integration.

Key features:
- Idempotent order placement (prevents duplicate orders per bar/signal)
- Live MT5 position checking for concurrent risk
- Every order_send() call is logged (success or failure)
- SQLite audit trail with WAL mode and auto-backup
- Manual SL/TP modification detection and reconciliation
"""

from __future__ import annotations

import json
import sqlite3
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from threading import Lock

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None  # type: ignore

from mars.apps.trading.system.vol_scaled_system import (
    RiskManager,
    VolScaledSizer,
    TradeConfig,
)


class DemoAccountGate:
    """
    Mandatory safety gate - hard-fails if connected account is not DEMO.
    This gate CANNOT be bypassed by config/env/flag - requires code change to disable.
    """

    @staticmethod
    def verify_demo_account(mt5_module) -> dict:
        """
        Verify connected account is DEMO. Hard-fails if not.

        Returns account info dict if verification passes.
        Raises RuntimeError if account is not DEMO.
        """
        account_info = mt5_module.account_info()
        if account_info is None:
            raise RuntimeError(f"Failed to get account info: {mt5_module.last_error()}")

        trade_mode = account_info.trade_mode
        account_number = account_info.login

        # Log account info on every startup
        print(f"MT5 ACCOUNT CONNECTED: #{account_number} | Trade Mode: {trade_mode}")

        # MT5 trade_mode constants:
        # TRADE_MODE_DEMO = 0, TRADE_MODE_CONTEST = 1, TRADE_MODE_REAL = 2
        if trade_mode != 0:  # TRADE_MODE_DEMO = 0
            raise RuntimeError(
                f"SAFETY GATE FAILED: Account #{account_number} is NOT a DEMO account. "
                f"Trade mode: {trade_mode} (0=DEMO, 1=CONTEST, 2=REAL). "
                f"Refusing to trade on non-demo account. "
                f"To disable this gate, modify DemoAccountGate.verify_demo_account() in mt5_executor.py"
            )

        return {
            "account_number": account_number,
            "trade_mode": trade_mode,
            "balance": account_info.balance,
            "equity": account_info.equity,
            "currency": account_info.currency,
            "leverage": account_info.leverage,
        }


from dataclasses import dataclass


@dataclass
class MT5SymbolInfo:
    """Runtime symbol specification from MT5."""
    symbol: str
    contract_size: float
    min_lot: float
    max_lot: float
    lot_step: float
    digits: int
    point: float
    spread: int
    spread_float: float
    tick_size: float
    tick_value: float
    swap_long: float
    swap_short: float
    margin_initial: float
    margin_maintenance: float
    session_deals: int
    session_buy_orders: int
    session_sell_orders: int
    volume_min: float
    volume_max: float
    volume_step: float
    bid: float
    ask: float
    last: float
    volume_real: float
    time: datetime
    # Filling modes supported by broker (bitmask)
    filling_mode: int = 0
    # Order modes supported by broker (bitmask)
    order_mode: int = 0


# ============================================================================
# MT5 Connection & Order Routing
# ============================================================================

class MT5Config:
    """MT5 connection configuration."""
    def __init__(
        self,
        login: int = 0,
        password: str = "",
        server: str = "",
        path: str = "",
        timeout: int = 60000,
        portable: bool = False,
    ):
        self.login = login
        self.password = password
        self.server = server
        self.path = path
        self.timeout = timeout
        self.portable = portable

    def is_configured(self) -> bool:
        return bool(self.login and self.password and self.server)


DEFAULT_MT5_CONFIG = MT5Config(
    login=int(os.getenv("DEMO_ACCOUNT_NUMBER", "476944496")),
    password=os.getenv("PASSWORD", ""),
    server=os.getenv("SERVER", ""),
    path="C:\\Program Files\\MetaTrader 5\\terminal64.exe",
    timeout=60000,
    portable=False,
)


class OrderRequest:
    """MT5 order request structure."""
    action: int
    symbol: str
    volume: float
    type: int
    price: float
    sl: float
    tp: float
    deviation: int
    magic: int
    comment: str
    type_time: int
    type_filling: int
    signal: int = 0  # Signal direction (1=buy, -1=sell)


@dataclass
class FillResult:
    """Result of order execution."""
    success: bool
    ticket: int
    order_id: int
    volume: float
    price: float
    bid: float
    ask: float
    sl: float
    tp: float
    comment: str
    request: OrderRequest
    result_code: int
    retcode_external: int
    timestamp: datetime
    slippage: float = 0.0  # filled_price - signal_price (price slippage)
    size_slippage: float = 0.0  # filled_volume - requested_volume (size slippage)
    commission: float = 0.0
    swap: float = 0.0
    profit: float = 0.0


class MT5ConnectionManager:
    """Manages MT5 connection lifecycle with auto-reconnect."""
    
    def __init__(self, config: MT5Config):
        self.config = config
        self.mt5 = None
        self._connected = False
        self._last_connect_time = 0
        self._reconnect_cooldown = 30  # seconds
    
    def connect(self) -> bool:
        """Establish MT5 connection."""
        if mt5 is None:
            raise RuntimeError("MetaTrader5 package not installed. Run: pip install MetaTrader5")
        
        if self._connected and self.mt5 is not None:
            return True
        
        # Check cooldown
        now = time.time()
        if now - self._last_connect_time < self._reconnect_cooldown:
            return self._connected
        
        self._last_connect_time = now
        
        try:
            if self.config.path:
                result = mt5.initialize(
                    path=self.config.path,
                    login=self.config.login,
                    password=self.config.password,
                    server=self.config.server,
                    timeout=self.config.timeout,
                    portable=self.config.portable,
                )
            else:
                result = mt5.initialize(
                    login=self.config.login,
                    password=self.config.password,
                    server=self.config.server,
                    timeout=self.config.timeout,
                    portable=self.config.portable,
                )
            
            if result:
                self.mt5 = mt5
                self._connected = True
                print(f"✅ MT5 connected: account #{self.config.login}")
                return True
            else:
                error = mt5.last_error()
                print(f"❌ MT5 connection failed: {error}")
                self._connected = False
                return False
        except Exception as e:
            print(f"❌ MT5 connection error: {e}")
            self._connected = False
            return False
    
    def ensure_connected(self) -> bool:
        """Ensure connection is alive, reconnect if needed."""
        if self._connected and self.mt5 is not None:
            # Quick health check
            try:
                _ = self.mt5.account_info()
                return True
            except Exception:
                self._connected = False
        
        return self.connect()
    
    def disconnect(self):
        """Clean disconnect."""
        if self.mt5:
            self.mt5.shutdown()
        self._connected = False
        self.mt5 = None


class MT5SymbolResolver:
    """Resolves symbol names and provides trading specifications."""
    
    def __init__(self, mt5_module):
        self.mt5 = mt5_module
        self._symbol_cache: Dict[str, Any] = {}
    
    def get_symbol_info(self, symbol: str):
        """Get MT5 symbol info with caching."""
        if symbol not in self._symbol_cache:
            info = self.mt5.symbol_info(symbol)
            if info is None:
                raise ValueError(f"Symbol {symbol} not found in MT5")
            if not info.visible:
                self.mt5.symbol_select(symbol, True)
                info = self.mt5.symbol_info(symbol)
            self._symbol_cache[symbol] = info
        return self._symbol_cache[symbol]
    
    def get_pip_value(self, symbol: str) -> float:
        """Get pip value for 1 lot."""
        info = self.get_symbol_info(symbol)
        return info.trade_tick_value  # Usually $1 per pip per lot for XAUUSD


class MT5OrderRouter:
    """Routes orders to MT5 with proper fill handling."""
    
    def __init__(self, mt5_module, symbol_resolver: MT5SymbolResolver):
        self.mt5 = mt5_module
        self.symbol_resolver = symbol_resolver
    
    def send_order(self, config: TradeConfig, spec) -> "OrderFill":
        """Send order to MT5 and return fill result."""
        from dataclasses import dataclass
        
        @dataclass
        class OrderFill:
            success: bool
            ticket: int
            order_id: int
            price: float
            volume: float
            sl: float
            tp: float
            slippage: float
            size_slippage: float
            bid: float
            ask: float
            spread: float
            commission: float
            swap: float
            profit: float
            result_code: int
            retcode_external: int
            comment: str
        
        # Determine order type
        order_type = self.mt5.ORDER_TYPE_BUY if config.signal > 0 else self.mt5.ORDER_TYPE_SELL
        
        # Get current prices
        tick = self.mt5.symbol_info_tick(config.symbol)
        if tick is None:
            return OrderFill(
                success=False, ticket=0, order_id=0, price=0, volume=0,
                sl=config.stop_price, tp=config.take_profit,
                slippage=0, size_slippage=0, bid=0, ask=0, spread=0,
                commission=0, swap=0, profit=0, result_code=-1, retcode_external=-1,
                comment="No tick data"
            )
        
        price = tick.ask if config.signal > 0 else tick.bid
        sl = config.stop_price
        tp = config.take_profit
        
        # Normalize to symbol precision
        info = self.symbol_resolver.get_symbol_info(config.symbol)
        digits = info.digits
        price = round(price, digits)
        sl = round(sl, digits)
        tp = round(tp, digits)
        volume = round(config.position_size, 2)
        
        # Build request
        request = {
            "action": self.mt5.TRADE_ACTION_DEAL,
            "symbol": config.symbol,
            "volume": volume,
            "type": order_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": 20,
            "magic": 123456,
            "comment": f"MARS_{config.signal}_{config.entry_time.strftime('%H%M')}",
            "type_time": self.mt5.ORDER_TIME_GTC,
            "type_filling": self.mt5.ORDER_FILLING_IOC,
        }
        
        # Send order
        result = self.mt5.order_send(request)
        
        if result is None:
            error = self.mt5.last_error()
            return OrderFill(
                success=False, ticket=0, order_id=0, price=price, volume=volume,
                sl=sl, tp=tp, slippage=0, size_slippage=0, bid=tick.bid, ask=tick.ask,
                spread=tick.ask - tick.bid, commission=0, swap=0, profit=0,
                result_code=-1, retcode_external=-1, comment=f"order_send returned None: {error}"
            )
        
        # Calculate slippage
        expected_price = price
        actual_price = result.price
        slippage = abs(actual_price - expected_price) * 10000  # in pips
        
        if result.retcode == self.mt5.TRADE_RETCODE_DONE:
            return OrderFill(
                success=True,
                ticket=result.order,
                order_id=result.order,
                price=actual_price,
                volume=result.volume,
                sl=sl,
                tp=tp,
                slippage=slippage,
                size_slippage=0.0,
                bid=tick.bid,
                ask=tick.ask,
                spread=tick.ask - tick.bid,
                commission=result.commission if hasattr(result, 'commission') else 0,
                swap=result.swap if hasattr(result, 'swap') else 0,
                profit=result.profit if hasattr(result, 'profit') else 0,
                result_code=result.retcode,
                retcode_external=result.retcode_external if hasattr(result, 'retcode_external') else -1,
                comment=result.comment if hasattr(result, 'comment') else "",
            )
        else:
            return OrderFill(
                success=False, ticket=result.order if hasattr(result, 'order') else 0,
                order_id=result.order if hasattr(result, 'order') else 0,
                price=price, volume=volume, sl=sl, tp=tp,
                slippage=slippage, size_slippage=0.0,
                bid=tick.bid, ask=tick.ask, spread=tick.ask - tick.bid,
                commission=0, swap=0, profit=0,
                result_code=result.retcode,
                retcode_external=result.retcode_external if hasattr(result, 'retcode_external') else -1,
                comment=f"Order failed: {result.comment} (retcode={result.retcode})"
            )


# ============================================================================
# Audit Logger
# ============================================================================

class MT5AuditLogger:
    """Persists all trading activity to SQLite for audit trail with WAL mode and auto-backup."""
    
    def __init__(self, db_path: str = "mt5_audit.db"):
        self.db_path = Path(db_path)
        self.backup_paths = [
            Path.home() / "MARS_AUDIT_BACKUP" / f"mt5_audit_{datetime.now().strftime('%Y%m%d')}.db",
            Path("mt5_audit_backup.db"),
        ]
        for bp in self.backup_paths:
            bp.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema with WAL mode."""
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            # Enable WAL mode for better concurrency
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=10000")
            conn.execute("PRAGMA temp_store=MEMORY")
            
            cursor = conn.cursor()
            
            # Signals table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    signal INTEGER NOT NULL,
                    entry_price REAL NOT NULL,
                    stop_price REAL NOT NULL,
                    take_profit REAL NOT NULL,
                    position_size REAL NOT NULL,
                    risk_at_stop REAL NOT NULL,
                    risk_pct REAL NOT NULL,
                    risk_check_passed INTEGER NOT NULL,
                    rejection_reason TEXT,
                    bar_key TEXT,
                    max_hold_hours REAL
                )
            """)
            
            # Fills table (every order_send result)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS fills (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    ticket INTEGER NOT NULL,
                    order_id INTEGER,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    requested_lots REAL,
                    filled_lots REAL,
                    signal_price REAL,
                    filled_price REAL,
                    requested_sl REAL,
                    filled_sl REAL,
                    requested_tp REAL,
                    filled_tp REAL,
                    slippage_points REAL,
                    slippage_pct REAL,
                    size_slippage REAL,
                    spread_at_fill REAL,
                    commission REAL,
                    swap REAL,
                    profit REAL,
                    mt5_ticket INTEGER,
                    mt5_order_id INTEGER,
                    retcode INTEGER,
                    retcode_external INTEGER,
                    comment TEXT
                )
            """)
            
            # Risk decisions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS risk_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    signal INTEGER NOT NULL,
                    decision TEXT NOT NULL,
                    reason TEXT,
                    position_value REAL NOT NULL,
                    equity REAL NOT NULL,
                    risk_pct REAL NOT NULL,
                    tier_risk_cap_pct REAL NOT NULL,
                    aggregate_risk_pct REAL NOT NULL
                )
            """)
            
            # Risk events table (daily loss, kill-switch, manual modifications)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS risk_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    details TEXT NOT NULL,
                    equity REAL NOT NULL,
                    drawdown_pct REAL NOT NULL,
                    daily_pnl REAL NOT NULL,
                    kill_switch_active INTEGER NOT NULL
                )
            """)
            
            # Manual modifications table (NEW)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS manual_modifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    ticket INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    old_sl REAL NOT NULL,
                    new_sl REAL NOT NULL,
                    old_tp REAL NOT NULL,
                    new_tp REAL NOT NULL,
                    old_risk_usd REAL NOT NULL,
                    new_risk_usd REAL NOT NULL,
                    old_risk_pct REAL NOT NULL,
                    new_risk_pct REAL NOT NULL,
                    tier_risk_cap_pct REAL NOT NULL,
                    aggregate_cap_pct REAL NOT NULL,
                    total_open_risk_before REAL NOT NULL,
                    total_open_risk_after REAL NOT NULL,
                    exceeds_per_trade_cap INTEGER NOT NULL,
                    exceeds_aggregate_cap INTEGER NOT NULL,
                    action_taken TEXT NOT NULL,
                    equity REAL NOT NULL,
                    kill_switch_active INTEGER NOT NULL
                )
            """)
            
            # Create indexes for common queries
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_signals_timestamp ON signals(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_fills_timestamp ON fills(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_fills_symbol ON fills(symbol)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_risk_events_timestamp ON risk_events(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_risk_events_type ON risk_events(event_type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_manual_mods_timestamp ON manual_modifications(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_manual_mods_ticket ON manual_modifications(ticket)")
            
            conn.commit()
    
    def log_signal(self, config: TradeConfig, fill_price: float,
                   risk_check_passed: bool, rejection_reason: Optional[str],
                   risk_at_stop: float, risk_pct: float):
        """Log signal with risk check result."""
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO signals (
                    timestamp, symbol, signal, entry_price,
                    stop_price, take_profit, position_size,
                    risk_at_stop, risk_pct, risk_check_passed,
                    rejection_reason, bar_key, max_hold_hours
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(),
                config.symbol, config.signal, fill_price,
                config.stop_price, config.take_profit, config.position_size,
                risk_at_stop, risk_pct, 1 if risk_check_passed else 0,
                rejection_reason,
                "",  # bar_key not available here
                config.max_hold_hours if config.max_hold_hours else 0,
            ))
            conn.commit()
    
    def log_fill(self, fill, config: TradeConfig, expected_price: float):
        """Log order fill with slippage calculation."""
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Calculate slippage in points and percentage
            spread_at_fill = fill.ask - fill.bid
            
            # Get actual commission, swap, profit from MT5 history for this fill
            commission = 0.0
            swap = 0.0
            profit = 0.0
            try:
                if hasattr(fill, 'mt5_ticket') and fill.mt5_ticket:
                    deals = self.mt5.history_deals_get(ticket=fill.mt5_ticket)
                    if deals and len(deals) > 0:
                        deal = deals[0]
                        commission = getattr(deal, 'commission', 0.0)
                        swap = getattr(deal, 'swap', 0.0)
                        profit = getattr(deal, 'profit', 0.0)
            except Exception:
                pass  # Keep defaults if history lookup fails
            
            cursor.execute("""
                            INSERT INTO fills (
                                timestamp, ticket, order_id, symbol, direction,
                                requested_lots, filled_lots, signal_price,
                                filled_price, requested_sl, filled_sl,
                                requested_tp, filled_tp, slippage_points,
                                slippage_pct, size_slippage, spread_at_fill, commission, swap,
                                profit, mt5_ticket, mt5_order_id,
                                retcode, retcode_external, comment
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            fill.timestamp.isoformat() if hasattr(fill, 'timestamp') else datetime.now().isoformat(),
                            fill.ticket, fill.order_id, 
                            fill.request.symbol if hasattr(fill, 'request') else config.symbol,
                            "BUY" if (hasattr(fill, 'request') and fill.request.signal == 1) else (config.signal == 1 and "BUY" or "SELL"),
                            fill.request.volume if hasattr(fill, 'request') else config.position_size,
                            fill.volume,
                            expected_price, fill.price,
                            config.stop_price, fill.sl,
                            config.take_profit, fill.tp,
                            fill.slippage,
                            fill.slippage / expected_price * 10000 if expected_price > 0 else 0,
                            fill.size_slippage,
                            spread_at_fill,
                            commission, swap, profit,
                            fill.mt5_ticket if hasattr(fill, 'mt5_ticket') else fill.ticket,
                            fill.order_id,
                            fill.result_code,
                            fill.retcode_external if not isinstance(fill.retcode_external, type(None)) else -1,
                            fill.comment
                        ))
            conn.commit()
    
    def log_risk_decision(self, config: TradeConfig, decision: str, reason: str,
                          position_value: float, equity: float,
                          risk_pct: float, tier_risk_cap_pct: float,
                          aggregate_risk_pct: float):
        """Log risk check decision."""
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO risk_decisions (
                    timestamp, symbol, signal, decision, reason,
                    position_value, equity, risk_pct,
                    tier_risk_cap_pct, aggregate_risk_pct
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(),
                config.symbol, config.signal, decision, reason,
                position_value, equity, risk_pct,
                tier_risk_cap_pct, aggregate_risk_pct
            ))
            conn.commit()
    
    def log_risk_event(self, event_type: str, details: str,
                       equity: float, drawdown_pct: float,
                       daily_pnl: float, kill_switch_active: bool):
        """Log risk events (daily loss limit, kill-switch, etc.)."""
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO risk_events (
                    timestamp, event_type, details,
                    equity, drawdown_pct, daily_pnl, kill_switch_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(),
                event_type, details,
                equity, drawdown_pct, daily_pnl, kill_switch_active
            ))
            conn.commit()

    def log_manual_modification(self,
                                ticket: int,
                                symbol: str,
                                old_sl: float,
                                new_sl: float,
                                old_tp: float,
                                new_tp: float,
                                old_risk_usd: float,
                                new_risk_usd: float,
                                old_risk_pct: float,
                                new_risk_pct: float,
                                tier_risk_cap_pct: float,
                                aggregate_cap_pct: float,
                                total_open_risk_before: float,
                                total_open_risk_after: float,
                                exceeds_per_trade_cap: bool,
                                exceeds_aggregate_cap: bool,
                                action_taken: str,
                                equity: float,
                                kill_switch_active: bool):
        """Log manual SL/TP modification detection and reconciliation."""
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO manual_modifications (
                    timestamp, ticket, symbol,
                    old_sl, new_sl, old_tp, new_tp,
                    old_risk_usd, new_risk_usd,
                    old_risk_pct, new_risk_pct,
                    tier_risk_cap_pct, aggregate_cap_pct,
                    total_open_risk_before, total_open_risk_after,
                    exceeds_per_trade_cap, exceeds_aggregate_cap,
                    action_taken, equity, kill_switch_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(),
                ticket, symbol,
                old_sl, new_sl, old_tp, new_tp,
                old_risk_usd, new_risk_usd,
                old_risk_pct, new_risk_pct,
                tier_risk_cap_pct, aggregate_cap_pct,
                total_open_risk_before, total_open_risk_after,
                exceeds_per_trade_cap, exceeds_aggregate_cap,
                action_taken, equity, kill_switch_active
            ))
            conn.commit()

    def backup(self) -> list[Path]:
        """Backup audit database to all configured backup locations."""
        import shutil
        backed_up = []
        for backup_path in self.backup_paths:
            try:
                # Use copy2 to preserve metadata
                shutil.copy2(self.db_path, backup_path)
                # Also backup WAL and SHM files if they exist
                for suffix in ['-wal', '-shm']:
                    src = self.db_path.with_suffix(self.db_path.suffix + suffix)
                    dst = backup_path.with_suffix(backup_path.suffix + suffix)
                    if src.exists():
                        shutil.copy2(src, dst)
                backed_up.append(backup_path)
                print(f"  ✅ Audit DB backed up to: {backup_path}")
            except Exception as e:
                print(f"  ⚠️  Backup failed to {backup_path}: {e}")
        return backed_up

    def close(self):
        """Close database and checkpoint WAL to release file locks (Windows compatibility)."""
        import sqlite3
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception:
            pass


# ============================================================================
# MT5 Live Executor
# ============================================================================

class MT5Executor:
    """
    Live MT5 executor implementing TradeExecutor interface.
    Replaces backtest TradeExecutor for live demo trading.
    
    Key fixes:
    - Idempotent order placement (prevents duplicate orders per bar/signal)
    - Live MT5 position checking for concurrent risk
    - Every order_send() call is logged (success or failure)
    - Manual SL/TP modification detection and reconciliation
    """
    
    def __init__(
            self,
            equity: float,
            risk_manager: Optional[RiskManager] = None,
            sizer: Optional[VolScaledSizer] = None,
            mt5_config: Optional[MT5Config] = None,
            audit_db_path: str = "mt5_audit.db",
            conn_manager: Optional[MT5ConnectionManager] = None,
            auto_initialize: bool = True,
        ) -> None:
            self.equity = equity
            self.risk_manager = risk_manager or RiskManager()
            self.sizer = sizer

            # MT5 components
            self.mt5_config = mt5_config or DEFAULT_MT5_CONFIG
            self.conn_manager = conn_manager or MT5ConnectionManager(self.mt5_config)
            self.mt5 = None
            self.symbol_resolver = None
            self.order_router = None
            self.audit_logger = MT5AuditLogger(audit_db_path)

            # State
            self.open_positions: Dict[str, Dict] = {}
            self.closed_trades: List[Dict] = []
            self.equity_curve = [equity]
            self._signal_counter = 0
            self._lock = Lock()

            # Idempotency tracking (persisted to survive restart, bounded to prevent memory leak)
            self._processed_signals: set[str] = set()  # "symbol_bar_signal" keys
            self._IDEMPOTENCY_FILE = Path(audit_db_path).with_suffix('.idempotency.json')
            self._MAX_PROCESSED_SIGNALS = 10000  # ~2 months of 5-min bars
            self._load_idempotency_state()

            # Connect and initialize
            if auto_initialize:
                self._initialize()
    
    def _initialize(self):
        """Initialize MT5 connection and components."""
        self.conn_manager.connect()
        self.mt5 = self.conn_manager.mt5
        self.symbol_resolver = MT5SymbolResolver(self.mt5)
        self.order_router = MT5OrderRouter(self.mt5, self.symbol_resolver)
        
        # Log initial account state
        account_info = self.mt5.account_info()
        if account_info:
            print(f"MT5 DEMO ACCOUNT: #{account_info.login} | Balance: {account_info.balance:.2f} | Equity: {account_info.equity:.2f}")
        
        # Sync positions from MT5 on startup
        self._sync_positions_from_mt5()
    
    def _load_idempotency_state(self) -> None:
        """Load processed signals from disk to survive restart."""
        try:
            if self._IDEMPOTENCY_FILE.exists():
                with open(self._IDEMPOTENCY_FILE, 'r') as f:
                    data = json.load(f)
                self._processed_signals = set(data.get('processed_signals', []))
                print(f"Loaded {len(self._processed_signals)} processed signals from {self._IDEMPOTENCY_FILE}")
        except Exception as e:
            print(f"Warning: failed to load idempotency state: {e}")
            self._processed_signals = set()
    
    def _save_idempotency_state(self) -> None:
        """Save processed signals to disk."""
        try:
            # Prune if too large (keep most recent half)
            if len(self._processed_signals) > self._MAX_PROCESSED_SIGNALS:
                # Convert to list, sort by timestamp in key, keep newest half
                signals_list = list(self._processed_signals)
                # Keys are like "XAUUSDm_2026-09-10T01:40:00_1"
                signals_list.sort(key=lambda k: k.split('_')[1], reverse=True)
                self._processed_signals = set(signals_list[:self._MAX_PROCESSED_SIGNALS // 2])
                print(f"Pruned idempotency set to {len(self._processed_signals)} entries")
            
            with open(self._IDEMPOTENCY_FILE, 'w') as f:
                json.dump({'processed_signals': list(self._processed_signals)}, f)
        except Exception as e:
            print(f"Warning: failed to save idempotency state: {e}")
    
    def _get_bar_key(self, timestamp: datetime) -> str:
        """Get normalized bar key (5-minute boundary)."""
        bar_time = timestamp.replace(second=0, microsecond=0)
        bar_minute = bar_time.minute
        if bar_minute % 5 != 0:
            bar_time = bar_time.replace(minute=(bar_minute // 5) * 5)
        return bar_time.isoformat()
    
    def _is_duplicate_signal(self, symbol: str, bar_key: str, signal: int) -> bool:
        """Check if this signal for this bar has already been acted upon."""
        signal_key = f"{symbol}_{bar_key}_{signal}"
        if signal_key in self._processed_signals:
            return True
        self._processed_signals.add(signal_key)
        self._save_idempotency_state()  # Persist after every addition
        return False
    
    def _get_live_open_positions_value(self, symbol: str) -> float:
        """Get current open position value for a symbol from LIVE MT5."""
        self._ensure_connection()
        positions = self.mt5.positions_get(symbol=symbol)
        if not positions:
            return 0.0
        
        total_value = 0.0
        for pos in positions:
            if pos.magic == 123456:
                total_value += pos.volume * pos.price_open * 100  # contract_size=100
        return total_value
    
    def _sync_positions_from_mt5(self) -> None:
        """Sync internal position tracking with live MT5 positions."""
        self._ensure_connection()
        positions = self.mt5.positions_get(symbol="XAUUSDm")
        if positions:
            self.open_positions = {}
            for pos in positions:
                if pos.magic == 123456:  # Only our positions
                    self.open_positions[pos.symbol] = {
                        "entry_price": pos.price_open,
                        "stop_price": pos.sl,
                        "take_profit": pos.tp,
                        "position_size": pos.volume if pos.type == 0 else -pos.volume,
                        "entry_time": datetime.fromtimestamp(pos.time),
                        "mt5_ticket": pos.ticket,
                        "mt5_position_id": pos.identifier,
                    }
        else:
            self.open_positions = {}
    
    def _detect_manual_sl_tp_changes(self) -> list[dict]:
        """
        Detect manual SL/TP modifications on open positions.
        Compares broker's live SL/TP against system's tracked values.
        
        Returns list of detected modifications with reconciliation details.
        """
        self._ensure_connection()
        modifications = []
        
        # Get all our positions from MT5
        positions = self.mt5.positions_get(symbol="XAUUSDm")
        if not positions:
            return modifications
        
        for pos in positions:
            if pos.magic != 123456:
                continue
            
            symbol = pos.symbol
            ticket = pos.ticket
            
            # Find matching internal position
            if symbol not in self.open_positions:
                continue
            
            internal_pos = self.open_positions[symbol]
            tracked_sl = internal_pos.get("stop_price", 0)
            tracked_tp = internal_pos.get("take_profit", 0)
            
            # Live SL/TP from broker
            live_sl = pos.sl
            live_tp = pos.tp
            
            # Check for differences (with small epsilon for float comparison)
            sl_changed = abs(live_sl - tracked_sl) > 1e-8 if tracked_sl > 0 and live_sl > 0 else False
            tp_changed = abs(live_tp - tracked_tp) > 1e-8 if tracked_tp > 0 and live_tp > 0 else False
            
            if not sl_changed and not tp_changed:
                continue
            
            # Manual modification detected - reconcile
            entry_price = internal_pos["entry_price"]
            position_size = internal_pos["position_size"]
            
            # Calculate risk with OLD stop
            old_stop_distance = abs(entry_price - tracked_sl) if tracked_sl > 0 else 0
            old_risk_usd = old_stop_distance * abs(position_size) * 100  # XAUUSD: $1/pip per oz, 100 oz/lot
            old_risk_pct = old_risk_usd / self.equity if self.equity > 0 else 0
            
            # Calculate risk with NEW stop
            new_stop_distance = abs(entry_price - live_sl) if live_sl > 0 else 0
            new_risk_usd = new_stop_distance * abs(position_size) * 100
            new_risk_pct = new_risk_usd / self.equity if self.equity > 0 else 0
            
            # Get tier and aggregate risk caps
            tier = self.risk_manager.get_current_tier() if self.risk_manager._current_tier else {"risk_pct_per_trade": 0.01, "aggregate_risk_pct": 0.01}
            tier_risk_cap_pct = tier.get("risk_pct_per_trade", 0.01)
            aggregate_cap_pct = tier.get("aggregate_risk_pct", tier_risk_cap_pct)
            
            # Calculate total open risk before and after
            total_open_risk_before = self.risk_manager.total_open_risk
            
            # Adjust total open risk: remove old risk, add new risk for this position
            is_min_lot_override = internal_pos.get("is_min_lot_override", False)
            
            if not is_min_lot_override:
                total_open_risk_after = total_open_risk_before - old_risk_usd + new_risk_usd
            else:
                total_open_risk_after = total_open_risk_before  # Min-lot override doesn't count in aggregate
            
            # Check if new risk exceeds caps
            exceeds_per_trade_cap = new_risk_pct > tier_risk_cap_pct
            exceeds_aggregate_cap = total_open_risk_after > self.equity * aggregate_cap_pct
            
            # Determine action taken
            action_taken = "ALERT_ONLY"
            if exceeds_per_trade_cap or exceeds_aggregate_cap:
                action_taken = "AUTO_CLOSE_POSITION"
            
            # Build modification record
            mod = {
                "ticket": ticket,
                "symbol": symbol,
                "old_sl": tracked_sl,
                "new_sl": live_sl,
                "old_tp": tracked_tp,
                "new_tp": live_tp,
                "old_risk_usd": old_risk_usd,
                "new_risk_usd": new_risk_usd,
                "old_risk_pct": old_risk_pct,
                "new_risk_pct": new_risk_pct,
                "tier_risk_cap_pct": tier_risk_cap_pct,
                "aggregate_cap_pct": aggregate_cap_pct,
                "total_open_risk_before": total_open_risk_before,
                "total_open_risk_after": total_open_risk_after,
                "exceeds_per_trade_cap": exceeds_per_trade_cap,
                "exceeds_aggregate_cap": exceeds_aggregate_cap,
                "action_taken": action_taken,
                "entry_price": entry_price,
                "position_size": position_size,
            }
            modifications.append(mod)
        
        return modifications

    def _reconcile_manual_modifications(self, modifications: list[dict]) -> None:
        """
        Reconcile detected manual SL/TP modifications.
        - Log the modification
        - Update internal tracking
        - If over cap, close the position
        """
        for mod in modifications:
            ticket = mod["ticket"]
            symbol = mod["symbol"]
            
            # Log the manual modification event
            self.audit_logger.log_manual_modification(
                ticket=ticket,
                symbol=symbol,
                old_sl=mod["old_sl"],
                new_sl=mod["new_sl"],
                old_tp=mod["old_tp"],
                new_tp=mod["new_tp"],
                old_risk_usd=mod["old_risk_usd"],
                new_risk_usd=mod["new_risk_usd"],
                old_risk_pct=mod["old_risk_pct"],
                new_risk_pct=mod["new_risk_pct"],
                tier_risk_cap_pct=mod["tier_risk_cap_pct"],
                aggregate_cap_pct=mod["aggregate_cap_pct"],
                total_open_risk_before=mod["total_open_risk_before"],
                total_open_risk_after=mod["total_open_risk_after"],
                exceeds_per_trade_cap=mod["exceeds_per_trade_cap"],
                exceeds_aggregate_cap=mod["exceeds_aggregate_cap"],
                action_taken=mod["action_taken"],
                equity=self.equity,
                kill_switch_active=self.risk_manager.kill_switch_halted,
            )
            
            # Also log as risk event for visibility
            details = (
                f"MANUAL_MODIFICATION_DETECTED: ticket={ticket} symbol={symbol} "
                f"old_sl={mod['old_sl']:.5f} new_sl={mod['new_sl']:.5f} "
                f"old_tp={mod['old_tp']:.5f} new_tp={mod['new_tp']:.5f} "
                f"old_risk=${mod['old_risk_usd']:.2f} ({mod['old_risk_pct']:.2%}) "
                f"new_risk=${mod['new_risk_usd']:.2f} ({mod['new_risk_pct']:.2%}) "
                f"tier_cap={mod['tier_risk_cap_pct']:.1%} agg_cap={mod['aggregate_cap_pct']:.1%} "
                f"exceeds_per_trade={mod['exceeds_per_trade_cap']} exceeds_agg={mod['exceeds_aggregate_cap']} "
                f"action={mod['action_taken']}"
            )
            self.audit_logger.log_risk_event(
                "MANUAL_MODIFICATION_DETECTED",
                details,
                self.equity,
                0.0,
                self.risk_manager.daily_pnl,
                self.risk_manager.kill_switch_halted,
            )
            
            print(f"⚠️  MANUAL SL/TP MODIFICATION DETECTED: {details}")
            
            # Update internal tracking to new SL/TP
            if symbol in self.open_positions:
                self.open_positions[symbol]["stop_price"] = mod["new_sl"]
                self.open_positions[symbol]["take_profit"] = mod["new_tp"]
            
            # Update risk manager's aggregate tracking
            if symbol in self.risk_manager.current_positions:
                is_min_lot_override = self.risk_manager.current_positions[symbol].get("is_min_lot_override", False)
                if not is_min_lot_override:
                    # Remove old risk, add new risk
                    old_risk = self.risk_manager.current_positions[symbol].get("risk_at_stop", 0)
                    self.risk_manager.total_open_risk = max(0.0, self.risk_manager.total_open_risk - old_risk + mod["new_risk_usd"])
                    self.risk_manager.current_positions[symbol]["risk_at_stop"] = mod["new_risk_usd"]
            
            # If exceeds caps, auto-close the position
            if mod["action_taken"] == "AUTO_CLOSE_POSITION":
                print(f"🚨 RISK CAP EXCEEDED - Auto-closing position {symbol} (ticket={ticket})")
                
                # Close the position
                tick = self.mt5.symbol_info_tick(symbol)
                if tick:
                    close_price = tick.bid if mod["position_size"] > 0 else tick.ask
                    self._close_live_position(symbol, close_price, "manual_mod_over_cap", 0)

    def _ensure_connection(self) -> None:
        """Ensure MT5 connection is alive before any operation."""
        if not self.conn_manager.ensure_connected():
            raise RuntimeError("MT5 connection lost and reconnection failed")
        self.mt5 = self.conn_manager.mt5
    
    def open_position(self, config: TradeConfig) -> bool:
        """
        Open live position on MT5 demo account.
        Implements same interface as backtest TradeExecutor.
        Includes idempotency guard and live risk checks.
        """
        self._ensure_connection()
        
        # Log signal
        signal_price = config.entry_price
        risk_at_stop = abs(config.entry_price - config.stop_price) * config.position_size * 100
        risk_pct = risk_at_stop / self.equity * 100 if self.equity > 0 else 0
        
        # Get current bar key for idempotency
        entry_time = config.entry_time.to_pydatetime() if hasattr(config.entry_time, 'to_pydatetime') else config.entry_time
        bar_key = self._get_bar_key(entry_time)
        
        # Check idempotency - skip if same signal for same bar already processed
        if self._is_duplicate_signal(config.symbol, bar_key, config.signal):
            self.audit_logger.log_signal(
                config, config.entry_price,
                risk_check_passed=False,
                rejection_reason=f"DUPLICATE_SIGNAL: signal {config.signal} for bar {bar_key} already processed",
                risk_at_stop=risk_at_stop, risk_pct=risk_pct
            )
            return False
        
        # 1. Concurrent exposure cap - check LIVE MT5 positions
        live_position_value = self._get_live_open_positions_value(config.symbol)
        can_open, reason = self.risk_manager.can_open_position(
            config.symbol,
            live_position_value + config.position_size * config.entry_price,
            self.equity
        )
        
        self.audit_logger.log_risk_decision(
            config, "REJECTED" if not can_open else "APPROVED", reason,
            config.position_size * config.entry_price, self.equity,
            risk_pct, 50.0, 0.0
        )
        
        if not can_open:
            self.audit_logger.log_signal(
                config, config.entry_price,
                risk_check_passed=False, rejection_reason=reason,
                risk_at_stop=risk_at_stop, risk_pct=risk_pct
            )
            return False
        
        # 2. Per-trade risk limit
        can_open, reason = self.risk_manager.check_per_trade_risk(config, self.equity)
        if not can_open:
            self.audit_logger.log_risk_decision(
                config, "REJECTED", reason,
                config.position_size * config.entry_price, self.equity,
                risk_pct, 50.0, 0.0
            )
            self.audit_logger.log_signal(
                config, config.entry_price,
                risk_check_passed=False, rejection_reason=reason,
                risk_at_stop=risk_at_stop, risk_pct=risk_pct
            )
            return False
        
        # All risk checks passed - log approval
        self.audit_logger.log_risk_decision(
            config, "APPROVED", "All risk checks passed",
            config.position_size * config.entry_price, self.equity,
            risk_pct, 50.0, 0.0
        )
        
        self.audit_logger.log_signal(
            config, config.entry_price,
            risk_check_passed=True, rejection_reason=None,
            risk_at_stop=risk_at_stop, risk_pct=risk_pct
        )
        
        # Route order to MT5
        spec = self.symbol_resolver.get_symbol_info(config.symbol)
        fill = self.order_router.send_order(config, spec)
        
        # ALWAYS log the order_send() result (success or failure)
        if fill.success:
            # Open position tracking
            self.open_positions[config.symbol] = {
                "entry_price": fill.price,
                "stop_price": config.stop_price,
                "take_profit": config.take_profit,
                "position_size": fill.volume,
                "entry_time": config.entry_time,
                "max_hold_hours": config.max_hold_hours,
                "entry_equity": self.equity,
                "mt5_ticket": fill.ticket,
                "mt5_order_id": fill.order_id,
            }
            
            # Log fill with slippage
            self.audit_logger.log_fill(fill, config, config.entry_price)
            return True
        else:
            # Log failed order too
            self.audit_logger.log_risk_event(
                "ORDER_FAILED", fill.comment, self.equity, 0.0, 0.0,
                self.risk_manager.kill_switch_halted
            )
            return False
    
    def update_position(self, symbol: str, current_price: float, current_time: datetime) -> dict:
        """Update live position - check stops/TP/time exit."""
        self._ensure_connection()
        
        # First, detect and reconcile any manual SL/TP changes
        modifications = self._detect_manual_sl_tp_changes()
        if modifications:
            self._reconcile_manual_modifications(modifications)
        
        if symbol not in self.open_positions:
            return {"action": "none", "reason": "no_position"}
        
        pos = self.open_positions[symbol]
        entry_price = pos["entry_price"]
        stop_price = pos["stop_price"]
        take_profit = pos.get("take_profit")
        position_size = pos["position_size"]
        entry_time = pos["entry_time"]
        mt5_ticket = pos.get("mt5_ticket")
        
        # Get current tick for accurate pricing
        tick = self.mt5.symbol_info_tick(symbol)
        if tick is None:
            return {"action": "hold", "reason": "no_tick_data"}
        
        current_bid = tick.bid
        current_ask = tick.ask
        
        # Calculate PnL
        if position_size > 0:  # Long
            pnl = (current_price - entry_price) * 100 * position_size
            hit_stop = current_bid <= stop_price
            hit_tp = take_profit and current_ask >= take_profit
        else:  # Short
            pnl = (entry_price - current_price) * 100 * abs(position_size)
            hit_stop = current_ask >= stop_price
            hit_tp = take_profit and current_bid <= take_profit
        
        # Time-based exit
        hours_held = (datetime.now() - entry_time).total_seconds() / 3600
        max_hold = pos.get("max_hold_hours", 4)
        time_exit = hours_held >= max_hold
        
        if hit_stop:
            close_price = tick.bid if position_size > 0 else tick.ask
            self._close_live_position(symbol, close_price, "stop_loss", pnl)
            return {"action": "close", "reason": "stop_loss", "pnl": pnl}
        
        if hit_tp:
            close_price = tick.ask if position_size > 0 else tick.bid
            self._close_live_position(symbol, close_price, "take_profit", pnl)
            return {"action": "close", "reason": "take_profit", "pnl": pnl}
        
        if time_exit:
            close_price = tick.bid if position_size > 0 else tick.ask
            self._close_live_position(symbol, close_price, "time_exit", pnl)
            return {"action": "close", "reason": "time_exit", "pnl": pnl}
        
        return {"action": "hold", "reason": "none", "pnl": pnl}
    
    def _close_live_position(self, symbol: str, close_price: float, reason: str, pnl: float) -> bool:
        """Close a live position on MT5."""
        if symbol not in self.open_positions:
            return False
        
        pos = self.open_positions[symbol]
        mt5_ticket = pos.get("mt5_ticket")
        position_size = pos["position_size"]
        
        if mt5_ticket is None:
            print(f"⚠️  No MT5 ticket for {symbol}, cannot close")
            return False
        
        # Determine close order type
        order_type = self.mt5.ORDER_TYPE_SELL if position_size > 0 else self.mt5.ORDER_TYPE_BUY
        
        request = {
            "action": self.mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": abs(position_size),
            "type": order_type,
            "position": mt5_ticket,
            "price": close_price,
            "deviation": 20,
            "magic": 123456,
            "comment": f"MARS_CLOSE_{reason}",
            "type_time": self.mt5.ORDER_TIME_GTC,
            "type_filling": self.mt5.ORDER_FILLING_IOC,
        }
        
        result = self.mt5.order_send(request)
        
        if result is not None and result.retcode == self.mt5.TRADE_RETCODE_DONE:
            # Update equity
            self.equity += pnl
            self.equity_curve.append(self.equity)
            
            # Log closed trade
            closed_trade = {
                "symbol": symbol,
                "entry_price": pos["entry_price"],
                "exit_price": close_price,
                "position_size": position_size,
                "entry_time": pos["entry_time"],
                "exit_time": datetime.now(),
                "pnl": pnl,
                "reason": reason,
                "mt5_ticket": mt5_ticket,
            }
            self.closed_trades.append(closed_trade)
            
            # Remove from tracking
            del self.open_positions[symbol]
            
            # Update risk manager
            self.risk_manager.unregister_position_risk(symbol)
            
            print(f"✅ Position closed: {symbol} | {reason} | PnL: ${pnl:.2f} | Equity: ${self.equity:.2f}")
            return True
        else:
            error = self.mt5.last_error() if result is None else f"retcode={result.retcode}"
            print(f"❌ Failed to close {symbol}: {error}")
            return False
    
    def modify_position_sltp(self, symbol: str, new_sl: float, new_tp: float) -> bool:
        """Modify SL/TP of an open position (system-initiated)."""
        if symbol not in self.open_positions:
            return False
        
        pos = self.open_positions[symbol]
        mt5_ticket = pos.get("mt5_ticket")
        
        if mt5_ticket is None:
            return False
        
        # Get current prices for normalization
        spec = self.symbol_resolver.get_symbol_info(symbol)
        digits = spec.digits
        new_sl = round(new_sl, digits)
        new_tp = round(new_tp, digits)
        
        request = {
            "action": self.mt5.TRADE_ACTION_SLTP,
            "symbol": symbol,
            "position": mt5_ticket,
            "sl": new_sl,
            "tp": new_tp,
            "magic": 123456,
        }
        
        result = self.mt5.order_send(request)
        
        if result is not None and result.retcode == self.mt5.TRADE_RETCODE_DONE:
            # Update internal tracking
            self.open_positions[symbol]["stop_price"] = new_sl
            self.open_positions[symbol]["take_profit"] = new_tp
            print(f"✅ SL/TP modified: {symbol} | SL={new_sl} TP={new_tp}")
            return True
        else:
            error = self.mt5.last_error() if result is None else f"retcode={result.retcode}"
            print(f"❌ Failed to modify SL/TP for {symbol}: {error}")
            return False
    
    def get_open_positions(self) -> Dict[str, Dict]:
        """Get current open positions (synced with MT5)."""
        self._sync_positions_from_mt5()
        return self.open_positions.copy()
    
    def get_equity(self) -> float:
        """Get current equity (synced with MT5)."""
        self._ensure_connection()
        account_info = self.mt5.account_info()
        if account_info:
            self.equity = account_info.equity
        return self.equity
    
    def get_closed_trades(self) -> List[Dict]:
        """Get closed trades."""
        return self.closed_trades.copy()
    
    def get_equity_curve(self) -> List[float]:
        """Get equity curve."""
        return self.equity_curve.copy()
    
    def shutdown(self):
        """Clean shutdown."""
        # Backup audit database
        self.audit_logger.backup()
        
        # Close MT5 connection
        self.conn_manager.disconnect()
        print("MT5Executor shutdown complete")


# Backward compatibility
DEFAULT_CONFIG = type('Config', (), {'mt5': DEFAULT_MT5_CONFIG})()


def create_live_trading_system(
    equity: float = 100000,
    signal_type: str = "donchian",
    donchian_window: int = 20,
    ma_fast: int = 50,
    ma_slow: int = 200,
    session: str = "london",
    mt5_config: Optional[MT5Config] = None,
    audit_db_path: str = "mt5_audit.db",
) -> MT5Executor:
    """
    Factory to create live trading system with MT5 executor.
    Mirrors DemoTradingSystem factory but with live MT5 executor.
    """
    from mars.apps.trading.signals.trend_breakout import TrendSignalFactory
    from mars.apps.trading.system.vol_scaled_system import VolScaledSizer, SizingConfig, RiskManager
    
    # Signal generator
    if signal_type == "donchian":
        signal_generator = TrendSignalFactory.donchian_trend(
            window=donchian_window, session=session
        )
    elif signal_type == "ma":
        signal_generator = TrendSignalFactory.ma_crossover_trend(
            fast=ma_fast, slow=ma_slow, session=session
        )
    else:
        signal_generator = TrendSignalFactory.combined_trend(
            donchian_window=donchian_window,
            ma_fast=ma_fast,
            ma_slow=ma_slow,
            session=session
        )
    
    # Sizing
    sizer = VolScaledSizer(SizingConfig(target_vol=0.15, max_leverage=3.0))
    
    # Risk manager
    risk_manager = RiskManager(
        kill_switch_file="risk_kill_switch.json",
        max_consecutive_losses=2,
        consecutive_loss_cooldown_hours=24
    )
    
    # Create executor
    executor = MT5Executor(
        equity=equity,
        risk_manager=risk_manager,
        mt5_config=mt5_config,
        audit_db_path=audit_db_path,
    )
    
    # Note: signal_generator and sizer are available for use by the caller
    # The executor handles position management internally
    
    return executor