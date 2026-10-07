#!/usr/bin/env python3
"""
M.A.R.S. Trading System — Monitoring Dashboard (rebuilt for 6-week baseline test).

Run: streamlit run dashboard.py

Design principles (Nov 3 checkpoint):
- Every data-loading function opens its OWN fresh sqlite3 connection with
  check_same_thread=False, runs the query, closes the connection. No
  shared/cached connection objects across Streamlit reruns (the previous
  dashboard crashed with "Cannot operate on a closed database" because
  get_db_connection() was @st.cache_resource and load_table() closed
  the shared connection in its finally block, leaving subsequent reruns
  holding a closed handle).
- Equity / Daily P&L / Expectancy / Heartbeat show REAL computed values
  against the audit DB. When a metric cannot be honestly computed (e.g.,
  Expectancy with zero closed trades), the panel shows an explicit
  "pending fix" message — never a fake zero.
- Signal/Trade Log is a single live-updating table combining signals,
  evaluations, risk_decisions, and fills, sorted by timestamp desc.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from mars.apps.trading.latency import derive_latency_metrics, format_latency_ms
from mars.apps.trading.risk_metrics import realized_r

# ---------------------------------------------------------------
# Page config + custom CSS
# ---------------------------------------------------------------
st.set_page_config(
    page_title="M.A.R.S. Trading Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
    /* All card backgrounds are light fills — text MUST be explicitly dark to
       remain readable under Streamlit's default dark theme. Without this,
       Streamlit's inherited text color (light) makes the card contents
       invisible against the light card background. */
    .metric-card,
    .metric-card.bullish,
    .metric-card.bearish,
    .metric-card.neutral,
    .metric-card.tradeable,
    .metric-card.not-tradeable,
    .metric-card.allowed,
    .metric-card.rejected {
        color: #111827 !important;  /* high-contrast dark primary text */
    }
    .metric-card h1, .metric-card h2, .metric-card h3, .metric-card h4,
    .metric-card h5, .metric-card h6,
    .metric-card p, .metric-card span, .metric-card div,
    .metric-card b, .metric-card strong, .metric-card small {
        color: inherit !important;
    }
    .metric-card b, .metric-card strong {
        color: #000000 !important;  /* bold text black for max contrast */
    }
    .metric-card small {
        color: #374151 !important;  /* secondary label grey */
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #1f77b4;
        margin-bottom: 0.5rem;
    }
    .metric-card.bullish { border-left-color: #2e7d32; background-color: #e8f5e9; color: #1b5e20 !important; }
    .metric-card.bearish { border-left-color: #c62828; background-color: #ffebee; color: #b71c1c !important; }
    .metric-card.neutral { border-left-color: #757575; background-color: #f5f5f5; color: #424242 !important; }
    .metric-card.tradeable { border-left-color: #2e7d32; background-color: #e8f5e9; color: #1b5e20 !important; }
    .metric-card.not-tradeable { border-left-color: #c62828; background-color: #ffebee; color: #b71c1c !important; }
    .metric-card.allowed { border-left-color: #2e7d32; background-color: #e8f5e9; color: #1b5e20 !important; }
    .metric-card.rejected { border-left-color: #c62828; background-color: #ffebee; color: #b71c1c !important; }
    .risk-event-critical { background-color: #ffebee; border-left-color: #f44336; color: #b71c1c !important; }
    .risk-event-warning { background-color: #fff3e0; border-left-color: #ff9800; color: #5d4037 !important; }
    .risk-event-info { background-color: #e3f2fd; border-left-color: #2196f3; color: #0d47a1 !important; }
    .risk-event-critical *, .risk-event-warning *, .risk-event-info * {
        color: inherit !important;
    }
    .enabled-badge { background-color: #c8e6c9; color: #1b5e20 !important; padding: 0.25rem 0.5rem; border-radius: 0.25rem; font-weight: 700; }
    .disabled-badge { background-color: #ffcdd2; color: #b71c1c !important; padding: 0.25rem 0.5rem; border-radius: 0.25rem; font-weight: 700; }
    .heartbeat-fresh { background-color: #e8f5e9; padding: 0.75rem; border-radius: 0.5rem; border-left: 6px solid #2e7d32; }
    .heartbeat-warn { background-color: #fff3e0; padding: 0.75rem; border-radius: 0.5rem; border-left: 6px solid #ff9800; }
    .heartbeat-stale { background-color: #ffebee; padding: 0.75rem; border-radius: 0.5rem; border-left: 6px solid #c62828; }
    .pending-fix { background-color: #fff8e1; padding: 0.75rem; border-radius: 0.5rem; border-left: 6px solid #ffc107; color: #5d4037; }
    h2 { margin-top: 1.5rem !important; }
    .panel-divider { border-top: 2px solid #e0e0e0; margin: 1.5rem 0 1rem 0; }
</style>
""",
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------
# Session definitions (UTC, for chart shading)
# ---------------------------------------------------------------
SESSION_DEFS_UTC = {
    "asia": (0, 8),
    "london": (8, 13),
    "overlap": (13, 17),
    "ny": (17, 22),
}
SESSION_COLORS = {
    "asia": "rgba(255, 193, 7, 0.15)",
    "london": "rgba(33, 150, 243, 0.15)",
    "overlap": "rgba(156, 39, 176, 0.15)",
    "ny": "rgba(76, 175, 80, 0.15)",
}


# ---------------------------------------------------------------
# Pair config (live, no caching)
# ---------------------------------------------------------------
def _load_pair_config() -> tuple[dict, list[str]]:
    sys.path.insert(0, str(Path(__file__).parent))
    from mars.apps.trading.system.pair_config import PAIR_CONFIG, get_enabled_symbols
    return PAIR_CONFIG, get_enabled_symbols()


PAIR_CONFIG, ENABLED_SYMBOLS = _load_pair_config()


# ---------------------------------------------------------------
# DB layer — every function opens its OWN connection, runs, closes
# ---------------------------------------------------------------
DB_PATH = os.path.join(tempfile.gettempdir(), "mt5_audit_real.db")
KS_PATH = os.path.join(tempfile.gettempdir(), "risk_kill_switch.json")
BACKUP_DIR = os.path.join(tempfile.gettempdir(), "audit_backups")


