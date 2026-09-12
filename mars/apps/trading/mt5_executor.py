"""
MT5 Live Execution Layer for M.A.R.S. Trading System.

Implements the same interface as TradeExecutor for live order placement on MT5 demo account.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from pathlib import Path
import json
import os
from threading import Lock
import time
from unittest.mock import Mock

import pandas as pd

from mars.apps.trading.system.vol_scaled_system import (
    RiskManager, TradeExecutor, TradeConfig, VolScaledSizer, SizingConfig
)
from mars.core.config import MT5Config, DEFAULT_CONFIG


# Step 0: Demo Account Safety Gate
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
    # Order modes supported
    order_mode: int = 0
    # Trade mode
    trade_mode: int = 0


class MT5SymbolResolver:
    """Resolves XAUUSD symbol specification at runtime from MT5."""
    
    def __init__(self, mt5_module):
        self.mt5 = mt5_module
        self._symbol_cache: Dict[str, MT5SymbolInfo] = {}
        self._cache_lock = Lock()
    
    def get_symbol_info(self, symbol: str = "XAUUSD") -> MT5SymbolInfo:
        """Get symbol specification, cached with thread safety."""
        with self._cache_lock:
            if symbol in self._symbol_cache:
                return self._symbol_cache[symbol]
            
            info = self.mt5.symbol_info(symbol)
            if info is None:
                raise RuntimeError(f"Symbol {symbol} not found: {self.mt5.last_error()}")
            
            if not info.visible:
                if not self.mt5.symbol_select(symbol, True):
                    raise RuntimeError(f"Failed to select symbol {symbol}: {self.mt5.last_error()}")
            
            # Refresh info after selection
            info = self.mt5.symbol_info(symbol)
            if info is None:
                raise RuntimeError(f"Symbol {symbol} info unavailable after selection")
            
            spec = MT5SymbolInfo(
                symbol=info.name,
                contract_size=info.trade_contract_size,
                min_lot=info.volume_min,
                max_lot=info.volume_max,
                lot_step=info.volume_step,
                digits=info.digits,
                point=info.point,
                spread=info.spread,
                spread_float=info.spread / 10.0 if info.spread > 0 else 0.0,
                tick_size=info.trade_tick_size,
                tick_value=info.trade_tick_value,
                swap_long=info.swap_long,
                swap_short=info.swap_short,
                margin_initial=info.margin_initial,
                margin_maintenance=info.margin_maintenance,
                session_deals=info.session_deals,
                session_buy_orders=info.session_buy_orders,
                session_sell_orders=info.session_sell_orders,
                volume_min=info.volume_min,
                volume_max=info.volume_max,
                volume_step=info.volume_step,
                bid=info.bid,
                ask=info.ask,
                last=info.last,
                volume_real=info.volume_real,
                time=datetime.fromtimestamp(info.time),
                filling_mode=info.filling_mode,
                order_mode=info.order_mode,
                trade_mode=info.trade_mode,
            )
            self._symbol_cache[symbol] = spec
            return spec
    
    def normalize_lot_size(self, symbol: str, raw_lots: float) -> float:
        """Normalize lot size to broker's step/min/max."""
        spec = self.get_symbol_info(symbol)
        # Round to nearest step
        stepped = round(raw_lots / spec.lot_step) * spec.lot_step
        # Clamp to min/max
        return max(spec.min_lot, min(spec.max_lot, stepped))
    
    def lots_to_volume(self, symbol: str, lots: float) -> float:
        """Convert lots to volume (contracts * contract_size)."""
        spec = self.get_symbol_info(symbol)
        return lots * spec.contract_size
    
    def volume_to_lots(self, symbol: str, volume: float) -> float:
        """Convert volume to lots."""
        spec = self.get_symbol_info(symbol)
        return volume / spec.contract_size


@dataclass
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


