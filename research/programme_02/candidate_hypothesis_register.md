# M.A.R.S. Quant — Research Programme 02
## Candidate Hypothesis Register

**Date:** 2026-11-25  
**Phase:** Assignment 19 — Research Discovery, Economic Plausibility and Candidate Screening  
**Primary Instrument:** Exness XAUUSDm  
**Primary Timeframe:** M5 (H1 context, M1 optional — not available)  
**Intended Live Capital:** USD $30  
**Data Version:** Exness XAUUSDm M5 v1.2.0 (369,972 bars, 2021-07-16 to 2026-10-09), H1 v1.2.0 (30,898 bars)  
**Instrument Spec:** `configs/instrument_spec_xauusdm.yaml` (contract_size=100, min_lot=0.01, spread median 200 pts = 20 pips = $0.20/0.01 lot RT)

---

## 1. Context: Programme 01 Rejections (Lessons Learned)

| Strategy ID | Name | Mechanism Source | Rejection Reason | Gate Failed |
|-------------|------|------------------|------------------|-------------|
| **XAU-MTF-DONCHIAN-001** | H1-Regime M5 Donchian Breakout | Mech 5 (Trend/Donchian) | IS -99.8%, OOS -20%; no edge after costs | C (cost), E (falsified) |
| **XAU-SESSION-MOM-001** | Asian-Session Momentum Continuation | Mech 1+2 (Session Decomposition) | IS net expectancy -$32.40 (train), -$34.77 (test); 4/5 falsification criteria fail | C (cost), E (falsified) |
| **XAU-SESSION-OPEN-MOM-002** | Session-Open Intraday Momentum | Mech 3 (Intraday Momentum) | **Infeasible at $30** — min lot breach at 1% risk (SL 15-30 pips → $15-30 > $0.30 budget) | D ($30 feasibility) |
| **XAU-US-REV-003** | US-Session Mean Reversion / Vol Fade | Mech 1 (US Session Negative Drift) | **Infeasible at $30** — high vol regime requires wider SL, breaches min lot | D ($30 feasibility) |

**Key Constraints for Programme 02:**
- Must NOT revive or rebrand rejected strategies (XAU-SESSION-MOM-001, XAU-SESSION-OPEN-MOM-002, XAU-US-REV-003, XAU-MTF-DONCHIAN-001)
- Must learn from rejection evidence: Exness Standard spread (median 20 pips) kills session momentum continuation
- $30 feasibility requires SL ≤ 300 pts (0.3 price) at 0.01 lots → risk $0.30 max
- Mechanisms 1, 2, 3, 5 have been **directly tested and falsified** on XAUUSDm M5
- Mechanisms 4, 7, 8 remain **untested** on XAUUSDm M5
- New candidate mechanisms must be **genuinely distinct** from rejected ones

---

## 2. Five Candidate Hypotheses

### Candidate 1: XAU-VOL-REGIME-SESSION-005
**Name:** Volatility-Regime-Filtered Session Momentum  
**Mechanism Source:** Mechanism 4 (Volatility-Conditioned Predictability) — Papers 11 (Wen et al.), 2 (Vojtko/Dujava), 12 (Wei)  
**Distinction from Rejected:** NOT XAU-SESSION-MOM-001 (unconditional). Adds **regime filter** — only trades session momentum when realized vol, FOMC, spread are favorable. XAU-REGIME-SESSION-004 was registered but never tested; this is its concrete instantiation with pre-specified filters.

**Proposed Mechanism:**  
Paper 11 (crypto): Intraday momentum/reversal patterns **change** with realized vol, jumps, FOMC, liquidity. Paper 2 (gold monthly): Real-rate regimes (Gold+Treasury momentum) condition returns. Paper 12: Session momentum works long-only; US session fails. **Synthesis:** Session momentum (Asia→Europe) may only generate edge in low-vol, non-FOMC, normal-spread regimes. High vol/news regimes favor reversal or noise.

**Testable Hypothesis:**  
*Asian-session momentum continuation (Asia close > open → long Europe open) generates positive expectancy after Exness costs WHEN conditioned on: (a) H1 realized volatility (20-bar) in bottom 2 quintiles, (b) NOT an FOMC day, (c) M5 spread at entry in bottom 2 quintiles. Unconditional execution (XAU-SESSION-MOM-001) fails; conditional succeeds.*

