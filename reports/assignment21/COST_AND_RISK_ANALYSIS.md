# Cost and Risk Analysis
**Strategy:** XAU-VOL-REGIME-SESSION-005
**Date:** 2026-11-25T14:11:34.724150+00:00

## Transaction Cost Model (Verified Assignment 17/20)
- Spread: Per-bar observed (points), 1× RT
- Commission: $0.00/lot RT (Exness Standard)
- Slippage: 0 points (base)
- Swap: $0.00 (intraday)
- Zero-spread bars: Substitute median (200 pts)
- Sensitivity multipliers: 1.0×, 1.5×, 2.0×

## Cost Breakdown (Model B - Regime-Filtered)
- Total Spread Cost: $4990.18
- Total Commission: $0.00
- Total Swap: $0.00
- Total Costs: $4990.18
- Avg Spread Cost/Trade: $14.94
- Cost as % of Gross P&L: 100.0%

## $30 Account Feasibility (Verified Assignment 20)
- Starting Equity: $30.00
- Risk Fraction: 1% ($0.30 budget)
- Min Lot: 0.01
- SL Cap: 200 pts → $0.20 risk at min lot
- Risk at Min Volume: $0.20 ≤ $0.30 ✅ FEASIBLE
- Max SL Before Breach: 300 pts
- Min-Volume Breach Action: REJECT (never force)

## Risk Metrics (at $10k normalized IS equity)
- Max DD: -99.80% ($-9980.38)
- Exposure: 0.16%
- Avg Leverage: 72.89x
- Rejected Signals: 124