# M.A.R.S. Quant — Research Programme 01
## Phase C: Strategy Hypothesis Register

**Date:** 2026-11-25  
**Source:** Mechanism Synthesis (Phase B)  
**Primary Instrument:** Exness XAUUSDm  
**Timeframes:** M5 (primary execution), H1 (context/regime), M1 (optional refinement)  
**Intended Live Capital:** USD $30

---

## Hypothesis Ranking Summary

| Rank | Strategy ID | Name | Mechanism Source | Priority | Feasibility at $30 |
|------|-------------|------|------------------|----------|-------------------|
| 1 | **XAU-SESSION-MOM-001** | Asian-Session Momentum Continuation | Mech 1 + 2 (Paper 12) | **TOP** | HIGH |
| 2 | **XAU-SESSION-OPEN-MOM-002** | Session-Open Intraday Momentum | Mech 3 (Papers 11, 10, 6, 9) | **HIGH** | HIGH |
| 3 | **XAU-US-REV-003** | US-Session Mean Reversion / Vol Fade | Mech 1 (Paper 12) | MEDIUM | MEDIUM |
| 4 | **XAU-REGIME-SESSION-004** | Volatility-Regime-Conditioned Session Momentum | Mech 4 (Papers 11, 2) | MEDIUM | MEDIUM |

---

## Detailed Hypothesis Specifications

### Strategy ID: XAU-SESSION-MOM-001
**Name:** Asian-Session Momentum Continuation  
**Research Motivation:** Paper 12 (Wei 2026) finds Asian session (00:00–08:00 UTC) produces 77.2% of gold's cumulative log return with lag-1 session autocorrelation of +0.13. Long-only session momentum yields Sharpe 1.68 after 0.02% costs. This is the **only gold-specific, session-based, cost-aware evidence** in the literature.

**Supporting Research Sources:**
- Paper 12 (Wei 2026): PRIMARY — Direct XAU/USD hourly session decomposition, momentum backtest with costs
- Paper 2 (Vojtko/Dujava): Monthly analog — Gold momentum predictive; dual-momentum refines regimes
- Paper 9 (Vojtko/Dujava): BTC overnight anomaly — Session decomposition concept

**Contradicting Research Sources:**
- Paper 1 (Baur et al.): No robust monthly timing after data-snooping — but different frequency
- Assignment 14: H1-regime Donchian REJECTED — but different mechanism (trend-following vs session momentum)

**Proposed Market Mechanism:** Post-2022 central bank gold accumulation shifted price discovery to Asian trading hours. Asian session momentum reflects persistent institutional/central bank flow imbalance that continues into subsequent sessions. The +0.13 autocorrelation indicates session-to-session predictability.

**Testable Hypothesis:** *If the Asian session (00:00–08:00 UTC) closes positive (close > open), entering long at the Europe open (08:00 UTC) and exiting at Europe close (14:30 UTC) or US open (14:30 UTC) generates positive expectancy after Exness transaction costs.*

**Instrument & Timeframe:** Exness XAUUSDm; Signal: H1 session bars (Asian, European); Execution: M5

**Entry Concept:**
- Compute Asian session return: `ret_asia = (close_08:00 - open_00:00) / open_00:00` using H1 bars (8 bars)
- If `ret_asia > threshold` (candidate: 0, or optimized in-sample), enter long at 08:00 UTC (Europe open)
- Entry on first M5 bar at 08:00 UTC (or 08:05 to avoid open auction)

**Exit Concept:**
- Primary: Exit at 14:30 UTC (Europe close / US open) — captures European session
- Alternative: Exit at 24:00 UTC (US close) — captures full day
- Stop-loss: Session low (Asian low or European low) or fixed ATR multiple
- Time-stop: Mandatory exit at 14:30 UTC (or 24:00 UTC) if SL/TP not hit

