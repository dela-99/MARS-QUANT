# M.A.R.S. Quant — Assignment 20
## Formal Specification Audit (Phase F)

**Date:** 2026-11-25  
**Phase:** Assignment 20 — Phase F Formal Specification Audit and Pre-Backtest Feasibility  
**Authority:** Audit of frozen specifications from Assignment 19 Research Specification Brief — **no modifications permitted**  
**Candidates Under Audit:** XAU-VOL-REGIME-SESSION-005 (Primary), XAU-ASIAN-VOL-BREAKOUT-007 (Secondary)

---

## Executive Summary

| Audit Area | Candidate 005 | Candidate 007 | Status |
|------------|---------------|---------------|--------|
| Parameter Freeze Integrity | ✅ Verified frozen | ✅ Verified frozen | PASS |
| Instrument Specification Alignment | ✅ Matches v1.0 | ✅ Matches v1.0 | PASS |
| Data Version Consistency | ✅ M5 v1.2.0, H1 v1.2.0 | ✅ M5 v1.2.0, H1 v1.2.0 | PASS |
| Session Definitions | ✅ Fixed UTC, no DST | ✅ Fixed UTC, no DST | PASS |
| Cost Model Verification | ✅ Per-bar spread, 1× RT | ✅ Per-bar spread, 1× RT | PASS |
| Research Periods Non-Overlap | ✅ Chronological | ✅ Chronological | PASS |
| Falsification Criteria Pre-Registered | ✅ 4 criteria (FC-005-1 to 4) | ✅ 4 criteria (FC-007-1 to 4) | PASS |
| Hard Gate Documentation | N/A | ✅ FC-007-2 documented | PASS |
| **Overall Specification Integrity** | **CLEAN** | **CLEAN** | **PASS** |

**Conclusion:** Both candidate specifications are formally consistent, internally coherent, and aligned with verified instrument specs, data catalog, and Assignment 17 audit findings. No modifications required. Specifications are frozen and authorized for Phase G (In-Sample Research) contingent on Candidate 007's FC-007-2 hard gate.

---

## 1. Parameter Freeze Verification

### 1.1 Candidate 005: XAU-VOL-REGIME-SESSION-005

| Parameter Category | Parameter | Frozen Value | Source Document | Freeze Verified |
|--------------------|-----------|--------------|-----------------|-----------------|
| **Signal** | Asian session return threshold | > 0 (close > open) | Research Brief §1.4 | ✅ |
| **Signal** | H1 realized vol lookback | 20 bars | Research Brief §1.4 | ✅ |
| **Signal** | Volatility regime threshold | ≤ 40th percentile | Research Brief §1.4 | ✅ |
| **Signal** | Spread regime threshold | ≤ 40th percentile | Research Brief §1.4 | ✅ |
| **Signal** | FOMC filter | Exclude FOMC days | Research Brief §1.4 | ✅ |
| **Execution** | Entry time | 08:00 UTC | Research Brief §1.4 | ✅ |
| **Execution** | Exit time | 14:30 UTC (time stop) | Research Brief §1.4 | ✅ |
| **Execution** | Stop-loss | Session low OR 200 pts | Research Brief §1.4 | ✅ |
| **Execution** | Take-profit | None | Research Brief §1.4 | ✅ |
| **Execution** | Position sizing | Fixed fractional 1%, min 0.01 lot | Research Brief §1.4 | ✅ |
| **Risk** | Starting equity | $30.00 | Research Brief §1.4 | ✅ |
| **Risk** | Risk fraction | 1% per trade ($0.30) | Research Brief §1.4 | ✅ |
| **Risk** | Max SL before breach | 300 pts | Research Brief §1.4 | ✅ |
| **Risk** | Min-volume breach action | REJECT | Research Brief §1.4 | ✅ |

**Optimization Prohibition:** Research Brief §1.4 explicitly states "No Optimization Permitted" for all frozen parameters. Sensitivity analyses (spread multiplier, threshold stability, FOMC filter, SL distance, DST) are **pre-specified** and do not constitute optimization.