**Instrument & Timeframe:** Exness XAUUSDm; Signal: H1 (regime) + H1 session bars; Execution: M5  
**Entry:** 08:00 UTC (Europe open) if: Asia session return > 0 AND all 3 regime filters PASS  
**Exit:** 14:30 UTC (Europe close / US open) or SL/TP  
**Risk:** Fixed fractional 1% equity; SL = session low or 200 pts (whichever tighter)  
**Frequency:** Reduced vs unconditional (~50-100 trades/year after filter)  
**Cost Sensitivity:** Lower — filter avoids high-spread regimes; median cost ~$0.20/RT at 0.01 lots

**Known Weaknesses:**
1. Data-snooping risk: Regime thresholds (40th percentile) could be optimized in-sample
2. Reduced sample: Filtering cuts trades → lower statistical power
3. Regime persistence: Volatility regime at 08:00 may not persist through 14:30
4. External dependency: FOMC calendar required (not in repo)
5. No gold M5 regime evidence — all from crypto (Paper 11) or monthly gold (Paper 2)

---

### Candidate 2: XAU-SESSION-CALENDAR-006
**Name:** Session-Controlled Calendar Seasonality  
**Mechanism Source:** Mechanism 7 (Seasonality/Calendar Effects) — Papers 1, 6, 9, 10, 11  
**Distinction from Rejected:** NOT XAU-SESSION-MOM-001/002. Tests **calendar effects independent of session momentum**. Paper 1 (monthly gold) negative after SPA; Papers 6,9,10,11 (BTC/crypto) show intraday seasonality but not persistent. **Gold M5 calendar effects untested.**

**Proposed Mechanism:**  
Institutional flows, central bank operations, options expiry, month-end rebalancing create recurring intraday patterns. **Crucial:** Must control for session effects (Asia/Europe/US) to isolate calendar from session. Session effects (Mech 1) are a form of intraday seasonality; calendar effects are orthogonal (day-of-week, week-of-month, month-of-year).

**Testable Hypothesis:**  
*After controlling for session (Asia/Europe/US), Exness XAUUSDm M5 returns exhibit statistically significant day-of-week, week-of-month, or month-of-year effects at specific hours (London open 08:00, NY open 14:30, London close 17:00, Asia open 00:00) that survive Exness Standard spread costs (20 pips median).*

**Instrument & Timeframe:** Exness XAUUSDm; M5 (signal + execution)  
**Entry:** At specific calendar-conditioned hours (e.g., Monday 08:00 long, Friday 14:30 short) based on significant effects  
**Exit:** Fixed horizon (6-12 M5 bars = 30-60 min) or session-end  
**Risk:** Fixed fractional 1% equity; SL = 5-10 pips (50-100 pts) fixed or ATR-based  
**Frequency:** ~1-5 trades/week depending on significant effects (50-250/year)  
**Cost Sensitivity:** Holding 30-60 min → spread cost critical; need >10 pips expected move net

**Known Weaknesses:**
1. Paper 1: Monthly gold seasonalities vanish after data-snooping correction (SPA test)
2. Papers 6,10: BTC patterns not persistent across sample
3. Multiple testing burden: Many calendar dimensions → FDR control required
4. Mechanism may be session effects in disguise (must partial out session)
5. Low frequency per condition → low statistical power per cell

---

### Candidate 3: XAU-ASIAN-VOL-BREAKOUT-007
**Name:** Asian Session Volatility Breakout (Directional)  
**Mechanism Source:** Mechanism 1 (Session Decomposition) + Mechanism 4 (Vol Regimes) — **novel combination**  
**Distinction from Rejected:** NOT XAU-SESSION-MOM-001 (momentum continuation). Tests **volatility breakout direction**, not return continuation. If Asia session is high-vol, the breakout direction may predict Europe session. Different signal: range/vol, not return sign.

**Proposed Mechanism:**  
Paper 12: Asian session produces 77% of returns but also has distinct volatility profile. High-vol Asian sessions may reflect resolved uncertainty (central bank action, news) where breakout direction carries information. Low-vol Asian sessions may be noise. This is a **volatility-regime-conditioned breakout**, not momentum continuation.

**Testable Hypothesis:**  
*When Asian session (00:00-08:00 UTC) realized volatility exceeds the 60th percentile of its trailing 60-session distribution, the direction of the Asian session breakout (close relative to session midpoint) predicts the Europe session (08:00-14:30 UTC) direction after Exness costs. Low-vol Asian sessions have no predictive power.*

