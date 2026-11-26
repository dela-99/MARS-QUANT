# M.A.R.S. Quant — Research Programme 02
## Gate E: Falsifiability Report

**Date:** 2026-11-25  
**Phase:** Assignment 19 — Research Discovery, Economic Plausibility and Candidate Screening  
**Input:** Gate D survivors (3 candidates): 005, 006, 007  
**Standard:** Each candidate must have pre-registered, observable falsification criteria with clear pass/fail thresholds. Must contrast with at least one rival hypothesis. Indeterminate outcomes must be defined.

---

## 1. Falsifiability Framework

| Requirement | Standard |
|-------------|----------|
| **Pre-registration** | Criteria defined BEFORE seeing target period results |
| **Observable Implication** | Measurable from Exness XAUUSDm M5/H1 v1.2.0 data |
| **Clear Threshold** | Numeric pass/fail boundary (not qualitative) |
| **Rival Contrast** | At least one alternative prediction that differs |
| **Indeterminate Definition** | What outcome = "inconclusive" vs "falsified" |
| **Statistical Validity** | Minimum trade count; multiple testing control where applicable |

**Gate E Pass Criterion:** Candidate has at least 3 independent falsification criteria, each with pre-registered threshold, rival contrast, and indeterminate zone defined.

---

## 2. Candidate-by-Candidate Falsification Criteria

### Candidate 005: XAU-VOL-REGIME-SESSION-005 (Vol-Regime Session Momentum)

**Core Hypothesis:** *Asian-session momentum continuation (Asia close > open → long Europe open) generates positive expectancy after Exness costs WHEN conditioned on: (a) H1 realized vol (20-bar) in bottom 2 quintiles, (b) NOT FOMC day, (c) M5 spread at entry in bottom 2 quintiles.*

**Rival Hypotheses:**
- **R1 (Null):** No predictability in any regime (session momentum = noise)
- **R2 (Unconditional works):** Unconditional session momentum works (contradicted by A17)
- **R3 (Regime hurts):** Regime filter degrades performance (overfitting)

#### Falsification Criterion 1: Conditional Net Expectancy
| Element | Specification |
|---------|---------------|
| **Observable** | Net expectancy ($/trade) after Exness costs in IS period (2021-07 to 2024-12) |
| **Measurement** | Backtest on Exness M5 v1.2.0 with per-bar observed spread, 0.01 lots, SL=200pts |
| **Pass Threshold** | Net expectancy > $0.00/trade |
| **Fail Threshold** | Net expectancy ≤ $0.00/trade |
| **Rival Contrast** | R1 predicts ≤ $0.00; R2 predicts > $0.00 unconditional (false per A17); R3 predicts conditional < unconditional |
| **Indeterminate** | $0.00 < expectancy < $0.05/trade (statistically indistinguishable from zero given trade count) |
| **Minimum Trades** | ≥ 30 trades in IS (for basic significance) |

#### Falsification Criterion 2: Regime Interaction Significance
| Element | Specification |
|---------|---------------|
| **Observable** | Interaction coefficient: Session_Momentum_Signal × Regime_Favorable (1/0) in logistic/linear regression |
| **Measurement** | Regress Europe session return on: Asia session return (signal), Regime_Favorable, Signal×Regime |
| **Pass Threshold** | Interaction coefficient > 0 with p < 0.05 (one-sided) |
| **Fail Threshold** | Interaction coefficient ≤ 0 OR p ≥ 0.05 |
| **Rival Contrast** | R1/R3 predict interaction ≤ 0; R2 predicts main effect > 0, interaction = 0 |
| **Indeterminate** | 0.05 ≤ p < 0.10 (marginal) |
| **Control Variables** | Realized vol (continuous), FOMC dummy, spread quintile |

#### Falsification Criterion 3: Out-of-Sample Persistence
| Element | Specification |
|---------|---------------|
| **Observable** | Net expectancy in OOS period (2025-01 to 2025-10) using IS-frozen regime thresholds |
| **Measurement** | Same backtest on 2025 data; regime thresholds (vol 40th pctl, spread 40th pctl) computed from IS only |
| **Pass Threshold** | Net expectancy > $0.00/trade |
| **Fail Threshold** | Net expectancy ≤ $0.00/trade |
| **Rival Contrast** | R1/R3 predict ≤ $0.00; R2 predicts > $0.00 but unconditional |
| **Indeterminate** | < 20 trades in OOS (insufficient power) OR expectancy in [$0.00, $0.10] |

