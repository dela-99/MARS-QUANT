"""Test compute_expectancy_breakdown() against the current 5 fills.
Expected: 0 SL, 0 TP, 3 mobile, 1 web, 1 client (expert in old reason_map).
"""
import sys, os
sys.path.insert(0, r"C:\Users\RIDGE\MARS-QUANT")
os.chdir(r"C:\Users\RIDGE\MARS-QUANT")

# Use a permissive streamlit stub
import types
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
    def multiselect(self, *a, **kw): return ['XAUUSDm','EURUSDm','USDJPYm']
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
        if hasattr(spec, '__len__') and not isinstance(spec, int):
            return [FakeColumn() for _ in range(len(spec))]
        return [FakeColumn() for _ in range(int(spec))]
    def multiselect(self, *a, **kw): return ['XAUUSDm','EURUSDm','USDJPYm']
    def selectbox(self, *a, **kw): return 0
    def number_input(self, *a, **kw): return 100
    def checkbox(self, *a, **kw): return True
    def __getattr__(self, k):
        if k in ('spinner','status','toast','expander','tabs','container','form'):
            class _Ctx:
                def __enter__(self_inner): return self_inner
                def __exit__(self_inner, *a_inner): return False
                def __getattr__(self_inner, k_inner): return lambda *a_i, **kw_i: None
            return lambda *a, **kw: _Ctx()
        return lambda *a, **kw: None

sys.modules['streamlit'] = FakeStreamlit()

import importlib, dashboard as dash
importlib.reload(dash)

print("=" * 70)
print("EXIT-REASON BREAKDOWN TEST")
print("=" * 70)
bd = dash.compute_expectancy_breakdown()
print(f"Source: {bd['source']}")
print()

def show(label, m):
    print(f"--- {label} ---")
    if m.get("is_empty", True) or m.get("n_trades", 0) == 0:
        print(f"  (empty — {m.get('n_trades', 0)} trades)")
        return
    print(f"  Trades:        {m['n_trades']}")
    print(f"  Win rate:      {m['win_rate']*100:.1f}%")
    print(f"  Avg win (R):   {m['avg_win_R']:+.2f}")
    print(f"  Avg loss (R):  {m['avg_loss_R']:+.2f}")
    print(f"  Expectancy:    {m['expectancy_R']:+.3f}R")
    pf = m['profit_factor']
    print(f"  Profit factor: {pf:.2f}" if pf != float('inf') else "  Profit factor: inf")
    print(f"  Gross profit:  ${m['gross_profit_usd']:,.2f}")
    print(f"  Gross loss:    ${m['gross_loss_usd']:,.2f}")
    print(f"  Max DD:        ${m['max_drawdown_usd']:,.2f}")
    bd = m.get("breakdown")
    if bd:
        print(f"  Breakdown:     {bd}")

show("ALL CLOSED TRADES", bd["all"])
print()
show("SYSTEM EXITS (SL/TP only)", bd["system"])
print()
show("MANUAL CLOSES (mobile/web/client/expert/unknown)", bd["manual"])
print()

print("=" * 70)
print("VERIFICATION AGAINST EXPECTED")
print("=" * 70)
all_bd = bd["all"]["breakdown"]
print(f"  Expected from DB: 0 SL, 0 TP, 3 mobile, 1 web, 1 client")
print(f"  Got:              {all_bd.get('sl_hit', 0)} SL, {all_bd.get('tp_hit', 0)} TP, "
      f"{all_bd.get('mobile', 0)} mobile, {all_bd.get('web', 0)} web, "
      f"{all_bd.get('client', 0)} client, {all_bd.get('expert', 0)} expert, "
      f"{all_bd.get('unknown', 0)} unknown, total={all_bd.get('total', 0)}")
assert all_bd.get("sl_hit", 0) == 0, "expected 0 SL exits"
assert all_bd.get("tp_hit", 0) == 0, "expected 0 TP exits"
assert all_bd.get("mobile", 0) == 3, "expected 3 mobile exits"
assert all_bd.get("web", 0) == 1, "expected 1 web exit"
assert all_bd.get("client", 0) == 1, "expected 1 client exit"
assert bd["system"]["is_empty"] is True, "system group must be empty (no SL/TP exits yet)"
assert bd["manual"]["n_trades"] == 5, "manual group must have 5 trades"
assert bd["all"]["n_trades"] == 5, "all group must have 5 trades"
print("\n  All assertions passed. 0 system exits + 5 manual closes as expected.")