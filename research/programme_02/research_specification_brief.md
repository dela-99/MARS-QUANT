# M.A.R.S. Quant — Research Programme 02
## Research Specification Brief (Phase F)

**Date:** 2026-11-25  
**Phase:** Assignment 19 — Research Discovery, Economic Plausibility and Candidate Screening  
**Output:** Formal specifications for advancing candidates to enter Phase F (Formal Strategy Specification) → Phase G (In-Sample Research)  
**Advancing Candidates:** 2 (maximum per programme constraint)

---

## 1. Candidate 1: XAU-VOL-REGIME-SESSION-005 (PRIMARY)
### Volatility-Regime-Filtered Session Momentum

### 1.1 Strategy Identity
| Field | Value |
|-------|-------|
| **Strategy ID** | XAU-VOL-REGIME-SESSION-005 |
| **Name** | Volatility-Regime-Filtered Session Momentum |
| **Programme** | 02 (Assignment 19) |
| **Priority** | PRIMARY |
| **Parent Mechanism** | Mechanism 4 (Volatility-Conditioned Predictability) + Mechanism 2 (Cross-Session Momentum) |
| **Distinction from Rejected** | Adds regime filter to XAU-SESSION-MOM-001 (rejected unconditional); tests hypothesis that session momentum only works in low-vol/low-spread/non-FOMC regimes |

### 1.2 Market Mechanism (Frozen)
*Post-2022 central bank gold accumulation shifted price discovery to Asian trading hours (Paper 12). In low-volatility, non-FOMC, normal-liquidity regimes, informed institutional/central bank flows persist across sessions → Asian session momentum continues into Europe session. In high-vol/news regimes, information events cause noisy repricing, market makers widen spreads, and momentum signals become unreliable (Paper 11: predictability changes with vol/FOMC/liquidity). The regime filter isolates the favorable conditions.*

### 1.3 Instrument & Data Specification
| Parameter | Specification |
|-----------|---------------|
| **Instrument** | Exness XAUUSDm (Standard account) |
| **Primary Timeframe** | M5 (execution) |
| **Signal Timeframe** | H1 (session bars, regime detection) |
| **Data Version** | M5 v1.2.0 (369,972 bars, 2021-07-16 to 2026-10-09), H1 v1.2.0 (resampled from M5) |
| **Session Definitions (UTC)** | Asia: 00:00-08:00, Europe: 08:00-14:30, US: 14:30-24:00 (fixed, no DST adjustment) |
| **Cost Model** | Per-bar observed spread (points), 1× RT, $0 commission, 0 slippage (base), swap $0 (intraday) |
| **Spread Median** | 200 points = 20 pips = $0.20 per 0.01 lot RT |

### 1.4 Frozen Parameters (No Optimization Permitted)

#### Signal Parameters
| Parameter | Value | Source |
|-----------|-------|--------|
| Asian session return threshold | > 0 (close > open) | Paper 12 baseline |
| H1 realized volatility lookback | 20 bars | Standard |
| Volatility regime threshold | Bottom 2 quintiles (≤ 40th percentile) | Pre-specified; test stability 30th-50th |
| Spread regime threshold | Bottom 2 quintiles (≤ 40th percentile) | Pre-specified; computed from IS spread distribution |
| FOMC filter | Exclude FOMC days | FRED calendar (external) |

#### Execution Parameters
| Parameter | Value |
|-----------|-------|
| Entry time | 08:00 UTC (first M5 bar at Europe open) |
| Exit time | 14:30 UTC (Europe close / US open) — mandatory time stop |
| Stop-loss | Session low (Asia or Europe) OR 200 pts (0.20 price), whichever tighter |
| Take-profit | None (time-stop exit) |
| Position sizing | Fixed fractional 1% equity; min lot 0.01; SL=200pts → $0.20 risk |

#### Risk & Account Parameters
| Parameter | Value |
|-----------|-------|
| Starting equity | $30.00 |
| Risk fraction | 1% per trade ($0.30 budget) |
| Max SL before min-volume breach | 300 pts (0.30 price) |
| Leverage assumption | 1:200 (margin $13.25, free $16.75) |
| Min-volume breach action | REJECT trade (never force) |

### 1.5 Research Periods (Chronological, No Overlap)

| Period | Date Range | Sessions (est.) | Purpose |
|--------|------------|-----------------|---------|
| **Burn-in** | 2021-07-16 → 2021-09-30 | ~60 | Vol percentile trailing window initialization |
| **In-Sample (IS)** | 2021-10-01 → 2024-12-31 | ~840 | Strategy development, parameter stability, sensitivity |
| **Out-of-Sample (OOS)** | 2025-01-01 → 2025-10-09 | ~220 | Frozen parameter validation |
| **Reserve** | 2025-10-10 → 2026-10-09 | ~260 | Future validation (not used in Programme 02) |