#### Falsification Criterion 4: Cost Sensitivity Robustness
| Element | Specification |
|---------|---------------|
| **Observable** | Net expectancy at spread multipliers 1.0×, 1.5×, 2.0× |
| **Measurement** | Re-run IS backtest with spread multiplied |
| **Pass Threshold** | Net expectancy > $0.00 at 1.0× AND 1.5× |
| **Fail Threshold** | Net expectancy ≤ $0.00 at 1.0× OR 1.5× |
| **Rival Contrast** | R1 predicts fail at all multipliers |
| **Indeterminate** | Pass at 1.0× but fail at 1.5× (fragile to cost increase) |

---

### Candidate 006: XAU-SESSION-CALENDAR-006 (Session-Controlled Calendar Seasonality)

**Core Hypothesis:** *After controlling for session (Asia/Europe/US), Exness XAUUSDm M5 returns exhibit statistically significant day-of-week, week-of-month, or month-of-year effects at specific hours (00:00, 08:00, 14:30, 17:00 UTC) that survive Exness Standard spread costs (20 pips median).*

**Rival Hypotheses:**
- **R1 (Null):** No calendar effects after session control (all patterns = session effects)
- **R2 (Session only):** All intraday seasonality = session effects (Mech 1); calendar adds nothing
- **R3 (Data mining):** Significant cells found but false discoveries (multiple testing)

#### Falsification Criterion 1: Session-Controlled Significance (FDR-Corrected)
| Element | Specification |
|---------|---------------|
| **Observable** | FDR-corrected p-values for calendar dummies in session-controlled regression |
| **Measurement** | Regress M5 returns on: Session dummies (Asia/Europe/US) + Calendar dummies (DoW, WoM, MoY) × Hour dummies (00, 08, 14:30, 17). Benjamini-Hochberg FDR at q=0.10. |
| **Pass Threshold** | ≥ 1 calendar×hour cell with FDR-corrected p < 0.10 AND correct sign consistency |
| **Fail Threshold** | Zero cells survive FDR correction |
| **Rival Contrast** | R1/R2 predict zero cells; R3 predicts cells but false discoveries |
| **Indeterminate** | Cells survive uncorrected (p<0.05) but not FDR (likely false discoveries) |
| **Aggregation Rule** | If per-cell power low, aggregate: DoW only (5×4=20 cells), MoY only (12×4=48 cells) |

#### Falsification Criterion 2: Economic Significance After Costs
| Element | Specification |
|---------|---------------|
| **Observable** | Net expectancy ($/trade) for significant calendar signals after Exness costs |
| **Measurement** | Backtest significant signals (from Criterion 1) on IS period; per-bar spread, 0.01 lots, SL=50-100pts |
| **Pass Threshold** | Net expectancy > $0.00/trade for ≥ 1 significant signal |
| **Fail Threshold** | All significant signals have net expectancy ≤ $0.00 |
| **Rival Contrast** | R1/R2 predict ≤ $0.00; R3 predicts > $0.00 IS but ≤ $0.00 OOS |
| **Indeterminate** | 1+ signals positive but < 20 trades each (low power) |

#### Falsification Criterion 3: Out-of-Sample Sign Consistency
| Element | Specification |
|---------|---------------|
| **Observable** | Sign of mean return for significant calendar cells in OOS (2025) vs IS |
| **Measurement** | Compute mean return for each IS-significant cell in OOS period |
| **Pass Threshold** | ≥ 50% of IS-significant cells have same sign in OOS (binomial test p < 0.10) |
| **Fail Threshold** | < 50% sign consistency OR binomial p ≥ 0.10 |
| **Rival Contrast** | R1/R2 predict 50% (chance); R3 predicts IS sign ≠ OOS sign |
| **Indeterminate** | < 5 significant cells in IS (binomial test underpowered) |

