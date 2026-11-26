# M.A.R.S. Quant — Research Programme 02
## Gate B: Data Eligibility Report

**Date:** 2026-11-25  
**Phase:** Assignment 19 — Research Discovery, Economic Plausibility and Candidate Screening  
**Input:** Gate A survivors (3 candidates): XAU-VOL-REGIME-SESSION-005, XAU-SESSION-CALENDAR-006, XAU-ASIAN-VOL-BREAKOUT-007  
**Data Baseline:** Exness XAUUSDm M5 v1.2.0 (369,972 bars, 2021-07-16 to 2026-10-09), H1 v1.2.0 (30,898 bars)  
**Data Catalog:** `data/catalog.yaml` | **Instrument Spec:** `configs/instrument_spec_xauusdm.yaml`

---

## 1. Data Eligibility Framework

| Requirement | Standard | Verification Method |
|-------------|----------|---------------------|
| **Source Provenance** | Immutable raw source with SHA-256; lineage documented | `data/catalog.yaml` source_checksums |
| **Date Coverage** | Covers proposed IS (2021-07 to 2024-12) and OOS (2025-01 to 2025-10) | Index range check |
| **Timeframe Integrity** | True M5 (no daily blocks); H1 resampled from M5 (no grid offset) | `validate_m5(expect_five_minute=True)` |
| **Timestamp Convention** | UTC, monotonic, no duplicates | Validation gates (hard failures) |
| **OHLC Integrity** | High ≥ Low, High ≥ Open/Close, Low ≤ Open/Close, prices > 0 | Hard failure gates |
| **Spread Availability** | Observed spread column preserved; units verified | Per-bar spread in points |
| **Tick Volume** | Preserved from Exness export (only volume proxy) | `tick_volume` column |
| **Session Alignment** | Fixed UTC boundaries (Asia 00-08, Europe 08-14:30, US 14:30-24) | Defined in instrument spec |
| **Look-Ahead Prevention** | Signal uses only prior-session data; chronological splits | `cross_session_momentum.py` design |
| **External Dependencies** | Documented with access plan; not required for core test | FOMC calendar, Treasury/DXY |

---

## 2. Baseline Data Verification (Exness XAUUSDm M5 v1.2.0)

| Metric | Value | Status | Source |
|--------|-------|--------|--------|
| **Rows** | 369,972 | ✅ | `data/catalog.yaml` |
| **Date Range** | 2021-07-16 13:00 UTC → 2026-10-09 20:55 UTC | ✅ | Parquet index |
| **True M5 Only** | Daily block (478 rows, 2020-01 to 2021-07) excluded | ✅ | `classify_daily_interval()` |
| **Duplicate Timestamps** | 0 | ✅ | Hard validation gate |
| **Monotonic Index** | True | ✅ | Hard validation gate |
| **OHLC Violations** | 0 | ✅ | Hard validation gate |
| **Non-Positive Prices** | 0 | ✅ | Hard validation gate |
| **Spread Column** | Preserved (integer points) | ✅ | `spread` column |
| **Spread Median** | 200 points | ✅ | `df['spread'].median()` |
| **Spread Mean** | 201.4 points | ✅ | `df['spread'].mean()` |
| **Zero-Spread Bars** | 98 (0.03%) | ⚠️ Documented | Cost model substitutes median |
| **Tick Volume** | Preserved | ✅ | `tick_volume` column |
| **Real Volume** | All zeros (Exness limitation) | ⚠️ Documented | `<VOL>` identically zero |
| **In-Session Outages** | 20 (max 10 missing bars) | ⚠️ Documented | Not filled |
| **H1 Resampled** | From M5 v1.2.0 (single source, no grid offset) | ✅ | `resample_ohlcv(rule="1h")` |
| **H1 Rows** | 30,898 | ✅ | `data/catalog.yaml` |

**Critical Spread Unit Note (from Programme 01 Data Eligibility Report):**
- Observed median spread = 200 points
- `InstrumentSpec.point_size = 0.001` → 200 pts = 0.2 price = 20 pips
- Exness Standard typical spread ~20 pips (consistent)
- Exness Raw Spread ~0.3 pips (different account type)
- **Verified:** Data is from Exness **Standard** account (not Raw Spread)
- Cost model uses observed spread directly (per-bar, not constant)

