# M.A.R.S. Quant — Research Programme 02
## Gate A: Economic Plausibility Assessment

**Date:** 2026-11-25  
**Phase:** Assignment 19 — Research Discovery, Economic Plausibility and Candidate Screening  
**Input:** Candidate Hypothesis Register (5 candidates)  
**Standard:** Mechanism must be grounded in market microstructure, institutional behavior, or identifiable economic forces — not purely statistical pattern mining. Must survive the "so what?" test: why would this persist?

---

## 1. Economic Plausibility Framework

| Plausibility Tier | Criteria | Example |
|-------------------|----------|---------|
| **HIGH** | Identifiable participant class with structural incentive; mechanism survives transaction costs; documented in multiple asset classes | Central bank gold accumulation shifting price discovery to Asian hours (Paper 12) |
| **MEDIUM** | Plausible microstructure mechanism; limited direct evidence for gold M5; relies on analogy from other assets | Intraday momentum at session opens from late-informed flow (Paper 11 crypto) |
| **LOW** | Statistical pattern without clear mechanism; data-mined calendar effects; single-asset single-frequency | "Monday effect" without institutional driver; optimized lookback windows |
| **REJECT** | Contradicted by market structure; requires irrational participants; no survivable cost model | UHF pairs arb on single-instrument retail FX |

**Key Question for Each Candidate:** *Who is on the other side of this trade, and why do they persist in providing the edge?*

---

## 2. Candidate-by-Candidate Assessment

### Candidate 005: XAU-VOL-REGIME-SESSION-005 (Vol-Regime Session Momentum)

**Proposed Mechanism:** Session momentum (Asia→Europe continuation) only works in low-vol, non-FOMC, normal-spread regimes. High vol/news regimes favor reversal/noise.

**Economic Rationale:**
- **Low-vol regime:** Institutional/central bank flows (Paper 12: "central bank accumulation shifted pricing eastward") persist across sessions when not disrupted by news. Informed participants execute gradually → momentum.
- **High-vol/FOMC regime:** Information events (FOMC, NFP, geopolitical) cause repricing. Initial moves are noisy (liquidity gaps, stop runs). Market makers widen spreads. Momentum signals become unreliable; reversal or mean-reversion may dominate (Paper 11: overreaction to non-fundamental info).
- **Spread regime:** Wide spreads signal low liquidity / high adverse selection. Momentum strategies require tight spreads to survive costs.

**Supporting Evidence:**
- **Paper 12 (Wei 2026):** Long-only session momentum survives 0.02% costs; Sharpe 1.68. Implies regime where momentum works exists.
- **Paper 11 (Wen et al.):** Intraday predictability **changes** with vol, jumps, FOMC, liquidity. Direct evidence for regime-conditionality (in crypto).
- **Paper 2 (Vojtko/Dujava):** Real-rate regimes (Gold+Treasury momentum) condition gold returns at monthly horizon.
- **Market Microstructure Theory:** Kyle (1985), Glosten-Milgrom (1985) — informed trading persists in low-adverse-selection regimes; noise trading dominates in high-uncertainty regimes.

**Contradicting / Uncertain Evidence:**
- Paper 12 sample: Only 2.04 years (Jul 2024–Aug 2026) — post-2022 central bank regime. Pre-2022 behavior unknown.
- Paper 11: Crypto only — different market structure (24/7 retail vs session-based institutional).
- No direct gold M5 evidence for vol/FOMC/spread regime conditioning.

**Plausibility Verdict: MEDIUM-HIGH**  
Mechanism is economically grounded (informed vs noise trading regimes), supported by gold monthly regime evidence (Paper 2) and crypto intraday regime evidence (Paper 11). The session momentum mechanism (Paper 12) provides the base signal; regime filter is a theoretically-motivated enhancement. **Primary risk:** Regime persistence from signal (08:00) to execution (08:00-14:30) unproven.

---

### Candidate 006: XAU-SESSION-CALENDAR-006 (Session-Controlled Calendar Seasonality)

**Proposed Mechanism:** After controlling for session effects (Asia/Europe/US), residual calendar effects (day-of-week, week-of-month, month-of-year) at specific hours reflect recurring institutional flows (month-end rebalancing, options expiry, central bank operations).

**Economic Rationale:**
- **Month-end rebalancing:** Institutional portfolios rebalance at month-end → predictable flow patterns in last/first week of month.
- **Options expiry:** Gold options (COMEX, OTC) expire monthly/quarterly → gamma hedging flows at specific strikes/times.
- **Central bank operations:** Scheduled gold purchases/sales (e.g., China PBOC reporting) may cluster on specific days.
- **Weekend effect:** Position squaring Friday → Monday gap/reversion.