**Risk & Position-Sizing Concept:**
- Fixed fractional: 1% of equity per trade (per programme constraint)
- Volatility-targeted alternative: Risk = min(1% equity, ATR_20 * contract_size * vol_target)
- At $30 equity: 1% = $0.30 risk budget
- Exness XAUUSDm: Contract size = 100 oz, min volume = 0.01 lots, tick size = 0.01, tick value = $1.00/lot
- Min lot (0.01) = $0.10/tick = $10.00/pip (10 ticks)
- SL in ticks = $0.30 / ($10.00 * 0.01) = 3 ticks = 0.03 price units
- **CRITICAL:** 0.03 price units = 3 pips. Exness spread ~0.3 pips. SL = 10× spread. **Feasible at $30.**
- Position size = 0.01 lots (minimum) — cannot go smaller

**Required Market Data:**
- Exness XAUUSDm M5 OHLC + spread (v1.2.0 available: 369,972 bars, 2021–2025)
- H1 resampled from M5 (v1.2.0 available: 30,898 bars)
- Session timestamps: Asia 00:00–08:00, Europe 08:00–14:30, US 14:30–24:00 UTC
- FOMC calendar (for regime filter testing)

**Expected Trading Frequency:** ~1 trade/day (250/year) on days with Asian session signal. Sufficient for statistical validity (need >30 trades/year for basic significance).

**Known Weaknesses:**
1. **Regime dependence:** Paper 12 sample is Jul 2024–Aug 2026 (post-2022 central bank regime). Pre-2022 behavior unknown.
2. **Short sample:** Only 2.04 years in Paper 12. Need Exness data 2021–2025 for robust IS/OOS.
3. **Session definition:** Fixed UTC, no DST adjustment. Exness uses UTC+2/3 (DST) — session mapping must account for this.
4. **Single-study evidence:** No independent replication of Paper 12 findings.
5. **Threshold optimization:** `ret_asia > 0` vs optimized threshold — data-snooping risk if optimized.

**Potential Transaction-Cost Sensitivity:**
- Exness spread: ~0.3 pips (0.003%) vs Paper 12's 0.02% assumption → **6.7× headroom**
- Commission: $0 (Exness raw spread) or ~$3.50/round-turn lot → at 0.01 lots = $0.035/trade
- Swap: Overnight only if holding past 24:00 UTC (not in primary exit)
- Slippage: Minimal at 0.01 lots on XAUUSDm
- **Verdict:** Cost headroom is large; strategy viable if signal exists

**Falsification Criteria:**
1. On Exness M5 2021–2024 (pre-2022): Asian session does NOT dominate returns (Asia% < 50%)
2. On Exness M5 2021–2025: Session momentum autocorrelation ≤ 0 (no predictability)
3. In-sample (2021–2024): Net expectancy ≤ 0 after Exness costs at 0.01 lots
4. Out-of-sample (2025): Net expectancy ≤ 0
5. Monte Carlo (10,000 reshuffles): Observed Sharpe not in top 5% of distribution

---

### Strategy ID: XAU-SESSION-OPEN-MOM-002
**Name:** Session-Open Intraday Momentum  
**Research Motivation:** Papers 11 (Wen et al.), 10 (Padysak/Vojtko), 6 (Baur et al.), 9 (Vojtko/Dujava) find first-period returns predict session remainder in crypto/BTC. Gold has analogous session opens (00:00, 08:00, 14:30 UTC) where order flow imbalances may create predictability.

**Supporting Research Sources:**
- Paper 11 (Wen et al.): Intraday momentum (first 30-min predicts last 30-min) in crypto; patterns change with vol/FOMC/liquidity
- Paper 10 (Padysak/Vojtko): 2-hour holding strategy at NYSE open/close on BTC hourly
- Paper 6 (Baur et al.): Time-of-day effects in BTC; higher activity during US equity hours
- Paper 9 (Vojtko/Dujava): BTC overnight anomaly linked to ETF flows

**Contradicting Research Sources:**
- Paper 11: Also finds **intraday reversal** ("unique to crypto") — same paper documents both
- Paper 6: BTC patterns not persistent across sample
- No gold-specific evidence at M5

**Proposed Market Mechanism:** At session opens (Asian 00:00, European 08:00, US 14:30 UTC), overnight/pre-session order accumulation creates imbalance. First few M5 bars reveal direction of informed flow. Late-informed participants (Paper 11) or institutional execution (Paper 10 VWAP analogy) extend the move.

**Testable Hypothesis:** *The return of the first 3 M5 bars after each session open (00:00, 08:00, 14:30 UTC) positively predicts the return of the next 6 M5 bars (30 minutes) in Exness XAUUSDm, after controlling for realized volatility, FOMC days, and spread regimes.*