### 1.6 Pre-Registered Falsification Criteria (from Gate E)

| ID | Criterion | Pass Threshold | Fail Threshold | Indeterminate |
|----|-----------|----------------|----------------|---------------|
| **FC-005-1** | Conditional Net Expectancy (IS) | > $0.00/trade | ≤ $0.00/trade | $0.00-$0.05 |
| **FC-005-2** | Regime Interaction Significance | coef > 0, p < 0.05 (one-sided) | coef ≤ 0 OR p ≥ 0.05 | 0.05 ≤ p < 0.10 |
| **FC-005-3** | OOS Persistence | > $0.00/trade | ≤ $0.00/trade | < 20 trades OR $0.00-$0.10 |
| **FC-005-4** | Cost Sensitivity (1.0×, 1.5× spread) | > $0.00 at both | ≤ $0.00 at either | Pass 1.0×, fail 1.5× |

**All 4 must PASS for strategy to advance past Phase K (Research Decision).**

### 1.7 Required Sensitivity Analyses
1. **Spread multiplier:** 1.0×, 1.5×, 2.0× (base = 1.0×)
2. **Vol percentile threshold:** 30th, 40th, 50th (base = 40th)
3. **Spread percentile threshold:** 30th, 40th, 50th (base = 40th)
4. **FOMC filter:** ON vs OFF (base = ON)
5. **SL distance:** 150, 200, 250, 300 pts (base = 200 pts)
6. **DST-adjusted sessions:** Test ±1 hour shift for Europe/US sessions (sensitivity only)

### 1.8 Minimum Statistical Requirements
- IS trades: ≥ 50 (after regime filter)
- OOS trades: ≥ 20
- IS net expectancy: > $0.05/trade (clear of indeterminate)
- OOS net expectancy: > $0.00/trade
- Regime interaction p-value: < 0.05 (one-sided)
- Max drawdown (IS): < 30% (at $30 equity scale)

### 1.9 Implementation Dependencies
- **Internal:** Exness M5/H1 v1.2.0 data, `ContractAwareFixedFractionalRisk`, session decomposition utilities
- **External:** FOMC calendar (FRED: `https://fred.stlouisfed.org/series/FOMCMEETINGS` or investing.com) — **optional for core test, required for FOMC filter sensitivity**
- **Code:** New strategy module extending `session_momentum_backtest.py` pattern with regime filter

---

## 2. Candidate 2: XAU-ASIAN-VOL-BREAKOUT-007 (SECONDARY)
### Asian Session Volatility Breakout

### 2.1 Strategy Identity
| Field | Value |
|-------|-------|
| **Strategy ID** | XAU-ASIAN-VOL-BREAKOUT-007 |
| **Name** | Asian Session Volatility Breakout |
| **Programme** | 02 (Assignment 19) |
| **Priority** | SECONDARY |
| **Parent Mechanism** | Mechanism 1 (Session Decomposition) + Mechanism 4 (Volatility Regimes) — **novel combination** |
| **Distinction from Rejected** | Tests **breakout direction** (close vs midpoint) in high-vol Asian sessions, not return continuation (001) or session-open momentum (002) |

### 2.2 Market Mechanism (Frozen)
*High-volatility Asian sessions (00:00-08:00 UTC) reflect resolved uncertainty — central bank intervention, scheduled news (China PMI, Japan CPI), or overnight order imbalance resolution. The breakout direction (close relative to session midpoint) reveals the resolved direction of informed flow. This directional information persists into the Europe session (08:00-14:30 UTC) where liquidity deepens. Low-vol Asian sessions are noise with no predictive breakout direction. This is a volatility-regime-conditioned breakout strategy, distinct from momentum continuation.*

### 2.3 Instrument & Data Specification
| Parameter | Specification |
|-----------|---------------|
| **Instrument** | Exness XAUUSDm (Standard account) |
| **Primary Timeframe** | M5 (execution) |
| **Signal Timeframe** | H1 (Asian session bars for vol/breakout calculation) |
| **Data Version** | M5 v1.2.0, H1 v1.2.0 (resampled from M5) |
| **Session Definitions (UTC)** | Asia: 00:00-08:00, Europe: 08:00-14:30 |
| **Cost Model** | Per-bar observed spread, 1× RT, $0 commission, 0 slippage, swap $0 |
| **Spread Median** | 200 points = 20 pips = $0.20 per 0.01 lot RT |

### 2.4 Frozen Parameters (No Optimization Permitted)

