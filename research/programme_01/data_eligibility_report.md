# M.A.R.S. Quant — Research Programme 01
## Phase E: Data Eligibility Report

**Date:** 2026-11-25  
**Primary Instrument:** Exness XAUUSDm  
**Primary Timeframe:** M5 (H1 context, M1 optional)  
**Dataset Version:** v1.2.0 (M5/H1), v1.0.0 (D1 excluded)

---

## 1. Dataset Inventory

| Dataset | Version | Rows | Date Range | Source | Status |
|---------|---------|------|------------|--------|--------|
| XAUUSDm M5 | v1.2.0 | 369,972 | 2021-07-16 13:00 UTC → 2026-10-09 20:55 UTC | Exness MT5 History Centre (consolidated) | **PRIMARY** |
| XAUUSDm H1 | v1.2.0 | 30,898 | 2021-07-16 13:00 UTC → 2026-10-09 20:00 UTC | Resampled from M5 v1.2.0 | **CONTEXT** |
| XAUUSDm D1 | v1.0.0 | 478 | 2020-01-02 00:00 UTC → 2021-07-16 00:00 UTC | Exported daily block (excluded from M5) | **EXCLUDED** (preserved for audit) |

---

## 2. Eligibility Gate Verification

### 2.1 Source Provenance ✅
- **Raw source:** `data/raw/xauusdm/m5/exness/XAUUSDm_M5_2020_2026_raw.csv` (consolidated Exness export)
- **Original yearly exports:** `C:\Users\RIDGE\trading-data\XAUUSDm_M5_*.csv` (immutable, outside repo)
- **SHA-256 recorded** for every source file in `SourceInventory` (builder output)
- **Filename vs content audit:** 2020 file = entirely daily bars; 2021 file = daily prefix + true M5; 2024 file = full year mislabelled as "jan to feb" — contents authoritative

### 2.2 Date Coverage ✅
- **M5 v1.2.0:** 2021-07-16 13:05 UTC → 2026-10-09 20:55 UTC (true M5 only)
- **Covers proposed IS:** 2021-07 → 2024-12 (3.5 years)
- **Covers proposed OOS:** 2025-01 → 2025-10 (10 months in v1.2.0)
- **Note:** 2026 data available but reserved for future validation

### 2.3 Timeframe ✅
- **True M5 only:** Daily-interval block (478 rows, spread=0) removed via `classify_daily_interval()`
- **Validation gate:** `validate_m5(expect_five_minute=True)` blocks any remaining daily intervals
- **H1:** Resampled from M5 v1.2.0 using `resample_ohlcv(rule="1h")` — single source, no grid mismatch

### 2.4 Timestamp Convention ✅
- **UTC timestamps** (validated in builder: `tz_localize("UTC")` or `tz_convert("UTC")`)
- **Monotonic increasing** enforced (hard failure in validation gate)
- **No duplicate timestamps** (hard failure)

### 2.5 Timezone ✅
- Data stored in UTC
- Session mapping uses fixed UTC boundaries (Asia 00-08, Europe 08-14:30, US 14:30-24)
- **DST note:** Exness server time tracks European DST (UTC+2 winter, UTC+3 summer). Fixed UTC session definitions mean seasonal distortions during DST transitions — documented but not silently corrected (per `cross_session_momentum.py`)

### 2.6 Missing Observations ✅
- **Validation gate classifies gaps:**
  - Weekend gaps (172,800–180,000s): Expected, documented
  - Session break gaps (3,600–4,200s): Daily session closure, documented
  - Multi-day closures: Documented
  - In-session outages: **5 gaps max** (max 5 missing bars), documented with examples, **not filled**
- **No silent filling** — gaps preserved, bar-count indicators unaffected in structure

### 2.7 Duplicate Observations ✅
- **Hard failure** in validation gate: `duplicate_timestamps > 0` → blocks dataset

### 2.8 OHLC Integrity ✅
- **Hard failure:** Any row with `high < low`, `high < open`, `high < close`, `low > open`, `low > close` → blocks dataset
- **Non-positive prices:** Hard failure

### 2.9 Spread Availability ✅
- **Observed spread column preserved** from Exness export (integer points)
- **M5 v1.2.0 spread stats:**
  - Mean: 201.4 points
  - Median: 200 points
  - Max: 3,352 points
  - Zero spread rows: 98 (0.03%) — cost model substitutes per-bar median
- **H1 v1.2.0 spread stats:**
  - Mean: 201.6 points
  - Median: 200 points
  - Max: 2,023 points
  - Zero spread rows: 8
- **Units:** 1 point = 0.001 price units (per `InstrumentSpec.point_size`). 200 points = 0.2 price = 20 pips.
- **Cost model:** Uses observed spread directly (`use_observed_spread=True`, `spread_multiplier=1.0`)

### 2.10 Tick-Volume Availability ✅
- **Preserved** from Exness export (`tick_volume` column)
- **Sum aggregation** on resampling (M5 → H1)
- **Available for:** Liquidity regime filter, volume-weighted features

### 2.11 H1/M5 Alignment ✅
- **Critical finding (Assignment 14):** Raw Exness H1 export sits on different hourly grid (DST-shifted) vs M5
- **Solution:** H1 **always resampled from M5 v1.2.0** — single source, single timeframe, no look-ahead
- **Validation:** `resample_ohlcv()` drops periods with no source bars; keeps partial periods (flagged by caller)

### 2.12 Resampling Convention ✅
- **OHLCV:** open=first, high=max, low=min, close=last, tick_volume=sum, volume=sum, spread=mean
- **Closed-candle:** Periods with no source bars dropped; partial periods kept
- **No forward-fill** — no invented data

