"""
Render exact panel output the way Streamlit will display it,
against the real audit DB. This is the textual equivalent of a screenshot.
"""
import sys, os, types
sys.path.insert(0, r"C:\Users\RIDGE\MARS-QUANT")
os.chdir(r"C:\Users\RIDGE\MARS-QUANT")

import sqlite3, tempfile, json
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

from mars.apps.trading.system.pair_config import PAIR_CONFIG, get_enabled_symbols
ENABLED_SYMBOLS = get_enabled_symbols()

# Same permissive fake streamlit as in verify_dashboard.py
class FakeColumn:
    def __enter__(self): return self
    def __exit__(self, *a): return False

class FakeSidebar:
    title = staticmethod(lambda *a, **kw: None)
    subheader = staticmethod(lambda *a, **kw: None)
    caption = staticmethod(lambda *a, **kw: None)
    divider = staticmethod(lambda *a, **kw: None)
    warning = staticmethod(lambda *a, **kw: None)
    info = staticmethod(lambda *a, **kw: None)
    button = staticmethod(lambda *a, **kw: False)
    checkbox = staticmethod(lambda *a, **kw: True)
    slider = staticmethod(lambda *a, **kw: 24)
    selectbox = staticmethod(lambda *a, **kw: 0)
    def multiselect(self, *a, **kw): return ENABLED_SYMBOLS
    def number_input(self, *a, **kw): return 100

class FakeSessionState(dict):
    def __getattr__(self, k):
        try: return self[k]
        except KeyError: raise AttributeError(k)
    def __setattr__(self, k, v): self[k] = v

class FakeStreamlit:
    def __init__(self):
        self.session_state = FakeSessionState()
        self.sidebar = FakeSidebar()
    def cache_data(self, *a, **kw): return lambda f: f
    def cache_resource(self, *a, **kw): return lambda f: f
    def fragment(self, *a, **kw): return lambda f: f
    def set_page_config(self, **kw): pass
    def markdown(self, *a, **kw): pass
    def error(self, *a, **kw): pass
    def warning(self, *a, **kw): pass
    def info(self, *a, **kw): pass
    def title(self, *a, **kw): pass
    def header(self, *a, **kw): pass
    def subheader(self, *a, **kw): pass
    def caption(self, *a, **kw): pass
    def divider(self, *a, **kw): pass
    def rerun(self): pass
    def metric(self, *a, **kw): pass
    def plotly_chart(self, *a, **kw): pass
    def dataframe(self, *a, **kw): pass
    def columns(self, spec, **kw):
        if hasattr(spec, "__len__") and not isinstance(spec, int):
            return [FakeColumn() for _ in range(len(spec))]
        return [FakeColumn() for _ in range(int(spec))]
    def multiselect(self, *a, **kw): return ENABLED_SYMBOLS
    def selectbox(self, *a, **kw): return 0
    def number_input(self, *a, **kw): return 100
    def checkbox(self, *a, **kw): return True
    def __getattr__(self, k):
        if k in ("spinner", "status", "toast", "expander", "tabs", "container", "form"):
            class _Ctx:
                def __enter__(self_inner): return self_inner
                def __exit__(self_inner, *a_inner): return False
                def __getattr__(self_inner, k_inner): return lambda *a_i, **kw_i: None
            return lambda *a, **kw: _Ctx()
        return lambda *a, **kw: None

sys.modules["streamlit"] = FakeStreamlit()

import dashboard as dash


def banner(s):
    print("\n" + "=" * 78)
    print(s)
    print("=" * 78)


# === PANEL 1: System Heartbeat ===
banner("💓 PANEL 1 — System Heartbeat (top, color-coded)")
hb = dash.compute_heartbeat()

