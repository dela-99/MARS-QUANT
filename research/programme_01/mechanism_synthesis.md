# M.A.R.S. Quant — Research Programme 01
## Phase B: Mechanism Extraction and Cross-Paper Synthesis

**Date:** 2026-11-25  
**Source:** 14 research papers + 1 process reference (Literature Evidence Register)  
**Primary Instrument:** Exness XAUUSDm  
**Timeframes:** M5 (primary), H1 (context), M1 (optional refinement)

---

## 1. Identified Market Mechanisms Across Literature

### Mechanism 1: Session Return Decomposition & Asymmetric Session Contribution
**Supporting Papers:** **12 (Wei 2026 — PRIMARY, VERY HIGH relevance)**  
**Contradicting Papers:** None directly; Paper 1 (monthly) finds no timing ability but at different frequency  
**Asset Specificity:** **Gold-specific (XAU/USD spot)** — only paper studying gold sessions directly  
**Horizon:** Hourly sessions (Asia 00–08, Europe 08–14:30, US 14:30–24 UTC) → 2.04 years (Jul 2024–Aug 2026)  
**Independent Replication:** Single study (Wei 2026); no independent replication yet  
**Statistical/Economic Significance:** 
- Asia: +77.2% of gold cumulative log return (positive every calendar year)
- Europe: +36.2%
- US: −13.4% (highest volatility, zero/negative drift)
- Lag-1 session autocorrelation: Gold +0.13, Silver +0.12 (concentrated in Asia continuation)
- Long-only session momentum: Net Sharpe 1.68 (gold), 0.84 (silver) after 0.02% cost
- Max DD cut from ~54% to ~26% (silver)

**Survives Transaction Costs:** **YES** — at 0.02% per position change (conservative institutional), long-only variant survives; long/short fails

**Transferability to Exness XAUUSDm M5/H1:** **HIGH** — Session structure (Asian/European/US) maps directly to FX sessions. M5 bars align with session boundaries. Exness spread ~0.2–0.4 pips (0.002–0.004%) — tighter than 0.02% assumption. H1 bars = 12 M5 bars per session.

**Unproven:** 
- Only 2.04 years (post-2022 regime); pre-2022 behavior unknown
- Stooq hourly data, not Exness M5
- No DST adjustment in session definitions
- No out-of-sample beyond Aug 2026
- Mechanism attributed to "central bank accumulation shifted pricing eastward" — regime-dependent

**Falsification Experiment:** 
- Run session decomposition on Exness XAUUSDm M5 data (2021–2025) — verify Asian session dominance persists pre-2022
- Test session momentum (long next session if current > 0) on M5/H1 with Exness costs
- Test if autocorrelation holds at M5 frequency (not just session-level)

---

### Mechanism 2: Cross-Session Momentum (Session-to-Session Predictability)
**Supporting Papers:** **12 (Wei 2026)**, **2 (Vojtko/Dujava — monthly analog)**, **9 (Vojtko/Dujava — BTC overnight)**  
**Contradicting Papers:** None  
**Asset Specificity:** Gold (12), Gold+Treasuries monthly (2), Bitcoin (9)  
**Horizon:** Session-to-session (12: hourly), Monthly (2), Overnight (9)  
**Independent Replication:** No — single study per asset/frequency  
**Statistical/Economic Significance:** 
- Paper 12: Lag-1 session autocorr +0.13 (gold), +0.12 (silver) — statistically significant at hourly
- Paper 2: Dual-momentum regime improves Sharpe 0.42→0.51 at monthly
- Paper 9: BTC overnight anomaly (incomplete excerpt)

**Survives Transaction Costs:** Paper 12: YES (long-only at 0.02%); Paper 2: Not modelled; Paper 9: Not modelled

**Transferability to Exness XAUUSDm M5/H1:** **HIGH** — Session momentum at hourly → testable at M5 (12 bars/session). Can test: "If Asia session close > open, long Europe open" etc.

**Unproven:**
- Whether M5-level momentum within session matches session-level momentum
- Whether momentum persists across session boundaries at M5 frequency
- Optimal lookback: 1 session (Paper 12) vs longer (Paper 2)

**Falsification Experiment:**
- Compute M5 returns within each session; test if first M5 bar predicts session remainder
- Test cross-session: Asia close → Europe open; Europe close → US open; US close → Asia open
- Compare Exness spread-inclusive vs Paper 12's 0.02%

---