#### Signal Parameters
| Parameter | Value | Source |
|-----------|-------|--------|
| Asian session vol lookback | 60 sessions (trailing) | Pre-specified; test stability |
| Volatility regime threshold | > 60th percentile | Pre-specified; test 50th, 60th, 70th, 80th |
| Breakout direction | sign(Asia_close - Asia_midpoint) | Asia_midpoint = (Asia_high + Asia_low) / 2 |
| Long signal | Breakout direction > 0 | Close > midpoint |
| Short signal | Breakout direction < 0 | Close < midpoint |

#### Execution Parameters
| Parameter | Value |
|-----------|-------|
| Entry time | 08:00 UTC (first M5 bar at Europe open) |
| Exit time | 14:30 UTC (Europe close / US open) — mandatory time stop |
| Stop-loss | **Capped at 200 pts (0.20 price)** — Asia session extreme if tighter, else 200 pts |
| Take-profit | None (time-stop exit) |
| Position sizing | Fixed fractional 1% equity; min lot 0.01; SL=200pts → $0.20 risk |

#### Risk & Account Parameters
| Parameter | Value |
|-----------|-------|
| Starting equity | $30.00 |
| Risk fraction | 1% per trade ($0.30 budget) |
| Max SL before min-volume breach | 300 pts (0.30 price) |
| **SL Cap Rule** | If Asia session extreme > 300 pts → use 200 pts fixed (never exceed 300) |
| Leverage assumption | 1:200 (margin $13.25, free $16.75) |
| Min-volume breach action | REJECT trade |

### 2.5 Research Periods (Chronological, No Overlap)

| Period | Date Range | Sessions (est.) | Purpose |
|--------|------------|-----------------|---------|
| **Burn-in** | 2021-07-16 → 2021-10-15 | ~60 | 60-session trailing vol percentile initialization |
| **In-Sample (IS)** | 2021-10-16 → 2024-12-31 | ~780 | Strategy development, threshold stability, spread-vol correlation |
| **Out-of-Sample (OOS)** | 2025-01-01 → 2025-10-09 | ~220 | Frozen parameter validation |
| **Reserve** | 2025-10-10 → 2026-10-09 | ~260 | Future validation |

### 2.6 Pre-Registered Falsification Criteria (from Gate E)

| ID | Criterion | Pass Threshold | Fail Threshold | Indeterminate |
|----|-----------|----------------|----------------|---------------|
| **FC-007-1** | Breakout Direction Predictive Power | Mean(Long)-Mean(Short) > 0, p < 0.05 | Diff ≤ 0 OR p ≥ 0.05 | 0.05 ≤ p < 0.10 OR \|diff\| < 5 pips |
| **FC-007-2** | Spread-Vol Correlation at 08:00 | Correlation ≤ 0.3 | Correlation > 0.5 | 0.3 < corr ≤ 0.5 |
| **FC-007-3** | Net Expectancy After Costs (IS) | > $0.00/trade | ≤ $0.00/trade | $0.00-$0.05 OR < 40 trades |
| **FC-007-4** | Threshold Stability | > $0.00 at 60th AND stable 50th-70th | Only 60th works OR sign flips | Works 60th but not 50th/70th |

**Critical Gate:** **FC-007-2 (Spread-Vol Correlation) MUST PASS before full backtest proceeds.** If correlation > 0.5, strategy terminates at Gate E validation.

**All 4 must PASS for strategy to advance past Phase K.**

### 2.7 Required Sensitivity Analyses
1. **Vol percentile threshold:** 50th, 60th, 70th, 80th (base = 60th)
2. **Spread multiplier:** 1.0×, 1.5×, 2.0× (base = 1.0×)
3. **SL distance:** 150, 200, 250 pts (base = 200 pts capped)
4. **Trailing window:** 40, 60, 80 sessions (base = 60)
5. **Breakout definition:** Close vs midpoint vs open (base = midpoint)

### 2.8 Minimum Statistical Requirements
- IS high-vol sessions: ≥ 40 per direction (Long/Short)
- OOS high-vol sessions: ≥ 15 per direction
- IS net expectancy: > $0.05/trade
- OOS net expectancy: > $0.00/trade
- Breakout direction t-test: p < 0.05 (one-sided)
- Spread-vol correlation: ≤ 0.3
- Max drawdown (IS): < 30% (at $30 equity scale)

### 2.9 Implementation Dependencies
- **Internal:** Exness M5/H1 v1.2.0 data, `ContractAwareFixedFractionalRisk`, session decomposition, rolling vol percentile calculation
- **External:** None (all data internal)
- **Code:** New strategy module; requires rolling 60-session vol percentile computation on H1 Asian session bars

---

## 3. Shared Research Infrastructure Requirements

### 3.1 Backtest Framework
- **Base:** `session_momentum_backtest.py` pattern (verified in Assignment 17)
- **Risk Engine:** `ContractAwareFixedFractionalRisk` (verified for $30 feasibility)
- **Cost Model:** Per-bar observed spread, 1× RT, configurable multiplier
- **Outputs:** Machine-readable JSON (trades, equity curve, metrics) + Markdown report

