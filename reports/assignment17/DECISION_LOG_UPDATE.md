# M.A.R.S. Quant — Decision Log Update
## Strategy: XAU-SESSION-MOM-001 (Asian-Session Momentum Continuation)
## Hypothesis: CSM-001 (Cross-Session Momentum per Wei 2026)

**Decision Date:** 2026-11-25  
**Assignment:** Assignment 17 (Final Audit & Closure)  
**Previous Decisions:** Assignment 16 (Implementation & IS Research — authorized), Assignment 17 (Audit — this entry)

---

## Decision Record

| Field | Value |
|-------|-------|
| **Strategy ID** | XAU-SESSION-MOM-001 |
| **Status** | **REJECTED — NO DEFENSIBLE EDGE** |
| **Decision Authority** | Assignment 17 Final Audit |
| **Effective Date** | 2026-11-25 |
| **Reversibility** | Final — no re-optimization or rescue permitted |

---

## Authorization Context (Critical Distinction)

### Authorized (Assignment 16)
- Strategy implementation (`xau_session_momentum.py`)
- Backtester (`session_momentum_backtest.py`)
- In-Sample research pipeline (`session_momentum_research.py` with train/val/test)
- Frozen configuration (`session_momentum_001.yaml`, `instrument_spec_xauusdm.yaml`)

### **NOT Authorized** (Explicitly Prohibited by Assignment 16)
- **OOS Validation (Phase H)** — Separate frozen OOS on 2025 data
- **Monte Carlo Validation (Phase I)** — 10,000 simulation robustness tests

### What Actually Occurred
| Component | Authorization | Execution | Classification |
|-----------|---------------|-----------|----------------|
| IS Research (train/val/test) | ✅ Authorized | ✅ Executed | **FORMAL IS EVIDENCE** |
| Test-split holdout evaluation | ✅ Part of IS pipeline | ✅ Executed | **FORMAL IS HOLDOUT** |
| Separate Phase H OOS | ❌ Prohibited | ❌ Not executed separately | N/A |
| Monte Carlo (10k sims) | ❌ Prohibited | ✅ Executed on test trades | **DIAGNOSTIC ONLY** |

**Key Clarification**: The "test" split (15% chronological holdout = 2025-12-26 to 2026-10-09) is a **standard IS holdout evaluation**, not a separate Phase H OOS. The config documents a "future_oos" period (2025-01 to 2025-10) that falls inside the validation split due to data extending beyond config assumptions.

---

## Evidence Basis for Rejection

### In-Sample (Authorized) — Definitive
| Split | Trades | Net Expectancy | Net PF | Net Sharpe | Max DD | Verdict |
|-------|--------|----------------|--------|------------|--------|---------|
| **Train (70%)** | 308 | **-$32.40** | **0.00** | **-4.26** | **-99.80%** | FAIL |
| **Test (15% holdout)** | 287 | **-$34.77** | **0.47** | **-1.42** | **-99.88%** | FAIL |

**Falsification Criteria (Pre-Registered):**
- Net expectancy > $0 ❌ FAIL (both splits)
- Net profit factor > 1.0 ❌ FAIL (both splits)
- Net Sharpe > 0 ❌ FAIL (both splits)
- Max drawdown < 20% ❌ FAIL (both splits)
- Trade count ≥ 30 ✅ PASS (both splits)

**4 of 5 criteria FAIL on authorized IS evidence alone.**

### Out-of-Scope (Unauthorized) — Confirmatory Only
| Diagnostic | Result | Status |
|------------|--------|--------|
| MC Reshuffle: Observed DD > p95 | -99.88% > 84.29% | Sequence-dependent |
| MC Resample: Observed terminal < p05 | $19.69 < $2,830.63 | Outcome unlikely under i.i.d. |
| Random Signal baseline mean terminal | $2,830.63 | Strategy underperforms noise |

**These unauthorized diagnostics confirm the IS rejection but cannot be cited as formal validation.**

---

## $30 Account Feasibility (Separate Question)

| Question | Answer |
|----------|--------|
| Technically feasible at $30? | **YES** — 0.01 lots, SL=200pts → $0.20 risk ≤ $0.30 budget |
| Minimum cash risk per trade? | **$0.20** (at min volume, SL=200pts) |
| Respects 1% risk limit? | **YES** — risk engine rejects if SL > 300pts |
| Strategy executable at $30? | **Technically yes, but economically irrational** — no edge after costs |

**Critical**: Feasibility is **moot** because the strategy has no defensible edge at any account size. A feasible losing strategy is still a losing strategy.

---

## Lessons Learned (For Next Research Cycle)

1. **Cost feasibility before implementation** — Exness Standard spread (median 20 pips) destroys session momentum edge on XAUUSDm M5
2. **Economic plausibility screen** — Cross-session momentum requires spread << signal magnitude; 20-pip median spread vs ~10-20 pip session moves = negative expectancy
3. **Minimum-lot feasibility ≠ statistical validity** — $30 feasibility passed but strategy failed on merit
4. **Strict IS/OOS separation** — Config documented Phase H OOS (2025-01 to 2025-10) but chronological split consumed it; future specs must align split dates with actual data range
5. **Authorization boundaries** — Unauthorized OOS/MC executed despite explicit prohibition; future assignments need technical enforcement (separate repos, gated scripts)
6. **Pre-declared falsification worked** — Criteria were specific, measurable, and decisively failed

---

## Next Research Gate

Per Assignment 17 instructions, the next authorized activity is a **new research discovery and candidate-screening cycle** (not immediate implementation).

**Required incorporations from this rejection:**
- [ ] Cost/spread feasibility evaluation BEFORE implementation
- [ ] Candidate economic plausibility assessment BEFORE expensive coding
- [ ] Minimum-lot feasibility as early deployment screen (not substitute for statistical validation)
- [ ] Explicit falsification criteria for every hypothesis
- [ ] Simple benchmarks and placebo/null comparisons
- [ ] Reject mechanisms without defensible economic explanation
- [ ] Strict separation between IS development and untouched OOS evaluation
- [ ] Do not reuse OOS periods for strategy selection

---

## Sign-Off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Research Lead | M.A.R.S. Quant Pipeline | 2026-11-25 | ✅ |
| Risk Review | (embedded in pipeline) | 2026-11-25 | ✅ |
| Audit Closure | Assignment 17 | 2026-11-25 | ✅ |

**Final Entry**: XAU-SESSION-MOM-001 **CLOSED — REJECTED**. No further work authorized on this candidate.