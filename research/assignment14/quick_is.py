"""Assignment 14 — Phase E quick look: in-sample baseline diagnostics.

Runs the frozen baseline parameters over the in-sample window and prints the
full metric block so the result can be sanity-checked before the research run.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mars.apps.research_lab.xau_mtf_donchian_001 import (  # noqa: E402
    IS_END,
    IS_START,
    ResearchConfig,
    compute_metrics,
    exit_reason_breakdown,
    load_dataset,
    run_window,
    session_breakdown,
    yearly_breakdown,
)


def main() -> None:
    m5, h1 = load_dataset(ROOT)
    print(f"M5 {len(m5):,} rows {m5.index[0]} -> {m5.index[-1]}")
    print(f"H1 {len(h1):,} rows {h1.index[0]} -> {h1.index[-1]}")

    cfg = ResearchConfig(repo_root=ROOT)
    t0 = time.time()
    res = run_window(cfg, m5, h1, IS_START, IS_END)
    print(f"\nIS backtest {time.time() - t0:.1f}s")

    m = compute_metrics(res)
    for k, v in m.items():
        if k != "conventions":
            print(f"  {k}: {v}")

    tf = res.trades_frame()
    print("\n--- r_multiple distribution ---")
    print(tf["r_multiple"].describe().to_string())
    print("\n--- exit reasons ---")
    print(exit_reason_breakdown(res).to_string())
    print("\n--- yearly ---")
    print(yearly_breakdown(res).to_string())
    print("\n--- session ---")
    print(session_breakdown(res).to_string())
    print("\n--- first 10 trades ---")
    print(tf[["side", "entry_time", "entry_price", "exit_time", "exit_price",
               "lots", "net_pnl", "exit_reason", "r_multiple"]].head(10).to_string(index=False))


if __name__ == "__main__":
    main()
