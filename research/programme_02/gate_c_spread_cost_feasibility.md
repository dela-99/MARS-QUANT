# M.A.R.S. Quant — Research Programme 02
## Gate C: Spread / Cost Feasibility Report

**Date:** 2026-11-25  
**Phase:** Assignment 19 — Research Discovery, Economic Plausibility and Candidate Screening  
**Input:** Gate B survivors (3 candidates): 005, 006, 007  
**Cost Baseline:** Exness XAUUSDm Standard account (verified from data + instrument spec)  
**Key Verified Cost Parameters:**
- Median spread: 200 points = 0.2 price units = 20 pips = **$0.20 per 0.01 lot round-trip**
- Spread distribution: Mean 201.4, Std 50.1, Max 3,352 pts (335 pips), Min 0 pts
- Commission: $0.00 (Standard account)
- Slippage: 0 pts assumed (configurable sensitivity)
- Swap: $0.00 (intraday holds, exit same session)
- Zero-spread bars (98, 0.03%): Substituted with dataset median (200 pts)

---

## 1. Cost Model Framework

### 1.1 Round-Trip Cost Calculation
```
Raw spread (points) × point_size (0.001) = price distance
Price distance × contract_size (100 oz) = $ per standard lot
$ per lot × position_lots = $ per trade
```
**Verified:** 200 pts × 0.001 = 0.2 price → 0.2 × 100 = $20/lot → **$0.20 per 0.01 lot RT**

### 1.2 Backtester Cost Application (from `session_momentum_backtest.py`, Assignment 17 Audit)
- **Entry:** Long buys at `bar_open + spread` (pays ask)
- **Exit:** Long sells at `bar_open` (receives bid)
- **Round-trip spread:** Exactly **1 × observed spread** per trade (not double-counted)
- **Per-bar observed spread used** (distribution preserved, not constant)
- **Multiplier sensitivity** tested at 1.0, 1.5, 2.0×

### 1.3 Cost Feasibility Threshold
**Gate C Pass Criterion:** Expected net expectancy > $0.00 per trade after Exness Standard costs at minimum viable position size (0.01 lots).

---

## 2. Candidate-by-Candidate Cost Analysis

### Candidate 005: XAU-VOL-REGIME-SESSION-005 (Vol-Regime Session Momentum)

**Trade Profile:**
- Holding period: ~6.5 hours (08:00 → 14:30 UTC)
- Frequency: ~50-100 trades/year (regime filter reduces from ~250)
- Entry: 08:00 UTC (Europe open) — typically normal liquidity
- Exit: 14:30 UTC (Europe close / US open) — typically normal liquidity
- Regime filter: Spread at entry in bottom 2 quintiles (≤ 40th percentile)

**Spread at Entry Analysis:**
- Full dataset spread 40th percentile: ~180 points (18 pips) — estimated from median 200, std 50
- Regime filter **explicitly selects low-spread periods** → cost headroom improved
- Expected median spread at entry: ~160-180 pts (16-18 pips) = **$0.16-0.18 per 0.01 lot RT**

**Expected Gross Move:**
- Paper 12 (Wei 2026): Asia session return predicts Europe session; long-only Sharpe 1.68 after 0.02% costs
- 0.02% = 2 pips on ~$2,650/oz → Paper 12 cost assumption **6.7× tighter** than Exness Standard (20 pips)
- Unconditional XAU-SESSION-MOM-001 **failed** at Exness Standard costs (net expectancy -$34.77)
- **Hypothesis:** Regime filter (low vol, non-FOMC, low spread) recovers edge by avoiding cost-destructive regimes

**Cost Sensitivity Scenarios:**
| Scenario | Spread at Entry | RT Cost (0.01 lot) | Required Gross Expectancy | Verdict |
|----------|-----------------|---------------------|---------------------------|---------|
| Optimistic (filtered) | 160 pts (16 pips) | $0.16 | > $0.16 | **Feasible if signal > 16 pips** |
| Median (unfiltered) | 200 pts (20 pips) | $0.20 | > $0.20 | **Unconditional fails (A17 proof)** |
| Pessimistic (spread spike) | 400 pts (40 pips) | $0.40 | > $0.40 | Likely infeasible |

**Key Question:** Does regime filter select periods where signal > 16-18 pips?
- Paper 12: Europe session mean return conditional on Asia positive = not directly reported
- Unconditional Europe session mean = +36.2% of cumulative (Paper 12) but includes all regimes
- **Unknown:** Conditional mean in low-vol/low-spread regime