**Instrument & Timeframe:** Exness XAUUSDm; M5 (signal + execution)

**Entry Concept:**
- At each session open (00:00, 08:00, 14:30 UTC), wait for 3 M5 bars to close (00:15, 08:15, 14:45)
- Compute `signal_ret = (close_3 - open_0) / open_0`
- If `signal_ret > long_threshold` (e.g., > 0.05% or vol-scaled), enter long
- If `signal_ret < short_threshold` (e.g., < -0.05%), enter short
- Thresholds: Start with 0; optimize in-sample with FDR control (per Paper 5 methodology)

**Exit Concept:**
- Fixed horizon: Exit after 6 M5 bars (30 min) — matches Paper 11 "first 30-min predicts last 30-min"
- Stop-loss: 1.5× ATR_20 (M5) or session extreme
- Take-profit: 2× risk (1:2 R:R) or session VWAP
- Time-stop: Mandatory exit at 6 bars if SL/TP not hit

**Risk & Position-Sizing Concept:**
- Volatility-targeted: Risk = 1% equity per trade; Size = Risk / (SL_distance * tick_value)
- At $30 equity: Risk = $0.30
- M5 ATR_20 ~ 10–20 pips (0.10–0.20 price units) typical
- SL = 1.5× ATR ≈ 15–30 pips → $15–30 per 0.01 lot
- **At 0.01 lots: SL cost = $15–30 > $0.30 risk budget → INFEASIBLE at $30 for typical vol**
- Requires either: (a) Higher equity, (b) Smaller min lot (not available), (c) Tighter SL (1× ATR or fixed 5 pips), (d) No SL (unacceptable)
- **FIXED SL ALTERNATIVE:** 5 pips fixed SL = $5 at 0.01 lots → still > $0.30
- **CONCLUSION:** This strategy is **INFEASIBLE at $30** with standard vol-targeting. Would need ~$300 equity minimum.

**Required Market Data:**
- Exness XAUUSDm M5 OHLC + spread (available)
- Session timestamps (defined)
- Realized volatility (M5 rolling ATR/std)
- FOMC calendar
- Spread series (for liquidity filter)

**Expected Trading Frequency:** ~3 trades/day (750/year) — high frequency, good statistical power

**Known Weaknesses:**
1. **INFEASIBLE at $30** — minimum lot size breach at 1% risk (see sizing analysis)
2. No gold-specific evidence — all supporting papers are crypto/BTC
3. Mechanism (late-informed investors) may not transfer to gold (central bank/institutional)
4. Paper 11 finds BOTH momentum AND reversal — sign uncertain
5. High frequency = high transaction cost drag (spread paid 3×/day)
6. Session open auction effects (first 1–2 M5 bars) may be noisy

**Potential Transaction-Cost Sensitivity:**
- 3 trades/day × 0.3 pips spread = 0.9 pips/day = ~22.5 pips/month
- At 0.01 lots: $2.25/month spread cost
- At $30 equity: 7.5%/month cost drag — **prohibitive**
- Commission: 3× $0.035 = $0.105/day = $22/month
- **Total cost ~$25/month = 83% of equity/month — STRATEGY FAILS COST TEST**

**Falsification Criteria:**
1. Regression of first 3-bar return on next 6-bar return: coefficient ≤ 0 (no momentum)
2. After Exness costs: Net expectancy ≤ 0 at any feasible position size
3. Momentum only exists in specific regimes (high vol, FOMC) — not robust
4. Reversal dominates (negative coefficient) — Paper 11 "unique to crypto" finding

---

### Strategy ID: XAU-US-REV-003
**Name:** US-Session Mean Reversion / Volatility Fade  
**Research Motivation:** Paper 12 finds US session (14:30–24:00 UTC) has highest volatility, zero/negative drift (−13.4% cumulative), and "high-variance information trading." Session momentum loses money net of costs in US session. This suggests mean-reversion or fade strategy may work.

**Supporting Research Sources:**
- Paper 12 (Wei 2026): US session negative drift, highest vol, momentum fails net of costs
- Paper 11 (Wen et al.): Intraday reversal in crypto (overreaction to non-fundamental info)

