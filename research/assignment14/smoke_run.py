"""Assignment 14 — smoke run of the XAU-MTF-DONCHIAN-001 engine.

Verifies the pipeline end to end on a short slice before the full research run.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mars.apps.backtester.mtf_donchian_backtest import (  # noqa: E402
    CostModel,
    ExecutionModel,
    MtfDonchianBacktester,
)
from mars.libs.risk.contract_aware import ContractAwareFixedFractionalRisk, InstrumentSpec  # noqa: E402
from mars.libs.strategies.xau_mtf_donchian import MtfDonchianParams, compute_signals  # noqa: E402

M5 = ROOT / "data/processed/xauusdm/m5/v1.2.0/data.parquet"
H1 = ROOT / "data/processed/xauusdm/h1/v1.2.0/data.parquet"


def main() -> None:
    m5 = pd.read_parquet(M5)
    h1 = pd.read_parquet(H1)
    m5 = m5.reset_index()
    h1 = h1.reset_index()
    print(f"M5 {len(m5):,} rows  {m5['timestamp'].iloc[0]} -> {m5['timestamp'].iloc[-1]}")
    print(f"H1 {len(h1):,} rows  {h1['timestamp'].iloc[0]} -> {h1['timestamp'].iloc[-1]}")

    params = MtfDonchianParams()
    t0 = time.time()
    sig = compute_signals(m5, h1, params).frame
    print(f"\nsignal computation: {time.time() - t0:.2f}s")
    print(f"  donchian_high NaN: {sig['donchian_high'].isna().sum()}")
    print(f"  atr NaN: {sig['atr'].isna().sum()}")
    print(f"  h1_regime unavailable rows: {sig['h1_regime'].isna().sum()}")
    print(f"  regime counts: {sig['h1_regime'].value_counts().to_dict()}")
    print(f"  entry_long: {int(sig['entry_long'].sum())}   entry_short: {int(sig['entry_short'].sum())}")
    print(f"  exit_long: {int(sig['exit_long'].sum())}   exit_short: {int(sig['exit_short'].sum())}")

    # Look-ahead probe: the H1 bar used must always be completed before the M5 bar.
    h1_comp = pd.DatetimeIndex(sig["h1_completion"].dropna())
    m5_comp = pd.DatetimeIndex(sig["timestamp"]) + pd.Timedelta(minutes=5)
    valid = sig["h1_completion"].notna()
    worst = (h1_comp - m5_comp[valid]).max()
    print(f"\n  max (h1_completion - m5_completion) = {worst}  (must be <= 0)")

    # Backtest on a 3-month slice for speed.
    slice_end = pd.Timestamp("2022-03-01", tz="UTC")
    m5s = m5[m5["timestamp"] < slice_end].reset_index(drop=True)
    h1s = h1[h1["timestamp"] < slice_end].reset_index(drop=True)
    spec = InstrumentSpec(symbol="XAUUSDm", contract_size=100.0, pip_size=0.01, point_size=0.001)
    policy = ContractAwareFixedFractionalRisk(spec=spec, risk_fraction=params.risk_fraction)
    bt = MtfDonchianBacktester(
        params, spec=spec, cost_model=CostModel(),
        execution_model=ExecutionModel(), risk_policy=policy,
    )
    t0 = time.time()
    res = bt.run(m5s, h1s)
    print(f"\nbacktest: {time.time() - t0:.2f}s for {len(m5s):,} bars")
    tf = res.trades_frame()
    print(f"  trades={len(tf)}  bars_in_market={res.bars_in_market}")
    if len(tf):
        print(tf[["side", "entry_time", "entry_price", "exit_time", "exit_price",
                   "lots", "net_pnl", "exit_reason", "holding_bars", "r_multiple"]].head(12).to_string(index=False))
        print(f"  net P&L = {tf['net_pnl'].sum():.2f}  final equity = {res.final_equity:.2f}")
        print(f"  exit reasons: {tf['exit_reason'].value_counts().to_dict()}")
        print(f"  sides: {tf['side'].value_counts().to_dict()}")
    print(f"  rejected signals: {len(res.rejected_signals)}")
    for r in res.rejected_signals[:5]:
        print(f"    {r['time']} {r['side']}: {r['reason']}")


if __name__ == "__main__":
    main()
