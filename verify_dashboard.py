"""
Programmatically exercise every dashboard data path against the real audit DB.
This is equivalent to what Streamlit does on its first run. If anything
errors with 'closed database' or similar, this catches it BEFORE the user
sees it in the browser.
"""
import sys, os, types
sys.path.insert(0, r"C:\Users\RIDGE\MARS-QUANT")
os.chdir(r"C:\Users\RIDGE\MARS-QUANT")

import sqlite3, tempfile, json
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Pre-load pair config (must succeed before st.* swap)
from mars.apps.trading.system.pair_config import PAIR_CONFIG, get_enabled_symbols
ENABLED_SYMBOLS = get_enabled_symbols()
print(f"[OK] pair_config loaded — enabled: {ENABLED_SYMBOLS}")


# Build a permissive fake streamlit module
class FakeColumn:
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def __getattr__(self, k):
        return lambda *a, **kw: None


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
    # Decorators: identity
    def cache_data(self, *a, **kw): return lambda f: f
    def cache_resource(self, *a, **kw): return lambda f: f
    def fragment(self, *a, **kw): return lambda f: f
    # Functions
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

    # Permissive catch-all for any unmocked method (incl. context managers)
    def __getattr__(self, k):
        # Context-manager-like methods
        if k in ("spinner", "status", "toast", "expander", "tabs", "container", "form"):
            class _Ctx:
                def __enter__(self_inner): return self_inner
                def __exit__(self_inner, *a_inner): return False
                def __getattr__(self_inner, k_inner): return lambda *a_i, **kw_i: None
            def _factory(*a, **kw): return _Ctx()
            return _factory
        return lambda *a, **kw: None


sys.modules["streamlit"] = FakeStreamlit()

# Now import dashboard
import importlib
import dashboard as dash
importlib.reload(dash)
print("[OK] dashboard.py imported")

print("\n=== Loading tables (each opens its own connection) ===")
for fn_name in [
    "load_table",
    "load_evaluations",
    "load_signals",
    "load_risk_decisions",
    "load_fills",
    "load_risk_events",
    "load_kill_switch",
    "load_backup_status",
    "load_reconciliation_status",
    "compute_equity",
    "compute_daily_pnl",
    "compute_expectancy",
    "compute_open_positions",
    "compute_heartbeat",
    "compute_regime_per_symbol",
]:
    fn = getattr(dash, fn_name)
    try:
        if fn_name == "compute_regime_per_symbol":
            result = fn(ENABLED_SYMBOLS)
        elif fn_name == "load_table":
            result = fn("evaluations", 50)
        else:
            result = fn()
        if isinstance(result, tuple):
            print(f"  [OK] {fn_name} -> tuple(len={len(result)}): {result}")
        elif isinstance(result, pd.DataFrame):
            print(f"  [OK] {fn_name} -> DataFrame({len(result)} rows, {len(result.columns)} cols)")
        elif isinstance(result, dict):
            keys = list(result.keys())[:6]
            print(f"  [OK] {fn_name} -> dict({len(result)} keys, sample: {keys})")
        else:
            print(f"  [OK] {fn_name} -> {type(result).__name__}: {repr(result)[:100]}")
    except Exception as e:
        print(f"  [FAIL] {fn_name}: {type(e).__name__}: {e}")
        raise

print("\n=== Multi-call stress (5 reruns × 5 loaders = 25 calls) ===")
for i in range(5):
    for fn_name in ["load_table", "load_evaluations", "load_fills", "load_signals", "load_risk_decisions"]:
        fn = getattr(dash, fn_name)
        try:
            if fn_name == "load_table":
                fn("evaluations", 50)
            else:
                fn()
        except Exception as e:
            print(f"  [FAIL iter {i}] {fn_name}: {e}")
            raise
print("[OK] 25 calls; zero 'closed database' errors")

print("\n=== Values dashboard will show (against real DB) ===")
print(f"  equity, src: {dash.compute_equity()}")
print(f"  daily_pnl, n_closed_today: {dash.compute_daily_pnl()}")
print(f"  expectancy: {dash.compute_expectancy()}")
print(f"  open_pos_df rows: {len(dash.compute_open_positions())}")
hb = dash.compute_heartbeat()
print(f"  heartbeat: {hb}")
print(f"  regime_df:")
print(dash.compute_regime_per_symbol(ENABLED_SYMBOLS).to_string(index=False))
recon = dash.load_reconciliation_status()
print(f"  reconciliation: {recon}")

print("\n=== Signal/Trade Log preview ===")
evals = dash.load_evaluations(20)
sigs = dash.load_signals(20)
risks = dash.load_risk_decisions(20)
fills = dash.load_fills(20)
print(f"  evals: {len(evals)}, sigs: {len(sigs)}, risks: {len(risks)}, fills: {len(fills)}")
print(evals[["timestamp","symbol","gate_result","trend_1h","bias_30m","context_15m"]].head(5).to_string(index=False))