#### Falsification Criterion 4: Frequency Constraint Verification
| Element | Specification |
|---------|---------------|
| **Observable** | Annual trade count from significant signals |
| **Measurement** | Count trades generated by significant calendar signals in IS |
| **Pass Threshold** | Annual trades ≤ 100 (from Gate C cumulative cost constraint) |
| **Fail Threshold** | Annual trades > 100 |
| **Rival Contrast** | R3 (data mining) tends to produce many weak signals → high frequency |
| **Indeterminate** | 100-150 trades/year (marginal cost drag) |

---

### Candidate 007: XAU-ASIAN-VOL-BREAKOUT-007 (Asian Session Volatility Breakout)

**Core Hypothesis:** *When Asian session (00:00-08:00 UTC) realized volatility exceeds the 60th percentile of its trailing 60-session distribution, the direction of the Asian session breakout (close relative to midpoint) predicts the Europe session (08:00-14:30 UTC) direction after Exness costs.*

**Rival Hypotheses:**
- **R1 (Null):** Breakout direction has no predictive power (random)
- **R2 (Momentum continuation):** Asia session return sign predicts (not breakout vs midpoint) — tested in 001, failed
- **R3 (Reversal):** High-vol breakout direction predicts OPPOSITE Europe session move (overreaction fade)

#### Falsification Criterion 1: Breakout Direction Predictive Power
| Element | Specification |
|---------|---------------|
| **Observable** | Europe session return conditional on: (Asia vol > 60th pctl) AND (Breakout direction = Long/Short) |
| **Measurement** | Compute mean Europe session return for: High-vol Asia + Long breakout vs High-vol Asia + Short breakout. t-test difference. |
| **Pass Threshold** | Mean(Long) - Mean(Short) > 0 with p < 0.05 (one-sided) |
| **Fail Threshold** | Difference ≤ 0 OR p ≥ 0.05 |
| **Rival Contrast** | R1 predicts difference = 0; R2 predicts Asia return sign matters (not breakout); R3 predicts difference < 0 |
| **Indeterminate** | 0.05 ≤ p < 0.10 OR |difference| < 5 pips (economically negligible) |
| **Minimum Samples** | ≥ 30 high-vol sessions per direction in IS |

#### Falsification Criterion 2: Spread-Vol Correlation at Entry
| Element | Specification |
|---------|---------------|
| **Observable** | Correlation between Asian session realized vol and M5 spread at 08:00 UTC entry |
| **Measurement** | Pearson correlation: Asia_session_vol vs spread_08:00_M5 across all sessions |
| **Pass Threshold** | Correlation ≤ 0.3 (weak/no correlation — high vol ≠ wide spread at entry) |
| **Fail Threshold** | Correlation > 0.5 (strong positive — high vol = wide spread = cost failure) |
| **Rival Contrast** | R1 neutral; R3 irrelevant; Cost model assumes independence |
| **Indeterminate** | 0.3 < correlation ≤ 0.5 (moderate — cost headroom reduced but not eliminated) |
| **Critical** | If fail → Candidate 007 cost feasibility (Gate C) invalidated |

#### Falsification Criterion 3: Net Expectancy After Costs (IS)
| Element | Specification |
|---------|---------------|
| **Observable** | Net expectancy ($/trade) for high-vol breakout signals in IS (2021-10 to 2024-12, post burn-in) |
| **Measurement** | Backtest: Enter at 08:00 in breakout direction if Asia vol > 60th pctl (trailing 60); SL=200pts; Exit 14:30; per-bar spread |
| **Pass Threshold** | Net expectancy > $0.00/trade |
| **Fail Threshold** | Net expectancy ≤ $0.00/trade |
| **Rival Contrast** | R1/R3 predict ≤ $0.00; R2 (momentum) predicts > $0.00 but failed in 001 |
| **Indeterminate** | $0.00 < expectancy < $0.05/trade OR < 40 trades in IS |

#### Falsification Criterion 4: Regime Stability (Vol Percentile Threshold)
| Element | Specification |
|---------|---------------|
| **Observable** | Net expectancy across vol percentile thresholds (50th, 60th, 70th, 80th) |
| **Measurement** | Re-run IS backtest with vol threshold at 50th, 60th, 70th, 80th percentiles |
| **Pass Threshold** | Net expectancy > $0.00 at 60th pctl AND monotonic or stable across 50th-70th |
| **Fail Threshold** | Only works at exactly 60th (overfit) OR sign flips across thresholds |
| **Rival Contrast** | R1 predicts ≤ $0.00 at all; R3 predicts sign flip at high thresholds |
| **Indeterminate** | Works at 60th but not 50th/70th (threshold-sensitive) |

