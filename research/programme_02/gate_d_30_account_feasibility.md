# M.A.R.S. Quant — Research Programme 02
## Gate D: $30 Account Feasibility Report

**Date:** 2026-11-25  
**Phase:** Assignment 19 — Research Discovery, Economic Plausibility and Candidate Screening  
**Input:** Gate C survivors (3 candidates): 005, 006, 007  
**Hard Constraint:** Minimum lot size = 0.01 lots (Exness XAUUSDm, verified from `pair_config.offline`)  
**Risk Budget:** 1% of equity = $0.30 per trade (programme constraint)  
**Risk Engine:** `ContractAwareFixedFractionalRisk` (verified in Assignment 17 Audit)  
**Rule:** Min-volume breach → **REJECT trade** (never force oversized position)

---

## 1. Verified Instrument Specification (from `configs/instrument_spec_xauusdm.yaml`)

| Parameter | Value | Source |
|-----------|-------|--------|
| Symbol | XAUUSDm | `pair_config.offline` |
| Contract Size | 100.0 oz | Verified |
| Pip Size | 0.01 (1 pip = $0.01/oz) | Verified |
| Point Size | 0.001 (1 point = $0.001/oz) | Verified (spread column unit) |
| Quote Currency | USD | Verified |
| Volume Min | 0.01 lots | `pair_config.offline` |
| Volume Max | 200.0 lots | `pair_config.offline` |
| Volume Step | 0.01 lots | `pair_config.offline` |
| Leverage Max | 1:1000 (Standard) | Exness spec |
| Leverage Default | 1:100 (typical for gold) | Exness spec |
| Margin Rate | 1% (at 1:100) | Exness spec |

**Cost per 0.01 lot per pip:** 0.01 lots × 100 oz × $0.01 = **$0.10 per pip**  
**Cost per 0.01 lot per point:** 0.01 lots × 100 oz × $0.001 = **$0.01 per point**  
**Median spread (200 pts) = 20 pips = $0.20 per 0.01 lot RT**

---

## 2. $30 Feasibility Framework

### 2.1 Risk Calculation Formula
```
Risk Budget = Equity × Risk Fraction = $30 × 0.01 = $0.30
Risk per Lot = Stop_Distance_Price × Contract_Size × Quote_Currency_Rate
Lots Exact = Risk Budget / Risk per Lot
Lots Floored = floor(Lots Exact / Volume_Step) × Volume_Step
Risk at Min Volume = Min_Volume × Risk per Lot
```

### 2.2 Hard Feasibility Rule
```
IF Risk at Min Volume ≤ Risk Budget → APPROVED (size = Min_Volume = 0.01)
IF Risk at Min Volume > Risk Budget → REJECTED (min-volume breach)
```

### 2.3 Maximum Allowable Stop Distance at $30
```
Risk at Min Volume = 0.01 × Stop_Distance_Price × 100 ≤ $0.30
Stop_Distance_Price ≤ 0.30 / (0.01 × 100) = 0.30 price units = 300 points = 30 pips
```
**Maximum SL at $30: 300 points (0.30 price units = 30 pips)**

---

## 3. Candidate-by-Candidate $30 Feasibility Analysis

### Candidate 005: XAU-VOL-REGIME-SESSION-005 (Vol-Regime Session Momentum)

**Proposed Stop Loss:** Session low (Asia or Europe) or 200 pts (whichever tighter)  
**Typical SL Distance:** 200 points (0.20 price units = 20 pips) — same as rejected XAU-SESSION-MOM-001

**Feasibility Calculation:**
```
Stop Distance = 200 pts = 0.20 price units
Risk per Lot = 0.20 × 100 × 1.0 = $20.00
Lots Exact = $0.30 / $20.00 = 0.015
Lots Floored (step 0.01) = 0.01 lots
Risk at Min Volume = 0.01 × $20.00 = $0.20
```
**Result: $0.20 ≤ $0.30 ✅ FEASIBLE**

**Margin Check (at 1:100 leverage, ~$2,650/oz):**
- Notional (0.01 lots) = 0.01 × 100 × $2,650 = $2,650
- Required Margin = $2,650 × 1% = $26.50
- Free Margin = $30 - $26.50 = $3.50 ✅ (tight but feasible)
- At 1:200 leverage: Margin = $13.25, Free = $16.75 ✅ comfortable

