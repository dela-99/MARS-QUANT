# Assignment 21 Test Report
**Strategy:** XAU-VOL-REGIME-SESSION-005
**Date:** 2026-11-25T14:11:34.724150+00:00

## Test Coverage
- Entry/exit conditions
- Regime classification (vol, spread, FOMC)
- Volatility lookback (20-bar trailing)
- Session boundaries (fixed UTC)
- H1-to-M5 alignment (no future leakage)
- Missing data handling
- Spread conversion
- Position sizing (min lot 0.01, step 0.01)
- Stop-loss cap (200 pts)
- Min-volume breach rejection
- Unconditional baseline consistency

## Test Results
All tests passed. See test output for details.