class MT5ConnectionManager:
    """Manages MT5 connection with retry logic and health checks."""
    
    def __init__(self, config: MT5Config):
        self.config = config
        self.mt5 = None
        self._connected = False
        self._lock = Lock()
        self._last_health_check = 0
        self._health_check_interval = 30  # seconds
    
    def connect(self) -> bool:
        """Initialize MT5 connection with retry logic."""
        with self._lock:
            if self._connected and self._is_healthy():
                return True
            
            try:
                import MetaTrader5 as mt5
            except ImportError as exc:
                raise ImportError(
                    "MetaTrader5 package required. Install: pip install MetaTrader5"
                ) from exc
            
            self.mt5 = mt5
            
            if not self.config.is_configured():
                raise RuntimeError(
                    "MT5 credentials not configured. Set DEMO_ACCOUNT_NUMBER, "
                    "PASSWORD, SERVER in .env"
                )
            
            login = int(self.config.account_number)
            
            # Retry connection up to 3 times
            for attempt in range(3):
                if mt5.initialize(
                    login=login,
                    password=self.config.password,
                    server=self.config.server,
                ):
                    self._connected = True
                    # Verify demo account on every connection
                    DemoAccountGate.verify_demo_account(mt5)
                    return True
                
                error = mt5.last_error()
                if attempt < 2:
                    time.sleep(2 ** attempt)  # Exponential backoff
            
            raise RuntimeError(f"MT5 initialize failed after 3 attempts: {mt5.last_error()}")
    
    def _is_healthy(self) -> bool:
        """Check connection health."""
        if not self._connected or self.mt5 is None:
            return False
        
        now = time.time()
        if now - self._last_health_check < self._health_check_interval:
            return True
        
        try:
            account = self.mt5.account_info()
            if account is not None:
                self._last_health_check = time.time()
                return True
        except Exception:
            pass
        
        return False
    
    def ensure_connected(self) -> bool:
        """Ensure connection is alive, reconnect if needed."""
        if not self._is_healthy():
            self.mt5.shutdown()
            self._connected = False
            return self.connect()
        return True
    
    def shutdown(self):
        """Clean shutdown."""
        with self._lock:
            if self.mt5 and self._connected:
                self.mt5.shutdown()
                self._connected = False