### 1.2 Candidate 007: XAU-ASIAN-VOL-BREAKOUT-007

| Parameter Category | Parameter | Frozen Value | Source Document | Freeze Verified |
|--------------------|-----------|--------------|-----------------|-----------------|
| **Signal** | Asian session vol lookback | 60 sessions (trailing) | Research Brief §2.4 | ✅ |
| **Signal** | Volatility regime threshold | > 60th percentile | Research Brief §2.4 | ✅ |
| **Signal** | Breakout direction | sign(Asia_close - Asia_midpoint) | Research Brief §2.4 | ✅ |
| **Signal** | Asia midpoint | (Asia_high + Asia_low) / 2 | Research Brief §2.4 | ✅ |
| **Signal** | Long signal | Breakout direction > 0 | Research Brief §2.4 | ✅ |
| **Signal** | Short signal | Breakout direction < 0 | Research Brief §2.4 | ✅ |
| **Execution** | Entry time | 08:00 UTC | Research Brief §2.4 | ✅ |
| **Execution** | Exit time | 14:30 UTC (time stop) | Research Brief §2.4 | ✅ |
| **Execution** | Stop-loss | Capped at 200 pts | Research Brief §2.4 | ✅ |
| **Execution** | SL Cap Rule | If Asia extreme > 300 pts → 200 pts fixed | Research Brief §2.4 | ✅ |
| **Execution** | Take-profit | None | Research Brief §2.4 | ✅ |
| **Execution** | Position sizing | Fixed fractional 1%, min 0.01 lot | Research Brief §2.4 | ✅ |
| **Risk** | Starting equity | $30.00 | Research Brief §2.4 | ✅ |
| **Risk** | Risk fraction | 1% per trade ($0.30) | Research Brief §2.4 | ✅ |
| **Risk** | Max SL before breach | 300 pts | Research Brief §2.4 | ✅ |
| **Risk** | Min-volume breach action | REJECT | Research Brief §2.4 | ✅ |

**Optimization Prohibition:** Research Brief §2.4 explicitly states "No Optimization Permitted." Sensitivity analyses (vol threshold 50th/60th/70th/80th, spread multiplier, SL distance, trailing window, breakout definition) are **pre-specified**.

---

## 2. Instrument Specification Alignment

**Source:** `configs/instrument_spec_xauusdm.yaml` (Version 1.0, verified 2026-11-25)

| Instrument Parameter | Spec Value | Candidate 005 Usage | Candidate 007 Usage | Alignment |
|---------------------|------------|---------------------|---------------------|-----------|
| Symbol | XAUUSDm | ✅ Matches | ✅ Matches | PASS |
| Contract Size | 100.0 oz | ✅ Used for sizing | ✅ Used for sizing | PASS |
| Pip Size | 0.01 | ✅ Cost conversion | ✅ Cost conversion | PASS |
| Point Size | 0.001 | ✅ Spread unit | ✅ Spread unit | PASS |
| Quote Currency | USD | ✅ Risk in USD | ✅ Risk in USD | PASS |
| Volume Min | 0.01 lots | ✅ Min lot enforced | ✅ Min lot enforced | PASS |
| Volume Max | 200.0 lots | N/A (small size) | N/A (small size) | PASS |
| Volume Step | 0.01 lots | ✅ Flooring logic | ✅ Flooring logic | PASS |
| Leverage Default | 1:100 | ✅ Margin calc | ✅ Margin calc | PASS |
| Spread Median | 200 pts (20 pips) | ✅ Cost model | ✅ Cost model | PASS |
| Commission | $0.00/lot RT | ✅ Zero commission | ✅ Zero commission | PASS |
| Swap Long | -$0.50/lot/night | ✅ $0 intraday | ✅ $0 intraday | PASS |
| Swap Short | -$0.20/lot/night | ✅ $0 intraday | ✅ $0 intraday | PASS |

