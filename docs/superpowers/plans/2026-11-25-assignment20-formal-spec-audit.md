# Assignment 20: Phase F Formal Specification Audit and Pre-Backtest Feasibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete Assignment 20 by producing 8 formal research deliverables that audit the frozen specifications from Assignment 19, verify pre-backtest feasibility for the two advancing candidates (XAU-VOL-REGIME-SESSION-005 Primary, XAU-ASIAN-VOL-BREAKOUT-007 Secondary), and produce the final decision report.

**Architecture:** Research/documentation-only task. No code implementation, optimization, backtesting, Monte Carlo, MT5 connection, or live trading. All work is analysis of frozen specifications from Assignment 19, verified instrument specs, data catalog, and Assignment 17 audit evidence.

**Tech Stack:** Markdown documentation, JSON output, verified data from `configs/instrument_spec_xauusdm.yaml`, `data/catalog.yaml`, Assignment 17 audit, and Assignment 19 deliverables.

## Global Constraints

- Research-only assignment: NO implementation, optimization, backtesting, Monte Carlo, MT5 connection, or live trading
- Must verify frozen specifications from Assignment 19 WITHOUT modification
- Mandatory: FC-007-2 hard gate (spread-vol correlation ≤ 0.3) for Candidate 007 before any backtest
- Mandatory comparison design for Candidate 005: unconditional baseline vs regime-filtered vs null
- Maximum 2 candidates (already selected in Assignment 19)
- Preserve original Programme 01 and Programme 02 documents
- Use actual instrument spec (`configs/instrument_spec_xauusdm.yaml`), data catalog, and verified cost model (Exness Standard: median 200 pts = 20 pips = $0.20/0.01 lot RT)
- $30 account feasibility: min lot 0.01, risk budget $0.30, max SL 300 pts, min-volume breach → REJECT
- All quantitative statements must be sourced (fact/assumption/estimate classification)
- Output directory: `reports/assignment20/` (already created)

---

### Task 1: Create Deliverable 1 - ASSIGNMENT_20_FORMAL_SPECIFICATION_AUDIT.md

**Files:**
- Create: `reports/assignment20/ASSIGNMENT_20_FORMAL_SPECIFICATION_AUDIT.md`

**Content Requirements:**
- Audit both candidate specifications against Assignment 19 Research Specification Brief
- Verify all parameters are frozen (no optimization permitted)
- Cross-check instrument specs, data versions, session definitions, cost model
- Verify research periods (burn-in, IS, OOS, reserve) are chronologically non-overlapping
- Confirm falsification criteria are pre-registered and match Gate E
- Document any discrepancies or clarifications needed

**Interfaces:**
- Consumes: Assignment 19 Research Specification Brief, Instrument Spec, Data Catalog
- Produces: Formal audit report confirming spec integrity

- [ ] Step 1.1: Write the formal specification audit document
- [ ] Step 1.2: Verify all frozen parameters against source documents
- [ ] Step 1.3: Cross-check research periods and session definitions
- [ ] Step 1.4: Validate falsification criteria alignment with Gate E
- [ ] Step 1.5: Save to `reports/assignment20/ASSIGNMENT_20_FORMAL_SPECIFICATION_AUDIT.md`

---

### Task 2: Create Deliverable 2 - CANDIDATE_005_REGIME_VALIDATION_DESIGN.md

**Files:**
- Create: `reports/assignment20/CANDIDATE_005_REGIME_VALIDATION_DESIGN.md`

**Content Requirements:**
- Design the mandatory comparison: unconditional baseline vs regime-filtered vs null
- Define the unconditional baseline (XAU-SESSION-MOM-001 equivalent: Asian session return > 0 → long Europe)
- Define the regime-filtered version (adds vol ≤ 40th pctl, spread ≤ 40th pctl, no FOMC)
- Define the null comparison (randomized regime labels or permutation test)
- Specify statistical tests for regime interaction (FC-005-2: coef > 0, p < 0.05 one-sided)
- Define sensitivity analyses per spec (spread multiplier, threshold stability, FOMC filter, SL distance, DST)
- Pre-register the comparison methodology before any research execution

**Interfaces:**
- Consumes: Candidate 005 spec from Research Brief, Assignment 17 audit (unconditional baseline evidence)
- Produces: Pre-registered comparison design document

- [ ] Step 2.1: Define unconditional baseline specification (recreate 001 logic)
- [ ] Step 2.2: Define regime-filtered specification (005 logic)
- [ ] Step 2.3: Define null comparison methodology
- [ ] Step 2.4: Specify statistical tests and decision rules
- [ ] Step 2.5: Document all 6 sensitivity analyses
- [ ] Step 2.6: Save to `reports/assignment20/CANDIDATE_005_REGIME_VALIDATION_DESIGN.md`

---

### Task 3: Create Deliverable 3 - CANDIDATE_007_FC007_2_SPREAD_VOL_ANALYSIS.md

**Files:**
- Create: `reports/assignment20/CANDIDATE_007_FC007_2_SPREAD_VOL_ANALYSIS.md`

