# M.A.R.S. Quant — Research Roadmap Update
## Post Assignment 17 (XAU-SESSION-MOM-001 Closure)

**Date:** 2026-11-25  
**Previous Roadmap:** Research Programme 01 — Phase G (Implementation & IS Research)  
**Current Phase:** **Phase Complete — Candidate Rejected**  
**Next Phase:** **Research Programme 02 — Discovery & Screening Cycle**

---

## Programme 01 Status Summary

| Phase | Activity | Strategy | Status | Outcome |
|-------|----------|----------|--------|---------|
| A | Data Audit & Preparation | — | ✅ Complete | XAUUSDm M5 v1.2.0 ready |
| B | Mechanism Synthesis | — | ✅ Complete | 4 mechanisms identified |
| C | Hypothesis Register | CSM-001 → 4 strategies | ✅ Complete | XAU-SESSION-MOM-001 top priority |
| D | Codebase Assessment | — | ✅ Complete | A14 components reusable |
| E | Data Eligibility | XAU-SESSION-MOM-001 | ✅ Complete | v1.2.0 covers 2021-2026 |
| F | Formal Specification | XAU-SESSION-MOM-001 | ✅ Complete | Frozen config + spec |
| G | Implementation & IS Research | XAU-SESSION-MOM-001 | ✅ Complete | **REJECTED** |
| H | Frozen OOS Validation | XAU-SESSION-MOM-001 | ❌ Not authorized | Skipped |
| I | Monte Carlo Validation | XAU-SESSION-MOM-001 | ❌ Not authorized | Unauthorized diagnostic run |
| J | $30 Feasibility | XAU-SESSION-MOM-001 | ✅ Complete | Feasible but moot |
| K | Research Decision | XAU-SESSION-MOM-001 | ✅ Complete | **REJECTED — NO DEFENSIBLE EDGE** |

**Other Candidates (from Hypothesis Register):**
- XAU-SESSION-OPEN-MOM-002: **REJECTED pre-implementation** — infeasible at $30 (min lot breach)
- XAU-US-REV-003: **REJECTED pre-implementation** — infeasible at $30 (min lot breach)
- XAU-REGIME-SESSION-004: **DEFERRED** — depends on 001 success

---

## Current Portfolio State

| Candidate | Status | Reason |
|-----------|--------|--------|
| XAU-MTF-DONCHIAN-001 (A14) | REJECTED | Negative IS expectancy; INFEASIBLE at $30 |
| XAU-SESSION-MOM-001 (A16/17) | REJECTED | Negative IS expectancy; feasible at $30 but no edge |
| XAU-SESSION-OPEN-MOM-002 | REJECTED (pre-impl) | Infeasible at $30 |
| XAU-US-REV-003 | REJECTED (pre-impl) | Infeasible at $30 |
| XAU-REGIME-SESSION-004 | DEFERRED | Requires viable parent strategy |

**Active Candidates: NONE**

---

## Roadmap Update

### IMMEDIATE (This Week)
- [ ] Archive Programme 01 artifacts to cold storage
- [ ] Document lessons learned in institutional knowledge base
- [ ] **DO NOT** begin implementation of any new strategy

### SHORT-TERM (Next 2 Weeks) — Programme 02: Discovery & Screening
- [ ] **Phase A**: Literature review update — new session-based gold papers since Wei 2026
- [ ] **Phase B**: Mechanism synthesis — focus on cost-aware mechanisms with spread headroom
- [ ] **Phase C**: Hypothesis register — new candidates with explicit $30 feasibility pre-screen
- [ ] **Phase D**: Economic plausibility screen — reject before coding if spread > signal magnitude

### MEDIUM-TERM (Next Month) — Programme 02: Implementation
- [ ] **Phase E**: Data eligibility — verify new candidate data requirements
- [ ] **Phase F**: Formal specification — with corrected split date alignment
- [ ] **Phase G**: Implementation — ONLY after Phases A-D pass screening
- [ ] **Phase H**: IS research — strict train/val/test, no OOS/MC until frozen

### LONG-TERM (Ongoing)
- [ ] Build research-to-trade process compliance checklist (Paper 15)
- [ ] Implement authorization gates (technical enforcement of phase boundaries)
- [ ] Establish candidate cemetery documentation (rejected strategies with reasons)

---

## Key Constraints for Programme 02

| Constraint | Enforcement |
|------------|-------------|
| **$30 feasibility pre-screen** | MANDATORY before Phase F — reject if min lot breach at 1% risk |
| **Spread headroom** | MANDATORY — signal magnitude must exceed 3× median spread |
| **Economic mechanism** | MANDATORY — defensible explanation for why edge persists after costs |
| **No OOS/MC until frozen** | TECHNICAL GATE — separate repo/branch for Phase H/I |
| **One-factor sensitivity only** | MANDATORY — no grid search, no optimization |
| **Pre-declared falsification** | MANDATORY — specific, measurable, binary criteria |

---

## Resource Allocation

| Resource | Programme 01 (Closed) | Programme 02 (New) |
|----------|----------------------|-------------------|
| Research Capital | $0 (simulation only) | $0 (simulation only) |
| Live Capital Target | $30 | $30 (or revised per feasibility) |
| Compute | Local backtest/MC | Local backtest/MC |
| Data | Exness XAUUSDm M5 v1.2.0 | Same + new instruments if needed |
| Timeline | 8 Phases (A-K) | Compressed: Screen → Spec → IS → Decision |

---

## Risk Register Update

| Risk | Programme 01 Outcome | Programme 02 Mitigation |
|------|---------------------|-------------------------|
| Strategy has no edge after costs | **REALIZED** (both candidates) | Pre-screen spread vs signal magnitude |
| $30 infeasible at min lot | **REALIZED** (Donchian) | Feasibility gate before coding |
| Unauthorized phase expansion | **REALIZED** (OOS/MC run) | Technical gates, separate environments |
| Config split dates wrong | **REALIZED** (2024 vs 2026) | Align config dates with actual data range |
| Volume specs unverified | **OPEN** | Flag all offline defaults; verify when MT5 available |

---

## Next Decision Point

**Programme 02 Phase C Completion** — New hypothesis register with screened candidates.

**Go/No-Go Criteria for Phase F (Specification):**
1. At least 1 candidate passes $30 feasibility pre-screen
2. At least 1 candidate passes spread headroom test (signal > 3× median spread)
3. Economic mechanism documented and defensible
4. Falsification criteria pre-declared and binary

If no candidates pass → **Programme 02 terminates, return to discovery.**

---

**Roadmap Status:** Programme 01 **CLOSED**. Programme 02 **NOT STARTED** — awaiting discovery cycle initiation.

**Preserved:** Master research process (Paper 15), $30 capital constraint, institutional standards.