**Instrument & Timeframe:** Exness XAUUSDm; Signal: H1 session bars (Asia vol, breakout direction); Execution: M5  
**Entry:** 08:00 UTC if: Asia session vol > 60th pctl AND breakout direction = sign(close - midpoint)  
**Exit:** 14:30 UTC or SL/TP  
**Risk:** Fixed fractional 1% equity; SL = 200 pts (0.2 price) or Asia session extreme  
**Frequency:** ~40% of days (vol > 60th pctl) → ~100 trades/year  
**Cost Sensitivity:** Similar to XAU-SESSION-MOM-001 but only trades high-vol days (wider spreads?) — need to verify

**Known Weaknesses:**
1. No direct literature support — novel combination of Mech 1 + 4
2. High-vol days may have wider spreads (Exness spread widens on news) → cost headroom reduced
3. Breakout direction may be random (efficient market in high vol)
4. Threshold (60th pctl) is arbitrary — data-snooping risk if optimized
5. Asian session vol percentile requires trailing window (lookback bias risk)

---

### Candidate 4: XAU-EUROPE-OPEN-REVERSAL-008
**Name:** Europe Open First-Bar Reversal  
**Mechanism Source:** Mechanism 3 (Intraday Momentum) — **RIVAL HYPOTHESIS** to momentum (Paper 11 finds reversal "unique to crypto")  
**Distinction from Rejected:** NOT XAU-SESSION-OPEN-MOM-002 (which tests MOMENTUM at session opens). This tests **REVERSAL** — the opposite sign. Paper 11 (Wen et al.) documents BOTH momentum AND reversal in crypto; reversal attributed to "overreaction to non-fundamental information." **Gold reversal at session opens untested.**

**Proposed Mechanism:**  
At Europe open (08:00 UTC), overnight Asian session order accumulation creates imbalance. First M5 bar may overshoot (liquidity gap, stop runs). Informed participants fade the move → reversion within 3-6 M5 bars. This is the **counter-trend rival** to Mechanism 3's momentum. Paper 11 calls reversal "unique to crypto" — falsifiable on gold.

**Testable Hypothesis:**  
*The return of the FIRST M5 bar after Europe open (08:00-08:05 UTC) NEGATIVELY predicts the return of the next 3-6 M5 bars (08:05-08:30 UTC) in Exness XAUUSDm, after controlling for realized volatility and spread. Reversal magnitude > spread cost (20 pips median).*

**Instrument & Timeframe:** Exness XAUUSDm; M5 (signal + execution)  
**Entry:** 08:05 UTC (after first M5 bar closes) in OPPOSITE direction of first bar return  
**Exit:** 08:30 UTC (6 bars = 30 min) or SL/TP  
**Risk:** Fixed fractional 1% equity; SL = 100 pts (10 pips) fixed or 1× ATR_20  
**Frequency:** 1 trade/day (Europe open only) → ~250 trades/year  
**Cost Sensitivity:** 30-min hold → spread paid once ($0.20 at 0.01 lots); need >10 pips expected reversion net

**Known Weaknesses:**
1. Paper 11: Reversal "unique to crypto" — mechanism (late-informed retail) may not transfer to gold (institutional/central bank)
2. First M5 bar at session open may be noisy (auction, gaps) — signal quality low
3. Short hold (30 min) = high turnover = high cumulative spread cost (~$50/month at 0.01 lots)
4. $30 feasibility: SL=100 pts → risk $1.00 at 0.01 lots > $0.30 budget → **INFEASIBLE at $30** unless SL ≤ 30 pts (unrealistic for reversal)
5. US session open (14:30) also testable but higher vol = wider SL needed

---

### Candidate 5: XAU-FOMC-EVENT-009
**Name:** FOMC Event-Driven Intraday Patterns  
**Mechanism Source:** Mechanism 4 (Volatility-Conditioned Predictability) — Paper 11 (FOMC days distinct), Paper 12 (US session info trading)  
**Distinction from Rejected:** NOT a continuous strategy. **Event-driven** — only trades on FOMC days (8/year). Different risk profile, different statistical framework (event study, not time-series).

**Proposed Mechanism:**  
Paper 11: Intraday patterns change on FOMC days (jumps, liquidity shifts). Paper 12: US session = "high-variance information trading." FOMC is the highest-impact scheduled event for gold (rate-sensitive). Pre-FOMC drift (positioning), post-FOMC reaction (directional), and reversal (overreaction) are documented in other assets.

**Testable Hypothesis:**  
*On FOMC announcement days (14:30 UTC), Exness XAUUSDm M5 exhibits: (a) Pre-announcement drift (13:30-14:30) in direction of eventual move, (b) Post-announcement directional move (14:30-15:30) exceeding normal vol, (c) Mean reversion within 60-120 min (overreaction fade). At least one pattern survives Exness costs and is tradable at $30.*