**Contradicting Research Sources:**
- Paper 11: Reversal "unique to crypto" — may not transfer to gold
- No direct gold mean-reversion evidence at M5

**Proposed Market Mechanism:** US session driven by information trading (news, data, Fed speak) with high variance and no directional drift. Large moves represent overreaction/liquidity gaps that revert as information is digested. Fading extremes captures this reversion.

**Testable Hypothesis:** *During US session (14:30–24:00 UTC), M5 bars with returns exceeding 2× session realized volatility revert in the opposite direction within 3–6 M5 bars, generating positive expectancy after Exness costs.*

**Instrument & Timeframe:** Exness XAUUSDm; M5 (US session only: 14:30–24:00 UTC)

**Entry Concept:**
- Compute session realized vol (rolling 20 M5 bars within US session)
- When |M5_return| > 2× session_realized_vol (or > 95th percentile of session returns):
  - If return > +threshold: Enter SHORT (fade up)
  - If return < -threshold: Enter LONG (fade down)
- Enter on next M5 bar open

**Exit Concept:**
- Target: Reversion to session VWAP or session open price
- Stop-loss: 1× ATR_20 or recent swing extreme
- Take-profit: 50% of entry-to-VWAP distance or 1:1 R:R
- Time-stop: Max 6 M5 bars (30 min) or session end (24:00)

**Risk & Position-Sizing Concept:**
- Volatility-targeted: 1% equity risk
- At $30: $0.30 risk
- US session vol typically higher → wider SL needed
- **INFEASIBLE at $30** for same reasons as Strategy 002 — min lot breach
- Counter-trend in high vol = wider SL = larger position size needed for same risk

**Required Market Data:**
- Exness XAUUSDm M5 OHLC + spread (US session only)
- Session realized volatility (rolling)
- FOMC/news calendar (US session events)

**Expected Trading Frequency:** Variable (depends on outlier frequency) — est. 1–5 trades/week

**Known Weaknesses:**
1. **INFEASIBLE at $30** — high vol regime requires wider SL, breaches min lot
2. Counter-trend in high vol = adverse selection risk (trend may continue)
3. Paper 11 reversal "unique to crypto" — mechanism unproven for gold
4. US session has fundamental drivers (FOMC, NFP, Fed speak) — not pure noise
5. Low trade count → low statistical power

**Potential Transaction-Cost Sensitivity:**
- High vol = wider spreads (Exness spread widens on news)
- Counter-trend = paying spread to enter against momentum
- Slippage risk on fast reversals
- **Likely negative expectancy after costs**

**Falsification Criteria:**
1. Large US-session M5 bars do NOT revert (continuation > reversion)
2. After costs: Net expectancy ≤ 0
3. Only works on FOMC days (not robust)
4. Reversion timeframe > 30 min (session end) — not actionable at M5

---

### Strategy ID: XAU-REGIME-SESSION-004
**Name:** Volatility-Regime-Conditioned Session Momentum  
**Research Motivation:** Paper 11 shows intraday predictability changes with volatility, jumps, FOMC, liquidity. Paper 2 shows real-rate regimes condition gold returns. Combining: Session momentum (Strategies 001/002) may only work in favorable regimes.

**Supporting Research Sources:**
- Paper 11 (Wen et al.): Intraday momentum/reversal conditional on vol, jumps, FOMC, liquidity
- Paper 2 (Vojtko/Dujava): Real-rate regimes (Gold+Treasury momentum) condition gold returns
- Paper 12 (Wei 2026): Session momentum works long-only; US session fails

**Contradicting Research Sources:**
- Paper 1 (Baur et al.): Fundamental regimes not robust after data-snooping (monthly)
- No M5 gold regime evidence

**Proposed Market Mechanism:** Market microstructure and participant composition change across volatility/liquidity regimes. Low-vol/normal-liquidity regimes favor momentum (informed flow persists). High-vol/news regimes favor reversal (overreaction, noise trading). Regime filtering improves signal-to-noise.

**Testable Hypothesis:** *Strategy 001 (Asian-session momentum) or 002 (session-open momentum) generates significantly higher risk-adjusted returns when conditioned on: (a) Low realized volatility (bottom 2 quintiles), (b) Non-FOMC days, (c) Low spread (bottom 2 quintiles), compared to unconditional execution.*

