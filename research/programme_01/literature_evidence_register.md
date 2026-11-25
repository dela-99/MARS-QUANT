# M.A.R.S. Quant — Research Programme 01
## Literature Evidence Register

**Phase A — Research Document Ingestion**  
**Primary Instrument:** Exness XAUUSDm  
**Primary Execution Timeframe:** M5 (H1 context, M1 optional)  
**Intended Live Capital:** USD $30  
**Date:** 2026-11-25  
**Total Documents:** 14 research papers + 1 process reference

---

## Document Inventory

| # | Title | Authors | Year | Source/Type | Asset | Timeframe | Sample Period |
|---|-------|---------|------|-------------|-------|-----------|---------------|
| 1 | Investing in Gold – Market Timing or Buy-and-Hold? | Baur, Dichtl, Drobetz, Wendt | 2018 | SSRN Working Paper (draft) | Gold (GLD, spot) | Monthly | 1975–2017 (approx) |
| 2 | Cross-Asset Price-Based Regimes for Gold | Vojtko, Dujava | — | Quantpedia Working Paper | Gold (GLD), U.S. Treasuries | Monthly | 2004–2024 (approx) |
| 3 | Ultra-high-frequency pairs trading in gold ETFs | Dao, McGroarty, Urquhart | — | Working Paper | Gold ETFs (GLD, IAU, etc.) | Tick / Millisecond | 2010–2019 (approx) |
| 4 | Cryptocurrency Volume-Weighted Time Series Momentum | Huang, Sangiorgi, Urquhart | — | Working Paper | Cryptocurrencies (100+) | Daily | 2015–2023 (approx) |
| 5 | Are Simple Technical Trading Rules Profitable in Bitcoin Markets? | Deprez, Frömmel | — | SSRN Preprint | Bitcoin (BTC/USD) | Daily, 60/30/10-min | 2012–2022 |
| 6 | Bitcoin Time-of-Day, Day-of-Week and Month-of-Year Effects | Baur, Cahill, Godfrey, Liu | 2017 | SSRN Working Paper | Bitcoin (7 exchanges) | Intraday / Hourly | 2011–2017 (15M obs) |
| 7 | Dual Momentum Allocation Between Physical Gold and Bitcoin | Vojtko, Dujava | 2026 | Quantpedia Blog/Working Paper | Gold (GLD), Bitcoin (IBIT/BITO) | Weekly | Dec 2018 – Apr 2026 |
| 8 | Revisiting Trend-following and Mean-reversion Strategies in Bitcoin | Beluska, Vojtko | 2024 | Quantpedia Blog | Bitcoin (Gemini) | Daily | Nov 2015 – Aug 2024 |
| 9 | How To Profitably Trade Bitcoin's Overnight Sessions | Vojtko, Dujava | 2024 | Quantpedia Blog | Bitcoin | Intraday / Overnight | 2015–2024 (approx) |
| 10 | Seasonality, Trend-following, and Mean reversion in Bitcoin | Padysak, Vojtko | — | SSRN Working Paper | Bitcoin (Gemini) | Hourly | Oct 2015 – Mar 2022 |
| 11 | Intraday Return Predictability in the Cryptocurrency Markets | Wen, Bouri, Xu, Zhao | — | SSRN Working Paper | BTC, ETH, LTC, XRP | Intraday (minute) | Mar 2013 – May 2020 |
| 12 | Who Moves the Price? Trading-Session Return Decomposition and Cross-Session Momentum in Gold and Silver Markets | Wei | 2026 | Working Paper | Gold (XAU/USD), Silver (XAG/USD) | Hourly (3 sessions) | Jul 2024 – Aug 2026 |
| 13 | How to Design a Simple Multi-Timeframe Trend Strategy on Bitcoin | Vojtko, Dujava | — | Quantpedia Blog | Bitcoin | Multi-timeframe | — |
| 14 | Catching Crypto Trends: A Tactical Approach for Bitcoin and Altcoins | Zarattini, Pagani, Barbon | 2025 | Working Paper (Concretum/Parma/St.Gallen) | Bitcoin + Top 20 Altcoins | Daily | 2015–2025 |
| 15 | Research-to-Trade Process (Summary) | Mateo (lecture) | 2026 | Internal Summary | General Process | — | — |

---

## Detailed Evidence per Document