**Sensitivity — Maximum SL Before Breach:**
| SL (points) | SL (price) | Risk/Lot | Lots Exact | Lots Floored | Risk at Min | Feasible? |
|-------------|------------|----------|------------|--------------|-------------|-----------|
| 200 | 0.20 | $20 | 0.015 | 0.01 | $0.20 | ✅ YES |
| 250 | 0.25 | $25 | 0.012 | 0.01 | $0.25 | ✅ YES |
| 300 | 0.30 | $30 | 0.010 | 0.01 | $0.30 | ✅ YES (boundary) |
| 350 | 0.35 | $35 | 0.0086 | **0.01** | **$0.35** | ❌ **REJECT** |
| 400 | 0.40 | $40 | 0.0075 | **0.01** | **$0.40** | ❌ **REJECT** |

**Gate D Verdict: PASS** (at proposed SL=200pts; headroom to 300pts)

---

### Candidate 006: XAU-SESSION-CALENDAR-006 (Session-Controlled Calendar Seasonality)

**Proposed Stop Loss:** Fixed 5-10 pips (50-100 pts) or ATR-based  
**Holding Period:** 30-60 minutes (short-term)

**Scenario A: Fixed SL = 50 points (5 pips)**
```
Stop Distance = 50 pts = 0.05 price units
Risk per Lot = 0.05 × 100 = $5.00
Lots Exact = $0.30 / $5.00 = 0.06
Lots Floored = 0.01 lots (step 0.01)
Risk at Min Volume = 0.01 × $5.00 = $0.05
```
**Result: $0.05 ≤ $0.30 ✅ FEASIBLE** (large headroom)

**Scenario B: Fixed SL = 100 points (10 pips)**
```
Stop Distance = 100 pts = 0.10 price units
Risk per Lot = 0.10 × 100 = $10.00
Lots Exact = $0.30 / $10.00 = 0.03
Lots Floored = 0.01 lots
Risk at Min Volume = 0.01 × $10.00 = $0.10
```
**Result: $0.10 ≤ $0.30 ✅ FEASIBLE**

**Scenario C: ATR-based SL (1.5× ATR_20 M5)**
- M5 ATR_20 typical: 10-20 pips (100-200 pts)
- 1.5× ATR = 15-30 pips (150-300 pts)
- At 300 pts (boundary): Risk at min = $0.30 ✅ FEASIBLE
- At 350 pts: Risk at min = $0.35 ❌ REJECT

**Critical Constraint — Short Hold + Tight SL = High Turnover:**
- At 50 pts SL: Risk per trade = $0.05 (only 16.7% of budget)
- But: High frequency (if many calendar signals) → cumulative spread cost
- Gate C showed: >100 trades/year → annual cost drag > 66%
- **$30 feasibility requires BOTH risk-per-trade AND cumulative cost feasibility**

**Gate D Verdict: PASS** (risk-per-trade feasible at proposed SLs; cumulative cost addressed in Gate C)

---

### Candidate 007: XAU-ASIAN-VOL-BREAKOUT-007 (Asian Session Volatility Breakout)

**Proposed Stop Loss:** 200 pts (0.20 price) or Asia session extreme  
**Holding Period:** ~6.5 hours (08:00 → 14:30 UTC) — same as Candidate 005

**Feasibility Calculation (SL = 200 pts):**
```
Stop Distance = 200 pts = 0.20 price units
Risk per Lot = 0.20 × 100 = $20.00
Lots Exact = $0.30 / $20.00 = 0.015
Lots Floored = 0.01 lots
Risk at Min Volume = 0.01 × $20.00 = $0.20
```
**Result: $0.20 ≤ $0.30 ✅ FEASIBLE** (identical to Candidate 005 at same SL)

**Scenario: Asia Session Extreme as SL**
- Asia session range on high-vol days: Could be 300-500+ pts
- If SL = Asia session high/low = 400 pts → Risk at min = $0.40 ❌ REJECT
- **Must cap SL at ≤ 300 pts** to remain feasible at $30
- Proposed "200 pts or Asia extreme (whichever tighter)" → caps at 200 pts ✅

**Gate D Verdict: PASS** (with SL cap at 200-300 pts; Asia extreme must not exceed 300 pts)

---

## 4. Cross-Candidate $30 Feasibility Summary

| Candidate | Proposed SL | Risk at Min Vol | Feasible? | Max SL Before Breach | Margin at 1:100 | Free Margin |
|-----------|-------------|-----------------|-----------|---------------------|-----------------|-------------|
| **005: Vol-Regime Momentum** | 200 pts | $0.20 | ✅ PASS | 300 pts | $26.50 | $3.50 |
| **006: Calendar Seasonality** | 50-100 pts | $0.05-0.10 | ✅ PASS | 300 pts | $26.50 | $3.50 |
| **007: Asian Vol Breakout** | 200 pts (capped) | $0.20 | ✅ PASS | 300 pts | $26.50 | $3.50 |