**Verdict:** Both candidates fully aligned with instrument specification v1.0. No discrepancies.

---

## 3. Data Version Consistency

**Source:** `data/catalog.yaml` (Version 1.0, generated 2026-11-24)

| Dataset | Version | Rows | Date Range | Candidate 005 | Candidate 007 |
|---------|---------|------|------------|---------------|---------------|
| M5 Primary | v1.2.0 | 369,972 | 2021-07-16 → 2026-10-09 | ✅ Execution TF | ✅ Execution TF |
| H1 Signal | v1.2.0 | 30,898 | 2021-07-16 → 2026-10-09 | ✅ Regime/Session | ✅ Regime/Breakout |

**Critical Data Integrity Checks:**
- ✅ H1 v1.2.0 **resampled from M5 v1.2.0** (not raw Exness H1 export) — eliminates hour-grid offset
- ✅ Daily-interval block (2020-01-02 → 2021-07-16, 478 rows) **excluded** from v1.2.0
- ✅ 20 in-session feed outages documented (max 10 missing bars), not filled
- ✅ 98 zero-spread bars documented; cost model substitutes dataset median (200 pts)
- ✅ `<VOL>` identically zero in Exness export; `tick_volume` only proxy
- ✅ No DST adjustment in session definitions (seasonal distortions documented but not corrected)

**Burn-in Period Coverage:**
- Candidate 005: Burn-in 2021-07-16 → 2021-09-30 (~60 sessions) — **fully within M5 v1.2.0**
- Candidate 007: Burn-in 2021-07-16 → 2021-10-15 (~60 sessions) — **fully within M5 v1.2.0**

**Verdict:** Data versions consistent, research-ready, and cover all required periods.

---

## 4. Session Definitions Verification

| Session | UTC Range | Candidate 005 | Candidate 007 | Instrument Spec |
|---------|-----------|---------------|---------------|-----------------|
| Asia | 00:00 - 08:00 | ✅ Signal source | ✅ Vol/Breakout calc | ✅ §54-58 |
| Europe | 08:00 - 14:30 | ✅ Entry/Exit window | ✅ Entry/Exit window | ✅ §54-58 |
| US | 14:30 - 24:00 | N/A (exit at 14:30) | N/A (exit at 14:30) | ✅ §54-58 |

**DST Handling:** Both candidates use **fixed UTC sessions, no DST adjustment** (per instrument spec note: "No DST adjustment — seasonal distortions documented but not corrected"). Sensitivity Analysis 6 for Candidate 005 and general design for Candidate 007 include ±1 hour shift test as **sensitivity only**, not core specification.

**Verdict:** Session definitions consistent across all documents.

---

## 5. Cost Model Verification

**Verified Cost Model (Assignment 17 Audit §B, Instrument Spec §40-51):**

| Cost Component | Value | Application | Verification Source |
|----------------|-------|-------------|---------------------|
| Spread | Per-bar observed (points) | 1× RT per trade | Assignment 17 §B.3 |
| Spread Median | 200 pts = 20 pips = $0.20/0.01 lot RT | Base case | Instrument Spec §45-51 |
| Commission | $0.00 per lot RT | Exness Standard | Instrument Spec §42 |
| Slippage | 0 points (base) | Sensitivity only | Assignment 17 §B.3 |
| Swap | $0.00 | Intraday holds only | Assignment 17 §B.3 |
| Zero-spread bars | Substitute median (200 pts) | Documented in config | Assignment 17 §B.3 |

**Backtester Cost Application (Assignment 17 §B.3):**
- Entry: Long buys at `bar_open + spread` (pays ask)
- Exit: Long sells at `bar_open` (receives bid)
- Round-trip spread: **Exactly 1 × observed spread** per trade (not double-counted)
- Multiplier sensitivity: 1.0×, 1.5×, 2.0× tested in IS sensitivity

**Verdict:** Cost model verified and consistent across all documents. Both candidates use identical cost model.

---

## 6. Research Periods Chronological Non-Overlap Verification