def _conn_ro() -> sqlite3.Connection:
    """Open a fresh read-only sqlite3 connection. Caller MUST close it."""
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"audit DB not found: {DB_PATH}")
    conn = sqlite3.connect(
        f"file:{DB_PATH}?mode=ro",
        uri=True,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    return conn


def _q(sql: str, params: tuple = ()) -> pd.DataFrame:
    """Run a query, return DataFrame. Connection opened and closed in this call."""
    conn = _conn_ro()
    try:
        df = pd.read_sql_query(sql, conn, params=params)
    finally:
        conn.close()
    return df


# ---------------------------------------------------------------
# Data loaders (TTL-stamped caching of the resulting DataFrame only,
# never of the underlying connection)
# ---------------------------------------------------------------
@st.cache_data(ttl=5)
def load_table(table: str, limit: int = 1000) -> pd.DataFrame:
    try:
        return _q(f"SELECT * FROM {table} ORDER BY rowid DESC LIMIT ?", (limit,))
    except Exception as e:
        st.error(f"Error loading {table}: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=5)
def load_evaluations(limit: int = 500) -> pd.DataFrame:
    return _q("SELECT * FROM evaluations ORDER BY rowid DESC LIMIT ?", (limit,))


@st.cache_data(ttl=5)
def load_signals(limit: int = 500) -> pd.DataFrame:
    return _q("SELECT * FROM signals ORDER BY rowid DESC LIMIT ?", (limit,))


@st.cache_data(ttl=5)
def load_risk_decisions(limit: int = 500) -> pd.DataFrame:
    return _q("SELECT * FROM risk_decisions ORDER BY rowid DESC LIMIT ?", (limit,))


@st.cache_data(ttl=5)
def load_fills(limit: int = 500) -> pd.DataFrame:
    return _q("SELECT * FROM fills ORDER BY rowid DESC LIMIT ?", (limit,))


@st.cache_data(ttl=5)
def load_pipeline_latency(limit: int = 500) -> pd.DataFrame:
    """Load additive per-attempt timing records; tolerate pre-migration DBs."""
    try:
        return _q("SELECT * FROM pipeline_latency ORDER BY rowid DESC LIMIT ?", (limit,))
    except sqlite3.OperationalError:
        return pd.DataFrame()


@st.cache_data(ttl=5)
def load_loss_audit(limit: int = 500) -> pd.DataFrame:
    """Load clean broker-closed SL/TP audit rows; tolerate pre-migration DBs."""
    try:
        return _q("SELECT * FROM loss_audit ORDER BY exit_time DESC, id DESC LIMIT ?", (limit,))
    except sqlite3.OperationalError:
        return pd.DataFrame()


@st.cache_data(ttl=5)
def load_risk_events(limit: int = 500) -> pd.DataFrame:
    return _q("SELECT * FROM risk_events ORDER BY rowid DESC LIMIT ?", (limit,))


@st.cache_data(ttl=5)
def load_kill_switch() -> dict:
    if not os.path.exists(KS_PATH):
        return {}
    try:
        with open(KS_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return {}


@st.cache_data(ttl=10)
def load_backup_status() -> dict:
    status: dict = {}
    if not os.path.isdir(BACKUP_DIR):
        return status
    for fname in ("primary", "secondary"):
        p = os.path.join(BACKUP_DIR, f"{fname}_backup_status.json")
        if os.path.exists(p):
            try:
                with open(p, "r") as f:
                    status[fname] = json.load(f)
            except Exception:
                pass
    return status


@st.cache_data(ttl=10)
def load_reconciliation_status() -> dict:
    """Reconciliation between DB rows in memory vs on disk."""
    try:
        # Fresh connection: count rows in each table
        conn = _conn_ro()
        try:
            counts = {}
            tables = ["signals", "fills", "risk_decisions", "risk_events", "evaluations"]
            has_latency_table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'pipeline_latency'"
            ).fetchone()
            if has_latency_table:
                tables.append("pipeline_latency")
            has_loss_audit_table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'loss_audit'"
            ).fetchone()
            if has_loss_audit_table:
                tables.append("loss_audit")
            for t in tables:
                cur = conn.execute(f"SELECT COUNT(*) FROM {t}")
                counts[t] = cur.fetchone()[0]
        finally:
            conn.close()

        db_size = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
        return {
            "db_path": DB_PATH,
            "db_size_bytes": db_size,
            "row_counts": counts,
            "ok": db_size > 0 and all(c >= 0 for c in counts.values()),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------
# Derived metrics (open + close their own connections)
# ---------------------------------------------------------------
@st.cache_data(ttl=5)
def compute_equity() -> tuple[float, str, str]:
    """
    Compute current equity.

    Priority:
    1. Most recent risk_decision.equity (live equity at last order check)
    2. Kill-switch current_equity
    3. Fall back: starting equity + sum(fill.profit) — only if both are non-zero

    Returns (equity, source_label, asof_timestamp).
    The asof_timestamp is when the underlying value was captured (i.e., the
    risk_decision timestamp or kill-switch mtime), NOT when this function ran.
    The dashboard surfaces this next to the Equity metric so the user can see
    exactly how stale the number is.
    """
    # 1. Last risk_decision
    df = load_risk_decisions(1)
    if not df.empty and "equity" in df.columns and float(df["equity"].iloc[0]) > 0:
        asof = df["timestamp"].iloc[0] if "timestamp" in df.columns else "unknown"
        return float(df["equity"].iloc[0]), "last risk_decision", str(asof)

    # 2. Kill-switch
    ks = load_kill_switch()
    if ks.get("current_equity"):
        # kill-switch JSON carries an updated_at or timestamp; fall back to file mtime
        asof = ks.get("updated_at") or ks.get("timestamp")
        if not asof and os.path.exists(KS_PATH):
            asof = datetime.fromtimestamp(os.path.getmtime(KS_PATH), tz=timezone.utc).isoformat()
        return float(ks["current_equity"]), "kill_switch", str(asof or "unknown")

    # 3. Sum of closed-trade profits + a reasonable starting equity assumption
    fills = load_fills(500)
    if not fills.empty and "profit" in fills.columns:
        # Sum only CLOSED fills (profit != 0 indicates a closing fill with realized P&L)
        closed = fills[fills["profit"] != 0]
        if not closed.empty:
            starting = 500.0  # documented tier-1 starting balance for this demo account
            asof = str(closed["timestamp"].iloc[0]) if "timestamp" in closed.columns else "unknown"
            return starting + float(closed["profit"].sum()), "starting + closed P&L (fallback)", asof

    return 0.0, "no data", "never"


@st.cache_data(ttl=5)
def compute_daily_pnl() -> tuple[float, int]:
    """
    Daily P&L = sum(profit) over fills with timestamp dated today (UTC).

    Returns (pnl, n_closed_today). If no closed fills, returns (0.0, 0)
    which is a REAL zero — no fake numbers.
    """
    fills = load_fills(500)
    if fills.empty or "profit" not in fills.columns or "timestamp" not in fills.columns:
        return 0.0, 0

    fills = fills.copy()
    fills["ts"] = pd.to_datetime(fills["timestamp"], errors="coerce", utc=True)
    fills = fills.dropna(subset=["ts"])
    # Only closing fills contribute to realized P&L
    closed = fills[fills["profit"] != 0]
    if closed.empty:
        return 0.0, 0

    today = pd.Timestamp.now(tz="UTC").normalize()
    today_closed = closed[closed["ts"] >= today]
    if today_closed.empty:
        return 0.0, 0
    return float(today_closed["profit"].sum()), int(len(today_closed))


SYSTEM_EXIT_REASONS = {"sl_hit", "tp_hit"}


def _expectancy_from_trades(closed: pd.DataFrame) -> dict:
    """Compute expectancy metrics on a pre-filtered closed-trades DataFrame.

    Assumes an entry-time USD-normalized ``R`` column computed by the shared
    risk-metrics helper, plus exit_time/timestamp for ordering.
    Returns dict with all numeric metrics; caller wraps in status envelope.
    """
    if closed.empty:
        return {"n_trades": 0}
    closed = closed.copy()
    wins = closed[closed["R"] > 0]
    losses = closed[closed["R"] <= 0]

    n = int(len(closed))
    n_wins = int(len(wins))
    n_losses = int(len(losses))
    win_rate = (n_wins / n) if n else 0.0
    avg_win = float(wins["R"].mean()) if n_wins else 0.0
    avg_loss = float(losses["R"].mean()) if n_losses else 0.0
    expectancy_r = win_rate * avg_win + (1 - win_rate) * avg_loss
    gross_profit = float(wins["net_pnl"].sum()) if n_wins else 0.0
    gross_loss = abs(float(losses["net_pnl"].sum())) if n_losses else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")

    sort_col = "exit_time" if "exit_time" in closed.columns else "timestamp"
    closed_sorted = closed.dropna(subset=[sort_col]).sort_values(sort_col)
    if closed_sorted.empty:
        max_dd = 0.0
    else:
        cum = closed_sorted["net_pnl"].cumsum()
        running_max = cum.cummax()
        drawdown = cum - running_max
        max_dd = float(drawdown.min()) if not drawdown.empty else 0.0

    return {
        "n_trades": n,
        "win_rate": win_rate,
        "avg_win_R": avg_win,
        "avg_loss_R": avg_loss,
        "expectancy_R": expectancy_r,
        "profit_factor": profit_factor,
        "max_drawdown_usd": max_dd,
        "gross_profit_usd": gross_profit,
        "gross_loss_usd": gross_loss,
    }


@st.cache_data(ttl=5)
def compute_expectancy_breakdown() -> dict:
    """Expectancy with SL/TP-exited trades broken out from manual-exited trades.

    System exits = SL hit or TP hit (executed by the bot's stop/target).
    Manual exits = anything else (mobile/web/client/expert/null/unknown) —
    closes that happened because a human closed via MT5 terminal, the
    session was restarted, or via any path the system did not initiate.

    Returns:
      {
        "all":    { ...metrics, breakdown: {sl_hit, tp_hit, manual, total}, is_empty },
        "system": { ...metrics, breakdown: {sl_hit, tp_hit, total},        is_empty },
        "manual": { ...metrics, breakdown: {mobile, web, client, expert, total}, is_empty },
        "source": "ok" | "no_data" | "no_closed_trades"
      }
    """
    fills = load_fills(1000)
    out: dict = {"all": {}, "system": {}, "manual": {},
                 "source": "no_data"}

    if fills.empty:
        return out

    if "is_closed" in fills.columns:
        closed = fills[fills["is_closed"] == 1].copy()
    else:
        closed = fills[fills["profit"] != 0].copy()
    if closed.empty:
        out["source"] = "no_closed_trades"
        return out

    # Build net_pnl / stop_dist / filled_lots once on the full closed set
    if "exit_profit" in closed.columns:
        closed["net_pnl"] = pd.to_numeric(closed["exit_profit"], errors="coerce").fillna(0.0)
        if "exit_commission" in closed.columns:
            closed["net_pnl"] = closed["net_pnl"] + pd.to_numeric(
                closed["exit_commission"], errors="coerce").fillna(0.0)
        if "exit_swap" in closed.columns:
            closed["net_pnl"] = closed["net_pnl"] + pd.to_numeric(
                closed["exit_swap"], errors="coerce").fillna(0.0)
    else:
        closed["net_pnl"] = pd.to_numeric(closed["profit"], errors="coerce").fillna(0.0)

    closed["stop_dist"] = (
        pd.to_numeric(closed["filled_sl"], errors="coerce").fillna(0.0)
        - pd.to_numeric(closed["filled_price"], errors="coerce").fillna(0.0)
    ).abs()
    closed["filled_lots"] = pd.to_numeric(closed["filled_lots"], errors="coerce").fillna(0.0)
    closed = closed[(closed["stop_dist"] > 0) & (closed["filled_lots"] > 0)]
    if closed.empty:
        out["source"] = "no_valid_stop_distance"
        return out

    def _shared_realized_r(row: pd.Series) -> float | None:
        try:
            return realized_r(
                symbol=str(row["symbol"]),
                entry_price=float(row["filled_price"]),
                stop_price=float(row["filled_sl"]),
                filled_lots=float(row["filled_lots"]),
                realized_pnl_usd=float(row["net_pnl"]),
            )
        except (KeyError, ValueError):
            return None

    # Use the same contract-size and entry-time quote-to-USD conversion as
    # loss_audit. Never replace unavailable non-USD conversions with a wrong R.
    closed["R"] = closed.apply(_shared_realized_r, axis=1)
    closed = closed.dropna(subset=["R"])
    if closed.empty:
        out["source"] = "no_usd_normalized_stop_risk"
        return out

    out["source"] = "ok"

    # Degraded-sizing split. Trades flagged degraded_sizing=1 used a wrong-size
    # lot because the sizer.fit() / fallback path was broken at the time. They
    # are NOT clean v1 baseline data and must be broken out separately.
    if "degraded_sizing" in closed.columns:
        clean_mask = (closed["degraded_sizing"].fillna(0).astype(int) == 0)
    else:
        clean_mask = pd.Series([True] * len(closed), index=closed.index)
    degraded_mask = ~clean_mask
    clean = closed[clean_mask].copy()
    degraded = closed[degraded_mask].copy()

    er = closed["exit_reason"].fillna("unknown") if "exit_reason" in closed.columns \
        else pd.Series(["unknown"] * len(closed), index=closed.index)
    er_clean = clean["exit_reason"].fillna("unknown") if "exit_reason" in clean.columns \
        else pd.Series(["unknown"] * len(clean), index=clean.index)

    # Counts for the all-trades breakdown (built on the CLEAN subset so
    # v1 baseline metrics never silently include degraded-size trades)
    all_breakdown: dict = {}
    for reason in ("sl_hit", "tp_hit"):
        all_breakdown[reason] = int((er_clean == reason).sum())
    manual_reasons = ["mobile", "web", "client", "expert"]
    for r in manual_reasons:
        all_breakdown[r] = int((er_clean == r).sum())
    all_breakdown["unknown"] = int(
        (~er_clean.isin(list(SYSTEM_EXIT_REASONS) + manual_reasons)).sum()
    )
    all_breakdown["manual_total"] = sum(all_breakdown[r] for r in manual_reasons + ["unknown"])
    all_breakdown["total"] = int(len(clean))
    all_breakdown["degraded_excluded"] = int(len(degraded))

    # Manual breakdown (mobile/web/client/expert + unknown grouped as 'manual')
    manual_breakdown: dict = {r: all_breakdown[r] for r in manual_reasons}
    manual_breakdown["unknown"] = all_breakdown["unknown"]
    manual_breakdown["total"] = all_breakdown["manual_total"]

    # System breakdown
    system_breakdown: dict = {
        "sl_hit": all_breakdown["sl_hit"],
        "tp_hit": all_breakdown["tp_hit"],
        "total":  all_breakdown["sl_hit"] + all_breakdown["tp_hit"],
    }

    system_mask = er_clean.isin(SYSTEM_EXIT_REASONS)
    manual_mask = ~system_mask

    out["all"] = {
        **_expectancy_from_trades(clean),
        "breakdown": all_breakdown,
        "is_empty": len(clean) == 0,
    }
    out["system"] = {
        **_expectancy_from_trades(clean[system_mask]),
        "breakdown": system_breakdown,
        "is_empty": len(clean[system_mask]) == 0,
    }
    out["manual"] = {
        **_expectancy_from_trades(clean[manual_mask]),
        "breakdown": manual_breakdown,
        "is_empty": len(clean[manual_mask]) == 0,
    }
    out["degraded"] = {
        **_expectancy_from_trades(degraded),
        "breakdown": {"total": int(len(degraded))},
        "is_empty": len(degraded) == 0,
    }
    return out


@st.cache_data(ttl=5)
def compute_expectancy() -> dict:
    """
    Legacy single-bucket expectancy (all closed trades combined).

    Kept for code that reads `compute_expectancy()["status"] == "ok"`.
    New code should call `compute_expectancy_breakdown()` which separates
    system exits (SL/TP) from manual exits (mobile/web/client/expert).

    Returns a dict with `status` field:
      - "ok"          : ≥1 closed trade, metrics are real
      - "pending_fix" : 0 closed trades in DB, panel must display the
                        pending-fix message per the task spec
    """
    bd = compute_expectancy_breakdown()
    if bd["source"] != "ok":
        return {
            "status": "pending_fix",
            "reason": ("No closed trades yet. Reconcile the audit DB with MT5 history "
                       "on session startup (`MT5AuditLogger.reconcile_from_broker()`) "
                       "to capture any closes that happened while no session was running."),
        }
    out = dict(bd["all"])
    out["status"] = "ok"
    return out


@st.cache_data(ttl=5)
def compute_open_positions() -> pd.DataFrame:
    """
    Approximate open positions: the most recent fill per symbol where the
    broker's exit has NOT been logged (is_closed != 1).

    When the close-tracking pipeline is working, an entry fill row stays
    is_closed=0 until the broker actually closes the position. Once closed,
    the row is updated to is_closed=1 and stops appearing here.
    """
    fills = load_fills(500)
    if fills.empty:
        return pd.DataFrame()

    df = fills.copy()
    df["ts"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    df = df.dropna(subset=["ts"])
    df = df.sort_values("ts", ascending=False)

    # Filter to only "not yet closed" rows
    if "is_closed" in df.columns:
        open_df = df[(df["is_closed"] == 0) | (df["is_closed"].isna())]
    else:
        # Pre-migration fallback: treat profit == 0 as open
        open_df = df[df["profit"].fillna(0) == 0]

    open_rows = []
    seen_symbols = set()
    for _, row in open_df.iterrows():
        sym = row.get("symbol")
        if sym in seen_symbols:
            continue
        direction = row.get("direction", "")
        if direction in ("BUY", "SELL"):
            open_rows.append(row)
            seen_symbols.add(sym)
    if not open_rows:
        return pd.DataFrame()
    out = pd.DataFrame(open_rows)
    keep = [
        "timestamp", "symbol", "direction", "filled_lots", "filled_price",
        "filled_sl", "filled_tp", "spread_at_fill", "ticket",
        "position_id", "exit_time",
    ]
    keep = [c for c in keep if c in out.columns]
    return out[keep]


@st.cache_data(ttl=5)
def compute_heartbeat() -> dict:
    """Timestamp of last evaluation, last fill, last signal."""
    evals = load_evaluations(1)
    fills = load_fills(1)
    sigs = load_signals(1)
    out = {"last_eval_ts": None, "last_fill_ts": None, "last_signal_ts": None}
    if not evals.empty and "timestamp" in evals.columns:
        out["last_eval_ts"] = evals["timestamp"].iloc[0]
    if not fills.empty and "timestamp" in fills.columns:
        out["last_fill_ts"] = fills["timestamp"].iloc[0]
    if not sigs.empty and "timestamp" in sigs.columns:
        out["last_signal_ts"] = sigs["timestamp"].iloc[0]
    return out


@st.cache_data(ttl=5)
def compute_regime_per_symbol(symbols: list[str]) -> pd.DataFrame:
    """For each symbol, latest evaluation's 1H trend / 30M bias / 15M tradeability."""
    if not symbols:
        return pd.DataFrame(columns=["symbol", "trend_1h", "bias_30m", "context_15m", "gate_result", "as_of"])
    evals = load_evaluations(2000)
    if evals.empty:
        return pd.DataFrame(columns=["symbol", "trend_1h", "bias_30m", "context_15m", "gate_result", "as_of"])
    rows = []
    for sym in symbols:
        sub = evals[evals["symbol"] == sym]
        if sub.empty:
            rows.append({
                "symbol": sym, "trend_1h": "—", "bias_30m": "—", "context_15m": "—",
                "gate_result": "—", "as_of": None,
            })
            continue
        latest = sub.iloc[0]
        rows.append({
            "symbol": sym,
            "trend_1h": latest.get("trend_1h", "—"),
            "bias_30m": latest.get("bias_30m", "—"),
            "context_15m": latest.get("context_15m", "—"),
            "gate_result": latest.get("gate_result", "—"),
            "as_of": latest.get("timestamp"),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------
# OHLCV loader for chart (only loader that touches a parquet file)
# ---------------------------------------------------------------
@st.cache_data(ttl=30)
def load_ohlcv_data(symbol: str, hours: int = 24) -> pd.DataFrame:
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from run_multi_pair_backtest import SYMBOL_CONFIGS, load_symbol_data
        from mars.apps.trading.system.pair_config import get_config_key

        config_key = get_config_key(symbol)
        if config_key not in SYMBOL_CONFIGS:
            return pd.DataFrame()
        df = load_symbol_data(config_key, start="2020-01-01")
        if df.empty:
            return pd.DataFrame()
        latest_available = df.index.max()
        cutoff = latest_available - timedelta(hours=hours + 48)
        return df[df.index >= cutoff]
    except Exception as e:
        st.error(f"Error loading OHLCV for {symbol}: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=30)
def compute_donchian_bands(df: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    if df.empty or len(df) < window:
        return pd.DataFrame()
    upper = df["high"].rolling(window).max().shift(1)
    lower = df["low"].rolling(window).min().shift(1)
    return pd.DataFrame({"donchian_upper": upper, "donchian_lower": lower}, index=df.index)


@st.cache_data(ttl=30)
def compute_atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    if df.empty or len(df) < window:
        return pd.Series(index=df.index, dtype=float)
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift(1)).abs()
    lc = (df["low"] - df["close"].shift(1)).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.rolling(window).mean()


def add_session_shading(fig: go.Figure, df: pd.DataFrame) -> None:
    if df.empty:
        return
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    start_date = df.index[0].date()
    end_date = df.index[-1].date()
    cur = start_date
    while cur <= end_date:
        for name, (h0, h1) in SESSION_DEFS_UTC.items():
            s = pd.Timestamp(cur, tz="UTC") + pd.Timedelta(hours=h0)
            e = pd.Timestamp(cur, tz="UTC") + pd.Timedelta(hours=h1)
            if e > df.index[0] and s < df.index[-1]:
                fig.add_vrect(
                    x0=s, x1=e, fillcolor=SESSION_COLORS[name], layer="below", line_width=0,
                    annotation_text=name.upper()[:3],
                    annotation_position="top left",
                    annotation_font_size=8, annotation_font_color="gray",
                )
        cur += timedelta(days=1)


# ---------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------
st.sidebar.title("📊 M.A.R.S. Dashboard")

if "session_symbols" not in st.session_state:
    st.session_state.session_symbols = ENABLED_SYMBOLS.copy()

st.sidebar.subheader("🎯 Session Symbols")
st.sidebar.caption("Symbols to include in panels below. Must be enabled in PAIR_CONFIG.")
session_symbols: list[str] = st.sidebar.multiselect(
    "Active Session Symbols",
    options=ENABLED_SYMBOLS,
    default=st.session_state.session_symbols,
    key="sidebar_session_symbols_multiselect",
)
st.session_state.session_symbols = session_symbols
if not session_symbols:
    st.sidebar.warning("⚠️ No symbols selected — most panels will be empty.")

st.sidebar.divider()

# Refresh controls
refresh_secs = st.sidebar.selectbox(
    "Auto-refresh interval",
    options=[0, 10, 30, 60],
    format_func=lambda x: "Off" if x == 0 else f"{x}s",
    index=2,
)
if st.sidebar.button("🔄 Refresh Now", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

# Chart settings
st.sidebar.subheader("📈 Chart Settings")
chart_symbol = st.sidebar.selectbox(
    "Chart Symbol",
    options=session_symbols or ENABLED_SYMBOLS,
    index=0,
    key="sidebar_chart_symbol_select",
)
chart_hours = st.sidebar.slider("Chart Time Range (hours)", min_value=1, max_value=168, value=24)

st.sidebar.subheader("Overlay Options")
show_donchian = st.sidebar.checkbox("Donchian Bands", value=True)
show_atr_stops = st.sidebar.checkbox("ATR Stops/Targets", value=True)
show_sessions = st.sidebar.checkbox("Session Shading", value=True)
show_trades = st.sidebar.checkbox("Trade Markers", value=True)


# ---------------------------------------------------------------
# Auto-refresh
# ---------------------------------------------------------------
if refresh_secs and refresh_secs > 0:
    @st.fragment(run_every=timedelta(seconds=refresh_secs))
    def _auto_clear():
        st.cache_data.clear()
    _auto_clear()


# ---------------------------------------------------------------
# Load everything we need once per render (cached separately, all
# connections opened + closed inside the loaders)
# ---------------------------------------------------------------
signals_df = load_signals(500)
risk_decisions_df = load_risk_decisions(500)
fills_df = load_fills(500)
pipeline_latency_df = load_pipeline_latency(500)
loss_audit_df = load_loss_audit(500)
risk_events_df = load_risk_events(500)
evaluations_df = load_evaluations(500)
kill_switch = load_kill_switch()
backup_status = load_backup_status()
recon = load_reconciliation_status()

heartbeat = compute_heartbeat()
equity, equity_src, equity_asof = compute_equity()
daily_pnl, n_closed_today = compute_daily_pnl()
expectancy = compute_expectancy()
open_pos_df = compute_open_positions()
regime_df = compute_regime_per_symbol(session_symbols)


# ===============================================================
# PANEL 1 — System Heartbeat (top, prominent, HIGH-CONTRAST)
# ===============================================================
st.title("M.A.R.S. Multi-Pair Trading Dashboard")


def _fmt_age(ts_str: Optional[str]) -> tuple[str, str, str]:
    """Return (display, color_hex, verb) for a timestamp.

    Returns inline color hex so the dashboard's custom HTML can override
    Streamlit's theme text color. Cards use light fills + explicit black
    text so they remain readable in both light and dark Streamlit themes.
    """
    if not ts_str:
        return ("never", "#c62828", "no data")
    try:
        ts = pd.to_datetime(ts_str, errors="coerce", utc=True)
        if pd.isna(ts):
            return (str(ts_str), "#c62828", "unparseable")
        age = pd.Timestamp.now(tz="UTC") - ts
        secs = int(age.total_seconds())
        if secs < 60:
            return (f"{secs}s ago", "#1b5e20", "active")
        if secs < 300:
            return (f"{secs // 60}m {secs % 60}s ago", "#1b5e20", "active")
        if secs < 1800:
            return (f"{secs // 60}m ago", "#e65100", "warn")
        return (f"{secs // 60}m ago", "#b71c1c", "STALE")
    except Exception:
        return (str(ts_str), "#c62828", "error")


def _heartbeat_card(label: str, ts: Optional[str], verb_label: Optional[str] = None) -> str:
    """Render one heartbeat card with explicit inline colors (visible in any theme)."""
    display, color, verb = _fmt_age(ts)
    bg = {
        "#1b5e20": "#c8e6c9",  # active  → light green
        "#e65100": "#ffe0b2",  # warn    → light orange
        "#b71c1c": "#ffcdd2",  # STALE   → light red
        "#c62828": "#ffcdd2",  # no data → light red
    }.get(color, "#eeeeee")
    return (
        f'<div style="background:{bg}; border-left:6px solid {color}; '
        f'padding:12px 16px; border-radius:6px; margin-bottom:8px; '
        f'font-family:inherit;">'
        f'<div style="color:#222; font-size:13px; font-weight:600; '
        f'text-transform:uppercase; letter-spacing:0.5px;">{label}</div>'
        f'<div style="color:{color}; font-size:22px; font-weight:700; '
        f'margin-top:4px;">{display}</div>'
        f'<div style="color:#555; font-size:12px; margin-top:2px;">'
        f'{verb_label or verb}</div>'
        f'</div>'
    )


def _db_card() -> str:
    db_size_kb = recon.get('db_size_bytes', 0) / 1024
    total_rows = sum(recon.get('row_counts', {}).values())
    return (
        f'<div style="background:#e3f2fd; border-left:6px solid #0d47a1; '
        f'padding:12px 16px; border-radius:6px; margin-bottom:8px;">'
        f'<div style="color:#222; font-size:13px; font-weight:600; '
        f'text-transform:uppercase; letter-spacing:0.5px;">Audit DB</div>'
        f'<div style="color:#0d47a1; font-size:22px; font-weight:700; '
        f'margin-top:4px;">{db_size_kb:.1f} KB</div>'
        f'<div style="color:#555; font-size:12px; margin-top:2px;">'
        f'{total_rows} rows across {len(recon.get("row_counts", {}))} tables</div>'
        f'<div style="color:#777; font-size:10px; margin-top:4px; '
        f'word-break:break-all;">{DB_PATH}</div>'
        f'</div>'
    )


st.markdown(
    "<hr style='border:none; border-top:2px solid #e0e0e0; margin:1rem 0;'>",
    unsafe_allow_html=True,
)
st.markdown(
    '<h2 style="margin-top:0.5rem;">💓 System Heartbeat '
    '<span style="font-size:14px; color:#888; font-weight:400;">'
    '— is the live session polling?</span></h2>',
    unsafe_allow_html=True,
)
hb_cols = st.columns(4)
with hb_cols[0]:
    st.markdown(
        _heartbeat_card("Last gate evaluation", heartbeat["last_eval_ts"]),
        unsafe_allow_html=True,
    )
with hb_cols[1]:
    st.markdown(
        _heartbeat_card("Last fill", heartbeat["last_fill_ts"]),
        unsafe_allow_html=True,
    )
with hb_cols[2]:
    st.markdown(
        _heartbeat_card("Last signal", heartbeat["last_signal_ts"]),
        unsafe_allow_html=True,
    )
with hb_cols[3]:
    st.markdown(_db_card(), unsafe_allow_html=True)


# ===============================================================
# PANEL 2 — Account Overview
# ===============================================================
st.markdown("<div class='panel-divider'></div>", unsafe_allow_html=True)
st.header("1️⃣ Account Overview")

# Daily P&L status
if n_closed_today == 0:
    daily_pnl_caption = f"$0.00 (no closed fills today, UTC)"
else:
    daily_pnl_caption = f"${daily_pnl:,.2f} from {n_closed_today} closed fill(s) today"

# Equity source string
peak = kill_switch.get("peak_equity", 0)
if peak and equity:
    dd_pct = (equity - peak) / peak * 100
else:
    dd_pct = 0.0

# Equity freshness display: surface when the value was actually captured
def _fmt_age_compact(ts_str: str) -> str:
    if not ts_str or ts_str in ("never", "unknown"):
        return "never"
    try:
        ts = pd.to_datetime(ts_str, errors="coerce", utc=True)
        if pd.isna(ts):
            return ts_str
        age = pd.Timestamp.now(tz="UTC") - ts
        secs = int(age.total_seconds())
        if secs < 60:
            return f"{secs}s ago"
        if secs < 3600:
            return f"{secs // 60}m ago"
        if secs < 86400:
            return f"{secs // 3600}h ago"
        return f"{secs // 86400}d ago"
    except Exception:
        return ts_str


col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    equity_age = _fmt_age_compact(equity_asof)
    # Use help and a small caption under the metric to make freshness unambiguous
    st.metric(
        "Equity",
        f"${equity:,.2f}",
        help=f"Source: {equity_src}\nLast update: {equity_asof}",
    )
    st.caption(f"as of {equity_age} ({equity_src})")
with col2:
    st.metric("Daily P&L", daily_pnl_caption)
with col3:
    dd_color = "🔴" if dd_pct < -10 else "🟡" if dd_pct < -5 else "🟢"
    st.metric("Drawdown vs Peak", f"{dd_color} {dd_pct:.2f}%")
with col4:
    ks_halted = kill_switch.get("kill_switch_halted", False)
    st.metric("Kill Switch", "🔴 HALTED" if ks_halted else "🟢 ACTIVE")
with col5:
    cl_halted = kill_switch.get("consecutive_loss_halted", False)
    cl_count = kill_switch.get("consecutive_losses", 0)
    st.metric("Consec. Losses", f"🔴 HALTED ({cl_count})" if cl_halted else f"🟢 OK ({cl_count})")

# Tier info if available
tier = kill_switch.get("current_tier", {})
if tier:
    st.info(
        f"📋 **Locked Risk Tier:** "
        f"${tier.get('min_equity', 0)}-{'∞' if tier.get('max_equity', float('inf')) == float('inf') else tier.get('max_equity', '?')} | "
        f"Risk/Trade: {tier.get('risk_pct_per_trade', 0) * 100:.1f}% | "
        f"Concurrent: {tier.get('max_concurrent_trades', 0)} | "
        f"RR: {tier.get('reward_risk_ratio', 0)}"
    )


# ===============================================================
# PANEL 3 — Regime Indicator (1H / 30M / 15M per symbol)
# ===============================================================
st.markdown(
    "<hr style='border:none; border-top:2px solid #e0e0e0; margin:1.5rem 0;'>",
    unsafe_allow_html=True,
)
st.markdown(
    '<h2 style="margin-top:0.5rem;">2️⃣ Regime Indicator '
    '<span style="font-size:14px; color:#888; font-weight:400;">'
    '— current 1H trend / 30M bias / 15M tradeability per symbol</span></h2>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div style="color:#666; font-size:13px; margin-bottom:8px;">'
    'Latest MTF gate evaluation per active symbol — updated each cycle. '
    'Required for the Nov 3 decision: was Donchian losing disproportionately '
    'in choppy regimes?</div>',
    unsafe_allow_html=True,
)


def _regime_value_html(label: str, value: str) -> tuple[str, str]:
    """Return (color_hex, bg_hex) for a regime value."""
    if value == "LONG_BIAS":
        return ("#1b5e20", "#c8e6c9")
    if value == "SHORT_BIAS":
        return ("#b71c1c", "#ffcdd2")
    if value == "TRADEABLE":
        return ("#1b5e20", "#c8e6c9")
    if value == "NOT_TRADEABLE":
        return ("#b71c1c", "#ffcdd2")
    if value == "ALLOWED":
        return ("#1b5e20", "#c8e6c9")
    if value == "REJECTED":
        return ("#e65100", "#ffe0b2")
    return ("#555555", "#eeeeee")  # neutral / unknown


def _regime_pill(value: str) -> str:
    """Compact colored pill for a regime value (label only, not the row)."""
    color, bg = _regime_value_html("", value)
    return (
        f'<span style="background:{bg}; color:{color}; padding:3px 10px; '
        f'border-radius:12px; font-size:13px; font-weight:700; '
        f'border:1px solid {color}; display:inline-block;">{value}</span>'
    )


def _regime_row(label: str, value: str) -> str:
    color, _ = _regime_value_html(label, value)
    return (
        f'<div style="display:flex; justify-content:space-between; '
        f'align-items:center; padding:6px 0; border-bottom:1px solid #eee;">'
        f'<span style="color:#333; font-size:13px; font-weight:600;">'
        f'{label}</span>'
        f'{_regime_pill(value)}'
        f'</div>'
    )


if regime_df.empty:
    st.markdown(
        '<div style="background:#fff8e1; padding:12px; border-radius:6px; '
        'border-left:6px solid #ffc107; color:#5d4037;">'
        'No regime data yet (no evaluations recorded for the selected symbols).'
        '</div>',
        unsafe_allow_html=True,
    )
else:
    cols = st.columns(len(regime_df))
    for idx, (_, row) in enumerate(regime_df.iterrows()):
        with cols[idx]:
            sym = row["symbol"]
            t1 = row["trend_1h"] or "—"
            t30 = row["bias_30m"] or "—"
            c15 = row["context_15m"] or "—"
            gate = row["gate_result"] or "—"
            asof = row.get("as_of", "") or "—"

            asof_display = asof
            if hasattr(asof, "isoformat"):
                asof_display = asof.isoformat()
            # Trim microseconds for compactness
            if isinstance(asof_display, str) and len(asof_display) > 19:
                asof_display = asof_display[:19].replace("T", " ") + " UTC"

            html = (
                f'<div style="background:#ffffff; border:2px solid #1976d2; '
                f'border-radius:8px; padding:14px 16px; margin-bottom:8px; '
                f'box-shadow:0 1px 3px rgba(0,0,0,0.08);">'
                f'<div style="display:flex; justify-content:space-between; '
                f'align-items:baseline; border-bottom:2px solid #1976d2; '
                f'padding-bottom:6px; margin-bottom:8px;">'
                f'<span style="color:#0d47a1; font-size:18px; font-weight:700;">'
                f'{sym}</span>'
                f'<span style="color:#888; font-size:11px;">{asof_display}</span>'
                f'</div>'
                f'{_regime_row("1H trend",    str(t1))}'
                f'{_regime_row("30M bias",    str(t30))}'
                f'{_regime_row("15M context", str(c15))}'
                f'{_regime_row("Gate result", str(gate))}'
                f'</div>'
            )
            st.markdown(html, unsafe_allow_html=True)


# ===============================================================
# PANEL 4 — Live Signal / Trade Log
# ===============================================================
_LATENCY_COLUMNS = (
    "detection_latency",
    "signal_latency",
    "execution_latency",
    "total_latency",
)


def _latency_display(trace: dict | None) -> dict[str, str]:
    """Format read-time pipeline durations without persisting derived values."""
    if trace is None:
        return {column: "—" for column in _LATENCY_COLUMNS}
    metrics = derive_latency_metrics(trace)
    return {
        "detection_latency": format_latency_ms(metrics["detection_latency_ms"]),
        "signal_latency": format_latency_ms(metrics["signal_latency_ms"]),
        "execution_latency": format_latency_ms(metrics["execution_latency_ms"]),
        "total_latency": format_latency_ms(metrics["total_latency_ms"]),
    }


latency_by_signal: dict[int, dict] = {}
latency_by_fill: dict[int, dict] = {}
if not pipeline_latency_df.empty:
    for _, latency_trace in pipeline_latency_df.iterrows():
        trace = latency_trace.to_dict()
        signal_id = trace.get("signal_id")
        fill_id = trace.get("fill_id")
        if pd.notna(signal_id):
            latency_by_signal[int(signal_id)] = trace
        if pd.notna(fill_id):
            latency_by_fill[int(fill_id)] = trace


st.markdown("<div class='panel-divider'></div>", unsafe_allow_html=True)
st.header("3️⃣ Live Signal / Trade Log")
st.caption("Combined stream of signals, MTF evaluations, risk decisions, and fills, "
           "sorted by timestamp desc. Latencies are computed from raw UTC audit timestamps.")

log_cols = st.columns([2, 2, 1])
with log_cols[0]:
    type_filter = st.multiselect(
        "Event Type",
        options=["EVAL", "SIGNAL", "RISK", "FILL"],
        default=["EVAL", "SIGNAL", "RISK", "FILL"],
        key="log_type_filter",
    )
with log_cols[1]:
    sym_filter = st.multiselect(
        "Symbol",
        options=session_symbols or ["(none)"],
        default=session_symbols or ["(none)"],
        key="log_symbol_filter",
    )
with log_cols[2]:
    log_limit = st.number_input("Max rows", min_value=20, max_value=1000, value=100, step=20)

rows: list[dict] = []

if "EVAL" in type_filter and not evaluations_df.empty:
    for _, r in evaluations_df.head(min(len(evaluations_df), log_limit)).iterrows():
        if sym_filter and r.get("symbol") not in sym_filter:
            continue
        rr = r.get("rejection_reason")
        rr_str = "no reason" if rr is None or (isinstance(rr, float) and pd.isna(rr)) else str(rr)
        rows.append({
            "timestamp": r.get("timestamp"),
            "type": "EVAL",
            "symbol": r.get("symbol"),
            "detail": f"{r.get('gate_result', '?')} ({rr_str})",
            "extra": f"1H={r.get('trend_1h','?')} 30M={r.get('bias_30m','?')} 15M={r.get('context_15m','?')} sig={r.get('breakout_signal',0)}",
            **_latency_display(None),
        })

if "SIGNAL" in type_filter and not signals_df.empty:
    for _, r in signals_df.head(min(len(signals_df), log_limit)).iterrows():
        if sym_filter and r.get("symbol") not in sym_filter:
            continue
        sig = r.get("signal", 0)
        sig_text = "LONG" if sig == 1 else "SHORT" if sig == -1 else "FLAT"
        passed = "PASS" if r.get("risk_check_passed") == 1 else "FAIL"
        rr = r.get("rejection_reason")
        rr_str = "" if rr is None or (isinstance(rr, float) and pd.isna(rr)) else str(rr)
        rows.append({
            "timestamp": r.get("timestamp"),
            "type": "SIGNAL",
            "symbol": r.get("symbol"),
            "detail": f"{sig_text} @ {r.get('entry_price', 0):.3f} | risk_check={passed}",
            "extra": rr_str[:60],
            **(
                _latency_display(latency_by_signal.get(int(r["id"])))
                if pd.notna(r.get("id"))
                else _latency_display(None)
            ),
        })

if "RISK" in type_filter and not risk_decisions_df.empty:
    for _, r in risk_decisions_df.head(min(len(risk_decisions_df), log_limit)).iterrows():
        if sym_filter and r.get("symbol") not in sym_filter:
            continue
        reason = r.get("reason")
        reason_str = "" if reason is None or (isinstance(reason, float) and pd.isna(reason)) else str(reason)
        rows.append({
            "timestamp": r.get("timestamp"),
            "type": "RISK",
            "symbol": r.get("symbol"),
            "detail": f"{r.get('decision', '?')} | signal={r.get('signal', 0)}",
            "extra": reason_str[:60],
            **_latency_display(None),
        })

if "FILL" in type_filter and not fills_df.empty:
    for _, r in fills_df.head(min(len(fills_df), log_limit)).iterrows():
        if sym_filter and r.get("symbol") not in sym_filter:
            continue
        pnl = float(r.get("profit", 0) or 0)
        pnl_str = f"P&L ${pnl:+.2f}" if pnl != 0 else "OPEN"
        rows.append({
            "timestamp": r.get("timestamp"),
            "type": "FILL",
            "symbol": r.get("symbol"),
            "detail": f"{r.get('direction', '?')} {r.get('filled_lots', 0):.2f} @ {r.get('filled_price', 0):.3f} | {pnl_str}",
            "extra": f"ticket={r.get('ticket', '?')}",
            **(
                _latency_display(latency_by_fill.get(int(r["id"])))
                if pd.notna(r.get("id"))
                else _latency_display(None)
            ),
        })

if rows:
    log_df = pd.DataFrame(rows)
    log_df["ts_parsed"] = pd.to_datetime(log_df["timestamp"], errors="coerce", utc=True)
    log_df = log_df.dropna(subset=["ts_parsed"]).sort_values("ts_parsed", ascending=False).head(log_limit)
    log_df["timestamp"] = log_df["ts_parsed"].dt.strftime("%Y-%m-%d %H:%M:%S")
    log_df = log_df[[
        "timestamp", "type", "symbol", "detail", "extra",
        "detection_latency", "signal_latency", "execution_latency", "total_latency",
    ]]
    st.dataframe(
        log_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "timestamp": "Time (UTC)",
            "type": "Type",
            "symbol": "Symbol",
            "detail": "Detail",
            "extra": "Extra",
            "detection_latency": "Detection",
            "signal_latency": "Signal → risk",
            "execution_latency": "Execution",
            "total_latency": "Total",
        },
    )
else:
    st.info("No events match the current filters.")


# ===============================================================
# ===============================================================
# PANEL 5 — Running Expectancy (with system vs manual exit split)
# ===============================================================
st.markdown("<div class='panel-divider'></div>", unsafe_allow_html=True)
st.header("4️⃣ Running Expectancy")

expectancy_breakdown = compute_expectancy_breakdown()

if expectancy_breakdown["source"] != "ok":
    st.markdown(
        f"""
<div class='pending-fix'>
  ⚠️ <b>Expectancy calculation pending fix:</b>
  {expectancy.get('reason', 'no closed trades')}
  <br>This panel will populate once the 6-week baseline produces realized P&amp;L.
</div>
        """,
        unsafe_allow_html=True,
    )
else:
    all_m = expectancy_breakdown["all"]
    sys_m = expectancy_breakdown["system"]
    man_m = expectancy_breakdown["manual"]
    deg_m = expectancy_breakdown.get("degraded", {"is_empty": True, "n_trades": 0})
    all_bd = all_m["breakdown"]
    deg_excluded = all_bd.get("degraded_excluded", 0)

    def _render_metrics_row(metrics, label: str, breakdown: dict | None):
        """Render one row of metrics. If empty, show explicit 'no data'."""
        empty = metrics.get("is_empty", metrics.get("n_trades", 0) == 0)
        if empty:
            st.markdown(
                f"<div class='pending-fix'>"
                f"<b>{label}</b>: no trades in this group yet "
                f"(SL/TP exits and manual closes are tracked separately; "
                f"metrics will populate as soon as the first qualifying trade lands)."
                f"</div>",
                unsafe_allow_html=True,
            )
            return
        cols = st.columns(7)
        with cols[0]:
            st.metric("Trades", metrics["n_trades"])
        with cols[1]:
            st.metric("Win Rate", f"{metrics['win_rate']*100:.1f}%")
        with cols[2]:
            st.metric("Avg Win (R)", f"{metrics['avg_win_R']:+.2f}")
        with cols[3]:
            st.metric("Avg Loss (R)", f"{metrics['avg_loss_R']:+.2f}")
        with cols[4]:
            st.metric("Expectancy (R)", f"{metrics['expectancy_R']:+.3f}")
        with cols[5]:
            pf = metrics["profit_factor"]
            st.metric("Profit Factor", f"{pf:.2f}" if pf != float("inf") else "∞")
        with cols[6]:
            st.metric("Max DD (USD)", f"${metrics['max_drawdown_usd']:,.2f}")
        if breakdown is not None:
            bd_parts = []
            for k in ("sl_hit", "tp_hit", "mobile", "web", "client", "expert", "unknown"):
                v = breakdown.get(k, 0)
                if v > 0:
                    bd_parts.append(f"{k}={v}")
            if bd_parts:
                st.caption("Counts by exit_reason: " + " · ".join(bd_parts))

    # Top: All trades
    st.subheader("All closed trades")
    _render_metrics_row(all_m, "All", all_bd)

    # Middle: System exits only (SL/TP) — this is the system's true performance
    sys_bd = sys_m["breakdown"]
    sys_caption = ""
    if sys_bd:
        sys_caption = (f"SL hit: {sys_bd.get('sl_hit', 0)}  ·  "
                       f"TP hit: {sys_bd.get('tp_hit', 0)}  ·  total: {sys_bd.get('total', 0)}")
    st.subheader("System exits (SL hit / TP hit only)")
    _render_metrics_row(sys_m, "System", None)
    if sys_caption:
        st.caption(sys_caption)

    # Bottom: Manual closes only — explicitly labelled so it's never blended
    man_bd = man_m["breakdown"]
    man_caption = ""
    if man_bd:
        parts = []
        for k in ("mobile", "web", "client", "expert", "unknown"):
            v = man_bd.get(k, 0)
            if v > 0:
                parts.append(f"{k}={v}")
        man_caption = (f"closes not initiated by the bot: " + " · ".join(parts)
                       + f"  ·  total: {man_bd.get('total', 0)}")
    st.subheader("Manual closes (mobile / web / client / expert — NOT system exits)")
    _render_metrics_row(man_m, "Manual", None)
    if man_caption:
        st.caption(man_caption)

    # Degraded-sizing bucket: trades where the sizer fell back to the wrong
    # formula (or where fit() failed) and used incorrect lot size. Same split
    # principle as system-exit vs manual-close: never silently blended into
    # the v1 baseline metrics shown in "All trades" above.
    deg_bd = deg_m.get("breakdown", {})
    if deg_excluded > 0:
        st.subheader("⚠️ Degraded sizing (excluded from All / System / Manual above)")
        _render_metrics_row(deg_m, "Degraded", None)
        st.caption(
            f"{deg_excluded} trade(s) tagged `degraded_sizing=1` because the sizer "
            f"fit() or fallback path produced incorrect lot sizes. These are NOT "
            f"clean v1 baseline data and must not be aggregated with system/manual "
            f"metrics above. Review and re-classify before the Nov 3 checkpoint."
        )
    elif deg_bd.get("total", 0) > 0:
        st.subheader("⚠️ Degraded sizing (excluded from All / System / Manual above)")
        _render_metrics_row(deg_m, "Degraded", None)

    # Footer explanation
    st.caption(
        f"System-generated performance (SL/TP only) is shown separately from manual "
        f"closes so the bot's own exit-decision quality is never silently blended with "
        f"trades a human closed via MT5 terminal. "
        f"All trades (clean only): {all_bd['total']} fills, "
        f"gross ${all_m['gross_profit_usd']:,.2f} / "
        f"${all_m['gross_loss_usd']:,.2f}. "
        f"Degraded-sizing trades broken out: {deg_excluded}."
    )


# ===============================================================
# PANEL 6 — System-exit loss audit
# ===============================================================
st.markdown("<div class='panel-divider'></div>", unsafe_allow_html=True)
st.header("System-exit loss audit")
st.caption(
    "Broker-confirmed SL/TP exits only. Manual exits and degraded sizing are "
    "excluded. Entry delay is reconstructed from the best available signal audit; "
    "regime is intentionally NULL until the retrospective regime backfill exists."
)

if loss_audit_df.empty:
    st.info("No clean system-exit audit rows are available yet.")
else:
    loss_audit_display = loss_audit_df.copy()
    for numeric_column in (
        "entry_delay_ms", "r_realized", "stop_distance", "atr_at_entry", "stop_distance_vs_atr",
    ):
        if numeric_column in loss_audit_display.columns:
            loss_audit_display[numeric_column] = pd.to_numeric(
                loss_audit_display[numeric_column], errors="coerce"
            ).round(6)
    loss_audit_display = loss_audit_display.rename(
        columns={
            "fill_id": "Fill ID",
            "source_signal_id": "Signal ID",
            "symbol": "Symbol",
            "direction": "Direction",
            "entry_time": "Entry time (UTC)",
            "source_signal_time": "Signal time (UTC)",
            "entry_delay_ms": "Entry delay (ms)",
            "entry_delay_source": "Entry-delay source",
            "r_realized": "Realized R",
            "stop_distance": "Stop distance",
            "atr_at_entry": "ATR at entry",
            "stop_distance_vs_atr": "Stop / ATR",
            "atr_recovery_status": "ATR recovery",
            "exit_type": "Exit type",
            "exit_time": "Exit time (UTC)",
            "regime_at_entry": "Regime at entry",
        }
    )
    audit_columns = [
        "Fill ID", "Signal ID", "Symbol", "Direction", "Entry time (UTC)",
        "Signal time (UTC)", "Entry delay (ms)", "Entry-delay source", "Realized R",
        "Stop distance", "ATR at entry", "Stop / ATR", "ATR recovery", "Exit type",
        "Exit time (UTC)", "Regime at entry",
    ]
    st.dataframe(
        loss_audit_display[[column for column in audit_columns if column in loss_audit_display]],
        hide_index=True,
    )


# ===============================================================
# PANEL 7 — Open Positions
# ===============================================================
st.markdown("<div class='panel-divider'></div>", unsafe_allow_html=True)
st.header("5️⃣ Open Positions")

if open_pos_df.empty:
    st.info("No open positions.")
else:
    display = open_pos_df.copy()
    if "timestamp" in display.columns:
        display["timestamp"] = pd.to_datetime(display["timestamp"], errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S")
    st.dataframe(display, use_container_width=True, hide_index=True)


# ===============================================================
# PANEL 7 — Per-Pair Status (config only, not data)
# ===============================================================
st.markdown("<div class='panel-divider'></div>", unsafe_allow_html=True)
st.header("6️⃣ Per-Pair Status")

session_pair_config = {s: PAIR_CONFIG[s] for s in session_symbols if s in PAIR_CONFIG}
if not session_pair_config:
    st.info("No session symbols selected.")
else:
    cols = st.columns(len(session_pair_config))
    for idx, (symbol, cfg) in enumerate(session_pair_config.items()):
        with cols[idx]:
            enabled = cfg.get("enabled", False)
            badge = "enabled-badge" if enabled else "disabled-badge"
            badge_text = "✅ ENABLED" if enabled else "❌ DISABLED"
            st.markdown(
                f"<div class='metric-card'>"
                f"<h4 style='margin:0;color:#0d47a1;font-size:18px;font-weight:700;'>{symbol}</h4>"
                f"<span class='{badge}'>{badge_text}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
            st.caption(f"Strategy: {cfg.get('strategy', '?')}")
            st.caption(f"Donchian: {cfg.get('donchian_window', '?')} | RR: {cfg.get('rr_ratio', '?')}")
            st.caption(f"Stop: {cfg.get('stop_mode', '?')} (×{cfg.get('stop_multiplier', cfg.get('risk_pips', '?'))})")
            st.caption(f"Session: {cfg.get('session_filter', 'all')}")
            if not enabled:
                st.caption(f"_Reason: {cfg.get('disabled_reason', 'N/A')}_")


# ===============================================================
# PANEL 8 — Price Chart
# ===============================================================
st.markdown("<div class='panel-divider'></div>", unsafe_allow_html=True)
st.header(f"7️⃣ Price Chart: {chart_symbol}")

pair_cfg = PAIR_CONFIG.get(chart_symbol, {})
donchian_window = pair_cfg.get("donchian_window", 20)
stop_multiplier = pair_cfg.get("stop_multiplier", 2.0)

with st.spinner(f"Loading {chart_symbol} price data..."):
    ohlcv_df = load_ohlcv_data(chart_symbol, hours=chart_hours)

if ohlcv_df.empty:
    st.warning(f"No price data available for {chart_symbol}.")
else:
    donchian_df = compute_donchian_bands(ohlcv_df, window=donchian_window)
    atr_series = compute_atr(ohlcv_df, window=14)

    symbol_fills = pd.DataFrame()
    if not fills_df.empty:
        symbol_fills = fills_df[fills_df["symbol"] == chart_symbol].copy()
        if not symbol_fills.empty:
            symbol_fills["timestamp"] = pd.to_datetime(symbol_fills["timestamp"], errors="coerce", utc=True)
            symbol_fills = symbol_fills.dropna(subset=["timestamp"])
            latest_time = ohlcv_df.index.max()
            cutoff = latest_time - timedelta(hours=chart_hours)
            symbol_fills = symbol_fills[symbol_fills["timestamp"] >= cutoff]

    fig = go.Figure()
    if show_sessions:
        add_session_shading(fig, ohlcv_df)

    fig.add_trace(
        go.Candlestick(
            x=ohlcv_df.index, open=ohlcv_df["open"], high=ohlcv_df["high"],
            low=ohlcv_df["low"], close=ohlcv_df["close"], name=f"{chart_symbol} OHLC",
            increasing_line_color="#26a69a", decreasing_line_color="#ef5350",
        )
    )

    if show_donchian and not donchian_df.empty:
        fig.add_trace(go.Scatter(
            x=donchian_df.index, y=donchian_df["donchian_upper"],
            mode="lines", line=dict(color="rgba(33,150,243,0.7)", width=1.5, dash="dash"),
            name=f"Donchian Upper ({donchian_window})",
        ))
        fig.add_trace(go.Scatter(
            x=donchian_df.index, y=donchian_df["donchian_lower"],
            mode="lines", line=dict(color="rgba(33,150,243,0.7)", width=1.5, dash="dash"),
            name=f"Donchian Lower ({donchian_window})",
            fill="tonexty", fillcolor="rgba(33,150,243,0.05)",
        ))

    if show_atr_stops and not atr_series.empty and not symbol_fills.empty:
        latest_fill = symbol_fills.iloc[-1]
        direction = latest_fill.get("direction", "")
        fill_price = latest_fill.get("filled_price", 0)
        fill_time = latest_fill.get("timestamp")
        if direction in ("BUY", "SELL") and fill_price > 0:
            try:
                atr_at_fill = atr_series.asof(fill_time) if fill_time is not None else atr_series.iloc[-1]
            except Exception:
                atr_at_fill = atr_series.iloc[-1]
            if pd.notna(atr_at_fill) and atr_at_fill > 0:
                stop_dist = stop_multiplier * atr_at_fill
                target_dist = stop_multiplier * 2.5 * atr_at_fill
                if direction == "BUY":
                    stop_price = fill_price - stop_dist
                    target_price = fill_price + target_dist
                else:
                    stop_price = fill_price + stop_dist
                    target_price = fill_price - target_dist
                x_end = ohlcv_df.index[-1]
                fig.add_trace(go.Scatter(
                    x=[fill_time, x_end], y=[stop_price, stop_price],
                    mode="lines", line=dict(color="red", width=2, dash="dot"),
                    name=f"Stop ({stop_price:.3f})",
                ))
                fig.add_trace(go.Scatter(
                    x=[fill_time, x_end], y=[target_price, target_price],
                    mode="lines", line=dict(color="green", width=2, dash="dot"),
                    name=f"Target ({target_price:.3f})",
                ))
                fig.add_trace(go.Scatter(
                    x=[fill_time, x_end], y=[fill_price, fill_price],
                    mode="lines", line=dict(color="blue", width=1.5, dash="solid"),
                    name=f"Entry ({fill_price:.3f})",
                ))

    if show_trades and not symbol_fills.empty:
        for _, fill in symbol_fills.iterrows():
            fill_time = fill["timestamp"]
            direction = fill.get("direction", "")
            fill_price = fill.get("filled_price", 0)
            profit = float(fill.get("profit", 0) or 0)
            if direction == "BUY":
                color, shape, label = "green", "triangle-up", f"BUY @ {fill_price:.3f}"
            elif direction == "SELL":
                color, shape, label = "red", "triangle-down", f"SELL @ {fill_price:.3f}"
            else:
                continue
            fig.add_trace(go.Scatter(
                x=[fill_time], y=[fill_price],
                mode="markers+text",
                marker=dict(symbol=shape, size=14, color=color, line=dict(width=2, color="white")),
                text=[label],
                textposition="top center" if direction == "BUY" else "bottom center",
                textfont=dict(size=9, color=color),
                showlegend=False,
            ))
            if profit != 0:
                fig.add_annotation(
                    x=fill_time, y=fill_price, text=f"${profit:+.2f}", showarrow=True,
                    arrowhead=2, font=dict(size=8, color="green" if profit > 0 else "red"),
                    yshift=20 if direction == "BUY" else -20,
                )

    fig.update_layout(
        title=f"{chart_symbol} - M5 Candlesticks (Last {chart_hours}h)",
        xaxis_title="Time (UTC)", yaxis_title="Price",
        xaxis_rangeslider_visible=False, height=600, template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=50, r=50, t=80, b=50),
    )
    if "JPY" in chart_symbol:
        fig.update_yaxes(tickformat=".3f")
    elif "XAU" in chart_symbol:
        fig.update_yaxes(tickformat=".2f")
    else:
        fig.update_yaxes(tickformat=".5f")
    st.plotly_chart(fig, use_container_width=True)

    if not ohlcv_df.empty:
        latest_time = ohlcv_df.index.max()
        earliest_time = ohlcv_df.index.min()
        st.caption(
            f"**Data:** {len(ohlcv_df)} M5 bars from {earliest_time.strftime('%Y-%m-%d %H:%M')} to "
            f"{latest_time.strftime('%Y-%m-%d %H:%M')} UTC | "
            f"Donchian: {donchian_window} | ATR: 14 | Stop: {stop_multiplier}x | "
            f"Sessions (UTC): Asia 00-08 | London 08-13 | Overlap 13-17 | NY 17-22"
        )


# ===============================================================
# PANEL 9 — Risk Events Feed
# ===============================================================
st.markdown("<div class='panel-divider'></div>", unsafe_allow_html=True)
st.header("8️⃣ Risk Events Feed")

ev_cols = st.columns(2)
with ev_cols[0]:
    event_filter = st.selectbox(
        "Event Type",
        options=["All", "KILL_SWITCH", "CONSECUTIVE_LOSS_HALT", "MTF_ALIGNMENT_REJECTED",
                 "MIN_LOT_OVERRIDE", "OTHER"],
        key="risk_event_type_filter",
    )
with ev_cols[1]:
    symbol_filter = st.selectbox(
        "Symbol",
        options=["All"] + session_symbols,
        key="risk_event_symbol_filter",
    )

if risk_events_df.empty:
    st.info("No risk events recorded.")
else:
    events = risk_events_df.copy()
    events["timestamp"] = pd.to_datetime(events["timestamp"], errors="coerce", utc=True)
    events = events.dropna(subset=["timestamp"]).sort_values("timestamp", ascending=False)

    if "details" in events.columns and session_symbols:
        def _extract_symbol(details: str) -> str:
            for sym in session_symbols:
                if sym in str(details):
                    return sym
            return "N/A"
        events["symbol"] = events["details"].apply(_extract_symbol)
    else:
        events["symbol"] = "N/A"

    if event_filter != "All":
        events = events[events["event_type"] == event_filter]
    if symbol_filter != "All":
        events = events[events["symbol"] == symbol_filter]

    events = events.head(100)
    if events.empty:
        st.info("No risk events match the current filters.")
    else:
        for _, row in events.iterrows():
            et = row.get("event_type", "UNKNOWN")
            css = "risk-event-critical" if any(k in et for k in ("HALT", "KILL", "REJECT")) \
                else "risk-event-warning" if "OVERRIDE" in et else "risk-event-info"
            st.markdown(
                f"""<div class="metric-card {css}">
                    <strong>{row['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}</strong> | {et} | {row.get('symbol', 'N/A')}
                    <br><small>{row.get('details', 'No message')}</small>
                </div>""",
                unsafe_allow_html=True,
            )


# ===============================================================
# PANEL 10 — Ops Status (reconciliation, backups, kill-switch)
# ===============================================================
st.markdown("<div class='panel-divider'></div>", unsafe_allow_html=True)
st.header("9️⃣ Ops Status")
op_cols = st.columns(2)

with op_cols[0]:
    st.subheader("System / Reconciliation")
    st.write(f"**DB Path:** `{recon.get('db_path', DB_PATH)}`")
    st.write(f"**DB Size:** {recon.get('db_size_bytes', 0) / 1024:.1f} KB")
    rc = recon.get("row_counts", {})
    if rc:
        st.write("**Row counts:**")
        for t, c in rc.items():
            st.write(f"  - `{t}`: {c}")
    st.write(f"**Reconciliation OK:** {'✅' if recon.get('ok') else '❌'}")
    ks = kill_switch
    st.write(f"**Kill Switch:** {'🔴 HALTED' if ks.get('kill_switch_halted') else '🟢 ACTIVE'}")
    st.write(f"**Consec. Losses:** {ks.get('consecutive_losses', 0)} "
             f"({'HALTED' if ks.get('consecutive_loss_halted') else 'OK'})")

with op_cols[1]:
    st.subheader("Backup Status")
    if not backup_status:
        st.caption("No backup status files found. Backups will appear here once they run.")
    for name in ("primary", "secondary"):
        info = backup_status.get(name)
        if info:
            st.write(f"**{name.title()} Backup:** {info.get('last_backup', 'Never')}")
            st.caption(f"  - location: {info.get('path', '?')}")
        else:
            st.write(f"**{name.title()} Backup:** Not configured")


# ===============================================================
# Footer
# ===============================================================
st.divider()
st.caption(
    "M.A.R.S. Trading Dashboard — Read-Only Monitoring | "
    "No order placement capability | "
    f"Rendered at {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')} | "
    f"Data source: SQLite audit DB ({DB_PATH})"
)
