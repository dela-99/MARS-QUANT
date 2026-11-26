# M.A.R.S. Quant — Assignment 20
## Final Decision Report
### Phase F Formal Specification Audit and Pre-Backtest Feasibility

**Date:** 2026-11-25  
**Phase:** Assignment 20 — Phase F Formal Specification Audit and Pre-Backtest Feasibility  
**Authority:** Final go/no-go decision for Phase G (In-Sample Research) commencement  
**Candidates:** XAU-VOL-REGIME-SESSION-005 (Primary), XAU-ASIAN-VOL-BREAKOUT-007 (Secondary)  
**Reference:** All Assignment 20 Deliverables 1-6, Assignment 19 Advancement Decision, Research Specification Brief

---

## Executive Decision

| Candidate | Decision | Conditions | Next Phase |
|-----------|----------|------------|------------|
| **XAU-VOL-REGIME-SESSION-005 (Primary)** | **AUTHORIZED FOR PHASE G** | None — specification clean, all controls verified | Phase G: In-Sample Research |
| **XAU-ASIAN-VOL-BREAKOUT-007 (Secondary)** | **CONDITIONALLY AUTHORIZED FOR PHASE G** | **FC-007-2 Hard Gate Must Pass** (spread-vol correlation ≤ 0.3) | Phase G: FC-007-2 Diagnostic First, then full IS |

**Zero candidates manufactured. Decision based on evidence-weighted audit of frozen specifications.**

---

## 1. Synthesis of Assignment 20 Deliverables

### 1.1 Deliverable 1: Formal Specification Audit
**Finding:** Both candidate specifications are **frozen, internally consistent, and aligned** with verified instrument specs (v1.0), data catalog (v1.0), and Assignment 17 audit. No discrepancies found. All parameters explicitly frozen with "No Optimization Permitted."

### 1.2 Deliverable 2: Candidate 005 Regime Validation Design
**Finding:** Mandatory three-way comparison (unconditional baseline vs regime-filtered vs null) **pre-registered with statistical rigor**. Unconditional baseline recreates rejected XAU-SESSION-MOM-001 (Assignment 17: -$34.77 expectancy). Regime filter tests incremental value via interaction regression (FC-005-2: β₃ > 0, p < 0.05). Null permutation tests (10,000 reps) control for chance. 6 sensitivity analyses pre-registered. All 8 Phase K criteria defined.

### 1.3 Deliverable 3: Candidate 007 FC-007-2 Spread-Vol Correlation Analysis
**Finding:** **Hard gate diagnostic plan frozen**. Pearson correlation between Asian session realized vol (H1, 20-bar) and 08:00 UTC spread (M5) on ~770 IS sessions. Pass ≤ 0.3, Fail > 0.5 (termination), Indeterminate 0.3-0.5. Sample size >99% power at ρ=0.3. Diagnostic extensions pre-registered (non-gating). **Must execute first in Phase G Week 2.**

### 1.4 Deliverable 4: Transaction Cost and Execution Audit
**Finding:** Cost model **fully verified** against Assignment 17: 200 pts = 20 pips = $0.20/0.01 lot RT. Per-bar observed spread, 1× RT, $0 commission, 0 slippage base, swap $0 intraday. Zero-spread substitution (median 200 pts). Sensitivity multipliers 1.0×/1.5×/2.0×. Execution: entry 08:00 UTC, exit 14:30 UTC, time-stop. SL logic verified: 005 min(session low, 200pts), 007 hard cap 200pts.

### 1.5 Deliverable 5: Account Scale Verification ($30)
**Finding:** **Both candidates FEASIBLE at $30**. Min lot 0.01, SL capped at 200pts → risk $0.20 ≤ $0.30 budget. Margin at 1:200: $13.25 used, $16.75 free. RT cost $0.20 = risk at min volume (100% cost/risk ratio). Min-volume breach at SL > 300pts → REJECT enforced. No linear scaling from $10k research.

### 1.6 Deliverable 6: IS/OOS Control Verification
**Finding:** Controls **robust**. Chronological periods non-overlapping. Burn-in sufficient (005: 60 sessions for 20-bar vol; 007: 60 sessions for 60-session vol). Threshold freezing: 005 freezes IS percentile values; 007 freezes trailing methodology. Min trade counts pre-registered. H1 v1.2.0 resampled from M5 v1.2.0 (no raw H1 contamination). No optimization post-freeze. Assignment 17 lessons incorporated: authorized OOS/MC phases, fixed calendar splits, documented assumptions.

---

## 2. Candidate 005: XAU-VOL-REGIME-SESSION-005 — Primary