---

## 3. Candidate-by-Candidate Data Eligibility

### Candidate 005: XAU-VOL-REGIME-SESSION-005 (Vol-Regime Session Momentum)

| Requirement | Met? | Evidence / Gap |
|-------------|------|----------------|
| Session return decomposition (Asia/Europe/US) | ✅ | M5/H1 covers all sessions 2021-2025; fixed UTC boundaries defined |
| Cross-session momentum (prev session → next session) | ✅ | 3 sessions × ~1,300 trading days = ~3,900 session observations |
| H1 realized volatility (20-bar) | ✅ | M5 close prices → H1 resampled → rolling std computable |
| FOMC day filter | ⚠️ **EXTERNAL** | FRED/investing.com calendar needed; not in repo |
| Spread at entry (M5) | ✅ | Per-bar observed spread available |
| Spread percentile filter (bottom 2 quintiles) | ✅ | Computable from historical spread distribution |
| $30 feasibility data (spread, min lot, contract spec) | ✅ | All in instrument spec + observed spread |
| **IS Period Coverage** | ✅ | 2021-07-16 → 2024-12-31 (~3.5 years, ~900 sessions) |
| **OOS Period Coverage** | ✅ | 2025-01-01 → 2025-10-09 (~10 months, ~220 sessions) |
| **2026 Reserve** | ✅ | 2025-10 → 2026-10 available for future validation |

**External Dependencies:**
- **FOMC Calendar:** Required for regime filter. Source: FRED (FOMC meeting dates) or investing.com. Access plan: Download CSV, add to `data/external/fomc_calendar.csv`. **Not required for core test** — can test without FOMC filter first.

**Data Eligibility Verdict: ELIGIBLE WITH EXTERNAL DEPENDENCY**  
Core test (session momentum + vol + spread filters) uses only internal data. FOMC filter is enhancement — document as sensitivity.

---

### Candidate 006: XAU-SESSION-CALENDAR-006 (Session-Controlled Calendar Seasonality)

| Requirement | Met? | Evidence / Gap |
|-------------|------|----------------|
| M5 returns by session (Asia/Europe/US) | ✅ | Session decomposition on M5 v1.2.0 |
| Day-of-week effects | ✅ | `index.dayofweek` on M5 timestamps |
| Week-of-month effects | ✅ | Computable from M5 timestamps |
| Month-of-year effects | ✅ | `index.month` on M5 timestamps |
| Specific hour effects (00:00, 08:00, 14:30, 17:00 UTC) | ✅ | M5 resolution (12 bars/session) allows hour isolation |
| Session control (partial out session effects) | ✅ | Regress returns on session dummies + calendar dummies |
| FDR control for multiple testing | ✅ | Methodology (Benjamini-Hochberg) — no data dependency |
| $30 feasibility data | ✅ | Instrument spec + observed spread |
| **IS Period Coverage** | ✅ | 2021-07 → 2024-12 (3.5 years, ~1,800 trading days) |
| **OOS Period Coverage** | ✅ | 2025-01 → 2025-10 (10 months, ~220 trading days) |
| **Per-Cell Sample Size** | ⚠️ **LOW** | 3.5 years / (5 days × 4 weeks × 12 months) ≈ 1.5 obs/cell |

**External Dependencies:** None — all internal data.

**Critical Concern:** Per-cell sample size extremely low (~1-2 observations per calendar cell in IS). Statistical power for day-of-week × week-of-month × month-of-year × hour interactions is negligible. **Must aggregate** (e.g., day-of-week only, or month-of-year only) to achieve usable cell counts.

**Data Eligibility Verdict: ELIGIBLE BUT STATISTICALLY CHALLENGED**  
Data exists but multiple testing burden + low per-cell counts require aggressive aggregation and FDR control. Core test feasible; interaction tests not feasible.

---

### Candidate 007: XAU-ASIAN-VOL-BREAKOUT-007 (Asian Session Volatility Breakout)