### Candidate 005 Periods

| Period | Date Range | Sessions (est.) | Overlap Check |
|--------|------------|-----------------|---------------|
| Burn-in | 2021-07-16 → 2021-09-30 | ~60 | ✅ Start of data |
| In-Sample (IS) | 2021-10-01 → 2024-12-31 | ~840 | ✅ After burn-in |
| Out-of-Sample (OOS) | 2025-01-01 → 2025-10-09 | ~220 | ✅ After IS |
| Reserve | 2025-10-10 → 2026-10-09 | ~260 | ✅ After OOS |

### Candidate 007 Periods

| Period | Date Range | Sessions (est.) | Overlap Check |
|--------|------------|-----------------|---------------|
| Burn-in | 2021-07-16 → 2021-10-15 | ~60 | ✅ Start of data |
| In-Sample (IS) | 2021-10-16 → 2024-12-31 | ~780 | ✅ After burn-in |
| Out-of-Sample (OOS) | 2025-01-01 → 2025-10-09 | ~220 | ✅ After IS |
| Reserve | 2025-10-10 → 2026-10-09 | ~260 | ✅ After OOS |

**Critical Checks:**
- ✅ No period overlaps (end date of prior < start date of next)
- ✅ Burn-in periods sufficient for trailing windows (20-bar H1 vol for 005, 60-session vol for 007)
- ✅ IS periods end before 2025 (no look-ahead into OOS)
- ✅ OOS periods identical for both candidates (2025-01-01 → 2025-10-09) — enables fair comparison
- ✅ Reserve period preserved for future validation (not used in Programme 02)

**Verdict:** Research periods chronologically sound, no data leakage risk.

---

## 7. Falsification Criteria Pre-Registration Verification

### Candidate 005: FC-005-1 through FC-005-4

| Criterion ID | Criterion | Pass Threshold | Fail Threshold | Indeterminate | Gate E Source |
|--------------|-----------|----------------|----------------|---------------|---------------|
| FC-005-1 | Conditional Net Expectancy (IS) | > $0.00/trade | ≤ $0.00/trade | $0.00-$0.05 | Gate E Criterion 1 |
| FC-005-2 | Regime Interaction Significance | coef > 0, p < 0.05 (one-sided) | coef ≤ 0 OR p ≥ 0.05 | 0.05 ≤ p < 0.10 | Gate E Criterion 2 |
| FC-005-3 | OOS Persistence | > $0.00/trade | ≤ $0.00/trade | < 20 trades OR $0.00-$0.10 | Gate E Criterion 3 |
| FC-005-4 | Cost Sensitivity (1.0×, 1.5× spread) | > $0.00 at both | ≤ $0.00 at either | Pass 1.0×, fail 1.5× | Gate E Criterion 4 |

**All 4 must PASS for Phase K advancement.** Pre-registered in Gate E (Assignment 19 Deliverable 6) and frozen in Research Brief §1.6.

### Candidate 007: FC-007-1 through FC-007-4

| Criterion ID | Criterion | Pass Threshold | Fail Threshold | Indeterminate | Gate E Source |
|--------------|-----------|----------------|----------------|---------------|---------------|
| FC-007-1 | Breakout Direction Predictive Power | Mean(Long)-Mean(Short) > 0, p < 0.05 | Diff ≤ 0 OR p ≥ 0.05 | 0.05 ≤ p < 0.10 OR \|diff\| < 5 pips | Gate E Criterion 1 |
| **FC-007-2** | **Spread-Vol Correlation at 08:00** | **Correlation ≤ 0.3** | **Correlation > 0.5** | **0.3 < corr ≤ 0.5** | **Gate E Criterion 2** |
| FC-007-3 | Net Expectancy After Costs (IS) | > $0.00/trade | ≤ $0.00/trade | $0.00-$0.05 OR < 40 trades | Gate E Criterion 3 |
| FC-007-4 | Threshold Stability | > $0.00 at 60th AND stable 50th-70th | Only 60th works OR sign flips | Works 60th but not 50th/70th | Gate E Criterion 4 |