### 2.1 Strengths Confirmed
- ✅ **Highest conviction candidate** (Advancement Decision Report)
- ✅ Addresses Programme 01 rejection directly: regime filter on unconditional momentum
- ✅ Strong economic plausibility (Kyle 1985, Paper 12, Paper 11)
- ✅ Clean data eligibility (all internal, FOMC optional)
- ✅ $30 feasibility solid (SL=200pts cap → $0.20 risk)
- ✅ Well-specified falsification (4 criteria including regime interaction)
- ✅ Mandatory comparison design pre-registered (unconditional/regime/null)

### 2.2 Risks Acknowledged
| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Regime filter overfit | MEDIUM | Pre-specified thresholds; stability tests (30th-50th); OOS validation; null permutation |
| Insufficient IS trades after filter | MEDIUM | Minimum 50 trades required (FC-005-1); if <50, candidate fails |
| FOMC calendar unavailable | LOW | Sensitivity with FOMC OFF; not core |
| DST session distortion | LOW | Sensitivity ±1 hour; not core |

### 2.3 Phase K Success Criteria (All Must Pass)
- [ ] FC-005-1: IS Conditional Expectancy > $0.00/trade
- [ ] FC-005-2: Regime Interaction β₃ > 0, p < 0.05 (one-sided)
- [ ] FC-005-3: OOS Expectancy > $0.00/trade
- [ ] FC-005-4: Cost Sensitivity PASS at 1.0× AND 1.5× spread
- [ ] IS Trades ≥ 50 (after regime filter)
- [ ] OOS Trades ≥ 20
- [ ] IS Max DD < 30% (at $30 equity)
- [ ] IS Net Expectancy > $0.05/trade

---

## 3. Candidate 007: XAU-ASIAN-VOL-BREAKOUT-007 — Secondary

### 3.1 Strengths Confirmed
- ✅ **Distinct mechanism** from rejected strategies (breakout direction vs continuation)
- ✅ Novel combination: Mechanism 1 (Asian dominance) + Mechanism 4 (vol regimes)
- ✅ Economic plausibility (informed trading in high-vol; Paper 12 Asian session flow)
- ✅ Clean data eligibility (all internal, 60-session burn-in documented)
- ✅ $30 feasibility (SL hard cap 200pts → $0.20 risk)
- ✅ Falsification includes cost-correlation test (FC-007-2 directly measures Gate C risk)

### 3.2 Critical Hard Gate: FC-007-2
> **FC-007-2 (Spread-Vol Correlation at 08:00 UTC) MUST PASS before full backtest proceeds.**
> If correlation > 0.5 → **Candidate 007 TERMINATED immediately.**

**Rationale:** High-vol Asian sessions (entry condition) may have wide spreads at 08:00 entry, destroying edge. This is the core Gate C risk made empirically testable.

### 3.3 Phase G Execution Order (Mandatory)
1. **Week 2: FC-007-2 Diagnostic** — Compute correlation on IS period
   - If PASS (ρ ≤ 0.3) → Proceed to full Candidate 007 IS research
   - If INDETERMINATE (0.3 < ρ ≤ 0.5) → Proceed with caution, document risk
   - If FAIL (ρ > 0.5) → **TERMINATE Candidate 007**; reallocate resources to 005
2. **Weeks 2-3: Full IS Research** (if FC-007-2 passes)
3. **Week 4: OOS Validation** (frozen parameters)
4. **Week 5: Monte Carlo + $30 Re-verification**
5. **Week 6: Phase K Decision**

### 3.4 Phase K Success Criteria (All Must Pass)
- [ ] **FC-007-2: Spread-Vol Correlation ≤ 0.3 (HARD GATE — already tested)**
- [ ] FC-007-1: Breakout Direction Predictive Power (p < 0.05, diff > 0)
- [ ] FC-007-3: IS Net Expectancy > $0.00/trade
- [ ] FC-007-4: Threshold Stability (50th-70th percentile)
- [ ] IS High-Vol Sessions ≥ 40 per direction
- [ ] OOS High-Vol Sessions ≥ 15 per direction
- [ ] IS Max DD < 30% (at $30 equity)
- [ ] IS Net Expectancy > $0.05/trade

---

## 4. Programme 02 Constraint Compliance

