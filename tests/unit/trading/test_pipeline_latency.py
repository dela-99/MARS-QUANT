"""Audit-only latency coverage for the signal → risk → execution pipeline."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pandas as pd

from mars.apps.trading.latency import derive_latency_metrics
from mars.apps.trading.mt5_executor import MT5Config, MT5Executor
from mars.apps.trading.system.vol_scaled_system import RiskManager, TradeConfig
from run_session_v3 import MockMT5ConnectionManager


def test_mocked_pipeline_persists_all_raw_latency_timestamps(tmp_path):
    """A broker-confirmed mock fill has all five UTC events and valid metrics."""
    equity = 500.0
    risk_manager = RiskManager(kill_switch_file=str(tmp_path / "risk_kill_switch.json"))
    risk_manager.reset_daily(equity)
    risk_manager.select_tier_for_equity(equity)
    risk_manager.current_equity = equity
    risk_manager.peak_equity = equity

    mt5_config = MT5Config(login=1, password="test", server="test")
    connection = MockMT5ConnectionManager(mt5_config)
    connection.connect()
    executor = MT5Executor(
        equity=equity,
        risk_manager=risk_manager,
        mt5_config=mt5_config,
        audit_db_path=str(tmp_path / "audit.db"),
        conn_manager=connection,
        auto_initialize=False,
    )
    executor.mt5 = connection.mt5
    from mars.apps.trading.mt5_executor import MT5OrderRouter, MT5SymbolResolver

    executor.symbol_resolver = MT5SymbolResolver(executor.mt5)
    executor.order_router = MT5OrderRouter(executor.mt5, executor.symbol_resolver)

    now = datetime.now(timezone.utc)
    config = TradeConfig(
        symbol="XAUUSDm",
        signal=1,
        entry_price=2000.30,
        stop_price=1999.30,
        take_profit=2003.30,
        position_size=0.01,
        entry_time=pd.Timestamp(now),
        movement_detected_at=(now - timedelta(minutes=5)).isoformat(),
        signal_generated_at=(now - timedelta(milliseconds=50)).isoformat(),
    )

    assert executor.open_position(config) is True

    with sqlite3.connect(tmp_path / "audit.db") as conn:
        conn.row_factory = sqlite3.Row
        trace = conn.execute("SELECT * FROM pipeline_latency").fetchone()

    assert trace is not None
    raw = dict(trace)
    for field in (
        "movement_detected_at",
        "signal_generated_at",
        "risk_approved_at",
        "order_submitted_at",
        "order_filled_at",
    ):
        assert raw[field] is not None
        assert pd.to_datetime(raw[field], utc=True).tzinfo is not None

    metrics = derive_latency_metrics(raw)
    # Independent hand check from the raw values: no derived value is stored.
    movement = pd.to_datetime(raw["movement_detected_at"], utc=True)
    signal = pd.to_datetime(raw["signal_generated_at"], utc=True)
    risk = pd.to_datetime(raw["risk_approved_at"], utc=True)
    submitted = pd.to_datetime(raw["order_submitted_at"], utc=True)
    filled = pd.to_datetime(raw["order_filled_at"], utc=True)
    assert metrics["detection_latency_ms"] == (signal - movement).total_seconds() * 1000
    assert metrics["signal_latency_ms"] == (risk - signal).total_seconds() * 1000
    assert metrics["execution_latency_ms"] == (filled - submitted).total_seconds() * 1000
    assert metrics["total_latency_ms"] == (filled - movement).total_seconds() * 1000
    assert trace["signal_id"] is not None
    assert trace["fill_id"] is not None