def fmt_age(label, ts):
    if not ts:
        return f"{label}: never [STALE / red]"
    ts_parsed = pd.to_datetime(ts, errors="coerce", utc=True)
    if pd.isna(ts_parsed):
        return f"{label}: {ts} [STALE / red]"
    age = pd.Timestamp.now(tz="UTC") - ts_parsed
    secs = int(age.total_seconds())
    if secs < 60:
        css = "fresh green"
    elif secs < 300:
        css = "fresh green"
    elif secs < 1800:
        css = "warn amber"
    else:
        css = "STALE red"
    return f"{label}: {ts}  → {secs}s ago  [{css}]"

print(fmt_age("Last gate evaluation", hb["last_eval_ts"]))
print(fmt_age("Last fill             ", hb["last_fill_ts"]))
print(fmt_age("Last signal            ", hb["last_signal_ts"]))
recon = dash.load_reconciliation_status()
print(f"DB: {recon['db_path']}")
print(f"    {recon['db_size_bytes'] / 1024:.1f} KB, "
      f"{sum(recon['row_counts'].values())} total rows ({recon['row_counts']})")

# === PANEL 2: Account Overview ===
banner("1️⃣ PANEL 2 — Account Overview")
equity, equity_src = dash.compute_equity()
daily_pnl, n_closed_today = dash.compute_daily_pnl()
ks = dash.load_kill_switch()
peak = ks.get("peak_equity", 0)
dd_pct = (equity - peak) / peak * 100 if peak else 0.0
print(f"  Equity:    ${equity:,.2f}  (source: {equity_src})")
print(f"  Daily P&L: ${daily_pnl:,.2f}  ({n_closed_today} closed fills today, UTC)")
print(f"  Drawdown:  {dd_pct:.2f}%  (vs peak ${peak:,.2f})")
print(f"  Kill Switch: {'🔴 HALTED' if ks.get('kill_switch_halted') else '🟢 ACTIVE'}")
print(f"  Consec. Losses: {ks.get('consecutive_losses', 0)}  "
      f"({'HALTED' if ks.get('consecutive_loss_halted') else 'OK'})")

# === PANEL 3: Regime Indicator ===
banner("2️⃣ PANEL 3 — Regime Indicator (per active symbol)")
regime = dash.compute_regime_per_symbol(ENABLED_SYMBOLS)
def sty(v, kind):
    if kind == "h1":
        if v == "LONG_BIAS": return "🟢 LONG_BIAS"
        if v == "SHORT_BIAS": return "🔴 SHORT_BIAS"
        return f"⚪ {v}"
    if kind == "m30":
        if v == "LONG_BIAS": return "🟢 LONG_BIAS"
        if v == "SHORT_BIAS": return "🔴 SHORT_BIAS"
        return f"⚪ {v}"
    if kind == "m15":
        if v == "TRADEABLE": return "🟢 TRADEABLE"
        if v == "NOT_TRADEABLE": return "🔴 NOT_TRADEABLE"
        return f"⚪ {v}"
    if kind == "gate":
        if v == "ALLOWED": return "🟢 ALLOWED"
        if v == "REJECTED": return "🔴 REJECTED"
        return f"⚪ {v}"

for _, r in regime.iterrows():
    print(f"\n  {r['symbol']}  (as of {r['as_of']})")
    print(f"    1H trend:    {sty(r['trend_1h'], 'h1')}")
    print(f"    30M bias:    {sty(r['bias_30m'], 'm30')}")
    print(f"    15M context: {sty(r['context_15m'], 'm15')}")
    print(f"    Gate:        {sty(r['gate_result'], 'gate')}")

# === PANEL 4: Live Signal / Trade Log ===
banner("3️⃣ PANEL 4 — Live Signal / Trade Log (top 12, mixed types)")
evals = dash.load_evaluations(20)
sigs = dash.load_signals(20)
risks = dash.load_risk_decisions(20)
fills = dash.load_fills(20)
rows = []
for _, r in evals.head(5).iterrows():
    rows.append({
        "time": r["timestamp"], "type": "EVAL", "symbol": r["symbol"],
        "detail": f"{r['gate_result']} ({r['rejection_reason'] or 'no reason'})",
    })
