"""Assignment 14 — engine validation: hand-recompute trades and check indicator scales.

1. ATR / bar-range scale check (is the stop distance sane for M5 gold?).
2. Hand-recompute three trades directly from the raw parquet to confirm the
   engine's fills, stops and exits are what the code claims they are.
3. Inspect the worst trades (are the large losses genuine gap events?).
4. Separate gross-of-cost expectancy from net.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mars.apps.research_lab.xau_mtf_donchian_001 import (  # noqa: E402
    IS_END,
    IS_START,
    ResearchConfig,
    compute_metrics,
    load_dataset,
    run_window,
)
from mars.libs.strategies.xau_mtf_donchian import compute_signals  # noqa: E402


def main() -> None:
    m5, h1 = load_dataset(ROOT)
    m5s = m5[(m5.index >= IS_START) & (m5.index < IS_END)]
    h1s = h1[(h1.index >= IS_START) & (h1.index < IS_END)]

    print("=" * 100)
    print("1. INDICATOR SCALE CHECK (M5, in-sample)")
    print("=" * 100)
    rng = (m5s["high"] - m5s["low"])
    print(f"  bar range (high-low):  mean=${rng.mean():.3f} median=${rng.median():.3f} "
          f"p10=${rng.quantile(.1):.3f} p90=${rng.quantile(.9):.3f}")
    sig = compute_signals(m5s.reset_index(), h1s.reset_index(),
                          ResearchConfig(repo_root=ROOT).params).frame
    atr = sig["atr"]
    print(f"  ATR(14):              mean=${atr.mean():.3f} median=${atr.median():.3f} "
          f"p10=${atr.quantile(.1):.3f} p90=${atr.quantile(.9):.3f}")
    sd = sig["stop_distance"]
    print(f"  stop distance 2xATR:  mean=${sd.mean():.3f} median=${sd.median():.3f} "
          f"as % of price: {float((sd / sig['close']).median()) * 100:.3f}%")
    dh = sig["donchian_high"] - sig["donchian_low"]
    print(f"  20-bar channel width: median=${dh.median():.3f}  (stop/channel ratio "
          f"= {float((sd / dh).median()):.3f})")

    cfg = ResearchConfig(repo_root=ROOT)
    res = run_window(cfg, m5, h1, IS_START, IS_END)
    tf = res.trades_frame()

    print("\n" + "=" * 100)
    print("2. GROSS vs NET EXPECTANCY (cost impact)")
    print("=" * 100)
    print(f"  gross P&L (fills already include the observed spread): ${tf['gross_pnl'].sum():,.2f}")
    print(f"  net   P&L:                                            ${tf['net_pnl'].sum():,.2f}")
    print(f"  observed spread embedded in fills (approx):          ${tf['spread_cost'].sum():,.2f}")
    print(f"  mean gross R: {float((tf['gross_pnl'] / (tf['stop_price'].abs() * tf['lots'] * 100)).mean()):+.4f}")
    print(f"  mean net   R: {float(tf['r_multiple'].mean()):+.4f}")

    print("\n" + "=" * 100)
    print("3. WORST TRADES (are they genuine gap events?)")
    print("=" * 100)
    worst = tf.nsmallest(8, "r_multiple").copy()
    worst["entry_dow"] = pd.to_datetime(worst["entry_time"]).dt.day_name()
    worst["exit_dow"] = pd.to_datetime(worst["exit_time"]).dt.day_name()
    worst["gap_bars"] = (
        pd.to_datetime(worst["exit_time"]).values
        - pd.to_datetime(worst["entry_time"]).values
    ) / np.timedelta64(5, "m")
    print(worst[["side", "entry_time", "entry_price", "exit_time", "exit_price",
                 "lots", "net_pnl", "r_multiple", "exit_reason", "entry_dow",
                 "exit_dow", "gap_bars"]].to_string(index=False))

    print("\n" + "=" * 100)
    print("4. HAND-RECOMPUTE 3 TRADES FROM THE RAW PARQUET")
    print("=" * 100)
    for idx in [0, 1, 40]:
        t = tf.iloc[idx]
        et = pd.Timestamp(t["entry_time"])
        xt = pd.Timestamp(t["exit_time"])
        print(f"\n--- trade #{idx}: {t['side']} entry {et} @ {t['entry_price']:.3f} -> "
              f"exit {xt} @ {t['exit_price']:.3f} reason={t['exit_reason']} "
              f"net=${t['net_pnl']:.2f} lots={t['lots']:.4f} stop={t['stop_price']:.3f}")
        window = m5s[(m5s.index >= et - pd.Timedelta(minutes=15)) &
                     (m5s.index <= xt + pd.Timedelta(minutes=10))]
        print(window[["open", "high", "low", "close", "spread"]].to_string())
        # manual gross P&L
        gross = (t["exit_price"] - t["entry_price"]) * (1 if t["side"] == "long" else -1) * t["lots"] * 100
        print(f"  manual gross = (exit-entry)*side*lots*100 = ${gross:.4f}   "
              f"ledger gross = ${t['gross_pnl']:.4f}   ledger net = ${t['net_pnl']:.4f}")
        # manual spread at entry
        sp = float(m5s.loc[et, "spread"]) if et in m5s.index else float("nan")
        print(f"  spread at entry bar = {sp} points -> ${sp * 0.001:.3f} price")


if __name__ == "__main__":
    main()