**Supporting Evidence:**
- **Paper 1 (Baur et al.):** Monthly seasonalities exist in-sample for gold but **vanish after SPA correction** (data-snooping).
- **Paper 6 (Baur et al.):** BTC time-of-day/day-of-week effects but **not persistent** across sample.
- **Paper 10 (Padysak/Vojtko):** 2-hour holding strategy at NYSE open/close on BTC hourly.
- **Market Practice:** Month-end rebalancing, options expiry, and central bank reporting schedules are documented institutional calendars.

**Contradicting / Uncertain Evidence:**
- Paper 1: Gold monthly seasonalities **not robust** after multiple testing correction — strongest contradicting evidence.
- Paper 6: Crypto calendar effects not persistent — analogy weak.
- No gold M5 evidence for calendar effects after session control.
- Multiple testing burden: 5 days × 4 weeks × 12 months × 4 session-hours = 960 cells → FDR control essential.

**Plausibility Verdict: LOW-MEDIUM**  
Institutional calendar drivers exist (month-end, options expiry, central bank schedules) but gold-specific evidence at M5 is absent. Paper 1's negative result at monthly frequency (with SPA correction) is a strong warning. Calendar effects may be session effects in disguise. **Requires:** Rigorous session partialling + FDR control + out-of-sample validation.

---

### Candidate 007: XAU-ASIAN-VOL-BREAKOUT-007 (Asian Session Volatility Breakout)

**Proposed Mechanism:** High-volatility Asian sessions reflect resolved uncertainty (central bank action, scheduled news). Breakout direction (close vs midpoint) carries information about the resolved direction → predicts Europe session. Low-vol Asian sessions are noise.

**Economic Rationale:**
- **Central bank intervention:** PBOC/other central banks may execute large orders during Asian hours. High vol sessions = intervention days. Breakout direction = intervention direction.
- **Scheduled news:** Asian-session data (China PMI, Japan CPI, Australia employment) releases create high vol. Breakout direction = market's interpretation.
- **Liquidity gap resolution:** Overnight accumulation of orders → first hours of Asia session resolve imbalance. High vol = large imbalance resolved. Direction persists.

**Supporting Evidence:**
- **Paper 12 (Wei 2026):** Asian session dominates returns (77%) and has distinct volatility profile. Central bank accumulation "shifted pricing eastward" — implies Asian session is where informed flow concentrates.
- **Market Microstructure:** Large informed orders execute in high-vol periods (Kyle 1985); direction reveals information.
- **Gold Specific:** Post-2022 central bank buying well-documented (WGC reports); Asian hours = Shanghai/London overlap for physical gold.

**Contradicting / Uncertain Evidence:**
- **No direct literature** on "Asian session vol breakout direction predicts Europe session" — novel combination.
- High vol may = noise (liquidity vacuum) not signal. Breakout direction could be random.
- Exness spread widens in high vol → cost headroom reduced (median 20 pips, max 335 pips).
- Threshold (60th percentile) arbitrary — data-snooping risk.
- Regime persistence: Asian session vol regime may not persist to Europe open.

**Plausibility Verdict: MEDIUM**  
Grounded in informed trading theory (high vol = informed flow) and gold-specific central bank narrative (Paper 12). But the specific breakout-direction signal is untested and novel. **Primary risk:** High vol = wide spreads = cost failure; breakout direction may not persist.

---

### Candidate 008: XAU-EUROPE-OPEN-REVERSAL-008 (Europe Open First-Bar Reversal)

**Proposed Mechanism:** At Europe open (08:00 UTC), overnight Asian order accumulation creates imbalance. First M5 bar overshoots (liquidity gap, stop runs). Informed participants fade → reversion within 30 min.

**Economic Rationale:**
- **Overnight order accumulation:** Asian session (00:00-08:00) accumulates orders. At Europe open, liquidity surges (London opens). Imbalance resolved → first bar overshoots.
- **Stop runs / liquidity grabs:** Algorithms target obvious levels (Asia high/low). First bar triggers stops → reversal.
- **Informed fading:** Market makers / HFTs provide liquidity against the initial surge, expecting reversion (Grossman-Miller 1988).

**Supporting Evidence:**
- **Paper 11 (Wen et al.):** Documents **intraday reversal** in crypto ("unique to crypto") — overreaction to non-fundamental info. Mechanism: late-informed retail chases, informed fades.
- **Market Microstructure:** Opening auction / first-bar reversal documented in equities (Biais et al. 1999), futures (Wang & Yau 2000).
- **Session Structure:** Europe open (08:00 UTC) = London open = major liquidity injection for gold.

**Contradicting / Uncertain Evidence:**
- **Paper 11 explicitly states reversal is "unique to crypto"** — mechanism (late-informed retail) may not transfer to gold (institutional/central bank dominated).
- Paper 11 also finds **momentum** in same data — sign uncertain.
- Gold session opens may not have "auction" dynamics like equities (24/5 FX).
- **$30 Feasibility:** SL ~100 pts needed for reversal → $1.00 risk at 0.01 lots > $0.30 budget → **Gate D failure likely**.