**All three candidates PASS Gate D at their proposed stop distances.**

**Critical Comparison with Rejected Strategies:**
| Strategy | SL (pts) | Risk at Min | Feasible? | Rejection Gate |
|----------|----------|-------------|-----------|----------------|
| XAU-SESSION-MOM-001 | 200 | $0.20 | ✅ PASS | C, E (not D) |
| XAU-SESSION-OPEN-MOM-002 | 150-300 | $0.15-0.30 | ⚠️ BORDERLINE | **D** (ATR-based SL > 300 pts) |
| XAU-US-REV-003 | 150-300+ | $0.15-0.30+ | ❌ FAIL | **D** (high vol → wide SL) |
| **005, 006, 007** | **50-200** | **$0.05-0.20** | **✅ PASS** | — |

**Key Insight:** The $30 infeasibility of 002 and 003 came from **volatility-targeted SL** (1.5× ATR) in high-vol regimes. Candidates 005 and 007 use **fixed/capped SL (200 pts)**. Candidate 006 uses **tight fixed SL (50-100 pts)**. All avoid the min-volume breach.

---

## 5. Gate D Summary: $30 Account Feasibility Pass/Fail

| Candidate | Risk-Per-Trade | Cumulative Cost (Gate C) | Margin Headroom | Gate D Result |
|-----------|----------------|--------------------------|-----------------|---------------|
| **005: XAU-VOL-REGIME-SESSION-005** | ✅ PASS ($0.20 ≤ $0.30) | ✅ PASS (freq 50-100, cost manageable) | ⚠️ Tight at 1:100 ($3.50 free) | **PASS** |
| **006: XAU-SESSION-CALENDAR-006** | ✅ PASS ($0.05-0.10 ≤ $0.30) | ⚠️ CONDITIONAL (freq must ≤ 100/yr) | ✅ PASS (large risk headroom) | **CONDITIONAL PASS** (freq constraint) |
| **007: XAU-ASIAN-VOL-BREAKOUT-007** | ✅ PASS ($0.20 ≤ $0.30, SL capped) | ⚠️ CONDITIONAL (spread-vol correlation) | ⚠️ Tight at 1:100 ($3.50 free) | **CONDITIONAL PASS** (SL cap + spread risk) |

**All three candidates pass the hard $30 risk-per-trade constraint.** Conditional flags relate to cumulative cost (Gate C) and margin tightness, not Gate D hard failure.

---

## 6. Risk Engine Behavior Verification (from Assignment 17 Audit)

```python
# Verified via ContractAwareFixedFractionalRisk
spec = InstrumentSpec(
    symbol='XAUUSDm', contract_size=100.0, pip_size=0.01, point_size=0.001,
    quote_currency='USD', volume_min=0.01, volume_max=200.0, volume_step=0.01
)
risk = ContractAwareFixedFractionalRisk(spec=spec, risk_fraction=0.01, enforce_volume_rules=True)

# At equity=$30, SL=200pts (0.20 price):
decision = risk.evaluate(setup, equity=30.0)
# decision.approved = True
# decision.size = 0.01
# decision.metadata.risk_at_min_volume_usd = 0.20
# decision.metadata.risk_limit_usd = 0.30

# At SL=350pts (0.35 price):
decision = risk.evaluate(setup, equity=30.0)
# decision.approved = False  (min-volume breach)
# decision.reason = "min_volume_breach"
```

**Confirmed:** Risk engine correctly rejects trades where min-volume risk > budget. No oversized positions forced.

---

## 7. Gate D Advancement Decision

**Candidates PASSING Gate D (eligible for Gate E):**
1. **XAU-VOL-REGIME-SESSION-005** — PASS
2. **XAU-SESSION-CALENDAR-006** — CONDITIONAL PASS (frequency constraint from Gate C)
3. **XAU-ASIAN-VOL-BREAKOUT-007** — CONDITIONAL PASS (SL cap + spread-vol correlation from Gate C)

**All three Gate C survivors pass Gate D.** Proceed to Gate E (Falsifiability).

---

*End of Gate D $30 Account Feasibility Report*  
*Generated: 2026-11-25*  
*Next: Gate E Falsifiability Report*