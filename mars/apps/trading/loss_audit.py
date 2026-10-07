"""Read-only analytical records for clean Donchian system exits.

The audit is deliberately downstream of the execution path: it derives records
only after a broker-confirmed close has already been written to ``fills``.
Nothing in this module can approve, reject, size, or submit an order.
"""
from __future__ import annotations

import sqlite3
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd


SYSTEM_EXIT_TYPES = ("sl_hit", "tp_hit")
ATR_WINDOW = 14


def ensure_loss_audit_schema(conn: sqlite3.Connection) -> None:
    """Create the idempotent, fill-linked system-exit analysis table."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS loss_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fill_id INTEGER NOT NULL UNIQUE,
            source_signal_id INTEGER,
            symbol TEXT NOT NULL,
            direction TEXT NOT NULL,
            entry_time TEXT NOT NULL,
            source_signal_time TEXT,
            entry_delay_ms REAL,
            entry_delay_source TEXT NOT NULL,
            r_realized REAL,
            stop_distance REAL,
            atr_at_entry REAL,
            stop_distance_vs_atr REAL,
            atr_recovery_status TEXT NOT NULL,
            exit_type TEXT NOT NULL CHECK (exit_type IN ('sl_hit', 'tp_hit')),
            exit_time TEXT NOT NULL,
            regime_at_entry TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_loss_audit_exit_time ON loss_audit(exit_time)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_loss_audit_symbol ON loss_audit(symbol)")


def _utc_timestamp(value: Any) -> pd.Timestamp | None:
    timestamp = pd.to_datetime(value, utc=True, errors="coerce")
    return None if pd.isna(timestamp) else timestamp


def _iso_or_none(value: Any) -> str | None:
    timestamp = _utc_timestamp(value)
    return timestamp.isoformat() if timestamp is not None else None


def _net_pnl(fill: sqlite3.Row) -> float:
    """Use the same realized-P&L definition as the dashboard expectancy view."""
    exit_profit = float(fill["exit_profit"] or 0.0)
    exit_commission = float(fill["exit_commission"] or 0.0)
    exit_swap = float(fill["exit_swap"] or 0.0)
    return exit_profit + exit_commission + exit_swap


def _realized_r(fill: sqlite3.Row) -> tuple[float | None, float | None]:
    stop_distance = abs(float(fill["filled_sl"] or 0.0) - float(fill["filled_price"] or 0.0))
    filled_lots = abs(float(fill["filled_lots"] or 0.0))
    denominator = stop_distance * filled_lots * 100.0
    if denominator <= 0:
        return None, stop_distance or None
    return _net_pnl(fill) / denominator, stop_distance


def _source_signal(conn: sqlite3.Connection, fill: sqlite3.Row) -> tuple[int | None, str | None, str]:
    """Find the best existing signal timestamp for entry-delay reconstruction."""
    has_latency = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'pipeline_latency'"
    ).fetchone()
    pipeline_row = None
    if has_latency:
        pipeline_row = conn.execute(
            """
            SELECT pl.signal_id, pl.signal_generated_at, s.timestamp
            FROM pipeline_latency AS pl
            LEFT JOIN signals AS s ON s.id = pl.signal_id
            WHERE pl.fill_id = ?
            """,
            (fill["id"],),
        ).fetchone()
    if pipeline_row:
        signal_time = pipeline_row["signal_generated_at"] or pipeline_row["timestamp"]
        if signal_time:
            return pipeline_row["signal_id"], signal_time, "pipeline_latency"

    direction_signal = 1 if fill["direction"] == "BUY" else -1
    signal_row = conn.execute(
        """
        SELECT id, timestamp
        FROM signals
        WHERE symbol = ?
          AND signal = ?
          AND risk_check_passed = 1
          AND timestamp <= ?
        ORDER BY timestamp DESC, id DESC
        LIMIT 1
        """,
        (fill["symbol"], direction_signal, fill["timestamp"]),
    ).fetchone()
    if signal_row:
        return signal_row["id"], signal_row["timestamp"], "nearest_approved_signal_before_fill"
    return None, None, "unrecoverable_no_matching_signal"


@lru_cache(maxsize=8)
def _load_price_history(symbol: str) -> pd.DataFrame:
    """Read each pair's immutable local M5 archive at most once per process."""
    from mars.apps.trading.system.pair_config import get_data_path

    data_path = Path(get_data_path(symbol))
    if not data_path.exists():
        raise FileNotFoundError(data_path)
    price = pd.read_parquet(data_path)
    if "timestamp" in price.columns:
        price = price.set_index("timestamp")
    if not isinstance(price.index, pd.DatetimeIndex):
        raise ValueError("price timestamp missing")
    price.index = pd.to_datetime(price.index, utc=True, errors="coerce")
    price = price[~price.index.isna()].sort_index()
    return price[["high", "low", "close"]]