**Content Requirements:**
- Detailed analysis plan for FC-007-2 (spread-vol correlation at 08:00 UTC)
- Define correlation calculation: Pearson correlation between Asian session realized vol (H1, 20-bar lookback) and spread at 08:00 UTC (first M5 bar of Europe session)
- Define population: All sessions in IS period (2021-10-16 to 2024-12-31)
- Define pass/fail/indeterminate thresholds: PASS ≤ 0.3, FAIL > 0.5, INDETERMINATE 0.3-0.5
- Specify this is a HARD GATE — if FAIL, strategy terminates before full backtest
- Document data requirements: M5 spread at 08:00, H1 Asian session realized volatility
- Note: This is a DIAGNOSTIC PLAN only — no actual computation in Assignment 20

**Interfaces:**
- Consumes: Candidate 007 spec, data catalog (M5 v1.2.0, H1 v1.2.0), instrument spec
- Produces: Pre-registered spread-vol correlation analysis plan

- [ ] Step 3.1: Define correlation computation methodology
- [ ] Step 3.2: Specify data extraction logic (M5 08:00 spread, H1 Asian vol)
- [ ] Step 3.3: Document pass/fail thresholds and decision rule
- [ ] Step 3.4: Specify sample size requirements (IS period sessions)
- [ ] Step 3.5: Document as hard gate with termination consequence
- [ ] Step 3.6: Save to `reports/assignment20/CANDIDATE_007_FC007_2_SPREAD_VOL_ANALYSIS.md`

---

### Task 4: Create Deliverable 4 - TRANSACTION_COST_AND_EXECUTION_AUDIT.md

**Files:**
- Create: `reports/assignment20/TRANSACTION_COST_AND_EXECUTION_AUDIT.md`

**Content Requirements:**
- Verify cost model from Assignment 17 audit: per-bar observed spread, 1× RT, $0 commission, 0 slippage base, swap $0 intraday
- Cross-check against instrument spec: spread median 200 pts, typical_pips 20.0
- Document spread distribution statistics (mean, median, std, min, max, zero-spread handling)
- Verify backtester cost application logic: entry at open+spread, exit at open, 1× spread per RT
- Document sensitivity multipliers: 1.0×, 1.5×, 2.0× for both candidates
- Verify no double-counting of spread
- Document execution parameters: entry 08:00 UTC, exit 14:30 UTC, time-stop mandatory
- Verify SL logic: session low or 200pts (005), Asia extreme capped at 200pts (007)

**Interfaces:**
- Consumes: Assignment 17 Audit (Section B), Instrument Spec, Research Specification Brief
- Produces: Verified transaction cost and execution audit

- [ ] Step 4.1: Document verified cost model from Assignment 17
- [ ] Step 4.2: Cross-check instrument spec spread statistics
- [ ] Step 4.3: Verify backtester cost application logic
- [ ] Step 4.4: Document sensitivity multiplier design
- [ ] Step 4.5: Verify execution parameters and SL logic for both candidates
- [ ] Step 4.6: Save to `reports/assignment20/TRANSACTION_COST_AND_EXECUTION_AUDIT.md`

---

### Task 5: Create Deliverable 5 - ACCOUNT_SCALE_VERIFICATION.md

**Files:**
- Create: `reports/assignment20/ACCOUNT_SCALE_VERIFICATION.md`

**Content Requirements:**
- Verify $30 account feasibility using instrument spec (contract_size=100, pip_size=0.01, point_size=0.001, min_lot=0.01)
- Recompute risk math: equity=$30, risk_fraction=1%, risk_budget=$0.30
- For Candidate 005: SL=200pts → risk_per_lot=$20 → lots_exact=0.015 → lots_floored=0.01 → risk_at_min=$0.20 ≤ $0.30 ✅
- For Candidate 007: SL capped at 200pts (Asia extreme if tighter, else 200, never >300) → same math ✅
- Document max SL before min-volume breach: 300 pts at $30 equity
- Verify margin requirements at 1:200 leverage: margin=$13.25, free=$16.75
- Document spread/commission impact at min volume: $0.20 RT = risk at min volume
- Separate normalized strategy performance ($10k research) from account-specific executable performance ($30 live)
- Explicit conclusion: Is XAUUSDm trading technically feasible with $30? Yes for both candidates at SL≤300pts.

**Interfaces:**
- Consumes: Instrument Spec (feasibility section), Assignment 17 Audit (Section E), Research Specification Brief
- Produces: $30 account-scale verification for both candidates

- [ ] Step 5.1: Recompute feasibility math for both candidates
- [ ] Step 5.2: Document max SL before breach (300 pts)
- [ ] Step 5.3: Verify margin at 1:200 leverage
- [ ] Step 5.4: Separate normalized vs account-specific performance
- [ ] Step 5.5: State explicit feasibility conclusion
- [ ] Step 5.6: Save to `reports/assignment20/ACCOUNT_SCALE_VERIFICATION.md`

---

### Task 6: Create Deliverable 6 - IS_OOS_CONTROL_VERIFICATION.md