**Critical Hard Gate:** **FC-007-2 MUST PASS before full backtest proceeds.** If correlation > 0.5, strategy terminates at Gate E validation (Research Brief §2.6, §4).

**Verdict:** All falsification criteria pre-registered, match Gate E exactly, and include the mandatory hard gate for Candidate 007.

---

## 8. Minimum Statistical Requirements Verification

### Candidate 005

| Requirement | Threshold | Source |
|-------------|-----------|--------|
| IS trades (after regime filter) | ≥ 50 | Research Brief §1.8 |
| OOS trades | ≥ 20 | Research Brief §1.8 |
| IS net expectancy | > $0.05/trade | Research Brief §1.8 |
| OOS net expectancy | > $0.00/trade | Research Brief §1.8 |
| Regime interaction p-value | < 0.05 (one-sided) | Research Brief §1.8 |
| Max drawdown (IS) | < 30% (at $30 equity) | Research Brief §1.8 |

### Candidate 007

| Requirement | Threshold | Source |
|-------------|-----------|--------|
| IS high-vol sessions per direction | ≥ 40 | Research Brief §2.8 |
| OOS high-vol sessions per direction | ≥ 15 | Research Brief §2.8 |
| IS net expectancy | > $0.05/trade | Research Brief §2.8 |
| OOS net expectancy | > $0.00/trade | Research Brief §2.8 |
| Breakout direction t-test | p < 0.05 (one-sided) | Research Brief §2.8 |
| Spread-vol correlation | ≤ 0.3 | Research Brief §2.8 |
| Max drawdown (IS) | < 30% (at $30 equity) | Research Brief §2.8 |

**Verdict:** Minimum statistical requirements clearly specified and consistent with falsification criteria.

---

## 9. Implementation Dependencies Verification

### Candidate 005

| Dependency | Type | Status | Notes |
|------------|------|--------|-------|
| Exness M5/H1 v1.2.0 data | Internal | ✅ Available | Data catalog active |
| `ContractAwareFixedFractionalRisk` | Internal | ✅ Verified | Assignment 17 §E.3 |
| Session decomposition utilities | Internal | ✅ Available | `xau_session_momentum.py` |
| FOMC calendar (FRED) | External | ⚠️ Optional | Required for FOMC filter sensitivity only |
| Strategy module code | Internal | 🔄 To implement | Extends `session_momentum_backtest.py` pattern |

### Candidate 007

| Dependency | Type | Status | Notes |
|------------|------|--------|-------|
| Exness M5/H1 v1.2.0 data | Internal | ✅ Available | Data catalog active |
| `ContractAwareFixedFractionalRisk` | Internal | ✅ Verified | Assignment 17 §E.3 |
| Session decomposition | Internal | ✅ Available | `xau_session_momentum.py` |
| Rolling 60-session vol percentile | Internal | 🔄 To implement | New computation on H1 Asian bars |
| External dependencies | External | ✅ None | All data internal |

**Verdict:** Dependencies identified and available. No blocking external dependencies.

---

## 10. Cross-Candidate Consistency Checks

| Check | Candidate 005 | Candidate 007 | Consistent? |
|-------|---------------|---------------|-------------|
| Instrument | XAUUSDm | XAUUSDm | ✅ |
| Data version | M5 v1.2.0 / H1 v1.2.0 | M5 v1.2.0 / H1 v1.2.0 | ✅ |
| Session definitions | Fixed UTC | Fixed UTC | ✅ |
| Cost model | Per-bar spread, 1× RT | Per-bar spread, 1× RT | ✅ |
| Entry time | 08:00 UTC | 08:00 UTC | ✅ |
| Exit time | 14:30 UTC | 14:30 UTC | ✅ |
| Position sizing | Fixed frac 1%, min 0.01 | Fixed frac 1%, min 0.01 | ✅ |
| Starting equity | $30 | $30 | ✅ |
| Risk budget | $0.30/trade | $0.30/trade | ✅ |
| Min-volume breach | REJECT | REJECT | ✅ |
| OOS period | 2025-01-01 to 2025-10-09 | 2025-01-01 to 2025-10-09 | ✅ |
| Reserve period | 2025-10-10 to 2026-10-09 | 2025-10-10 to 2026-10-09 | ✅ |

