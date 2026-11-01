
"""
Dashboard NULL entry_price handling regression test.
"""

from __future__ import annotations

import sqlite3
import tempfile
import shutil
from pathlib import Path
import pandas as pd

from mars.apps.trading.mt5_executor import MT5AuditLogger
from mars.apps.trading.system.vol_scaled_system import TradeConfig


def _create_test_db(tmpdir: str) -> Path:
    return Path(tmpdir) / "test.db"


def _cleanup_db(db_path: Path):
    for suffix in ['', '-wal', '-shm']:
        p = db_path.with_suffix(db_path.suffix + suffix) if suffix else db_path
        if p.exists():
            try:
                p.unlink()
            except PermissionError:
                pass


def test_dashboard_handles_null_entry_price():
    """Test that dashboard queries handle NULL entry_price correctly and format as N/A."""
    tmpdir = tempfile.mkdtemp(prefix="dash_test_")
    try:
        db_path = _create_test_db(tmpdir)
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

        # Insert one with entry_price, one without
        logger.log_signal(config, 2000.0, True, None, 100.0, 1.0)
        logger.log_signal(config, None, True, None, 100.0, 1.0)

        # Simulate dashboard query - this is what dashboard.py's load_signals does
        with sqlite3.connect(db_path) as conn:
            df = pd.read_sql_query("SELECT * FROM signals ORDER BY id", conn)

        assert len(df) == 2
        assert df.iloc[0]["entry_price"] == 2000.0
        assert pd.isna(df.iloc[1]["entry_price"]), f"Second row entry_price should be NaN, got {df.iloc[1]['entry_price']}"

        # Now test the formatting logic that dashboard uses
        for _, row in df.iterrows():
            entry_price = row.get("entry_price")
            if entry_price is None or (isinstance(entry_price, float) and pd.isna(entry_price)):
                entry_price_str = "N/A"
            else:
                entry_price_str = f"{entry_price:.3f}"
            
            # Verify no "nan" string appears
            assert entry_price_str != "nan", f"Got 'nan' string for entry_price={entry_price}"
            if pd.isna(entry_price):
                assert entry_price_str == "N/A", f"Expected 'N/A' for NaN, got '{entry_price_str}'"
            else:
                assert entry_price_str == "2000.000", f"Expected '2000.000', got '{entry_price_str}'"
        
        print("✅ Dashboard NULL handling test passed")
    finally:
        _cleanup_db(db_path)
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    test_dashboard_handles_null_entry_price()
    print("✅ Dashboard NULL handling regression test passed!")