**Instrument & Timeframe:** Exness XAUUSDm; M5 (FOMC days only)  
**Entry:** Multiple sub-hypotheses: (a) 13:30 long/short based on positioning proxy, (b) 14:30 direction of first 3 M5 bars, (c) 15:30 fade extreme move  
**Exit:** 15:30, 16:30, or SL/TP  
**Risk:** Fixed fractional 1% equity; SL = 200 pts or event-based  
**Frequency:** 8 FOMC meetings/year × 1-3 trades = 8-24 trades/year  
**Cost Sensitivity:** Low frequency = low cumulative cost; but high vol = wider spreads on FOMC days

**Known Weaknesses:**
1. **Extremely low sample:** 8 events/year → 40 events in 5 years → no statistical power for traditional tests
2. Requires external FOMC calendar (not in repo) — Gate B dependency
3. Event study methodology needed, not standard backtest
4. Pre-FOMC drift requires positioning proxy (not available on Exness)
5. Gold reaction to FOMC changed post-2022 (central bank regime) — regime break risk

---

## 3. Candidate Summary Table

| ID | Name | Mechanism | Key Distinction from Rejected | $30 Feasibility (Prelim) | Data Dependencies |
|----|------|-----------|-------------------------------|--------------------------|-------------------|
| **005** | Vol-Regime Session Momentum | Mech 4 (Vol regimes) | Conditional on vol/FOMC/spread; not unconditional 001 | **Likely PASS** (SL=200pts, same as 001) | FOMC calendar (external) |
| **006** | Session-Controlled Calendar | Mech 7 (Seasonality) | Calendar orthogonal to session; not momentum | **Likely PASS** (SL=50-100pts feasible) | None (internal) |
| **007** | Asian Vol Breakout | Mech 1+4 (Novel combo) | Vol breakout direction, not return continuation | **Likely PASS** (SL=200pts) | None (internal) |
| **008** | Europe Open Reversal | Mech 3 (RIVAL: reversal) | Tests REVERSAL, not momentum (002) | **LIKELY FAIL** (SL~100pts → $1.00 > $0.30) | None (internal) |
| **009** | FOMC Event-Driven | Mech 4 (Event study) | Event-driven (8/yr), not continuous | **Uncertain** (depends on SL) | FOMC calendar (external) |

---

## 4. Screening Gates to Apply

Each candidate will be evaluated against **5 mandatory gates**:

| Gate | Criterion | Pass Threshold |
|------|-----------|----------------|
| **A** | Economic Plausibility | Mechanism grounded in market microstructure / institutional behavior; not purely statistical pattern |
| **B** | Data Eligibility | All required data available in Exness XAUUSDm M5/H1 v1.2.0 OR external source documented with access plan |
| **C** | Spread/Cost Feasibility | Expected net expectancy > 0 after Exness Standard spread (median 20 pips = $0.20/0.01 lot RT) + commission ($0) + slippage (assumed 0) |
| **D** | $30 Account Feasibility | Minimum lot (0.01) at configured SL ≤ $0.30 risk budget (1% of $30). **Hard rule: min-volume breach → REJECT trade** |
| **E** | Falsifiability | Pre-registered test with clear pass/fail criteria; observable implication; rival prediction contrast |

**Advancement Rule:** Maximum 2 candidates may advance. If none pass all 5 gates, report zero — **do not manufacture shortlist**.

---

## 5. Source Classification for This Register

| Statement Type | Examples in This Document |
|----------------|---------------------------|
| **Measured Fact** | Exness spread median = 200 pts (from data catalog); contract_size = 100 (from instrument spec); 369,972 M5 bars (from catalog) |
| **Published Finding** | Paper 12: Asia session 77% of returns, autocorr +0.13; Paper 11: crypto intraday momentum/reversal conditional on vol/FOMC; Paper 1: monthly gold timing fails SPA test |
| **Assumption** | Exness Standard account (spread 20 pips); 1% risk fraction; SL=200pts default; FOMC 8/year; vol percentile thresholds (40th/60th) |
| **Estimate** | Trade frequencies (~250/yr, ~100/yr, ~50/yr); cost per trade ($0.20); risk at min lot ($0.20); monthly cost drag ($25-50) |

---

*End of Candidate Hypothesis Register*  
*Generated: 2026-11-25*  
*Next: Economic Plausibility Assessment (Gate A)*