### 1. Investing in Gold – Market Timing or Buy-and-Hold?
**Authors:** Dirk G. Baur, Hubert Dichtl, Wolfgang Drobetz, Viktoria-Sophie Wendt  
**Publication:** SSRN Working Paper, draft November 2018 (https://ssrn.com/abstract=3202658)  
**Asset:** Gold (GLD ETF, spot gold)  
**Timeframe:** Monthly  
**Sample Period:** ~1975–2017 (42+ years)  

**Research Question:** Can gold be actively timed vs. buy-and-hold using seasonal, technical, and fundamental signals?

**Methodology:**
- Tested 4,000+ timing strategies (seasonal, trend-following, fundamental)
- Used Hansen's (2005) Superior Predictive Ability (SPA) test for multiple-testing control
- Stepwise SPA extensions (Hsu et al. 2010, 2014)
- Transaction costs included (bid-ask spread + commission)

**Variables/Indicators Tested:**
- Seasonal: Monthly dummies, Halloween effect, etc.
- Technical: Moving averages (1–12 month), momentum (1–12 month), Donchian channels, RSI
- Fundamental: Real interest rates, inflation, USD index, stock market returns, VIX

**Reported Findings:**
- Some strategies show statistical and economic gains vs. buy-and-hold
- **However:** Results NOT robust to data-snooping biases (SPA test p-values > 0.05 after correction)
- Gains limited to specific evaluation periods
- Conclusion: Evidence supports gold market efficiency

**Transaction Costs:** Bid-ask spread + commission (explicitly modelled)

**Benchmarks:** Buy-and-hold gold, risk-free asset

**Statistical Significance:** SPA test controls family-wise error rate; no strategy survives correction

**Limitations/Threats to Validity:**
- Data-snooping bias across 4,000+ strategies
- Monthly frequency only (no intraday)
- Survivorship bias in fundamental data?
- Transaction cost model simplified
- Sample ends 2017 (pre-COVID, pre-2022 regime shift)

**Relevance to XAUUSDm M5/H1:** LOW — Monthly frequency, no intraday mechanisms, negative result after multiple testing correction. But: establishes that simple trend/seasonal signals on gold are likely spurious at monthly horizon.

**Key Page References:** pp. 1–3 (abstract, intro), pp. 54–66 (SPA test methodology), Tables 1–4 (results)

---

### 2. Cross-Asset Price-Based Regimes for Gold
**Authors:** Radovan Vojtko, Cyril Dujava (Quantpedia)  
**Publication:** Quantpedia Working Paper (undated, appears 2024+)  
**Asset:** Gold (GLD), Long-duration U.S. Treasury Total Return Indices  
**Timeframe:** Monthly (1M, 3M, 6M, 12M momentum horizons)  
**Sample Period:** ~2004–2024 (GLD inception 2004)

**Research Question:** Does joint momentum of gold + long-duration Treasuries identify macro regimes that improve gold timing?

**Methodology:**
- Dual-momentum regime classifier: Gold momentum × Treasury momentum
- Four regimes: (++, +−, −+, −−) where + = positive momentum
- Long-only timing: Invest in GLD when regime favorable, else cash (Fed Funds rate)
- Standardized momentum signals (z-scores)
- Out-of-sample evaluation across horizons

**Mechanism:** Joint momentum encodes real interest rate direction, Fed policy stance, global risk appetite

**Reported Findings (Table 1, 2):**
| Regime | CAGR | Vol | Sharpe | Max DD | Perf/DD |
|--------|------|-----|--------|--------|---------|
| Gold+ / Treasury+ (falling real rates) | 6.95% | 13.73% | 0.51 | -36.71% | 0.19 |
| Gold+ / Treasury− | 6.47–8.01% | 14.23–15.76% | 0.44–0.51 | -35% to -54% | 0.12–0.23 |
| Gold− / Treasury+ | 0.92% | 9.11% | 0.10 | -46.63% | 0.02 |
| Gold− / Treasury− (rising real rates) | 1.14% | 9.11% | 0.10 | -46.63% | 0.02 |
| Buy-and-hold GLD | 7.68% | 18.11% | 0.42 | -60.02% | 0.13 |

- Dual-momentum improves Sharpe (0.42 → 0.51) and reduces max DD (-60% → -37%)
- Positive gold momentum alone is predictive; adding Treasury momentum refines regime
- Works best at 12M horizon

**Transaction Costs:** Not explicitly modelled in tables; cash returns use Fed Funds

**Benchmarks:** Buy-and-hold GLD, 60/40 portfolio

**Statistical Significance:** Not formally tested (descriptive performance comparison)

**Limitations:**
- Monthly frequency only
- GLD-only (not XAUUSDm spot/futures)
- No explicit transaction cost modelling
- Regime definition uses same data for classification and testing (potential look-ahead)
- Sample period includes 2022 regime shift but not tested separately pre/post
- Quantpedia working paper (not peer-reviewed)

**Relevance to XAUUSDm M5/H1:** MEDIUM — Regime concept (real rates, risk appetite) transfers to intraday; cross-asset momentum (gold + Treasuries) could be proxied via H1/D1 correlations. But: monthly frequency, no intraday session decomposition, no cost model for M5.

**Key Page References:** pp. 1–3 (abstract, intro), pp. 147–160 (Tables 1, 2, Figures 1, 2)

---

### 3. Ultra-high-frequency pairs trading in gold ETFs
**Authors:** Thong M Dao, Frank McGroarty, Andrew Urquhart (Southampton)  
**Publication:** Working Paper  
**Asset:** Gold ETFs (GLD, IAU, SGOL, etc.) — multiple ETFs tracking same underlying  
**Timeframe:** Tick / Millisecond (UHF)  
**Sample Period:** ~2010–2019

**Research Question:** Can pairs trading of gold ETFs generate excess returns at ultra-high frequency?

**Methodology:**
- Cointegration-based pairs selection (Engle-Granger, Johansen)
- Formation period → Trading period
- Full convergence vs. Partial convergence exit rules
- Partial convergence: exit at ~40% of divergence (optimal)
- Transaction costs: bid-ask spread + commission

**Mechanism:** Law of one price — same underlying (gold) → ETFs should move together; temporary mispricing from liquidity shocks, creation/redemption frictions

**Reported Findings:**
- Full convergence: 2.1% p.a. excess return after costs
- Partial convergence (40% target): 3.38% p.a. after costs
- Outperformance consistent across whole sample and sub-samples
- Returns exceed risk compensation → market inefficient at UHF
- High-frequency traders capture this; speed critical (ms reaction times)

**Transaction Costs:** Bid-ask spread + commission (explicit)

**Benchmarks:** Buy-and-hold, risk-free

**Statistical Significance:** t-tests on returns; robustness across sub-samples

**Limitations/Threats:**
- **UHF only** — requires colocation, ms execution, not feasible for retail/M5
- Gold ETFs only (not XAUUSDm spot/futures)
- Survivorship bias in ETF universe?
- Creation/redemption mechanism specific to ETF structure
- Pre-2020 data (market structure changed)
- Partial convergence rule optimized in-sample

**Relevance to XAUUSDm M5/H1:** VERY LOW — UHF mechanism (ms arbitrage across ETFs) does not transfer to M5 single-instrument trading. No pairs available on Exness XAUUSDm.

**Key Page References:** pp. 1–3 (abstract, intro), pp. 244–262 (methodology, partial convergence)

---

### 4. Cryptocurrency Volume-Weighted Time Series Momentum
**Authors:** Zih-Chun Huang, Ivan Sangiorgi, Andrew Urquhart  
**Publication:** Working Paper (ICMA Centre, Birmingham)  
**Asset:** 100+ Cryptocurrencies  
**Timeframe:** Daily  
**Sample Period:** ~2015–2023

**Research Question:** Does volume-weighting improve TSMOM in crypto?

**Methodology:**
- Volume-weighted Winner-Minus-Loser (VW-WML) portfolio
- Winner: positive past return; Loser: negative past return
- Weight by daily trading volume (not market cap — avoids founder manipulation)
- Compare: VW-WML vs. EW, CW, IV-WML
- Control for wash trading (trusted exchange volume subset)
- Three-factor model (Liu et al. 2022)

**Mechanism:** Volume signals informed trading / liquidity; low volume → higher future returns (Lee & Swaminathan 2000)

**Reported Findings:**
- VW-WML: 0.94% per day, annualized Sharpe 2.17
- Outperforms EW, CW, IV weighting
- Not explained by market, size, momentum factors
- Robust to wash-trading controls (trusted exchanges)
- Strong TSMOM in volume-weighted market return

**Transaction Costs:** Not explicitly modelled (mentioned as future work)

**Benchmarks:** Buy-and-hold, equally-weighted, cap-weighted

**Statistical Significance:** t-stats on portfolio returns; factor model alphas

**Limitations:**
- Crypto only — **not gold**
- Daily frequency
- No transaction cost model
- Wash trading concerns (partially addressed)
- Survivor bias in coin universe
- 0.94%/day seems implausibly high (likely pre-cost, pre-slippage)

**Relevance to XAUUSDm M5/H1:** LOW — Asset class mismatch (crypto vs gold). Volume-weighting concept *could* transfer (tick volume on M5), but crypto microstructure differs fundamentally from FX/spot gold.

**Key Page References:** pp. 1–3 (abstract, intro), pp. 314–337 (methodology, VW-WML construction)

---

### 5. Are Simple Technical Trading Rules Profitable in Bitcoin Markets?
**Authors:** Niek Deprez, Michael Frömmel (Ghent University)  
**Publication:** SSRN Preprint (https://ssrn.com/abstract=4401552), not peer-reviewed  
**Asset:** Bitcoin (BTC/USD, Bitstamp)  
**Timeframe:** Daily, 60-min, 30-min, 10-min  
**Sample Period:** 2012–2022 (pre-2013 initialization)

**Research Question:** Can simple technical rules beat buy-and-hold in BTC after costs and data-mining correction?

**Methodology:**
- 75,360 simple technical rules (6 classes × frequencies)
- Multiple hypothesis testing: False Discovery Rate (FDR) control
- Select best rules after transaction costs (bid-ask spread + fee)
- Form portfolios of selected rules
- Out-of-sample evaluation

**Rule Classes:** Moving average, Filter, Support/Resistance, Channel, On-Balance Volume, Momentum

**Reported Findings:**
- Some rules outperform buy-and-hold risk-return wise OOS
- **But:** After FDR correction, significance diminishes
- Intraday (10-min) rules perform better than daily
- Transaction costs critical — many rules profitable gross, not net
- Long-only variants tend to work better

**Transaction Costs:** Average daily bid-ask spread + minimum fee (Bitstamp)

**Benchmarks:** Buy-and-hold BTC

**Statistical Significance:** FDR control (Benjamini-Hochberg); OOS portfolio formation

**Limitations:**
- Bitcoin only — **not gold**
- Bitstamp only (single exchange)
- Pre-2022 data (pre-ETF, pre-institutional)
- Rule space limited to "simple" technical rules
- FDR control conservative but still multiple testing concern

**Relevance to XAUUSDm M5/H1:** LOW-MEDIUM — Methodology (FDR, OOS, cost-aware) is directly transferable. Intraday frequency (10-min) closer to M5. But: asset class mismatch; BTC 24/7 vs gold session-based; different microstructure.

**Key Page References:** pp. 1–3 (abstract), pp. 417–477 (data, methodology, Table 1)

---

### 6. Bitcoin Time-of-Day, Day-of-Week and Month-of-Year Effects
**Authors:** Dirk G. Baur, Daniel Cahill, Keith Godfrey, Zhangxin (Frank) Liu (UWA)  
**Publication:** SSRN Working Paper (https://ssrn.com/abstract=3088472), December 2017  
**Asset:** Bitcoin (7 global exchanges)  
**Timeframe:** Intraday / Hourly  
**Sample Period:** >15M observations, ~2011–2017

**Research Question:** Do time-of-day, day-of-week, month-of-year anomalies exist in Bitcoin?

**Methodology:**
- Heatmaps of returns and volume by hour/day/month
- Statistical tests for significance
- Cross-exchange comparison (USD, JPY, CNY denominated)
- Session alignment with US equity hours

**Reported Findings:**
- Lower weekend volume effect
- Higher Monday return effect (currency-like)
- Increased activity during US equity hours
- USD-denominated exchanges show stronger patterns
- **No consistent/persistent patterns** across sample period
- Conclusion: Bitcoin markets are weak-form efficient

**Transaction Costs:** Not modelled

**Benchmarks:** Random walk / efficient market

**Statistical Significance:** Heatmap visualization + statistical tests (not fully detailed in excerpt)

**Limitations:**
- Bitcoin only — **not gold**
- Sample ends 2017 (pre-institutional, pre-ETF)
- 7 exchanges but aggregated
- No transaction cost model
- No out-of-sample validation

**Relevance to XAUUSDm M5/H1:** MEDIUM — **Session-based analysis directly relevant**. Gold has clear Asian/European/US sessions (like Wei 2026). Time-of-day effects in gold may exist. Methodology (heatmaps, session decomposition) directly applicable to XAUUSDm M5/H1.

**Key Page References:** pp. 1–3 (abstract, intro), pp. 524–549 (data, session analysis)

---

### 7. Dual Momentum Allocation Between Physical Gold and Bitcoin
**Authors:** Radovan Vojtko, Cyril Dujava (Quantpedia)  
**Publication:** Quantpedia Blog / Working Paper, May 2026  
**Asset:** Gold (GLD), Bitcoin (IBIT/BITO)  
**Timeframe:** Weekly (Wednesday rebalance)  
**Sample Period:** Dec 31, 2018 – Apr 2026

**Research Question:** Can dual-momentum allocation between gold and Bitcoin improve risk-adjusted returns?

**Methodology:**
- Dual momentum: absolute (time-series) + relative (cross-sectional)
- Weekly rebalancing at Wednesday close
- GLD: NYSE trading days; BTC: Bitfinex hourly → aligned to GLD close
- Volatility targeting (implied)
- Benchmarks: BTC, GLD, 50/50 static

**Reported Findings (Table 1):**
| Asset | CAGR | Vol | Sharpe | Max DD | Calmar |
|-------|------|-----|--------|--------|--------|
| Bitcoin | 46.66% | 64.01% | 0.73 | -77.49% | 0.60 |
| GLD | 18.80% | 17.09% | 1.10 | -20.71% | 0.91 |
| 50/50 | 38.65% | 34.44% | 1.12 | -50.99% | 0.76 |

- Bitcoin: high return, extreme vol, catastrophic DD
- Gold: stability, lower return
- 50/50: intermediate, doesn't resolve tension
- Dual momentum aims to rotate based on momentum signals

**Transaction Costs:** Not explicitly modelled (implied in "net-of-fees" mention in similar papers)

**Benchmarks:** Static allocations, buy-and-hold

**Statistical Significance:** Descriptive; no formal tests

**Limitations:**
- Weekly frequency (not M5/H1)
- GLD/IBIT only (not XAUUSDm)
- Short sample (2018–2026, ~7.5 years)
- Quantpedia working paper
- No transaction cost model
- Volatility targeting details not specified

**Relevance to XAUUSDm M5/H1:** LOW-MEDIUM — Dual momentum concept transfers; but weekly frequency, ETF vehicles only, Bitcoin component irrelevant per programme constraints.

**Key Page References:** pp. 1–3 (abstract, intro), pp. 595–648 (methodology, Table 1)

---

### 8. Revisiting Trend-following and Mean-reversion Strategies in Bitcoin
**Authors:** Soňa Beluská, Radovan Vojtko (Quantpedia)  
**Publication:** Quantpedia Blog, September 2024  
**Asset:** Bitcoin (Gemini, daily open prices)  
**Timeframe:** Daily  
**Sample Period:** Nov 2015 – Aug 2024

**Research Question:** Do MAX (trend-following) and MIN (mean-reversion) strategies work on Bitcoin?

**Methodology:**
- MAX strategy: Buy when price at x-day maximum (trend continuation)
- MIN strategy: Buy when price at x-day minimum (mean reversion)
- Lookbacks: 10, 20, 30, 40, 50 days
- In-sample (original) vs extended (2022–2024) analysis

**Reported Findings:**
- Both strategies "remain alive and effective, especially for 10-day periods"
- MAX stronger than MIN (higher returns, lower drawdown)
- Both efficient for trading (per paper's claim)
- Recent period (2022–2024) included

**Transaction Costs:** Not modelled in excerpt

**Benchmarks:** Buy-and-hold BTC

**Statistical Significance:** Not formally tested in excerpt (descriptive performance)

**Limitations:**
- Bitcoin only — **not gold**
- Daily frequency
- No transaction costs
- Quantpedia blog (not peer-reviewed)
- Lookback optimization in-sample
- "Efficient for trading" claim unsupported by stats

**Relevance to XAUUSDm M5/H1:** LOW — Asset mismatch; daily frequency; no cost model. But: MAX/MIN concept (Donchian-style) is similar to Assignment 14's Donchian breakout — which was REJECTED.

**Key Page References:** pp. 1–3 (abstract, methodology), pp. 700–705 (results, Table 1)

---

### 9. How To Profitably Trade Bitcoin's Overnight Sessions
**Authors:** Radovan Vojtko, Cyril Dujava (Quantpedia)  
**Publication:** Quantpedia Blog, November 2024  
**Asset:** Bitcoin  
**Timeframe:** Intraday / Overnight sessions  
**Sample Period:** ~2015–2024

**Research Question:** Does overnight anomaly exist in Bitcoin; can it be exploited?

**Methodology:**
- Decompose daily vs overnight (nightly) sessions
- Analyze day-of-week / weekend effects
- Build seasonal strategy exploiting overnight effect
- Hypothesis: ETF inflows/outflows tied to TradFi hours → structure shift

**Mechanism:** Institutional ETF flows concentrated in exchange hours → overnight returns reflect unresolved imbalance

**Reported Findings:** (Excerpt incomplete — full results not visible)

**Transaction Costs:** Not detailed in excerpt

**Benchmarks:** Buy-and-hold BTC

**Limitations:**
- Bitcoin only — **not gold**
- Quantpedia blog
- Incomplete excerpt
- ETF-flow mechanism specific to BTC ETF structure

**Relevance to XAUUSDm M5/H1:** MEDIUM — **Session decomposition directly relevant**. Gold has clear overnight (Asian session) vs daytime (Europe/US) structure. Wei (2026) shows Asian session dominates gold returns. Overnight anomaly concept transfers.

**Key Page References:** pp. 1–3 (abstract, intro, background)

---

### 10. Seasonality, Trend-following, and Mean reversion in Bitcoin
**Authors:** Matus Padysak, Radovan Vojtko (Quantpedia)  
**Publication:** SSRN Working Paper (https://ssrn.com/abstract=4081000)  
**Asset:** Bitcoin (Gemini, hourly)  
**Timeframe:** Hourly  
**Sample Period:** Oct 2015 – Mar 2022

**Research Question:** Do seasonality, trend-following, and mean-reversion effects exist in Bitcoin?

**Methodology:**
- Seasonality: NYSE open/close effects, intraday/overnight components
- 2-hour holding strategy (simple seasonality)
- Trend-following: MAX strategy (price at x-day max)
- Mean-reversion: MIN strategy (price at x-day min)
- Lookbacks: 10–50 days
- Hourly data from Gemini

**Reported Findings:**
- Simple seasonality: Hold BTC only 2 hours/day → positive results
- BTC trends at maximum, reverts at minimum
- Both trend-following and mean-reversion coexist (horizon-dependent)
- Short-term reversal vs longer-term momentum

**Transaction Costs:** Not modelled in excerpt

**Benchmarks:** Buy-and-hold

**Limitations:**
- Bitcoin only — **not gold**
- Hourly frequency (closer to H1)
- No transaction costs
- SSRN working paper
- Gemini only (single exchange)
- Sample ends Mar 2022

**Relevance to XAUUSDm M5/H1:** MEDIUM — **Hourly frequency, session-based seasonality directly relevant**. NYSE open/close effects may map to London/NY session opens for gold. 2-hour holding concept could map to M5 session-window strategies. But: asset mismatch.

**Key Page References:** pp. 1–3 (abstract, intro), pp. 832–858 (methodology, seasonality, trend/mean-reversion)

---

### 11. Intraday Return Predictability in the Cryptocurrency Markets
**Authors:** Zhuzhu Wen, Elie Bouri, Yahua Xu, Yang Zhao  
**Publication:** SSRN Working Paper (https://ssrn.com/abstract=4080253)  
**Asset:** BTC, ETH, LTC, XRP  
**Timeframe:** Intraday (minute-level)  
**Sample Period:** Mar 3, 2013 – May 31, 2020

**Research Question:** Is there intraday momentum and/or reversal in crypto?

**Methodology:**
- High-frequency price data
- Test first half-hour return predicting last half-hour return
- Condition on: large intraday jumps, FOMC announcements, liquidity, COVID-19
- Economic value of timing strategy vs always-long/buy-and-hold
- Late-informed investor theory (momentum) vs overreaction/overconfidence (reversal)

**Reported Findings:**
- **Both intraday momentum AND reversal** exist in crypto
- Patterns change with jumps, FOMC, liquidity, COVID
- Intraday momentum: first 30-min return predicts last 30-min return positively
- Intraday reversal: unique to crypto (overreaction to non-fundamental info)
- Timing strategy beats benchmarks economically
- Also found in ETH, LTC, XRP

**Transaction Costs:** Not detailed in excerpt

**Benchmarks:** Always-long, buy-and-hold

**Statistical Significance:** Regression-based predictability tests; economic value metrics

**Limitations:**
- Crypto only — **not gold**
- Minute frequency (but 24/7, no sessions)
- Pre-2020 data
- No explicit transaction cost model in excerpt
- Mechanism (late-informed investors) may not transfer to gold

**Relevance to XAUUSDm M5/H1:** MEDIUM — **Intraday momentum/reversal at minute level directly relevant to M5**. First/last half-hour pattern maps to session open/close. But: crypto 24/7 vs gold session-based; different participant structure.

**Key Page References:** pp. 1–3 (abstract, intro), pp. 912–936 (literature, methodology)

---

### 12. Who Moves the Price? Trading-Session Return Decomposition and Cross-Session Momentum in Gold and Silver Markets
**Authors:** WEI Wenling (CMBC Wealth Management)  
**Publication:** Working Paper, August 2026  
**Asset:** Gold (XAU/USD), Silver (XAG/USD) — **DIRECTLY RELEVANT**  
**Timeframe:** Hourly (3 UTC sessions: Asia 00–08, Europe 08–14:30, US 14:30–24)  
**Sample Period:** 22 Jul 2024 – 7 Aug 2026 (~2.04 years, 529 trading days, 1,587 session obs)

**Research Question:** How are gold/silver returns distributed across sessions? Is there cross-session momentum?

**Methodology:**
- Decompose cumulative log returns by session (Lou, Polk, Skouras 2019 logic)
- Session returns chain to total log return
- Session momentum rule: Long session t+1 if session t return > 0
- Cost: 0.02% per position change (conservative institutional)
- Long-only and long/short variants

**Mechanism:** Post-2022 central bank gold accumulation shifted pricing eastward (Asian session dominance)

**Reported Findings:**
| Session | Gold Cum Log Return | Silver Cum Log Return |
|---------|---------------------|----------------------|
| Asia (00–08 UTC) | **+77.2%** | **+61.7%** |
| Europe (08–14:30) | +36.2% | +46.6% |
| US (14:30–24) | **−13.4%** | **−8.2%** |

- Asian session: positive in **every calendar year**; absorbed 2026 sell-off
- US session: highest volatility, zero/negative drift (high-variance info trading)
- **Session momentum (lag-1 autocorr): Gold +0.13, Silver +0.12** (concentrated in Asia continuation)
- **Before costs:** Session momentum beats buy-and-hold
- **After 0.02% cost:** Only long-only survives
  - Gold: Net Sharpe 1.68, ~half buy-and-hold DD
  - Silver: Net Sharpe 0.84, DD cut from -53.6% to -26.2%
- US session momentum loses money net of costs

**Transaction Costs:** 0.02% per position change (explicit, conservative for institutional spot/futures)

**Benchmarks:** Buy-and-hold gold/silver

**Statistical Significance:** Autocorrelation coefficients; backtest performance with costs

**Limitations:**
- **Short sample:** Jul 2024 – Aug 2026 only (~2 years)
- Post-2022 regime specific (central bank accumulation)
- Hourly data (Stooq) — not M5, not Exness XAUUSDm
- 0.02% cost may not reflect Exness spread + commission
- Session definition fixed UTC (no DST adjustment mentioned)
- No out-of-sample beyond Aug 2026

**Relevance to XAUUSDm M5/H1:** **VERY HIGH** — **Only paper studying XAU/USD spot directly with session decomposition**. Asian session dominance (77% of returns) is a structural finding. Cross-session momentum (+0.13 autocorr) is a testable mechanism at M5/H1. Cost model (0.02%) provides benchmark. **This is the strongest evidence for a gold-specific intraday strategy.**

**Key Page References:** pp. 1–3 (abstract, intro), pp. 967–1005 (methodology, decomposition, momentum backtest, Tables)

---

### 13. How to Design a Simple Multi-Timeframe Trend Strategy on Bitcoin
**Authors:** Radovan Vojtko, Cyril Dujava (Quantpedia)  
**Publication:** Quantpedia Blog  
**Asset:** Bitcoin  
**Timeframe:** Multi-timeframe (trend)  
**Sample Period:** Not specified in excerpt

**Research Question:** How to design a simple multi-timeframe trend strategy?

**Methodology:** (Excerpt incomplete — only title page visible)

**Relevance to XAUUSDm M5/H1:** LOW — Bitcoin only, incomplete excerpt. But: multi-timeframe trend concept is core to Assignment 14 (H1 regime filter + M5 Donchian) which was REJECTED.

---

### 14. Catching Crypto Trends: A Tactical Approach for Bitcoin and Altcoins
**Authors:** Carlo Zarattini, Alberto Pagani, Andrea Barbon (Concretum/Parma/St.Gallen)  
**Publication:** Working Paper, April 2025  
**Asset:** Bitcoin + Top 20 liquid altcoins (survivorship-bias-free)  
**Timeframe:** Daily  
**Sample Period:** 2015–2025

**Research Question:** Does ensemble Donchian trend-following work across crypto universe?

**Methodology:**
- Ensemble of Donchian channel models (multiple lookbacks) → single signal
- Volatility-based position sizing
- Rotational portfolio: Top 20 most liquid coins
- Transaction cost mitigation technique
- On-chain vs off-chain execution discussion

**Reported Findings:**
- Net-of-fees Sharpe > 1.5
- Annualized alpha 10.8% vs Bitcoin
- Cost mitigation technique effective
- Low correlation with traditional asset trend-following

**Transaction Costs:** Explicitly modelled; mitigation technique proposed

**Benchmarks:** Bitcoin, buy-and-hold

**Limitations:**
- Crypto only — **not gold**
- Daily frequency
- Ensemble Donchian similar to Assignment 14 (REJECTED)
- Rotational portfolio not feasible on single-instrument XAUUSDm
- Survivorship-bias-free universe (good practice)

**Relevance to XAUUSDm M5/H1:** LOW — Asset mismatch; daily; rotational not applicable. But: ensemble Donchian + volatility sizing + cost mitigation are methodological transfers. **Assignment 14 already tested Donchian on XAUUSDm and REJECTED.**

---

### 15. Research-to-Trade Process (Summary)
**Source:** Internal lecture summary by Mateo, October 2026  
**Content:** Institutional workflow for research → automated trading

**Key Takeaways:**
1. Ideas from research (SSRN) → clear entry/exit/sizing rules before live
2. Validation essential: Monte Carlo (reshuffle & resample), in-sample vs out-of-sample, risk heuristics
3. Typical simulations: 10,000–20,000 runs
4. Simple strategies often outperform complex
5. Run multiple uncorrelated strategies, automate monitoring/risk

**Monte Carlo:**
- Reshuffle (permutation): preserves trades, randomizes order → sequence risk
- Resampling (bootstrap): trades repeat/omitted → outcome distribution
- Tight distribution = strong edge; wide = weak edge
- Outputs: expected profit, P(drawdown > threshold)
- Live heuristics: red-flag thresholds after N trades

**Pipeline:** Idea → Encode Rules → Backtest → Validate (MC, IS/OOS) → Live Automated → Monitor → Iterate

**Rule Components:**
- Entry: condition (price signal, event, VWAP cross, gap)
- Exit: SL, TP, time-based (e.g., close by 15:30 ET)
- Position Sizing: volatility targeting or fixed-dollar risk
  - Vol targeting: constant risk per trade (e.g., $10k), adjust size by vol
  - Dev phase: 1 contract; live: vol sizing

**Source of Ideas:** 90–95% from academic/industry research (SSRN highlighted)
- Extract finding + "why", don't copy verbatim
- Translate to testable rules
- Use LLMs to summarize papers

**Example Strategies:**
1. Opening Range / Intraday Momentum (overnight gap + first 30 min)
2. VWAP Crossover (institutional algos target VWAP)
3. Post-Earnings Announcement Drift (60-day drift)
4. Overnight Returns Anomaly (90% of index returns overnight)

**Relevance to Programme 01:** **HIGH** — This is the operational playbook. Defines validation standards (10k–20k MC runs, reshuffle + resample, IS/OOS, risk heuristics), rule components, and translation process. Must be followed rigorously.

---

## Summary: Evidence Relevance to XAUUSDm M5/H1

| Relevance | Papers | Key Transferable Mechanisms |
|-----------|--------|----------------------------|
| **VERY HIGH** | 12 (Wei 2026) | Session return decomposition (Asia 77% of gold returns), cross-session momentum (+0.13 autocorr), cost-aware backtest (0.02%), long-only session momentum survives costs |
| **MEDIUM** | 2, 6, 9, 10, 11 | Regime classification (gold + Treasuries), session/time-of-day effects, overnight anomaly, intraday momentum/reversal, seasonality at hourly level |
| **LOW** | 1, 4, 5, 7, 8, 13, 14 | Monthly frequency (1), crypto-only (4,5,7,8,13,14), UHF (3), negative result after data-snooping (1) |
| **PROCESS** | 15 | Validation standards, rule translation, MC methodology, pipeline discipline |

---

## Contradictions & Tensions Identified

1. **Paper 1 (Baur et al.)** → No robust timing ability at monthly frequency after data-snooping correction
2. **Paper 2 (Vojtko/Dujava)** → Dual-momentum regime improves gold timing at monthly frequency
3. **Paper 12 (Wei)** → Strong session-based predictability at hourly frequency (Asian session dominance, cross-session momentum)
4. **Papers 8, 10, 14** → Donchian/trend-following works on Bitcoin (daily)
5. **Assignment 14** → H1-regime-filtered M5 Donchian on XAUUSDm **REJECTED** (IS: -99%, OOS: -20%)

**Resolution:** Frequency matters. Monthly (Papers 1, 2) ≠ Hourly/Intraday (Papers 6, 9, 10, 11, 12). Session structure (Paper 12) is a distinct mechanism from trend-following (Papers 2, 8, 10, 14). Assignment 14 tested trend-following (Donchian) + regime filter — not session momentum. Paper 12's session momentum is a **different, untested hypothesis** on XAUUSDm.

---

## Next Steps (Phase B → C)

1. **Phase B:** Mechanism synthesis focusing on:
   - Session return decomposition & cross-session momentum (Paper 12 — strongest)
   - Intraday momentum/reversal at session boundaries (Papers 6, 9, 10, 11)
   - Volatility-conditioned predictability (Paper 11: jumps, FOMC, liquidity)
   - Real-rate regime proxy at intraday (Paper 2 concept → H1/D1)

2. **Phase C:** Develop strategy hypotheses from strongest mechanisms:
   - Hypothesis 1: Asian-session momentum continuation (Paper 12)
   - Hypothesis 2: Session-open intraday momentum (Papers 6, 9, 10, 11)
   - Hypothesis 3: Cross-session mean-reversion (US session negative drift)
   - Hypothesis 4: Volatility-regime-conditioned entry (Paper 11)

3. **Phase D:** Codebase assessment (existing M.A.R.S. components)
4. **Phase E:** Data eligibility (Exness XAUUSDm M5/H1 datasets)
5. **Phase F+:** Specification, implementation, IS/OOS, MC, $30 feasibility

---

*End of Literature Evidence Register*  
*Generated: 2026-11-25*  
*Total Papers Reviewed: 14 + 1 process reference*