**Plausibility Verdict: LOW**  
Mechanism plausible in equities/futures but Paper 11's "unique to crypto" claim and gold's different participant base (central banks, not retail) weaken the analogy. Combined with likely $30 infeasibility (Gate D), economic plausibility is low for **this programme's constraints**.

---

### Candidate 009: XAU-FOMC-EVENT-009 (FOMC Event-Driven Patterns)

**Proposed Mechanism:** FOMC is highest-impact scheduled event for rate-sensitive gold. Pre-FOMC positioning drift, post-FOMC directional reaction, and overreaction fade create tradable patterns.

**Economic Rationale:**
- **Pre-FOMC drift:** Institutions position ahead of FOMC (Fed funds futures, gold as rate hedge). Directional drift 13:30-14:30.
- **Post-FOMC reaction:** Surprise component (vs expectations) drives immediate gold move. First 30-60 min = price discovery.
- **Overreaction fade:** Initial move overshoots (liquidity vacuum, algorithmic amplification). Mean reversion within 60-120 min as information digested.

**Supporting Evidence:**
- **Paper 11 (Wen et al.):** FOMC days show distinct intraday patterns (jumps, liquidity shifts) in crypto.
- **Paper 12 (Wei 2026):** US session = "high-variance information trading" — FOMC is the canonical info event.
- **Extensive Literature:** FOMC effects on gold documented (e.g., Lucca & Moench 2015 "pre-FOMC drift" in equities; gold as rate proxy).
- **Market Practice:** Gold traders specifically track FOMC; volume spikes documented.

**Contradicting / Uncertain Evidence:**
- **Sample size:** 8 FOMC/year × 5 years = 40 events. **No statistical power** for traditional significance testing.
- **Regime break:** Post-2022 central bank gold buying may have changed gold's rate sensitivity (WGC: gold decoupled from real rates 2022-2024).
- **External dependency:** FOMC calendar + surprise component (Fed funds futures) not in repo.
- **Event study methodology required** — not standard backtest framework.
- **Exness spread on FOMC days:** Likely widens significantly (max 3352 pts observed) → cost headroom uncertain.

**Plausibility Verdict: MEDIUM (but METHODOLOGICAL MISMATCH)**  
Economic mechanism is well-grounded (FOMC → rates → gold). But **event-driven strategy with n=40 is incompatible with the programme's statistical framework** (requires IS/OOS/MC on continuous time-series). Would need separate event-study validation track. **Not suitable for standard Programme 02 advancement** under current framework.

---

## 3. Gate A Summary: Economic Plausibility Pass/Fail

| Candidate | Plausibility Tier | Gate A Result | Rationale |
|-----------|-------------------|---------------|-----------|
| **005: XAU-VOL-REGIME-SESSION-005** | MEDIUM-HIGH | **PASS** | Informed vs noise trading regimes; gold monthly regime evidence (Paper 2); crypto intraday regime evidence (Paper 11); base signal from Paper 12 |
| **006: XAU-SESSION-CALENDAR-006** | LOW-MEDIUM | **CONDITIONAL PASS** | Institutional calendars exist but Paper 1 negative at monthly (SPA corrected); requires rigorous session control + FDR; weak direct evidence |
| **007: XAU-ASIAN-VOL-BREAKOUT-007** | MEDIUM | **PASS** | Informed trading in high vol (Kyle 1985); central bank narrative (Paper 12); but novel signal, untested |
| **008: XAU-EUROPE-OPEN-REVERSAL-008** | LOW | **FAIL** | Paper 11: reversal "unique to crypto"; gold participant base different; likely Gate D fail compounds |
| **009: XAU-FOMC-EVENT-009** | MEDIUM | **FAIL (Framework Mismatch)** | Economic mechanism sound but n=40 events incompatible with continuous IS/OOS/MC framework; requires event-study track |

---

## 4. Gate A Advancement Decision

**Candidates PASSING Gate A (eligible for Gates B-E):**
1. **XAU-VOL-REGIME-SESSION-005** — PASS
2. **XAU-SESSION-CALENDAR-006** — CONDITIONAL PASS (with caveats)
3. **XAU-ASIAN-VOL-BREAKOUT-007** — PASS

**Candidates FAILING Gate A:**
4. **XAU-EUROPE-OPEN-REVERSAL-008** — FAIL (low plausibility + likely Gate D fail)
5. **XAU-FOMC-EVENT-009** — FAIL (framework mismatch for Programme 02)

**Three candidates proceed to Gate B (Data Eligibility).**

---

*End of Gate A Economic Plausibility Assessment*  
*Generated: 2026-11-25*  
*Next: Gate B Data Eligibility Report*