### 2.13 Look-Ahead Leakage ✅
- **Session signal design (cross_session_momentum.py):** Signal for session N uses only session N-1 data (available at session N open)
- **Entry at session N open, exit at session N close** — no intra-session look-ahead
- **Chronological splits:** Train/Val/Test by time order (no shuffle)

---

## 3. Data Quality Summary (Validation Report)

| Metric | M5 v1.2.0 | H1 v1.2.0 | Threshold |
|--------|-----------|-----------|-----------|
| Rows | 369,972 | 30,898 | > 100k |
| Duplicate timestamps | 0 | 0 | 0 (hard) |
| Monotonic index | True | True | True (hard) |
| OHLC violations | 0 | 0 | 0 (hard) |
| Non-positive prices | 0 | 0 | 0 (hard) |
| Missing values | 0 | 0 | 0 (hard) |
| Negative spread | 0 | 0 | 0 (hard) |
| Zero spread rows | 98 (0.03%) | 8 (0.03%) | Note only |
| Daily intervals remaining | 0 | N/A | 0 (hard) |
| Non-5-min intervals | 0 | N/A | 0 (hard) |
| Weekend gaps | ~1,040 | ~87 | Expected |
| Session break gaps | ~1,300 | ~109 | Expected |
| In-session outages | 5 (max 5 bars) | 0 | Documented |

---

## 4. Suitability for XAU-SESSION-MOM-001

| Requirement | Met? | Evidence |
|-------------|------|----------|
| Session return decomposition (Asia/Europe/US) | ✅ | M5/H1 data covers all sessions 2021-2025; fixed UTC boundaries defined |
| Cross-session momentum (prev session → next session) | ✅ | 3 sessions × ~1,300 trading days = ~3,900 session observations |
| Session-open intraday momentum (first M5 bars) | ✅ | M5 resolution (12 bars/session) allows first 3-bar signal |
| Volatility regime filter (realized vol, ATR) | ✅ | M5 close prices → realized vol, ATR computable |
| FOMC day filter | ⚠️ | **External dependency** — FRED/investing.com calendar needed |
| Real-rate regime proxy (Gold + Treasury) | ⚠️ | **External dependency** — DGS10 (10Y), DXY from FRED/Yahoo |
| $30 account feasibility (spread, min lot) | ✅ | Observed spread + InstrumentSpec (min 0.01 lots) available |
| Cost model (observed spread only) | ✅ | Spread column preserved; commission/slippage/swap configurable assumptions |

---

## 5. Known Limitations & Mitigations

| Limitation | Impact | Mitigation |
|------------|--------|------------|
| **Fixed UTC sessions** (no DST adjustment) | Seasonal distortion: Europe/US sessions shift relative to local market hours during DST transitions | Documented in `cross_session_momentum.py`; test DST-adjusted variant in sensitivity |
| **Short OOS in v1.2.0** (only 10 months of 2025) | Limited out-of-sample evidence | Reserve 2026 data for future validation; use walk-forward in IS |
| **No FOMC calendar in repo** | Cannot test regime filter without external data | Source from FRED (FOMC meeting dates) or investing.com; add to data ingestion |
| **No Treasury/DXY data in repo** | Cannot test real-rate regime proxy | Add FRED ingestion (DGS10, DTWEXBGS) or Yahoo Finance |
| **Spread units ambiguity** (200 points median = 20 pips?) | Cost model depends on correct interpretation | Verify with Exness spec: 1 point = 0.001 price; 200 points = 0.2 = 20 pips. If Exness typical spread is 0.3 pips, data may be in different units. **ACTION: Verify with raw Exness export.** |
| **In-session outages** (max 5 missing bars) | Bar-count indicators (ATR, rolling) unaffected in structure but missing data | Documented; sensitivity test with/without outage periods |

---

## 6. Spread Unit Verification (Critical)

**Observed:** Median spread = 200 points in processed data  
**InstrumentSpec:** `point_size = 0.001`, `pip_size = 0.01`  
**Implied:** 200 points × 0.001 = 0.2 price units = 20 pips (since 1 pip = 0.01)

**Exness Typical Spread:** ~0.3 pips (raw spread account) = 3 points

**Discrepancy:** 20 pips vs 0.3 pips = **67× difference**

**Possible Explanations:**
1. Exness CSV spread column is in **different units** (e.g., 1/10 pip = 0.1 pip per point)
2. Point size in InstrumentSpec is wrong (should be 0.0001?)
3. Data comes from different account type (standard vs raw spread)

**Action Required:** 
- Inspect raw Exness CSV spread values directly
- Compare with Exness contract specification
- Adjust `InstrumentSpec.point_size` if needed
- **This must be resolved before Phase F (cost model depends on it)**

---

## 7. Verdict

**DATA ELIGIBLE WITH ONE CRITICAL RESOLUTION**

✅ All structural requirements met  
✅ Sufficient coverage for IS (2021-2024) and OOS (2025)  
✅ Session decomposition, cross-session momentum, intraday momentum all supported  
⚠️ **BLOCKER:** Spread unit verification required before cost model can be trusted  
⚠️ External data needed for FOMC calendar and real-rate regime proxy (Phase F+)

**Next Step:** Resolve spread unit discrepancy → then proceed to Phase F (Formal Strategy Specification)

---

*End of Data Eligibility Report*  
*Generated: 2026-11-25*  
*Next: Phase F — Formal Strategy Specification for XAU-SESSION-MOM-001*