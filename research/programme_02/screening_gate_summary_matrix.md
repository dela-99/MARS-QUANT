# M.A.R.S. Quant — Research Programme 02
## Screening Gate Summary Matrix

**Date:** 2026-11-25  
**Phase:** Assignment 19 — Research Discovery, Economic Plausibility and Candidate Screening  
**Purpose:** Consolidated view of all 5 mandatory screening gates across all candidates

---

## 1. Complete Gate Results Matrix

| Gate | Criterion | **005: XAU-VOL-REGIME-SESSION-005** | **006: XAU-SESSION-CALENDAR-006** | **007: XAU-ASIAN-VOL-BREAKOUT-007** |
|------|-----------|--------------------------------------|-----------------------------------|-------------------------------------|
| **A** | Economic Plausibility | **PASS** (MEDIUM-HIGH) | **CONDITIONAL PASS** (LOW-MEDIUM) | **PASS** (MEDIUM) |
| **B** | Data Eligibility | **PASS** | **CONDITIONAL PASS** | **PASS** |
| **C** | Spread/Cost Feasibility | **CONDITIONAL PASS** | **CONDITIONAL PASS** | **CONDITIONAL PASS** |
| **D** | $30 Account Feasibility | **PASS** | **CONDITIONAL PASS** | **CONDITIONAL PASS** |
| **E** | Falsifiability | **PASS** | **PASS** | **PASS** |

**Legend:**
- **PASS** = Meets criterion without significant caveats
- **CONDITIONAL PASS** = Meets criterion but with documented constraints/risks that must be resolved in research
- **FAIL** = Does not meet criterion (eliminated)

---

## 2. Detailed Gate-by-Gate Evidence Summary

### Gate A: Economic Plausibility

| Candidate | Tier | Key Evidence | Key Risk |
|-----------|------|--------------|----------|
| **005** | MEDIUM-HIGH | Informed vs noise regimes (Kyle 1985); Gold monthly regimes (Paper 2); Crypto intraday regimes (Paper 11); Base signal Paper 12 | Regime persistence unproven; Crypto→Gold analogy |
| **006** | LOW-MEDIUM | Institutional calendars exist (month-end, options expiry, CB schedules) | Paper 1: Monthly gold seasonalities fail SPA correction; Paper 6: BTC not persistent |
| **007** | MEDIUM | Informed trading in high vol (Kyle 1985); CB narrative Paper 12 | Novel signal (no direct lit); Breakout direction may be random |

### Gate B: Data Eligibility

| Candidate | Core Data | External Deps | Statistical Power | Key Limitation |
|-----------|-----------|---------------|-------------------|----------------|
| **005** | ✅ Complete | FOMC calendar (optional) | ✅ ~900 IS / ~220 OOS sessions | FOMC filter untested without external data |
| **006** | ✅ Complete | None | ⚠️ Low per-cell; requires aggregation | Multiple testing burden (960 cells → FDR) |
| **007** | ✅ Complete | None | ✅ ~840 IS / ~220 OOS (post burn-in) | 60-session burn-in (first 3 months lost) |

### Gate C: Spread/Cost Feasibility

| Candidate | Hold Period | Est. Freq/yr | Est. Median Spread at Entry | RT Cost/Trade | Annual Cost Drag ($30) | Key Risk |
|-----------|-------------|--------------|----------------------------|---------------|------------------------|----------|
| **005** | 6.5 hrs | 50-100 | 160-180 pts (filtered) | $0.16-0.18 | $8-18 (27-60%) | Filter efficacy unproven; unconditional fails |
| **006** | 30-60 min | 50-250 | 170-230 pts (hour-dep) | $0.17-0.23 | $8.5-57.5 (28-192%) | Frequency must ≤ 100/yr; calendar effects weak |
| **007** | 6.5 hrs | ~100 | 200-500 pts (vol-dep) | $0.20-0.50 | $20-50 (67-167%) | Spread-vol correlation at 08:00 unknown |

**Reference (Rejected 001):** 6.5 hrs, ~250 trades, 200 pts, $0.20, $50 (167%) — **FAILED** (net expectancy -$34.77)

### Gate D: $30 Account Feasibility

| Candidate | Proposed SL | Risk at Min Vol | Feasible? | Max SL Before Breach | Margin at 1:100 | Free Margin |
|-----------|-------------|-----------------|-----------|---------------------|-----------------|-------------|
| **005** | 200 pts | $0.20 | ✅ PASS | 300 pts | $26.50 | $3.50 |
| **006** | 50-100 pts | $0.05-0.10 | ✅ PASS | 300 pts | $26.50 | $3.50 |
| **007** | 200 pts (capped) | $0.20 | ✅ PASS | 300 pts | $26.50 | $3.50 |

**All pass hard risk-per-trade constraint.** Conditional flags from Gates C (cumulative cost) and margin tightness at 1:100.

### Gate E: Falsifiability

| Candidate | # Criteria | Key Falsification Tests | Indeterminate Zones Defined |
|-----------|------------|-------------------------|----------------------------|
| **005** | 4 | Conditional expectancy, Regime interaction, OOS persistence, Cost sensitivity | Yes (expectancy bands, p-value margins) |
| **006** | 4 | FDR significance, Economic significance, OOS sign consistency, Frequency constraint | Yes (FDR vs uncorrected, trade count) |
| **007** | 4 | Breakout prediction, Spread-vol correlation, Net expectancy, Threshold stability | Yes (correlation bands, expectancy bands) |