| Requirement | Met? | Evidence / Gap |
|-------------|------|----------------|
| Asian session (00:00-08:00 UTC) OHLC | ✅ | H1 resampled from M5: 8 H1 bars = Asia session |
| Asian session realized volatility | ✅ | M5 close prices within session → rolling std |
| Asian session midpoint (high+low)/2 | ✅ | Computable from session H1 bars |
| Breakout direction: sign(close - midpoint) | ✅ | Computable |
| Trailing 60-session vol percentile (60th) | ✅ | Rolling window on session-level vol series |
| Europe session (08:00-14:30 UTC) returns | ✅ | H1 resampled: 6-7 H1 bars = Europe session |
| Spread at entry (08:00 M5) | ✅ | Per-bar observed spread |
| $30 feasibility data | ✅ | Instrument spec + observed spread |
| **IS Period Coverage** | ✅ | ~900 Asia sessions (2021-07 to 2024-12) |
| **OOS Period Coverage** | ✅ | ~220 Asia sessions (2025-01 to 2025-10) |
| **Trailing Window Burn-in** | ⚠️ | First 60 sessions (2021-07 to ~2021-10) unavailable for signal |

**External Dependencies:** None — all internal data.

**Critical Concern:** Trailing 60-session window for vol percentile means first ~3 months of data cannot generate signals (burn-in). Effective IS start ≈ 2021-10. Still ~3.2 years usable.

**Data Eligibility Verdict: ELIGIBLE**  
All data internal. Burn-in period documented. Sufficient sessions for statistical validity (~840 IS, ~220 OOS).

---

## 4. Gate B Summary: Data Eligibility Pass/Fail

| Candidate | Core Data | External Dependencies | Statistical Power | Gate B Result |
|-----------|-----------|----------------------|-------------------|---------------|
| **005: XAU-VOL-REGIME-SESSION-005** | ✅ Complete | FOMC calendar (optional enhancement) | ✅ ~900 IS / ~220 OOS sessions | **PASS** |
| **006: XAU-SESSION-CALENDAR-006** | ✅ Complete | None | ⚠️ Low per-cell; requires aggregation | **CONDITIONAL PASS** (with aggregation plan) |
| **007: XAU-ASIAN-VOL-BREAKOUT-007** | ✅ Complete | None | ✅ ~840 IS / ~220 OOS sessions (post burn-in) | **PASS** |

---

## 5. Data Limitations Carried Forward (from Programme 01)

| Limitation | Impact on Programme 02 | Mitigation |
|------------|------------------------|------------|
| **Fixed UTC sessions (no DST adjustment)** | Seasonal distortion: Europe/US sessions shift relative to local market hours during DST transitions | Documented; test DST-adjusted variant in sensitivity (not core) |
| **Short OOS in v1.2.0** (only 10 months of 2025) | Limited out-of-sample evidence | Reserve 2026 data for future validation; use walk-forward in IS |
| **No FOMC calendar in repo** | Cannot test Candidate 005 FOMC filter without external data | Source from FRED; add to data ingestion; test without first |
| **No Treasury/DXY data in repo** | Cannot test real-rate regime proxy (Candidate 005 enhancement) | Not required for core tests; enhancement only |
| **Spread unit ambiguity resolved** | Cost model depends on correct interpretation | Verified: 200 pts = 20 pips = Exness Standard; cost model uses per-bar observed spread |
| **In-session outages** (max 10 missing bars) | Bar-count indicators (ATR, rolling) unaffected in structure | Documented; sensitivity test with/without outage periods |

---

## 6. Gate B Advancement Decision

**Candidates PASSING Gate B (eligible for Gates C-E):**
1. **XAU-VOL-REGIME-SESSION-005** — PASS
2. **XAU-SESSION-CALENDAR-006** — CONDITIONAL PASS (requires aggregation plan for calendar cells)
3. **XAU-ASIAN-VOL-BREAKOUT-007** — PASS

**All three Gate A survivors pass Gate B.** Proceed to Gate C (Spread/Cost Feasibility).

---

*End of Gate B Data Eligibility Report*  
*Generated: 2026-11-25*  
*Next: Gate C Spread/Cost Feasibility Report*