**Gate C Verdict: CONDITIONAL PASS**  
Cost structure is favorable **if** regime filter works. Filter explicitly avoids high-spread periods. Unconditional version fails (proven in Assignment 17). **Feasibility hinges entirely on regime filter efficacy** — must be tested empirically.

---

### Candidate 006: XAU-SESSION-CALENDAR-006 (Session-Controlled Calendar Seasonality)

**Trade Profile:**
- Holding period: 30-60 minutes (6-12 M5 bars)
- Frequency: ~50-250 trades/year (depends on significant calendar effects)
- Entry: Specific hours (00:00, 08:00, 14:30, 17:00 UTC)
- Exit: Fixed horizon or session-end
- Multiple calendar conditions → multiple sub-strategies

**Spread at Entry Analysis:**
- 00:00 UTC (Asia open): Typically lower liquidity → wider spreads (median may exceed 200 pts)
- 08:00 UTC (Europe open): London open → high liquidity → tighter spreads (median ~180-200 pts)
- 14:30 UTC (US open): NY open + Europe overlap → highest liquidity → tightest spreads (median ~160-180 pts)
- 17:00 UTC (London close): Liquidity draining → wider spreads

**Expected Gross Move per Trade:**
- Short hold (30-60 min) → expected move small
- M5 ATR_20 typical: 10-20 pips (0.10-0.20 price units)
- Signal must overcome: spread (16-25 pips) + slippage buffer
- **Required signal: > 20-30 pips per trade** to be net positive after costs

**Cost Sensitivity Scenarios:**
| Entry Hour | Est. Median Spread | RT Cost (0.01 lot) | Required Signal | Feasibility |
|------------|-------------------|---------------------|-----------------|-------------|
| 00:00 (Asia open) | 220 pts (22 pips) | $0.22 | > 22 pips | **Marginal** |
| 08:00 (Europe open) | 190 pts (19 pips) | $0.19 | > 19 pips | **Feasible if signal exists** |
| 14:30 (US open) | 170 pts (17 pips) | $0.17 | > 17 pips | **Most feasible** |
| 17:00 (London close) | 230 pts (23 pips) | $0.23 | > 23 pips | **Marginal** |

**Cumulative Cost Drag:**
- At 250 trades/year × $0.20 avg = $50/year spread cost
- At $30 equity = **167% annual cost drag** — prohibitive unless win rate + expectancy very high
- At 50 trades/year × $0.20 = $10/year = 33% annual drag — manageable

**Gate C Verdict: CONDITIONAL PASS (with frequency constraint)**  
**Only feasible if trade frequency ≤ 100/year** (annual cost drag ≤ 66%). Higher frequency strategies fail cost test. **Must demonstrate** that significant calendar effects are sparse (not every day/week). Paper 1 (monthly gold) and Paper 6 (BTC) suggest calendar effects are weak/non-persistent — frequency likely low. **Feasibility depends on sparsity of significant effects.**

---

### Candidate 007: XAU-ASIAN-VOL-BREAKOUT-007 (Asian Session Volatility Breakout)

**Trade Profile:**
- Holding period: ~6.5 hours (08:00 → 14:30 UTC) — same as Candidate 005
- Frequency: ~100 trades/year (40% of days = vol > 60th pctl)
- Entry: 08:00 UTC (Europe open) — normal liquidity
- Exit: 14:30 UTC (Europe close / US open)
- **Critical difference from 005:** Trades **high-vol Asian sessions only**

**Spread at Entry Analysis:**
- High-vol Asian sessions often coincide with news/events → **spreads may be wider at 08:00 UTC**
- Exness spread max 3,352 pts (335 pips) observed during high-vol periods
- Median spread on high-vol days: **Unknown** — must be measured from data
- Risk: Vol filter selects high-spread periods → **cost headroom reduced**

**Expected Gross Move:**
- Breakout direction signal: No direct literature
- Asia session range on high-vol days: Larger moves → potentially larger Europe session continuation
- But: High vol = more noise, wider spreads, higher adverse selection
- Paper 12: US session (high vol) has negative drift and momentum fails — **warning for high-vol regimes**