---

## 3. Cross-Candidate Falsifiability Summary

| Candidate | # Criteria | Key Falsification Risks | Gate E Result |
|-----------|------------|-------------------------|---------------|
| **005: Vol-Regime Momentum** | 4 | Regime filter overfit; unconditional fails (A17); OOS power low | **PASS** (well-specified, testable) |
| **006: Calendar Seasonality** | 4 | Multiple testing burden; low per-cell power; Paper 1 negative | **PASS** (FDR control specified, aggregation plan) |
| **007: Asian Vol Breakout** | 4 | Spread-vol correlation (Gate C risk); novel signal; threshold sensitivity | **PASS** (includes cost-correlation test) |

**All three candidates have ≥ 4 pre-registered falsification criteria with clear thresholds, rival contrasts, and indeterminate zones.**

---

## 4. Gate E Advancement Decision

**Candidates PASSING Gate E (eligible for final screening matrix):**
1. **XAU-VOL-REGIME-SESSION-005** — PASS
2. **XAU-SESSION-CALENDAR-006** — PASS
3. **XAU-ASIAN-VOL-BREAKOUT-007** — PASS

**All three Gate D survivors pass Gate E.** Proceed to Screening Gate Summary Matrix.

---

## 5. Falsification Criteria Registry (Machine-Readable)

```yaml
candidates:
  XAU-VOL-REGIME-SESSION-005:
    criteria:
      - id: "FC-005-1"
        name: "Conditional Net Expectancy"
        threshold: "> 0.00 USD/trade"
        period: "IS (2021-07 to 2024-12)"
        min_trades: 30
      - id: "FC-005-2"
        name: "Regime Interaction Significance"
        threshold: "interaction_coef > 0, p < 0.05 (one-sided)"
        period: "IS"
      - id: "FC-005-3"
        name: "OOS Persistence"
        threshold: "> 0.00 USD/trade"
        period: "OOS (2025-01 to 2025-10)"
        frozen_thresholds: true
      - id: "FC-005-4"
        name: "Cost Sensitivity Robustness"
        threshold: "> 0.00 at 1.0x AND 1.5x spread multiplier"
        period: "IS"
  
  XAU-SESSION-CALENDAR-006:
    criteria:
      - id: "FC-006-1"
        name: "FDR-Corrected Significance"
        threshold: "≥1 cell with FDR q<0.10"
        period: "IS"
        aggregation: "DoW/MoY if per-cell underpowered"
      - id: "FC-006-2"
        name: "Economic Significance After Costs"
        threshold: "> 0.00 USD/trade for ≥1 signal"
        period: "IS"
      - id: "FC-006-3"
        name: "OOS Sign Consistency"
        threshold: "≥50% sign match, binomial p<0.10"
        period: "OOS (2025)"
      - id: "FC-006-4"
        name: "Frequency Constraint"
        threshold: "≤100 trades/year"
        period: "IS"
  
  XAU-ASIAN-VOL-BREAKOUT-007:
    criteria:
      - id: "FC-007-1"
        name: "Breakout Direction Predictive Power"
        threshold: "Mean(Long)-Mean(Short) > 0, p<0.05"
        period: "IS (post burn-in)"
        min_per_direction: 30
      - id: "FC-007-2"
        name: "Spread-Vol Correlation at Entry"
        threshold: "correlation ≤ 0.3"
        period: "Full data"
      - id: "FC-007-3"
        name: "Net Expectancy After Costs"
        threshold: "> 0.00 USD/trade"
        period: "IS (2021-10 to 2024-12)"
      - id: "FC-007-4"
        name: "Threshold Stability"
        threshold: "> 0.00 at 60th pctl AND stable 50th-70th"
        period: "IS"
```

---

*End of Gate E Falsifiability Report*  
*Generated: 2026-11-25*  
*Next: Screening Gate Summary Matrix (Deliverable 7)*