### Mechanism 3: Intraday Momentum (First-Half Predicts Second-Half)
**Supporting Papers:** **11 (Wen et al. — crypto)**, **10 (Padysak/Vojtko — BTC hourly)**, **6 (Baur et al. — BTC time-of-day)**, **9 (Vojtko/Dujava — BTC overnight)**  
**Contradicting Papers:** **11** also finds **intraday reversal** (unique to crypto) — same paper documents both  
**Asset Specificity:** Cryptocurrencies (BTC, ETH, LTC, XRP) — **NOT gold**  
**Horizon:** Minute-level (11), Hourly (10), Intraday sessions (6, 9)  
**Independent Replication:** Multiple crypto studies (11, 10, 6, 9) but all crypto; no gold replication  
**Statistical/Economic Significance:** 
- Paper 11: First 30-min return predicts last 30-min return positively (momentum); also reversal pattern
- Paper 10: 2-hour holding strategy works; NYSE open/close effects
- Paper 6: Time-of-day patterns but not persistent
- Paper 9: Overnight anomaly linked to ETF flows

**Survives Transaction Costs:** Paper 11: Economic value vs benchmarks reported but cost model not explicit; Papers 6, 9, 10: Not modelled

**Transferability to Exness XAUUSDm M5/H1:** **MEDIUM** — Concept transfers (session open → session close predictability) but:
- Crypto 24/7 vs Gold session-based (distinct open/close)
- Crypto retail-dominated vs Gold institutional/central bank
- Different microstructure (no "first 30-min" in 24/7; but session opens exist)
- Paper 11 mechanism: "late-informed investors" — may not apply to gold

**Unproven for Gold:**
- Whether first M5 bars of session predict session remainder
- Whether mechanism is late-informed investors (equity-like) or central bank flows (gold-specific)
- Whether reversal also exists in gold (Paper 11 says reversal "unique to crypto")

**Falsification Experiment:**
- At each session open (00:00, 08:00, 14:30 UTC), measure first 3–5 M5 bars return
- Regress on session remaining return (or next N M5 bars)
- Control for: realized vol, news (FOMC), day of week
- Test both momentum (positive coeff) and reversal (negative coeff)

---

### Mechanism 4: Volatility-Conditioned Predictability (Regime-Dependent Patterns)
**Supporting Papers:** **11 (Wen et al. — jumps, FOMC, liquidity, COVID)**, **2 (Vojtko/Dujava — real rate regimes)**, **1 (Baur et al. — fundamental regimes)**  
**Contradicting Papers:** None explicit  
**Asset Specificity:** Crypto (11), Gold monthly (2, 1)  
**Horizon:** Intraday (11), Monthly (1, 2)  
**Independent Replication:** Multiple for crypto (11 cites several); for gold monthly, Papers 1 & 2 differ on whether regimes add value  
**Statistical/Economic Significance:** 
- Paper 11: Intraday momentum/reversal patterns **change** with jumps, FOMC, liquidity, COVID
- Paper 2: Real rate regimes (via Gold+Treasury momentum) identify distinct return distributions
- Paper 1: Fundamental regimes tested but no robust timing after data-snooping

**Survives Transaction Costs:** Paper 11: Not explicit; Paper 2: Not modelled; Paper 1: Modelled but negative result

**Transferability to Exness XAUUSDm M5/H1:** **MEDIUM-HIGH** — Volatility regimes at M5 are measurable (realized vol, ATR, GARCH). FOMC schedule known. Liquidity proxies (spread, tick volume) available. Real-rate regime proxy via H1/D1 gold + Treasury correlation (if Treasury data available).

**Unproven:**
- Which volatility measure best conditions predictability at M5 (realized vol? ATR? GARCH? spread?)
- Whether FOMC days show distinct M5 patterns in gold (likely yes — gold reacts to rates)
- Whether "jumps" at M5 (large bars) condition subsequent predictability
- Real-rate regime at intraday: how to proxy without Treasury futures data on Exness?

**Falsification Experiment:**
- Stratify M5 session-open momentum (Mechanism 3) by: realized vol quintile, FOMC day Y/N, spread quintile
- Test if predictability concentrated in specific regimes
- Build real-rate regime proxy: H1 gold return vs H1 DXY/US10Y (if available) or gold momentum alone

---