**Cost Sensitivity Scenarios:**
| Scenario | Est. Spread at 08:00 | RT Cost (0.01 lot) | Required Gross Expectancy |
|----------|---------------------|---------------------|---------------------------|
| Optimistic (vol ≠ wide spread) | 200 pts (20 pips) | $0.20 | > 20 pips |
| Realistic (vol → wider spread) | 300 pts (30 pips) | $0.30 | > 30 pips |
| Pessimistic (news day) | 500 pts (50 pips) | $0.50 | > 50 pips |

**Key Risk:** Positive correlation between Asian session vol and 08:00 UTC spread. If high-vol Asian sessions → wide spreads at Europe open, cost advantage evaporates. **Must verify empirically.**

**Gate C Verdict: CONDITIONAL PASS (with spread-vol correlation risk)**  
Same holding period as Candidate 005 but **trades high-vol regime** (opposite filter). Cost feasibility **uncertain** — depends on spread-vol correlation at 08:00 UTC. If high-vol Asian sessions have normal spreads at 08:00, feasible. If spreads widen, likely infeasible. **Requires empirical measurement.**

---

## 3. Cross-Candidate Cost Comparison

| Candidate | Hold Period | Est. Freq/Year | Est. Median Spread at Entry | RT Cost/Trade | Annual Cost Drag ($30) | Cost Feasibility |
|-----------|-------------|----------------|----------------------------|---------------|------------------------|------------------|
| **005: Vol-Regime Momentum** | 6.5 hrs | 50-100 | 160-180 pts (filtered) | $0.16-0.18 | $8-18 (27-60%) | **Conditional: Filter must work** |
| **006: Calendar Seasonality** | 30-60 min | 50-250 | 170-230 pts (hour-dep) | $0.17-0.23 | $8.5-57.5 (28-192%) | **Conditional: Freq ≤ 100/yr** |
| **007: Asian Vol Breakout** | 6.5 hrs | ~100 | 200-500 pts (vol-dep) | $0.20-0.50 | $20-50 (67-167%) | **Conditional: Spread-vol correlation** |

**Reference: XAU-SESSION-MOM-001 (Rejected)**
- Hold: 6.5 hrs | Freq: ~250 | Spread: 200 pts | Cost: $0.20 | Annual: $50 (167%) | **FAILED** (net expectancy -$34.77)

**Key Insight:** All three candidates have **lower or equal frequency** vs rejected 001, but **005 and 007 have same hold period**. Cost feasibility depends on:
1. **005:** Regime filter selecting periods where signal > cost (unconditional fails)
2. **006:** Sparsity of significant calendar effects (frequency constraint)
3. **007:** Spread-vol correlation at entry time (high-vol ≠ wide spread?)

---

## 4. Gate C Summary: Spread/Cost Feasibility Pass/Fail

| Candidate | Cost Structure | Key Risk | Gate C Result |
|-----------|----------------|----------|---------------|
| **005: XAU-VOL-REGIME-SESSION-005** | Favorable (filter avoids high spread) | Filter efficacy unproven; unconditional fails | **CONDITIONAL PASS** |
| **006: XAU-SESSION-CALENDAR-006** | Favorable per trade; cumulative drag at high freq | Frequency must be low; calendar effects weak historically | **CONDITIONAL PASS** (freq ≤ 100/yr) |
| **007: XAU-ASIAN-VOL-BREAKOUT-007** | Uncertain (high-vol may = high spread) | Spread-vol correlation at 08:00 UTC unknown | **CONDITIONAL PASS** (requires measurement) |

**All three candidates receive CONDITIONAL PASS.** None are outright infeasible on cost grounds, but all require empirical validation of their cost-advantage mechanism. Proceed to Gate D ($30 Account Feasibility) where hard constraints apply.

---

## 5. Cost Assumptions Carried Forward

| Assumption | Value | Source | Sensitivity Tested |
|------------|-------|--------|-------------------|
| Exness account type | Standard (not Raw Spread) | Data catalog spread median 200 pts = 20 pips | N/A (data-verified) |
| Commission | $0.00/lot RT | Instrument spec | N/A |
| Slippage | 0 points (base) | Config default | 1.0, 1.5, 2.0× spread multiplier |
| Swap | $0.00 (intraday) | Instrument spec (intraday holds) | N/A |
| Zero-spread substitution | Dataset median (200 pts) | Backtester config | N/A |
| Position size for cost calc | 0.01 lots (minimum) | Gate D constraint | N/A |

---

*End of Gate C Spread/Cost Feasibility Report*  
*Generated: 2026-11-25*  
*Next: Gate D $30 Account Feasibility Report*