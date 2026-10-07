"""Audit-only coverage for clean SL/TP loss-audit records."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from mars.apps.trading import loss_audit
from mars.apps.trading.mt5_executor import MT5AuditLogger


def test_broker_close_creates_clean_system_exit_audit_row(tmp_path, monkeypatch):
    """A broker-confirmed SL close is recorded; degraded fills remain excluded."""
    monkeypatch.setattr(
        loss_audit,
        "_atr_at_entry",
        lambda symbol, entry_time: (0.5, "test_atr_recovery"),
    )
    exit_epoch = int(datetime(2026, 10, 5, 12, 10, tzinfo=timezone.utc).timestamp())
    exit_deal = SimpleNamespace(
        entry=1,
        time=exit_epoch,
        price=149.0,
        commission=0.0,
        swap=0.0,
        profit=-66.66666666666667,
        reason=4,
        ticket=9002,
    )
    mt5 = SimpleNamespace(history_deals_get=lambda **kwargs: [exit_deal])
    logger = MT5AuditLogger(tmp_path / "audit.db", mt5_module=mt5)

    import sqlite3

    with sqlite3.connect(logger.db_path) as conn:
        conn.execute(
            """
            INSERT INTO signals (timestamp, symbol, signal, risk_check_passed)
            VALUES (?, ?, ?, ?)
            """,
            ("2026-10-05T12:00:00+00:00", "USDJPYm", 1, 1),
        )
        cursor = conn.execute(
            """
            INSERT INTO fills (
                timestamp, ticket, symbol, direction, filled_lots, filled_price,
                filled_sl, filled_tp, position_id, is_closed, degraded_sizing
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("2026-10-05T12:00:02+00:00", 9001, "USDJPYm", "BUY", 0.1, 150.0,
             149.0, 153.0, 9001, 0, 0),
        )
        clean_fill_id = cursor.lastrowid
        conn.execute(
            """
            INSERT INTO fills (
                timestamp, ticket, symbol, direction, filled_lots, filled_price,
                filled_sl, filled_tp, exit_time, exit_reason, is_closed, degraded_sizing
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("2026-10-05T12:01:00+00:00", 9003, "USDJPYm", "BUY", 0.1, 150.0,
             149.0, 153.0, "2026-10-05T12:11:00+00:00", "tp_hit", 1, 1),
        )

    assert logger.log_close_fill(clean_fill_id) is True

    with sqlite3.connect(logger.db_path) as conn:
        row = conn.execute(
            """
            SELECT fill_id, source_signal_id, entry_delay_ms, r_realized,
                   stop_distance, atr_at_entry, stop_distance_vs_atr,
                   exit_type, regime_at_entry
            FROM loss_audit
            """
        ).fetchone()

    assert row == (clean_fill_id, 1, 2000.0, -1.0, 1.0, 0.5, 2.0, "sl_hit", None)