### Mechanism 5: Trend-Following / Donchian Breakout / Time-Series Momentum
**Supporting Papers:** **2 (Vojtko/Dujava — monthly gold momentum)**, **8 (Beluská/Vojtko — BTC daily MAX)**, **10 (Padysak/Vojtko — BTC daily MAX)**, **13 (Vojtko/Dujava — BTC multi-TF trend)**, **14 (Zarattini et al. — crypto ensemble Donchian)**, **4 (Huang et al. — crypto volume-weighted TSMOM)**  
**Contradicting Papers:** **1 (Baur et al. — monthly gold trend/technical NOT robust after data-snooping)**, **Assignment 14 (XAU-MTF-DONCHIAN-001 — H1-regime M5 Donchian REJECTED: IS -99%, OOS -20%)**  
**Asset Specificity:** Gold monthly (2), Bitcoin daily (8, 10, 13), Crypto daily (4, 14), **XAUUSDm M5 (Assignment 14 — NEGATIVE)**  
**Horizon:** Monthly (2), Daily (8, 10, 4, 14), M5 (Assignment 14)  
**Independent Replication:** Multiple for crypto/BTC; conflicting for gold (2 vs 1); negative for XAUUSDm M5  
**Statistical/Economic Significance:** 
- Paper 2: Gold momentum alone predictive (all horizons); +Treasury refines
- Papers 8, 10: MAX strategy (trend at max) works on BTC daily
- Paper 14: Ensemble Donchian Sharpe > 1.5 on crypto (daily)
- Paper 4: Volume-weighted TSMOM 0.94%/day, Sharpe 2.17 on crypto
- **Assignment 14: REJECTED on XAUUSDm M5** — no edge

**Survives Transaction Costs:** Papers 2, 8, 10, 13, 4: Not modelled or partial; Paper 14: Modelled with mitigation; Assignment 14: Modelled with Exness spread — REJECTED

**Transferability to Exness XAUUSDm M5/H1:** **LOW** — **Directly tested and REJECTED** (Assignment 14). Monthly gold momentum (Paper 2) ≠ M5 Donchian. Crypto daily trend (Papers 4, 8, 10, 14) ≠ Gold M5. Different asset, frequency, microstructure.

**Unproven (and likely false for XAUUSDm M5):**
- Any Donchian/breakout variant at M5 with any regime filter
- Volume-weighted TSMOM at M5 (no reliable volume on Exness M5 — only tick volume)
- Multi-timeframe trend alignment (H1 regime + M5 signal) — Assignment 14 tested this exact combination

**Falsification Experiment:** **Already done** — Assignment 14. No further resources on this mechanism for XAUUSDm M5.

---

### Mechanism 6: Pairs Trading / Statistical Arbitrage (UHF)
**Supporting Papers:** **3 (Dao et al. — gold ETFs UHF)**  
**Contradicting Papers:** None (no other paper tests this)  
**Asset Specificity:** Gold ETFs (GLD, IAU, etc.) — **NOT XAUUSDm**  
**Horizon:** Millisecond / Tick  
**Independent Replication:** Single study  
**Statistical/Economic Significance:** 2.1% p.a. (full convergence), 3.38% p.a. (partial convergence 40%) after costs

**Survives Transaction Costs:** YES (explicitly modelled)

**Transferability to Exness XAUUSDm M5/H1:** **NONE** — Requires multiple cointegrated instruments (ETFs tracking same underlying). Exness XAUUSDm is single instrument. No pairs available. UHF not feasible at M5.

---

### Mechanism 7: Seasonality / Calendar Effects
**Supporting Papers:** **1 (Baur et al. — monthly seasonalities)**, **6 (Baur et al. — BTC time-of-day/day-of-week/month)**, **9 (Vojtko/Dujava — BTC overnight/weekend)**, **10 (Padysak/Vojtko — BTC hourly seasonality)**, **11 (Wen et al. — crypto intraday)**  
**Contradicting Papers:** **1** finds monthly seasonalities NOT robust after data-snooping; **6** finds BTC patterns NOT persistent  
**Asset Specificity:** Gold monthly (1), Bitcoin (6, 9, 10), Crypto (11)  
**Horizon:** Monthly (1), Intraday/Hourly (6, 9, 10, 11)  
**Independent Replication:** Multiple for BTC/crypto; single for gold monthly (negative)  
**Statistical/Economic Significance:** 
- Paper 1: Monthly seasonalities exist in-sample but vanish after SPA test
- Paper 6: BTC time-of-day/day-of-week effects but not persistent
- Paper 9: BTC overnight/weekend effects (incomplete)
- Paper 10: 2-hour holding strategy on BTC hourly
- Paper 11: Intraday patterns change with regimes