| Constraint | Status | Evidence |
|------------|--------|----------|
| **Max 5 candidates identified** | ✅ | 5 in Candidate Hypothesis Register (Assignment 19) |
| **Max 2 candidates advance** | ✅ | 2 advancing (005, 007); 1 not advancing (006); 2 failed Gate A (008, 009) |
| **No revival of rejected strategies** | ✅ | 005 ≠ 001 (adds regime filter); 007 ≠ 001 (breakout vs continuation); 006 ≠ any rejected |
| **Learn from rejections** | ✅ | 005 addresses 001 failure via regime filter; 007 tests rival mechanism; 006 avoids 002/003 $30 infeasibility |
| **Every quantitative statement sourced** | ✅ | All traced to Papers 1,2,11,12, Assignment 17 Audit, Instrument Spec, Data Catalog |
| **Distinguish fact/assumption/estimate** | ✅ | Classification maintained in all deliverables |
| **If none pass, report zero** | N/A | 2 candidates pass all gates |
| **Original Programme 01/02 docs preserved** | ✅ | No modifications to source documents |

---

## 5. Resource Allocation Recommendation

| Candidate | Priority | Phase G Effort | Dependencies |
|-----------|----------|----------------|--------------|
| **005** | **HIGH (Primary)** | Medium (regime filter + session momentum base exists) | FOMC calendar (optional) |
| **007** | **MEDIUM (Secondary)** | Medium-High (novel signal, FC-007-2 diagnostic first) | None |

**Execution Strategy:** **Parallel execution with gate.**
- Week 1: Both candidates — environment setup, data validation
- Week 2: **Candidate 007 FC-007-2 diagnostic runs FIRST** (hard gate)
  - If 007 FAILS → full resources to 005 deep dive
  - If 007 PASSES/INDETERMINATE → parallel IS research
- Weeks 2-3: IS research (both or 005 only)
- Week 4: OOS validation (frozen params)
- Week 5: Monte Carlo + $30 re-verify
- Week 6: Phase K decision

---

## 6. Open Risks and Clarifications

| Risk | Candidate | Status | Action |
|------|-----------|--------|--------|
| FOMC calendar source (FRED vs investing.com) | 005 | OPEN | Use FRED (official); document in Phase G |
| FC-007-2 correlation indeterminate (0.3-0.5) | 007 | OPEN | Proceed with caution; require stronger Phase K evidence |
| Insufficient OOS trades (< 20 for 005, < 15/dir for 007) | Both | LOW | Reserve 2026 data available; walk-forward in IS if needed |
| DST distortion in 2021-2024 data | Both | LOW | Sensitivity test ±1 hour; not core |

---

## 7. Final Authorization

### Authorization for Phase G Commencement

> **AUTHORIZED FOR PHASE G (In-Sample Research):**
> 1. **XAU-VOL-REGIME-SESSION-005** — PRIMARY — Full IS research per Regime Validation Design (Deliverable 2)
> 2. **XAU-ASIAN-VOL-BREAKOUT-007** — SECONDARY — **Conditional on FC-007-2 PASS** (Deliverable 3). FC-007-2 diagnostic executes first in Week 2. If FAIL, 007 terminated immediately.

> **NOT AUTHORIZED:**
> - XAU-SESSION-CALENDAR-006 (insufficient gate clearance; 4 conditional gates)
> - Any parameter optimization or unfrozen research
> - Any citation of Assignment 17 unauthorized OOS/MC as formal validation

### Research-to-Trade Process Compliance

This decision follows the authorized Research-to-Trade Process phases:
- ✅ **Phase F:** Formal Specification (this Assignment 20) — COMPLETE
- 🔄 **Phase G:** In-Sample Research — AUTHORIZED TO COMMENCE
- ⏳ **Phase H:** Frozen OOS Validation — Pending Phase G results
- ⏳ **Phase I:** Monte Carlo (10,000+ reshuffle/resample) — Pending Phase H
- ⏳ **Phase J:** $30 Feasibility Re-verification — Pending Phase I
- ⏳ **Phase K:** Research Decision (All falsification criteria PASS → Live Sim) — Pending Phase J

**No phase skipping. Sequential gates enforced.**

---

## 8. Sign-Off

**Decision Report Finalized:** 2026-11-25  
**Decision Authority:** M.A.R.S. Quant Research Pipeline  
**Classification:** Internal — Final Decision Report

> **Final Statement:** Assignment 20 has rigorously audited the frozen specifications for both advancing Programme 02 candidates. Candidate 005 is authorized for In-Sample Research with a pre-registered regime validation design. Candidate 007 is conditionally authorized contingent on its hard-gate spread-volatility correlation diagnostic (FC-007-2). All controls, cost models, account-scale feasibility, and IS/OOS protocols are verified. The Research-to-Trade Process proceeds to Phase G.

---

*End of Assignment 20 Decision Report*  
*Deliverable 7 of 8 — Assignment 20 Complete*