**Files:**
- Create: `reports/assignment20/IS_OOS_CONTROL_VERIFICATION.md`

**Content Requirements:**
- Verify research periods are chronologically non-overlapping for both candidates
- Candidate 005: Burn-in 2021-07-16 to 2021-09-30, IS 2021-10-01 to 2024-12-31, OOS 2025-01-01 to 2025-10-09
- Candidate 007: Burn-in 2021-07-16 to 2021-10-15, IS 2021-10-16 to 2024-12-31, OOS 2025-01-01 to 2025-10-09
- Confirm no data leakage: thresholds frozen from IS, applied to OOS without re-optimization
- Verify minimum trade counts: 005 IS≥50, OOS≥20; 007 IS≥40/direction, OOS≥15/direction
- Document that H1 data is resampled from M5 v1.2.0 (no raw H1 contamination)
- Confirm frozen parameters: no optimization permitted post-freeze
- Reference Assignment 17 lesson: unauthorized OOS/MC must not be cited as formal validation

**Interfaces:**
- Consumes: Research Specification Brief (periods), Data Catalog (v1.2.0 lineage), Assignment 17 Audit (lessons)
- Produces: IS/OOS control verification report

- [ ] Step 6.1: Verify chronological non-overlap for both candidates
- [ ] Step 6.2: Confirm threshold freezing protocol
- [ ] Step 6.3: Verify minimum trade count requirements
- [ ] Step 6.4: Confirm H1 resampled from M5 v1.2.0
- [ ] Step 6.5: Document no-optimization rule and Assignment 17 lessons
- [ ] Step 6.6: Save to `reports/assignment20/IS_OOS_CONTROL_VERIFICATION.md`

---

### Task 7: Create Deliverable 7 - ASSIGNMENT_20_DECISION_REPORT.md

**Files:**
- Create: `reports/assignment20/ASSIGNMENT_20_DECISION_REPORT.md`

**Content Requirements:**
- Synthesize findings from all 6 prior deliverables
- State go/no-go for each candidate to proceed to Phase G (In-Sample Research)
- Candidate 005: Ready for Phase G if spec audit clean, validation design complete, costs verified, account feasible, IS/OOS controlled
- Candidate 007: CONDITIONAL — Ready for Phase G ONLY if FC-007-2 diagnostic (spread-vol correlation) passes when executed in Phase G; hard gate documented
- Document any open risks or clarifications needed
- Reference Programme 02 constraints: max 2 candidates, no revival of rejected, learn from rejections
- Final authorization statement for Phase G commencement

**Interfaces:**
- Consumes: All 6 prior deliverables
- Produces: Final decision report authorizing (or not) Phase G research

- [ ] Step 7.1: Synthesize findings from deliverables 1-6
- [ ] Step 7.2: State go/no-go for Candidate 005
- [ ] Step 7.3: State conditional go/no-go for Candidate 007 (FC-007-2 hard gate)
- [ ] Step 7.4: Document open risks
- [ ] Step 7.5: Reference Programme 02 constraints compliance
- [ ] Step 7.6: Save to `reports/assignment20/ASSIGNMENT_20_DECISION_REPORT.md`

---

### Task 8: Create Deliverable 8 - assignment20_results.json

**Files:**
- Create: `reports/assignment20/assignment20_results.json`

**Content Requirements:**
- Machine-readable summary of all Assignment 20 findings
- Structure: specification_audit, candidate_005_validation_design, candidate_007_fc007_2_plan, transaction_cost_audit, account_scale_verification, is_oos_control, decision_report
- Include key metrics, pass/fail statuses, frozen parameters, research periods
- Ensure JSON is valid and parseable

**Interfaces:**
- Consumes: All 7 prior deliverables
- Produces: Machine-readable results summary

- [ ] Step 8.1: Extract key data from all 7 deliverables
- [ ] Step 8.2: Structure JSON with all required sections
- [ ] Step 8.3: Validate JSON syntax
- [ ] Step 8.4: Save to `reports/assignment20/assignment20_results.json`

---

## Execution Order

Tasks 1-6 can be executed in parallel (independent deliverables). Task 7 depends on 1-6. Task 8 depends on 1-7.

**Recommended sequence:**
1. Tasks 1, 4, 5, 6 (foundational audits - can parallel)
2. Tasks 2, 3 (candidate-specific designs - can parallel)
3. Task 7 (synthesis)
4. Task 8 (JSON summary)

---

## Verification Checklist

After all tasks complete:
- [ ] All 8 files exist in `reports/assignment20/`
- [ ] No deliverable modifies Assignment 19 frozen specs
- [ ] FC-007-2 hard gate explicitly documented for Candidate 007
- [ ] Candidate 005 comparison design includes unconditional/regime/null
- [ ] $30 feasibility verified with instrument spec math
- [ ] IS/OOS periods verified non-overlapping
- [ ] Cost model matches Assignment 17 verified model
- [ ] JSON is valid and contains all required sections
- [ ] All quantitative statements sourced (fact/assumption/estimate)