**Survives Transaction Costs:** Paper 1: Modelled, negative; Papers 6, 9, 10, 11: Not modelled

**Transferability to Exness XAUUSDm M5/H1:** **LOW-MEDIUM** — Monthly seasonalities (Paper 1) negative for gold. Intraday seasonalities (Papers 6, 9, 10, 11) are on BTC/crypto, not gold. However: **Session-based effects (Mechanism 1) ARE a form of intraday seasonality specific to gold** — Asian session dominance is a persistent intraday seasonal pattern.

**Unproven for Gold:**
- Day-of-week effects at M5 (Monday vs Friday)
- Month-of-year effects at M5
- Specific hour-of-day effects beyond session boundaries
- Whether 2-hour holding window (Paper 10) maps to gold session windows

**Falsification Experiment:**
- Test day-of-week, week-of-month, month-of-year effects on Exness XAUUSDm M5 returns
- Control for session (Asia/Europe/US) — isolate calendar from session effects
- Test specific hours: London open (08:00), NY open (14:30), London close (17:00), Asia open (00:00)

---

### Mechanism 8: Dual Momentum / Regime Switching (Absolute + Relative)
**Supporting Papers:** **2 (Vojtko/Dujava — gold monthly)**, **7 (Vojtko/Dujava — gold/BTC weekly)**, **12 (Wei — session momentum as regime)**  
**Contradicting Papers:** **1 (Baur et al. — no robust timing after data-snooping at monthly)**  
**Asset Specificity:** Gold monthly (2), Gold/BTC weekly (7), Gold hourly sessions (12)  
**Horizon:** Monthly (2), Weekly (7), Hourly/Session (12)  
**Independent Replication:** Two Quantpedia papers (2, 7) — same authors; Paper 12 independent but different frequency  
**Statistical/Economic Significance:** 
- Paper 2: Dual-momentum (Gold + Treasury) improves Sharpe 0.42→0.51
- Paper 7: Dual-momentum allocation between GLD/BTC (descriptive only)
- Paper 12: Session momentum = implicit regime switch (long only in favorable sessions)

**Survives Transaction Costs:** Paper 12: YES (long-only at 0.02%); Papers 2, 7: Not modelled

**Transferability to Exness XAUUSDm M5/H1:** **MEDIUM** — Session momentum (Mechanism 2) is a form of regime switching. Could extend: H1 trend filter (Assignment 14) + session filter. But Assignment 14's H1 regime filter (Donchian-based) was REJECTED. Need different regime definition.

**Unproven:**
- Whether H1 trend (non-Donchian) + session filter works
- Whether cross-asset regime (Gold + DXY/US10Y) at H1 adds value at M5
- Whether dual-momentum (absolute gold momentum + relative vs Treasuries) at H1/D1 improves M5 entries

**Falsification Experiment:**
- Define H1 regimes: (Gold momentum+, Treasury momentum+) etc. using Exness H1 resampled + external Treasury proxy
- Test M5 session-momentum entries only in favorable H1 regimes
- Compare vs session-momentum alone (Mechanism 2)

---

## 2. Cross-Paper Synthesis: Contradictions Resolved

| Contradiction | Resolution |
|---------------|------------|
| **Paper 1: No monthly gold timing** vs **Paper 2: Monthly dual-momentum works** | Paper 1 tests 4000+ strategies with SPA correction; Paper 2 tests ONE pre-specified dual-momentum regime. Paper 1's null result applies to data-mined strategies; Paper 2's result may be valid for a theoretically-grounded regime classifier. But both monthly — not relevant to M5. |
| **Papers 8,10,14: Donchian works on BTC** vs **Assignment 14: Donchian FAILS on XAUUSDm M5** | Different assets (BTC vs Gold), frequencies (Daily vs M5), market structures (24/7 retail crypto vs session-based institutional gold). Assignment 14 is the decisive evidence for XAUUSDm M5. |
| **Paper 11: Crypto has BOTH momentum AND reversal** vs **Paper 10: BTC trends at max, reverts at min** | Consistent: horizon-dependent. Short-term reversal (intraday) vs longer-term momentum (daily). Paper 11 explicitly notes this. For gold: session momentum (Paper 12) is ~hourly continuation; intraday reversal untested. |
| **Paper 12: Asian session dominates (post-2022)** vs **Pre-2022 unknown** | Regime-dependent mechanism. Central bank accumulation post-2022 may have shifted pricing eastward. Must test pre-2022 on Exness data. If Asian dominance is regime-specific, strategy must include regime detection. |