def _atr_at_entry(symbol: str, entry_time: str) -> tuple[float | None, str]:
    """Recover a 14-bar M5 ATR from historical data when the entry bar exists."""
    try:
        price = _load_price_history(symbol)
        entry_at = _utc_timestamp(entry_time)
        if entry_at is None:
            return None, "unavailable_entry_time_invalid"
        eligible = price.loc[:entry_at, ["high", "low", "close"]]
        if len(eligible) < ATR_WINDOW:
            return None, "unavailable_insufficient_historical_bars"
        previous_close = eligible["close"].shift(1)
        true_range = pd.concat(
            [
                eligible["high"] - eligible["low"],
                (eligible["high"] - previous_close).abs(),
                (eligible["low"] - previous_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        atr = true_range.rolling(ATR_WINDOW).mean().iloc[-1]
        if pd.isna(atr) or float(atr) <= 0:
            return None, "unavailable_atr_not_computable"
        return float(atr), "m5_atr_14_historical"
    except FileNotFoundError:
        return None, "unavailable_price_data_missing"
    except ValueError as exc:
        if str(exc) == "price timestamp missing":
            return None, "unavailable_price_timestamp_missing"
        return None, "unavailable_atr_recovery_error:ValueError"
    except Exception as exc:
        return None, f"unavailable_atr_recovery_error:{type(exc).__name__}"


def upsert_loss_audit_for_fill(conn: sqlite3.Connection, fill_id: int, now_utc_iso: str) -> bool:
    """Upsert one eligible clean system exit. Return ``True`` when recorded.

    The caller is responsible for committing.  Existing rows are refreshed so
    an exit reason or broker-close correction is reflected in the analysis.
    """
    conn.row_factory = sqlite3.Row
    fill = conn.execute("SELECT * FROM fills WHERE id = ?", (fill_id,)).fetchone()
    if not fill:
        return False

    is_system_exit = fill["exit_reason"] in SYSTEM_EXIT_TYPES
    is_clean = int(fill["degraded_sizing"] or 0) == 0
    is_closed = int(fill["is_closed"] or 0) == 1
    if not (is_closed and is_system_exit and is_clean):
        conn.execute("DELETE FROM loss_audit WHERE fill_id = ?", (fill_id,))
        return False

    signal_id, signal_time, delay_source = _source_signal(conn, fill)
    entry_at = _utc_timestamp(fill["timestamp"])
    signal_at = _utc_timestamp(signal_time)
    entry_delay_ms = (
        (entry_at - signal_at).total_seconds() * 1000.0
        if entry_at is not None and signal_at is not None
        else None
    )
    r_realized, stop_distance = _realized_r(fill)
    atr_at_entry, atr_status = _atr_at_entry(fill["symbol"], fill["timestamp"])
    stop_distance_vs_atr = (
        stop_distance / atr_at_entry
        if stop_distance is not None and atr_at_entry is not None and atr_at_entry > 0
        else None
    )
    exit_time = _iso_or_none(fill["exit_time"])
    if exit_time is None:
        return False

    conn.execute(
        """
        INSERT INTO loss_audit (
            fill_id, source_signal_id, symbol, direction, entry_time,
            source_signal_time, entry_delay_ms, entry_delay_source,
            r_realized, stop_distance, atr_at_entry, stop_distance_vs_atr,
            atr_recovery_status, exit_type, exit_time, regime_at_entry,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
        ON CONFLICT(fill_id) DO UPDATE SET
            source_signal_id = excluded.source_signal_id,
            symbol = excluded.symbol,
            direction = excluded.direction,
            entry_time = excluded.entry_time,
            source_signal_time = excluded.source_signal_time,
            entry_delay_ms = excluded.entry_delay_ms,
            entry_delay_source = excluded.entry_delay_source,
            r_realized = excluded.r_realized,
            stop_distance = excluded.stop_distance,
            atr_at_entry = excluded.atr_at_entry,
            stop_distance_vs_atr = excluded.stop_distance_vs_atr,
            atr_recovery_status = excluded.atr_recovery_status,
            exit_type = excluded.exit_type,
            exit_time = excluded.exit_time,
            regime_at_entry = NULL,
            updated_at = excluded.updated_at
        """,
        (
            fill["id"], signal_id, fill["symbol"], fill["direction"],
            _iso_or_none(fill["timestamp"]), _iso_or_none(signal_time), entry_delay_ms,
            delay_source, r_realized, stop_distance, atr_at_entry, stop_distance_vs_atr,
            atr_status, fill["exit_reason"], exit_time, now_utc_iso, now_utc_iso,
        ),
    )
    return True


def backfill_loss_audit(conn: sqlite3.Connection, now_utc_iso: str) -> int:
    """Populate/refresh every clean historical SL/TP exit and remove exclusions."""
    ensure_loss_audit_schema(conn)
    fill_ids = [
        row[0]
        for row in conn.execute(
            "SELECT id FROM fills WHERE is_closed = 1 AND exit_reason IN ('sl_hit', 'tp_hit')"
        ).fetchall()
    ]
    recorded = 0
    for fill_id in fill_ids:
        recorded += int(upsert_loss_audit_for_fill(conn, int(fill_id), now_utc_iso))
    conn.execute(
        """
        DELETE FROM loss_audit
        WHERE fill_id IN (
            SELECT id FROM fills
            WHERE is_closed != 1
               OR exit_reason NOT IN ('sl_hit', 'tp_hit')
               OR COALESCE(degraded_sizing, 0) != 0
        )
        """
    )
    return recorded