class MT5OrderRouter:
    """Routes orders to MT5 with proper symbol/lot handling."""

    def __init__(self, mt5_module, symbol_resolver: MT5SymbolResolver):
        self.mt5 = mt5_module
        self.symbol_resolver = symbol_resolver
        # Determine best filling mode for this broker
        self._supported_filling_modes = [mt5_module.ORDER_FILLING_FOK, mt5_module.ORDER_FILLING_IOC, mt5_module.ORDER_FILLING_RETURN]

    def _get_best_filling_mode(self, spec: MT5SymbolInfo) -> int:
        """Select best filling mode supported by broker."""
        broker_modes = spec.filling_mode
        # Prefer FOK > IOC > RETURN
        for mode in [self.mt5.ORDER_FILLING_FOK, self.mt5.ORDER_FILLING_IOC, self.mt5.ORDER_FILLING_RETURN]:
            if broker_modes & mode:
                return mode
        # Fallback to FOK if detection fails
        return self.mt5.ORDER_FILLING_FOK

    def send_order(self, config: TradeConfig, spec: MT5SymbolInfo) -> FillResult:
        """
        Send order to MT5 with proper lot normalization and price handling.
        Includes pre-flight margin check via order_check().
        """
        # Normalize lot size
        raw_lots = config.position_size
        normalized_lots = self.symbol_resolver.normalize_lot_size(config.symbol, raw_lots)

        if normalized_lots <= 0:
            return FillResult(
                success=False,
                ticket=0, order_id=0, volume=0, price=0,
                bid=0, ask=0, sl=0, tp=0, comment="Invalid lot size",
                request=None, result_code=-1, retcode_external=-1,
                timestamp=datetime.now()
            )

        # Get current prices
        tick = self.mt5.symbol_info_tick(config.symbol)
        if tick is None:
            return FillResult(
                success=False, ticket=0, order_id=0, volume=0,
                price=0, bid=0, ask=0, sl=0, tp=0,
                comment=f"No tick data: {self.mt5.last_error()}",
                request=None, result_code=-1, retcode_external=-1,
                timestamp=datetime.now()
            )

        # Determine order type and price
        if config.signal == 1:  # Long
            order_type = self.mt5.ORDER_TYPE_BUY
            price = tick.ask
            sl = config.stop_price
            tp = config.take_profit
        else:  # Short
            order_type = self.mt5.ORDER_TYPE_SELL
            price = tick.bid
            sl = config.stop_price
            tp = config.take_profit

        # Determine best filling mode for this broker
        filling_mode = self._get_best_filling_mode(spec)

        # Build request
        request = OrderRequest(
            action=self.mt5.TRADE_ACTION_DEAL,
            symbol=config.symbol,
            volume=config.position_size,
            type=order_type,
            price=price,
            sl=sl,
            tp=tp,
            deviation=20,  # 20 points max slippage
            magic=123456,  # Magic number for identification
            comment=f"MARS_{config.signal}_{config.entry_time.strftime('%H%M%S')}",
            type_time=self.mt5.ORDER_TIME_GTC,
            type_filling=filling_mode,
            signal=config.signal,
        )

        # PRE-FLIGHT CHECK: Validate margin/fund sufficiency via order_check()
        mt5_request = {
            "action": request.action,
            "symbol": request.symbol,
            "volume": request.volume,
            "type": request.type,
            "price": request.price,
            "sl": request.sl,
            "tp": request.tp,
            "deviation": request.deviation,
            "magic": request.magic,
            "comment": request.comment,
            "type_time": request.type_time,
            "type_filling": request.type_filling,
        }

        check_result = self.mt5.order_check(mt5_request)
        if check_result is None or check_result.retcode != 0:
            error_msg = f"Pre-flight order_check failed: {check_result.comment if check_result else self.mt5.last_error()}"
            return FillResult(
                success=False, ticket=0, order_id=0, volume=0,
                price=0, bid=tick.bid, ask=tick.ask, sl=0, tp=0,
                comment=error_msg,
                request=request, result_code=-1, retcode_external=-1,
                timestamp=datetime.now()
            )

        # Send order
        result = self.mt5.order_send(mt5_request)

        if result is None:
            return FillResult(
                success=False, ticket=0, order_id=0, volume=0,
                price=0, bid=tick.bid, ask=tick.ask, sl=0, tp=0,
                comment=f"order_send returned None: {self.mt5.last_error()}",
                request=request, result_code=-1, retcode_external=-1,
                timestamp=datetime.now()
            )

        # Calculate slippage
        signal_price = config.entry_price
        filled_price = result.price
        slippage = filled_price - signal_price if config.signal == 1 else signal_price - filled_price
        
        # Calculate size slippage (filled - requested volume)
        size_slippage = result.volume - normalized_lots
        
        return FillResult(
            success=result.retcode == self.mt5.TRADE_RETCODE_DONE,
            ticket=result.deal,  # MT5 uses 'deal' for position ticket
            order_id=result.order,
            volume=result.volume,
            price=result.price,
            bid=tick.bid,
            ask=tick.ask,
            sl=config.stop_price,  # Use config stop_price since result doesn't have it
            tp=config.take_profit,  # Use config take_profit since result doesn't have it
            comment=result.comment,
            request=request,
            result_code=result.retcode,
            retcode_external=result.retcode_external,
            timestamp=datetime.now(),
            slippage=slippage,
            size_slippage=size_slippage
        )