---

## 3. Mechanism Ranking for XAUUSDm M5/H1

| Rank | Mechanism | Evidence Strength | Transferability | Cost Survivability | Falsifiability | Overall Priority |
|------|-----------|-------------------|-----------------|-------------------|----------------|------------------|
| **1** | Session Return Decomposition & Asymmetric Contribution (Mech 1) | **VERY HIGH** (Gold-specific, 2yr hourly, structural) | **HIGH** (Direct session mapping) | **YES** (0.02% cost; Exness tighter) | **HIGH** (Exness M5 data available) | **TOP** |
| **2** | Cross-Session Momentum (Mech 2) | **HIGH** (Gold hourly, +0.13 autocorr) | **HIGH** (M5 session boundaries) | **YES** (Long-only survives) | **HIGH** (Direct test on Exness M5) | **TOP** |
| **3** | Volatility-Conditioned Predictability (Mech 4) | **MEDIUM-HIGH** (Crypto + Gold monthly regimes) | **MEDIUM-HIGH** (M5 vol/FOMC/spread measurable) | **UNKNOWN** (Not tested) | **HIGH** (Stratification testable) | **HIGH** |
| **4** | Intraday Momentum at Session Opens (Mech 3) | **MEDIUM** (Crypto/BTC only, but session opens map) | **MEDIUM** (Concept transfers, mechanism may differ) | **UNKNOWN** | **HIGH** (Regression testable) | **MEDIUM-HIGH** |
| **5** | Dual Momentum / Regime Switching (Mech 8) | **MEDIUM** (Monthly/weekly gold, session hourly) | **MEDIUM** (H1 regime + M5 session) | **PARTIAL** (Session alone yes; H1 regime untested) | **MEDIUM** (Requires external data) | **MEDIUM** |
| **6** | Seasonality / Calendar Effects (Mech 7) | **LOW** (Monthly gold negative; BTC not persistent) | **LOW-MEDIUM** (Session effects = intraday seasonality) | **UNKNOWN** | **HIGH** | **LOW-MEDIUM** |
| **7** | Trend-Following / Donchian / TSMOM (Mech 5) | **NEGATIVE** (Assignment 14 REJECTED on XAUUSDm M5) | **LOW** (Directly tested, failed) | **NO** (Failed with costs) | **DONE** | **REJECT** |
| **8** | UHF Pairs Arbitrage (Mech 6) | **N/A** (Wrong instrument/frequency) | **NONE** | **N/A** | **N/A** | **REJECT** |

---

## 4. Proposed Strategy Hypotheses (Phase C Preview)

Based on Mechanism Synthesis, the strongest candidates for Phase C:

### H1: Asian-Session Momentum Continuation (from Mechanism 1 + 2)
- **Mechanism:** Paper 12: Asian session produces 77% of gold returns with +0.13 lag-1 autocorrelation
- **Hypothesis:** If Asian session (00:00–08:00 UTC) close > open, long at Europe open (08:00) targeting European session continuation; or long next Asian session open
- **Instrument:** Exness XAUUSDm
- **Timeframe:** H1 (session bars) for signal; M5 for entry/exit execution
- **Entry:** Europe open (08:00 UTC) if Asia session return > threshold
- **Exit:** Europe close (14:30) or US open (14:30) or fixed M5 bars
- **Risk:** Fixed fractional (1% equity) or volatility-targeted; SL at session low/high
- **Frequency:** ~1 trade/day (250/year) — sufficient for statistical validity
- **Cost Sensitivity:** Exness spread ~0.3 pips (0.003%); 0.02% in Paper 12 → 6.7x headroom
- **Falsification:** Test on Exness M5 2021–2024 (pre-2022); if Asian dominance absent, reject

