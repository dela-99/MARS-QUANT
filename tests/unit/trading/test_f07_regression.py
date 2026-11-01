
"""
Regression tests for F-07: signals.entry_price nullable fix.
Tests:
1. Signal creation before entry price is known (NULL entry_price)
2. Signal creation with a valid entry price
3. Existing database migration (NOT NULL -> nullable)
4. Dashboard handles NULL entry_price correctly
"""

from __future__ import annotations

import sqlite3
import tempfile
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from mars.apps.trading.mt5_executor import MT5AuditLogger
from mars.apps.trading.system.vol_scaled_system import TradeConfig
import pandas as pd


def _create_test_db(tmpdir: str) -> Path:
    """Create a test database path."""
    return Path(tmpdir) / "test.db"


def _cleanup_db(db_path: Path):
    """Clean up database file and WAL/SHM files."""
    for suffix in ['', '-wal', '-shm']:
        p = db_path.with_suffix(db_path.suffix + suffix) if suffix else db_path
        if p.exists():
            try:
                p.unlink()
            except PermissionError:
                pass  # Ignore on Windows


def test_signal_creation_with_null_entry_price():
    """Test that a signal can be created with NULL entry_price."""
    tmpdir = tempfile.mkdtemp(prefix="f07_test_")
    try:
        db_path = Path(tmpdir) / "test.db"
        logger = MT5AuditLogger(db_path)

        config = TradeConfig(
            symbol="XAUUSDm",
            signal=1,
            entry_price=2000.0,
            stop_price=1990.0,
            take_profit=2030.0,
            position_size=0.1,
            max_hold_hours=24,
            risk_pct=0.01,
            entry_time=pd.Timestamp.now(tz='UTC'),
        )

        signal_id = logger.log_signal(
            config=config,
            fill_price=None,
            risk_check_passed=True,
            rejection_reason=None,
            risk_at_stop=100.0,
            risk_pct=1.0,
        )

        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM signals WHERE id = ?", (signal_id,)).fetchone()
            assert row is not None, "Signal should be inserted"
            assert row["entry_price"] is None, f"entry_price should be NULL, got {row['entry_price']}"
            assert row["symbol"] == "XAUUSDm"
            assert row["signal"] == 1
            assert row["risk_check_passed"] == 1
    finally:
        _cleanup_db(db_path)
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_signal_creation_with_valid_entry_price():
    """Test that a signal can be created with a valid entry_price."""
    tmpdir = tempfile.mkdtemp(prefix="f07_test_")
    try:
        db_path = Path(tmpdir) / "test.db"
        logger = MT5AuditLogger(db_path)

        config = TradeConfig(
            symbol="XAUUSDm",
            signal=1,
            entry_price=2000.0,
            stop_price=1990.0,
            take_profit=2030.0,
            position_size=0.1,
            max_hold_hours=24,
            risk_pct=0.01,
            entry_time=pd.Timestamp.now(tz='UTC'),
        )

        signal_id = logger.log_signal(
            config=config,
            fill_price=2000.0,
            risk_check_passed=True,
            rejection_reason=None,
            risk_at_stop=100.0,
            risk_pct=1.0,
        )

        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM signals WHERE id = ?", (signal_id,)).fetchone()
            assert row is not None, "Signal should be inserted"
            assert row["entry_price"] == 2000.0, f"entry_price should be 2000.0, got {row['entry_price']}"
            assert row["symbol"] == "XAUUSDm"
            assert row["signal"] == 1
    finally:
        _cleanup_db(db_path)
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_existing_database_migration():
    """Test that existing databases with NOT NULL constraint are migrated."""
    tmpdir = tempfile.mkdtemp(prefix="f07_test_")
    try:
        db_path = Path(tmpdir) / "test.db"

        # Create a database with the OLD schema (NOT NULL constraint)
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE signals (
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
            cursor.execute("""
                INSERT INTO signals (timestamp, symbol, signal, entry_price, stop_price, take_profit,
                                   position_size, risk_at_stop, risk_pct, risk_check_passed)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, ("2026-10-05T12:00:00+00:00", "XAUUSDm", 1, 2000.0, 1990.0, 2030.0, 0.1, 100.0, 1.0, 1))
            conn.commit()

        # Now create MT5AuditLogger which should trigger migration
        logger = MT5AuditLogger(db_path)

        # Verify migration worked
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='signals'").fetchone()
            assert row is not None
            schema = row[0]
            assert "entry_price REAL NOT NULL" not in schema, f"Schema still has NOT NULL: {schema}"
            assert "entry_price REAL" in schema, f"Schema missing entry_price: {schema}"

            row = conn.execute("SELECT * FROM signals WHERE id = 1").fetchone()
            assert row is not None
            assert row["entry_price"] == 2000.0

            # Should be able to insert new row with NULL entry_price
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO signals (timestamp, symbol, signal, stop_price, take_profit,
                                   position_size, risk_at_stop, risk_pct, risk_check_passed)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, ("2026-10-05T13:00:00+00:00", "XAUUSDm", -1, 1990.0, 2030.0, 0.1, 100.0, 1.0, 0))
            conn.commit()

            row = conn.execute("SELECT entry_price FROM signals WHERE id = 2").fetchone()
            assert row["entry_price"] is None, f"New row entry_price should be NULL, got {row['entry_price']}"
    finally:
        _cleanup_db(db_path)
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_dashboard_handles_null_entry_price():
    """Test that dashboard queries handle NULL entry_price correctly."""
    tmpdir = tempfile.mkdtemp(prefix="f07_test_")
    try:
        db_path = Path(tmpdir) / "test.db"
        logger = MT5AuditLogger(db_path)

        config = TradeConfig(
            symbol="XAUUSDm",
            signal=1,
            entry_price=2000.0,
            stop_price=1990.0,
            take_profit=2030.0,
            position_size=0.1,
            max_hold_hours=24,
            risk_pct=0.01,
            entry_time=pd.Timestamp.now(tz='UTC'),
        )

        logger.log_signal(config, 2000.0, True, None, 100.0, 1.0)
        logger.log_signal(config, None, True, None, 100.0, 1.0)

        # Simulate dashboard query
        with sqlite3.connect(db_path) as conn:
            df = pd.read_sql_query("SELECT * FROM signals ORDER BY id", conn)

        assert len(df) == 2
        assert df.iloc[0]["entry_price"] == 2000.0
        assert pd.isna(df.iloc[1]["entry_price"]), f"Second row entry_price should be NaN, got {df.iloc[1]['entry_price']}"
    finally:
        _cleanup_db(db_path)
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    test_signal_creation_with_null_entry_price()
    print("✅ test_signal_creation_with_null_entry_price passed")

    test_signal_creation_with_valid_entry_price()
    print("✅ test_signal_creation_with_valid_entry_price passed")

    test_existing_database_migration()
    print("✅ test_existing_database_migration passed")

    test_dashboard_handles_null_entry_price()
    print("✅ test_dashboard_handles_null_entry_price passed")

    print("\nAll F-07 regression tests passed!")