---

## 3. Composite Scorecard

| Candidate | Gates Passed (5) | Conditional Gates | Hard Fail Gates | Overall Status |
|-----------|------------------|-------------------|-----------------|----------------|
| **005: XAU-VOL-REGIME-SESSION-005** | 5/5 | 1 (Gate C) | 0 | **ADVANCE** |
| **006: XAU-SESSION-CALENDAR-006** | 5/5 | 3 (Gates A, B, C, D) | 0 | **CONDITIONAL ADVANCE** |
| **007: XAU-ASIAN-VOL-BREAKOUT-007** | 5/5 | 2 (Gates C, D) | 0 | **CONDITIONAL ADVANCE** |

**Conditional Gate Count:**
- 005: 1 conditional (Gate C — filter efficacy)
- 006: 4 conditional (Gates A, B, C, D — multiple weak evidence + frequency constraint)
- 007: 2 conditional (Gates C, D — spread-vol correlation + SL cap)

---

## 4. Advancement Ranking

| Rank | Candidate | Rationale |
|------|-----------|-----------|
| **1** | **005: XAU-VOL-REGIME-SESSION-005** | Strongest economic plausibility (regime theory + gold monthly evidence); only 1 conditional gate; builds on Paper 12 base signal with theoretically-motivated filter; falsification well-specified |
| **2** | **007: XAU-ASIAN-VOL-BREAKOUT-007** | Novel but grounded mechanism; 2 conditional gates (spread-vol correlation is measurable); distinct from rejected 001 (breakout vs continuation); Gate E includes cost-correlation test |
| **3** | **006: XAU-SESSION-CALENDAR-006** | Weakest economic plausibility (Paper 1 negative); 4 conditional gates; high multiple testing burden; low per-cell power; calendar effects historically fragile |

---

## 5. Maximum 2 Advancement Rule Check

**Programme 02 Constraint:** Maximum 2 candidates may advance to research specification.

**Current Status:** 3 candidates pass all 5 gates (2 conditional, 1 strong).

**Decision Required:** Select top 2 for advancement.

**Recommended Selection:**
1. **XAU-VOL-REGIME-SESSION-005** — Clear advance (strongest overall)
2. **XAU-ASIAN-VOL-BREAKOUT-007** — Conditional advance (distinct mechanism, testable cost risk)

**XAU-SESSION-CALENDAR-006** — **NOT ADVANCED** (weakest plausibility, most conditional gates, highest data-mining risk)

---

## 6. Key Risks for Advancing Candidates

### Candidate 005 (Primary)
| Risk | Severity | Mitigation |
|------|----------|------------|
| Regime filter overfit (thresholds optimized in-sample) | HIGH | Pre-specify thresholds (40th pctl); test stability across 30th-50th; OOS validation |
| Unconditional session momentum fails (A17 proof) | HIGH | Filter MUST recover edge; if conditional ≈ unconditional, reject |
| Regime persistence (08:00 vol regime → 14:30) | MEDIUM | Measure regime autocorrelation; test shorter hold periods |
| FOMC calendar external dependency | LOW | Test without FOMC filter first; add as sensitivity |

### Candidate 007 (Secondary)
| Risk | Severity | Mitigation |
|------|----------|------------|
| Spread-vol correlation at 08:00 (Gate C risk) | HIGH | **Gate E Criterion 2 directly tests this** — if correlation > 0.5, reject |
| Novel signal (no direct literature) | MEDIUM | Treat as exploratory; require stronger OOS evidence |
| Threshold sensitivity (60th pctl arbitrary) | MEDIUM | Gate E Criterion 4 tests stability across 50th-70th |
| High-vol = high adverse selection | MEDIUM | Monitor win rate vs unconditional; expect lower |

---

## 7. Gate Summary Matrix (Condensed for Decision)

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                    PROGRAMME 02 SCREENING GATE SUMMARY                               │
├──────────┬──────────────┬──────────────┬──────────────┬──────────────┬──────────────┤
│ Candidate│      A       │      B       │      C       │      D       │      E       │
│    ID    │  Economic    │    Data      │   Spread/    │   $30 Acct   │  Falsifi-    │
│          │ Plausibility │ Eligibility  │    Cost      │  Feasibility │  ability     │
├──────────┼──────────────┼──────────────┼──────────────┼──────────────┼──────────────┤
│   005    │   PASS ✅    │   PASS ✅    │  COND ⚠️     │   PASS ✅    │   PASS ✅    │
│   006    │  COND ⚠️     │  COND ⚠️     │  COND ⚠️     │  COND ⚠️     │   PASS ✅    │
│   007    │   PASS ✅    │   PASS ✅    │  COND ⚠️     │  COND ⚠️     │   PASS ✅    │
├──────────┼──────────────┼──────────────┼──────────────┼──────────────┼──────────────┤
│ ADVANCE? │    YES       │    YES       │   YES*       │    YES       │    YES       │
└──────────┴──────────────┴──────────────┴──────────────┴──────────────┴──────────────┘
* Conditional on empirical validation of cost-advantage mechanism
```

---

*End of Screening Gate Summary Matrix*  
*Generated: 2026-11-25*  
*Next: Advancement Decision Report (Deliverable 8)*