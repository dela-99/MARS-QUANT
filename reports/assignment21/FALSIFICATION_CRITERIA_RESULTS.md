# Falsification Criteria Results (Phase K)
**Strategy:** XAU-VOL-REGIME-SESSION-005
**Date:** 2026-11-25T14:11:34.724150+00:00

## Pre-Registered Criteria (All 8 Must Pass for Phase K Advancement)

### fc_005_1_expectancy_positive
- **Status:** ❌ FAIL
- **threshold:** > $0.0
- **observed:** $-29.88

### fc_005_2_interaction
- **Status:** ❌ FAIL
- **threshold:** β_3 > 0, p < 0.05 (one-sided)
- **observed:** β_3 = -21.7912, p = 1.0000

### fc_005_3_oos_expectancy
- **Status:** ⏳ NOT RUN
- **threshold:** > $0.0
- **observed:** NOT_RUN_IN_ASSIGNMENT_21
- **note:** OOS validation requires separate Assignment 22+ authorization

### fc_005_4_cost_sensitivity
- **Status:** ⏳ NOT RUN
- **threshold_1x:** > $0.0 at 1.0×
- **observed_1x:** $-29.88
- **pass_1x:** False
- **threshold_1_5x:** > $0.0 at 1.5×
- **observed_1_5x:** $-45.36
- **pass_1_5x:** False

### min_trades_is
- **Status:** ✅ PASS
- **threshold:** ≥ 50
- **observed:** 334

### min_trades_oos
- **Status:** ⏳ NOT RUN
- **threshold:** ≥ 20
- **observed:** NOT_RUN_IN_ASSIGNMENT_21
- **note:** OOS validation requires separate Assignment 22+ authorization

### max_dd_is
- **Status:** ❌ FAIL
- **threshold:** < 30% ($29.94 at $30 equity)
- **observed:** -99.80% ($29.94 at $30 equity)

### min_expectancy_is
- **Status:** ❌ FAIL
- **threshold:** > $0.05/trade
- **observed:** $-29.88/trade

## Overall Verdict: REJECTED — NO DEFENSIBLE EDGE

## Decision Rules
- All 8 criteria must PASS for candidate to advance to OOS (Phase H)
- Any FAIL → REJECTED — NO DEFENSIBLE EDGE
- INDETERMINATE → INCONCLUSIVE — ADDITIONAL IS EVIDENCE REQUIRED
- Criteria not run in Assignment 21 (OOS) marked as NOT RUN