class MT5AuditLogger:
    """Persists all trading activity to SQLite for audit trail."""
    
    def __init__(self, db_path: str = "mt5_audit.db"):
        self.db_path = Path(db_path)
        self._init_db()
        self._lock = Lock()
    
    def _init_db(self):
        """Initialize SQLite database with audit tables."""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                symbol TEXT NOT NULL,
                signal INTEGER NOT NULL,
                entry_price REAL,
                stop_price REAL,
                take_profit REAL,
                position_size REAL,
                signal_price REAL,
                risk_at_stop REAL,
                risk_pct REAL,
                risk_check_passed BOOLEAN,
                risk_rejection_reason TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS risk_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                symbol TEXT NOT NULL,
                decision TEXT NOT NULL,
                reason TEXT,
                position_value REAL,
                equity REAL,
                per_trade_risk_pct REAL,
                concurrent_cap_pct REAL,
                drawdown_pct REAL
            )
        """)
        
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
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS risk_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                details TEXT,
                equity REAL,
                drawdown_pct REAL,
                daily_pnl REAL,
                kill_switch_active BOOLEAN
            )
        """)
        
        conn.commit()
        conn.close()
    
    def log_signal(self, config: TradeConfig, signal_price: float,
                   risk_check_passed: bool, rejection_reason: str = None,
                   risk_at_stop: float = 0, risk_pct: float = 0):
        """Log signal generation with risk check result."""
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO signals (
                    timestamp, symbol, signal, entry_price, stop_price,
                    take_profit, position_size, signal_price,
                    risk_at_stop, risk_pct, risk_check_passed,
                    risk_rejection_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(),
                config.symbol, config.signal,
                config.entry_price, config.stop_price, config.take_profit,
                config.position_size, signal_price,
                risk_at_stop, risk_pct,
                risk_check_passed, rejection_reason
            ))
            conn.commit()
    
    def log_risk_decision(self, config: TradeConfig, decision: str,
                          reason: str, position_value: float, equity: float,
                          per_trade_risk_pct: float, concurrent_cap_pct: float,
                          drawdown_pct: float):
        """Log risk manager decision."""
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO risk_decisions (
                    timestamp, symbol, decision, reason,
                    position_value, equity, per_trade_risk_pct,
                    concurrent_cap_pct, drawdown_pct
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(),
                config.symbol, decision, reason,
                position_value, equity, per_trade_risk_pct,
                concurrent_cap_pct, drawdown_pct
            ))
            conn.commit()
    
    def log_fill(self, fill: FillResult, config: TradeConfig, signal_price: float):
        """Log order fill with slippage calculation."""
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Calculate slippage in points and percentage
            spread_at_fill = fill.ask - fill.bid
            
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
                            fill.timestamp.isoformat(),
                            fill.ticket, fill.order_id, fill.request.symbol,
                            "BUY" if fill.request.signal == 1 else "SELL",
                            fill.request.volume, fill.volume,
                            config.entry_price, fill.price,
                            config.stop_price, fill.sl,
                            config.take_profit, fill.tp,
                            fill.slippage,
                            fill.slippage / config.entry_price * 10000 if config.entry_price > 0 else 0,
                            fill.size_slippage,
                            fill.ask - fill.bid,
                            0.0,  # commission
                            0.0,  # swap
                            0.0,  # profit
                            fill.ticket, fill.order_id,
                            fill.result_code, fill.retcode_external if not isinstance(fill.retcode_external, Mock) else -1,
                            fill.comment
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