**Instrument & Timeframe:** Exness XAUUSDm; H1 (regime detection) + M5 (execution)

**Entry Concept:**
- Regime filter (checked at session open):
  - Realized vol (H1, 20-bar) < 40th percentile → PASS
  - Not FOMC day → PASS
  - Current spread < 40th percentile → PASS
  - All 3 PASS → Regime = FAVORABLE
- If FAVORABLE: Execute Strategy 001 or 002 signal
- If UNFAVORABLE: No trade (flat)

**Exit Concept:** Same as parent strategy (001 or 002)

**Risk & Position-Sizing Concept:** Same as parent strategy
- Strategy 001: **Feasible at $30** (SL ~3 pips at 0.01 lots)
- Strategy 002: **Infeasible at $30** (SL ~15–30 pips at 0.01 lots)
- **Use Strategy 001 as parent**

**Required Market Data:**
- Exness XAUUSDm M5/H1 OHLC + spread (available)
- FOMC calendar (external)
- Realized vol percentiles (computable from history)
- Spread percentiles (computable)

**Expected Trading Frequency:** Reduced vs parent (regime filter) — est. 50–100 trades/year

**Known Weaknesses:**
1. **Data-snooping risk:** Regime thresholds (40th percentile) optimized in-sample
2. **Reduced sample:** Filtering cuts trades → lower statistical power
3. **Regime persistence:** Volatility regimes may not persist from signal to execution
4. **External data dependency:** FOMC calendar required
5. **No gold M5 regime evidence** — all from crypto/monthly gold

**Potential Transaction-Cost Sensitivity:**
- Fewer trades = lower total spread cost
- But regime filter may select only low-spread periods (beneficial)
- **Net: Likely improves cost profile vs unconditional**

**Falsification Criteria:**
1. Conditional Sharpe ≤ Unconditional Sharpe (no regime benefit)
2. Interaction term (signal × regime) not statistically significant
3. Out-of-sample: Regime filter degrades performance (overfit)
4. Regime definition not robust (different percentiles give different results)

---

## 5. Selection for Phase F (Implementation)

### Primary Candidate: **XAU-SESSION-MOM-001** (Asian-Session Momentum Continuation)
**Rationale:**
1. **Strongest evidence:** Only gold-specific, session-based, cost-aware study (Paper 12)
2. **Feasible at $30:** SL ~3 pips at 0.01 lots fits $0.30 risk budget
3. **Low complexity:** One signal (Asian session return), one entry (Europe open), one exit (Europe close)
4. **Adequate frequency:** ~250 trades/year → statistical validity
5. **Large cost headroom:** Exness spread 0.3 pips vs 3-pip SL = 10× buffer
6. **Falsifiable:** Clear criteria on Exness 2021–2025 data

### Secondary Candidate: **XAU-REGIME-SESSION-004** (Regime-Filtered 001)
**Rationale:**
- Tests whether regime conditioning adds value (Paper 11, 2)
- Only if 001 shows promise; regime filter as enhancement
- Same feasibility at $30

### REJECTED for $30: **XAU-SESSION-OPEN-MOM-002**, **XAU-US-REV-003**
**Rationale:** Minimum lot size breach at 1% risk. Infeasible at intended capital.

---

## 6. Next Steps (Phase D → F)

1. **Phase D:** Codebase assessment — verify existing components support session-based strategies
2. **Phase E:** Data eligibility — confirm Exness M5/H1 v1.2.0 covers 2021–2025 with session alignment
3. **Phase F:** Formal specification for XAU-SESSION-MOM-001
4. **Phase G:** In-sample research (2021–2024)
5. **Phase H:** Freeze + OOS (2025)
6. **Phase I:** Monte Carlo (10,000+ runs per Research-to-Trade Process)
7. **Phase J:** $30 feasibility (already analyzed — PASSES for 001)
8. **Phase K:** Research decision

---

*End of Strategy Hypothesis Register*  
*Generated: 2026-11-25*  
*Primary Candidate: XAU-SESSION-MOM-001*  
*Status: Ready for Phase D (Codebase Assessment)*