### H2: Session-Open Intraday Momentum (from Mechanism 3)
- **Mechanism:** Papers 11, 10, 6, 9: First period return predicts session remainder (momentum)
- **Hypothesis:** First 3–5 M5 bars after session open (00:00, 08:00, 14:30 UTC) predict next N M5 bars direction
- **Instrument:** Exness XAUUSDm
- **Timeframe:** M5 (signal + execution)
- **Entry:** At session open + 3 M5 bars (00:15, 08:15, 14:45 UTC) in direction of first 3-bar return
- **Exit:** Fixed horizon (6–12 M5 bars = 30–60 min) or session-end
- **Risk:** Volatility-targeted (ATR-based SL); 1% equity risk
- **Frequency:** ~3 trades/day (750/year) — high frequency, good for stats
- **Cost Sensitivity:** 3–5 M5 bars holding → spread cost critical; need >5 pips expected move
- **Falsification:** Regress first 3-bar return on next 6-bar return by session; control for vol/FOMC

### H3: US-Session Mean Reversion / High-Volatility Fade (from Mechanism 1)
- **Mechanism:** Paper 12: US session has highest volatility, zero/negative drift (−13.4%), "high-variance information trading"
- **Hypothesis:** Extreme US-session moves (large M5 bars) revert within session; fade outliers
- **Instrument:** Exness XAUUSDm
- **Timeframe:** M5 (signal + execution) during US session (14:30–24:00 UTC)
- **Entry:** When M5 bar return > 2× session realized vol (or > 95th percentile), counter-trend
- **Exit:** Mean reversion target (VWAP, session open, or fixed R:R 1:1)
- **Risk:** Tight SL (1× ATR); small size (high vol regime)
- **Frequency:** Variable (depends on outlier frequency)
- **Cost Sensitivity:** High — counter-trend in high vol = wide spreads, slippage risk
- **Falsification:** Test if US-session large M5 bars predict opposite-direction next bars; control for news

### H4: Volatility-Regime-Conditioned Session Momentum (from Mechanism 4)
- **Mechanism:** Paper 11: Intraday predictability changes with vol, jumps, FOMC, liquidity; Paper 2: Real-rate regimes
- **Hypothesis:** Session momentum (H1/H2) only works in specific volatility/liquidity regimes
- **Instrument:** Exness XAUUSDm
- **Timeframe:** H1 (regime detection) + M5 (execution)
- **Entry:** Session momentum signal (H1 or H2) ONLY when: realized vol in bottom 2 quintiles AND not FOMC day AND spread in bottom 2 quintiles
- **Exit:** Session-end or vol-targeted
- **Risk:** 1% equity; vol-adjusted size
- **Frequency:** Reduced vs H1/H2 (regime filter)
- **Cost Sensitivity:** Lower (filter avoids high-spread regimes)
- **Falsification:** Stratify H1/H2 performance by vol/spread/FOMC regimes; test interaction significance

---

## 5. Key Decisions for Phase C

1. **Do NOT pursue:** Trend-following/Donchian/TSMOM (Mechanism 5) — Assignment 14 definitively REJECTED on XAUUSDm M5
2. **Do NOT pursue:** UHF pairs (Mechanism 6) — wrong instrument/frequency
3. **Do NOT pursue:** Monthly seasonalities (Mechanism 7, Paper 1) — negative for gold
4. **FOCUS on:** Session-based mechanisms (1, 2, 3, 4) — only gold-specific intraday evidence
5. **Primary hypothesis:** H1 (Asian-session momentum continuation) — strongest evidence, lowest complexity, highest cost headroom
6. **Secondary hypothesis:** H2 (Session-open intraday momentum) — higher frequency, testable at M5 directly
7. **Tertiary hypotheses:** H3, H4 — more complex, require regime detection

---

## 6. Data Requirements for Testing

| Data Need | Source | Status |
|-----------|--------|--------|
| Exness XAUUSDm M5 OHLCV + spread | Existing dataset v1.2.0 (369,972 bars) | ✅ Available |
| Exness XAUUSDm H1 resampled from M5 | Existing dataset v1.2.0 (30,898 bars) | ✅ Available |
| Session timestamps (Asia/Europe/US UTC) | Fixed definition (00–08, 08–14:30, 14:30–24) | ✅ Definable |
| FOMC calendar | Public (FRED, investing.com) | ⚠️ Need to source |
| US Treasury yields (10Y) for real-rate proxy | FRED (DGS10) + CPI | ⚠️ Need to source |
| DXY / USD index for cross-asset regime | External (not on Exness) | ⚠️ Need to source |
| Realized volatility (M5, H1, session) | Computable from M5 | ✅ Computable |

---

*End of Mechanism Synthesis*  
*Generated: 2026-11-25*  
*Next: Phase C — Strategy Hypothesis Register*