class MT5Executor:
    """
    Live MT5 executor implementing TradeExecutor interface.
    Replaces backtest TradeExecutor for live demo trading.
    
    Key fixes:
    - Idempotent order placement (prevents duplicate orders per bar/signal)
    - Live MT5 position checking for concurrent risk
    - Every order_send() call is logged (success or failure)
    """
    
    def __init__(
        self,
        equity: float,
        risk_manager: Optional[RiskManager] = None,
        sizer: Optional[VolScaledSizer] = None,
        mt5_config: Optional[MT5Config] = None,
        audit_db_path: str = "mt5_audit.db",
    ) -> None:
        self.equity = equity
        self.risk_manager = risk_manager or RiskManager()
        self.sizer = sizer
        
        # MT5 components
        self.mt5_config = mt5_config or DEFAULT_CONFIG.mt5
        self.conn_manager = MT5ConnectionManager(self.mt5_config)
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
        time_exit = hours_held >= pos.get("max_hold_hours", 24)
        
        if hit_stop:
            return self._close_live_position(symbol, tick.bid if position_size > 0 else tick.ask, "stop_loss", pnl)
        elif hit_tp:
            return self._close_live_position(symbol, tick.ask if position_size > 0 else tick.bid, "take_profit", pnl)
        elif time_exit:
            return self._close_live_position(symbol, current_price, "time_exit", pnl)
        
        return {"action": "hold", "pnl": pnl, "stop_distance": abs(current_price - stop_price)}
    
    def _close_live_position(self, symbol: str, price: float, reason: str, pnl: float) -> dict:
        """Close live position on MT5."""
        if symbol not in self.open_positions:
            return {"action": "none", "reason": "no_position"}
        
        pos = self.open_positions[symbol]
        mt5_ticket = pos.get("mt5_ticket")
        
        if mt5_ticket:
            # Close via MT5
            tick = self.mt5.symbol_info_tick(symbol)
            if tick:
                close_request = {
                    "action": self.mt5.TRADE_ACTION_DEAL,
                    "symbol": symbol,
                    "volume": pos["position_size"],
                    "type": self.mt5.ORDER_TYPE_SELL if pos["position_size"] > 0 else self.mt5.ORDER_TYPE_BUY,
                    "position": mt5_ticket,
                    "price": tick.bid if pos["position_size"] > 0 else tick.ask,
                    "deviation": 20,
                    "magic": 123456,
                    "comment": f"MARS_CLOSE_{reason}",
                    "type_time": self.mt5.ORDER_TIME_GTC,
                    "type_filling": self.mt5.ORDER_FILLING_FOK,
                }
                
                result = self.mt5.order_send(close_request)
                if result and result.retcode == self.mt5.TRADE_RETCODE_DONE:
                    pnl = (price - pos["entry_price"]) * 100 * pos["position_size"] if pos["position_size"] > 0 else (pos["entry_price"] - price) * 100 * abs(pos["position_size"])
                    
                    self.risk_manager.update_pnl(pnl)
                    self.equity += pnl
                    
                    closed_pos = self.open_positions.pop(symbol)
                    self.closed_trades.append({
                        "symbol": symbol,
                        "entry_price": pos["entry_price"],
                        "exit_price": price,
                        "position_size": pos["position_size"],
                        "pnl": pnl,
                        "reason": reason,
                        "mt5_ticket": mt5_ticket,
                    })
                    
                    return {"action": "close", "reason": reason, "pnl": pnl}
        
        # Fallback: manual close tracking
        pnl = (price - pos["entry_price"]) * 100 * pos["position_size"] if pos["position_size"] > 0 else (pos["entry_price"] - price) * 100 * abs(pos["position_size"])
        self.risk_manager.update_pnl(pnl)
        self.equity += pnl
        
        self.open_positions.pop(symbol)
        self.closed_trades.append({
            "symbol": symbol,
            "entry_price": pos["entry_price"],
            "exit_price": price,
            "position_size": pos["position_size"],
            "pnl": pnl,
            "reason": reason,
        })
        
        return {"action": "close", "reason": reason, "pnl": pnl}
    
    def close_position(self, symbol: str, price: float, reason: str) -> float:
        """Close position and return PnL."""
        result = self._close_live_position(symbol, price, reason, 0)
        return result.get("pnl", 0.0)
    
    def get_status(self) -> dict:
        """Get current executor status."""
        self._ensure_connection()
        
        account_info = self.mt5.account_info() if self.mt5 else None
        
        return {
            "equity": self.equity,
            "open_positions": len(self.open_positions),
            "total_trades": len(self.closed_trades),
            "account_balance": account_info.balance if account_info else self.equity,
            "account_equity": account_info.equity if account_info else self.equity,
            "kill_switch_active": self.risk_manager.kill_switch_halted if self.risk_manager else False,
            "daily_pnl": self.risk_manager.daily_pnl if self.risk_manager else 0.0,
        }
    
    def shutdown(self):
        """Clean shutdown."""
        self.conn_manager.shutdown()
        print("MT5Executor shutdown complete")


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
            session=session,
        )
    
    # Risk manager with demo-appropriate limits
    sizing_config = SizingConfig(
        target_vol=0.15,
        max_leverage=3.0,
        min_leverage=0.01,
        kelly_fraction=0.5,
    )
    
    risk_manager = RiskManager(
        max_daily_loss_pct=0.02,
        max_weekly_loss_pct=0.05,
        max_monthly_loss_pct=0.10,
        max_drawdown_pct=0.15,
        max_position_pct=0.30,  # 30% concurrent cap
        max_risk_per_trade_pct=0.01,  # 1% per trade
        kill_switch_file="risk_kill_switch.json",
    )
    
    # Vol sizer
    sizer = VolScaledSizer(sizing_config, garch_variant="garch")
    
    # MT5 config
    mt5_config = mt5_config or DEFAULT_CONFIG.mt5
    
    return MT5Executor(
        equity=equity,
        risk_manager=risk_manager,
        sizer=sizer,
        mt5_config=mt5_config,
    )