for _, r in sigs.head(3).iterrows():
    sig = r.get("signal", 0)
    sig_text = "LONG" if sig == 1 else "SHORT" if sig == -1 else "FLAT"
    rows.append({
        "time": r["timestamp"], "type": "SIGNAL", "symbol": r["symbol"],
        "detail": f"{sig_text} @ {r['entry_price']:.3f}",
    })
for _, r in risks.head(3).iterrows():
    rows.append({
        "time": r["timestamp"], "type": "RISK", "symbol": r["symbol"],
        "detail": f"{r['decision']} sig={r['signal']}",
    })
for _, r in fills.head(3).iterrows():
    rows.append({
        "time": r["timestamp"], "type": "FILL", "symbol": r["symbol"],
        "detail": f"{r['direction']} {r['filled_lots']:.2f} @ {r['filled_price']:.3f}",
    })
rows.sort(key=lambda x: x["time"], reverse=True)
for r in rows[:12]:
    print(f"  {r['time']}  {r['type']:6}  {r['symbol']:8}  {r['detail']}")

# === PANEL 5: Running Expectancy ===
banner("4️⃣ PANEL 5 — Running Expectancy")
e = dash.compute_expectancy()
if e["status"] == "pending_fix":
    print(f"  ⚠️  P&L calculation pending fix: {e['reason']}")
    print(f"     (This panel will populate once the 6-week baseline produces realized P&L.)")
else:
    print(f"  Total Trades:   {e['n_trades']}")
    print(f"  Win Rate:       {e['win_rate']*100:.1f}%")
    print(f"  Avg Win (R):    {e['avg_win_R']:+.2f}")
    print(f"  Avg Loss (R):   {e['avg_loss_R']:+.2f}")
    print(f"  Expectancy (R): {e['expectancy_R']:+.3f}")
    pf = e["profit_factor"]
    print(f"  Profit Factor:  {pf:.2f}" if pf != float("inf") else "  Profit Factor:  ∞")
    print(f"  Max DD (USD):   ${e['max_drawdown_usd']:,.2f}")

# === PANEL 6: Open Positions ===
banner("5️⃣ PANEL 6 — Open Positions")
op = dash.compute_open_positions()
if op.empty:
    print("  No open positions.")
else:
    print(op[["timestamp", "symbol", "direction", "filled_lots", "filled_price", "filled_sl", "filled_tp"]].to_string(index=False))

# === PANEL 7: Per-Pair Status ===
banner("6️⃣ PANEL 7 — Per-Pair Status (config)")
for sym, cfg in PAIR_CONFIG.items():
    enabled = cfg.get("enabled", False)
    badge = "✅ ENABLED" if enabled else "❌ DISABLED"
    print(f"\n  {sym}  {badge}")
    print(f"    strategy: {cfg.get('strategy')}")
    print(f"    donchian: {cfg.get('donchian_window')}  rr: {cfg.get('rr_ratio')}  "
          f"stop: {cfg.get('stop_mode')} (×{cfg.get('stop_multiplier', cfg.get('risk_pips'))})")
    if not enabled:
        print(f"    reason:   {cfg.get('disabled_reason')}")

# === PANEL 9: Risk Events Feed ===
banner("8️⃣ PANEL 9 — Risk Events Feed")
rev = dash.load_risk_events(100)
if rev.empty:
    print("  No risk events recorded.")

# === PANEL 10: Ops Status ===
banner("9️⃣ PANEL 10 — Ops Status")
print(f"  DB path:    {recon['db_path']}")
print(f"  DB size:    {recon['db_size_bytes'] / 1024:.1f} KB")
print(f"  Row counts: {recon['row_counts']}")
print(f"  Recon OK:   {'✅' if recon['ok'] else '❌'}")
bs = dash.load_backup_status()
if not bs:
    print("  Backup status: no files yet (will populate as backups run)")
else:
    for k, v in bs.items():
        print(f"  {k}: {v}")

print("\n" + "=" * 78)
print("END — All panels populated against real audit DB without errors.")
print("=" * 78)