### 3.2 Validation Pipeline (Per Research-to-Trade Process)
1. **Phase F:** Formal specification (this document) → frozen config YAML
2. **Phase G:** In-sample research (IS period) → `is_report.md`, `is_results.json`
3. **Phase H:** Frozen OOS validation (OOS period) → `oos_report.md`, `oos_results.json`
4. **Phase I:** Monte Carlo (10,000+ reshuffle/resample) → `mc_report.md`, `mc_results.json`
5. **Phase J:** $30 feasibility re-verification (already done in Gates C-D)
6. **Phase K:** Research decision (all falsification criteria PASS → advance to live sim)

### 3.3 Reproducibility Requirements
- All parameters frozen in config YAML (no optimization)
- Random seeds fixed (IS: 20261125, MC: 20261126)
- Data version pinned (M5 v1.2.0, H1 v1.2.0)
- Git commit hash recorded for code version
- Environment: Python 3.11+, pandas, numpy, specified in `requirements.txt`

---

## 4. Go/No-Go Decision Rules for Phase K

### Candidate 005 (Primary) — Advances to Live Sim IF:
- [ ] FC-005-1 PASS (IS conditional expectancy > $0.00)
- [ ] FC-005-2 PASS (Regime interaction p < 0.05)
- [ ] FC-005-3 PASS (OOS expectancy > $0.00)
- [ ] FC-005-4 PASS (Cost sensitivity at 1.0× and 1.5×)
- [ ] IS max DD < 30%
- [ ] Minimum trade counts met (IS ≥ 50, OOS ≥ 20)

### Candidate 007 (Secondary) — Advances to Live Sim IF:
- [ ] FC-007-2 PASS FIRST (Spread-vol correlation ≤ 0.3) — **hard gate**
- [ ] FC-007-1 PASS (Breakout direction p < 0.05)
- [ ] FC-007-3 PASS (IS expectancy > $0.00)
- [ ] FC-007-4 PASS (Threshold stability 50th-70th)
- [ ] IS max DD < 30%
- [ ] Minimum trade counts met (IS ≥ 40/direction, OOS ≥ 15/direction)

**If any criterion FAILS → Strategy REJECTED. No parameter changes permitted post-freeze.**

---

## 5. Timeline & Milestones

| Milestone | Candidate 005 | Candidate 007 | Owner |
|-----------|---------------|---------------|-------|
| **Phase F: Spec Freeze** | Week 1 | Week 1 | Research |
| **Phase G: IS Research** | Weeks 2-3 | Weeks 2-3 | Research |
| **FC-007-2 Diagnostic** | N/A | Week 2 (first) | Research |
| **Phase H: OOS Validation** | Week 4 | Week 4 | Research |
| **Phase I: Monte Carlo** | Week 5 | Week 5 | Research |
| **Phase J: $30 Re-verify** | Week 5 | Week 5 | Research |
| **Phase K: Decision** | Week 6 | Week 6 | Research + User |

**Parallel Execution:** Both candidates run simultaneously. Candidate 007's FC-007-2 diagnostic runs first in Week 2 — if FAIL, 007 resources redirect to 005.

---

## 6. Risk Register (Post-Specification)

| Risk | Candidate | Likelihood | Impact | Mitigation |
|------|-----------|------------|--------|------------|
| Regime filter overfit | 005 | MEDIUM | HIGH | Pre-specified thresholds; stability tests; OOS validation |
| Spread-vol correlation > 0.5 | 007 | MEDIUM | HIGH (terminal) | FC-007-2 diagnostic first; if fail, terminate early |
| FOMC calendar unavailable | 005 | LOW | MEDIUM | Test without FOMC filter; add as sensitivity only |
| Insufficient OOS trades | Both | LOW | MEDIUM | Reserve 2026 data; walk-forward in IS if needed |
| DST session distortion | Both | LOW | LOW | Sensitivity test ±1 hour; not core |

---

## 7. Sign-Off

**Research Specification Authorized For:**
1. **XAU-VOL-REGIME-SESSION-005** — PRIMARY — Proceed to Phase F implementation
2. **XAU-ASIAN-VOL-BREAKOUT-007** — SECONDARY — Proceed to Phase F implementation (contingent on FC-007-2)

**Not Authorized:**
- XAU-SESSION-CALENDAR-006 (insufficient gate clearance)
- Any parameter optimization or unfrozen research

**Authorization:** This specification is frozen. No parameter changes permitted after Phase F config commit. All research must follow the Research-to-Trade Process phases G→K sequentially.

---

*End of Research Specification Brief*  
*Generated: 2026-11-25*  
*Deliverable 9 of 9 — Assignment 19 Complete*