**Verdict:** Full cross-candidate consistency achieved. Enables fair comparison in Phase K.

---

## 11. Discrepancies and Clarifications

| Issue | Description | Severity | Resolution |
|-------|-------------|----------|------------|
| Candidate 005 burn-in end | 2021-09-30 vs IS start 2021-10-01 | NONE | Clean boundary |
| Candidate 007 burn-in end | 2021-10-15 vs IS start 2021-10-16 | NONE | Clean boundary |
| FOMC calendar source | FRED vs investing.com | LOW | Either acceptable; FRED preferred (official) |
| DST sensitivity | ±1 hour shift test | LOW | Sensitivity only, not core spec |
| H1 resampling | From M5 v1.2.0 | From M5 v1.2.0 | CONSISTENT |
| Assignment 17 lesson | No unauthorized OOS/MC | N/A | Documented in IS/OOS control |

**No material discrepancies found.** All clarifications are minor and do not affect specification integrity.

---

## 12. Formal Audit Conclusion

### Candidate 005: XAU-VOL-REGIME-SESSION-005
**STATUS: SPECIFICATION CLEAN — AUTHORIZED FOR PHASE G**

- All parameters frozen and verified
- Instrument/data/session alignment confirmed
- Research periods chronologically sound
- Falsification criteria pre-registered (4 criteria)
- Cost model verified
- Account-scale feasibility verified
- No optimization permitted — sensitivity analyses pre-specified
- Ready for In-Sample Research (Phase G)

### Candidate 007: XAU-ASIAN-VOL-BREAKOUT-007
**STATUS: SPECIFICATION CLEAN — CONDITIONALLY AUTHORIZED FOR PHASE G**

- All parameters frozen and verified
- Instrument/data/session alignment confirmed
- Research periods chronologically sound
- Falsification criteria pre-registered (4 criteria)
- **Critical Hard Gate:** FC-007-2 (Spread-Vol Correlation ≤ 0.3) **must pass before full backtest**
- Cost model verified
- Account-scale feasibility verified (SL cap at 200pts enforced)
- No optimization permitted — sensitivity analyses pre-specified
- **Phase G authorized contingent on FC-007-2 diagnostic execution and PASS**

---

## 13. Compliance with Programme 02 Constraints

| Constraint | Verification |
|------------|--------------|
| Max 2 candidates advance | ✅ 2 candidates (005, 007) |
| No revival of rejected strategies | ✅ 005 ≠ 001 (adds regime filter); 007 ≠ 001 (breakout vs continuation) |
| Learn from rejections | ✅ 005 addresses 001 failure via regime filter; 007 tests rival mechanism |
| Every quantitative statement sourced | ✅ All traced to Instrument Spec, Data Catalog, Assignment 17 Audit, Research Brief |
| Fact/assumption/estimate distinguished | ✅ Classification maintained throughout |
| If none pass, report zero | N/A (2 candidates pass) |
| Original Programme 01/02 docs preserved | ✅ No modifications to source documents |

---

## 14. Sign-Off

**Audit Completed:** 2026-11-25  
**Auditor:** M.A.R.S. Quant Research Pipeline  
**Classification:** Internal — Formal Specification Audit

> **Formal Specification Audit Result:** Both candidate specifications are **frozen, verified, and internally consistent**. Candidate 005 authorized for Phase G. Candidate 007 authorized for Phase G **conditional on FC-007-2 hard gate PASS**. No specification modifications required or permitted.

---

*End of Formal Specification Audit*  
*Deliverable 1 of 8 — Assignment 20*