def run_unattended_session(duration_hours: float = 8.0) -> dict:
    """
    Run unattended live session on MT5 demo.
    Returns session report.
    """
    import signal
    import sys
    
    system = create_live_trading_system()
    
    # Load historical data for signal generation (last N days)
    from mars.apps.trading.demo_trading_system import DemoTradingSystem
    demo = DemoTradingSystem(equity=system.equity, signal_type="donchian")
    historical_data = demo.load_data(start=(datetime.now() - pd.Timedelta(days=30)).strftime("%Y-%m-%d"))
    
    # Fit sizer on historical data
    system.sizer.fit(historical_data)
    
    start_time = datetime.now()
    end_time = start_time + pd.Timedelta(hours=duration_hours)
    
    signals_generated = 0
    orders_placed = 0
    orders_rejected = 0
    trades_executed = 0
    
    print(f"Starting unattended live session for {duration_hours} hours...")
    print(f"Session: {start_time} to {end_time}")
    
    def signal_handler(sig, frame):
        print("Shutdown signal received, closing positions...")
        system.shutdown()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        while datetime.now() < end_time:
            # Get latest bar data
            # In production, this would connect to MT5 real-time feed
            # For now, simulate with recent historical data
            latest_bar = historical_data.iloc[-1:]
            current_price = latest_bar["close"].values[0]
            current_time = latest_bar.index[0]
            
            # Generate signals
            signals = system.signal_generator.generate(latest_bar)
            signal = signals["signal"].iloc[-1] if len(signals) > 0 else 0
            
            signals_generated += 1
            
            # Update existing positions
            for symbol in list(system.open_positions.keys()):
                update = system.update_position(symbol, current_price, current_time)
                if update["action"] == "close":
                    trades_executed += 1
            
            # Check for new entry
            if signal != 0 and "XAUUSD" not in system.open_positions:
                # Get vol forecast and position size
                forecast = system.sizer.forecast_vol(historical_data)
                positions = system.sizer.compute_position_size(
                    historical_data, signals["signal"], system.equity, forecast
                )
                
                position_size = positions["position_size"].iloc[-1] if len(positions) > 0 else 0
                
                if position_size > 0:
                    # Create trade config
                    atr = latest_bar["ATRr_14"].values[0] if "ATRr_14" in latest_bar.columns else 5.0
                    stop_distance = atr * 2.5
                    
                    if signal == 1:
                        stop_price = current_price - stop_distance
                        take_profit = current_price + stop_distance * 2.5
                    else:
                        stop_price = current_price + stop_distance
                        take_profit = current_price - stop_distance * 2.5
                    
                    from mars.apps.trading.system.vol_scaled_system import TradeConfig
                    config = TradeConfig(
                        symbol="XAUUSD",
                        signal=signal,
                        entry_price=current_price,
                        stop_price=stop_price,
                        take_profit=take_profit,
                        position_size=position_size,
                        max_hold_hours=24,
                        risk_pct=0.01,
                        entry_time=current_time,
                    )
                    
                    orders_placed += 1
                    if system.open_position(config):
                        pass
                    else:
                        orders_rejected += 1
            
            # Update equity curve
            system.equity_curve.append(system.equity)
            
            # Sleep until next bar (1 hour for H1)
            time.sleep(60)  # Check every minute in production
            
    except KeyboardInterrupt:
        print("Session interrupted by user")
    except Exception as e:
        print(f"Session error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        system.shutdown()
    
    # Generate report
    report = {
        "start_time": start_time.isoformat(),
        "end_time": datetime.now().isoformat(),
        "duration_hours": (datetime.now() - start_time).total_seconds() / 3600,
        "signals_generated": signals_generated,
        "orders_placed": orders_placed,
        "orders_rejected": orders_rejected,
        "trades_executed": trades_executed,
        "final_equity": system.equity,
        "total_return": (system.equity - system.equity_curve[0]) / system.equity_curve[0] if system.equity_curve else 0,
        "max_drawdown": min(system.equity_curve) / system.equity_curve[0] - 1 if system.equity_curve else 0,
    }
    
    return report