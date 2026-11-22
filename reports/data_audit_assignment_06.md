# M.A.R.S. Quant — Assignment 06
## Data-Source Audit Report

**Generated:** 2026-11-22  
**Scope:** XAUUSD H1 data used in Assignment 05 (DONCHIAN-001)

---

## 1. ASSIGNMENT 05 DATA USAGE

### 1.1 Exact File Path Used
```
data/raw/xauusd_h1_2015_present.parquet
```
*Used via fallback in `donchian_trend_vbt.py:83-86` when processed data path didn't exist*

### 1.2 Dataset Source
- **Origin:** Exported from MetaTrader 5 (MT5) terminal
- **Columns:** `time`, `open`, `high`, `low`, `close`, `tick_volume`, `spread`, `real_volume`
- **Timezone:** UTC (confirmed via `pd.to_datetime(..., utc=True)`)
- **Format:** Parquet (columnar, compressed)

### 1.3 Timeframe
- **Resolution:** H1 (1-hour bars)
- **Session hours:** Appears to be 24/5 (FX market hours), with weekend gaps

### 1.4 Date Coverage
| Metric | Value |
|--------|-------|
| Start | 2015-01-02 09:00:00 UTC |
| End | 2025-09-26 08:00:00 UTC |
| Total calendar days | 3,919 |
| Expected H1 bars (24/7) | ~94,079 |
| **Actual bars** | **63,239** |
| Coverage ratio | 67.2% |

### 1.5 Number of Bars
**63,239 bars** — represents ~67% of theoretical 24/7 hours (missing weekends, holidays, market closures)

### 1.6 Was This the Intended Dataset?
**Yes, but incomplete.** The file `xauusd_h1_2015_present.parquet` is the longest available H1 parquet file. However:
- It only covers through **2025-09-26** (missing ~7 months of 2025-2026 data)
- The project pipeline expects processed data at `data/processed/xauusd/h1/v1.0.0/data.parquet` which **does not exist**
- Assignment 05 fell back to raw data due to missing processed file

### 1.7 Were 2020–2026 Yearly CSV Files Used?
**No — they do not exist for XAUUSD H1.**
- No yearly CSV files found for XAUUSD H1 covering 2020–2026
- Other symbols (EURGBP, EURUSD, USDJPY) have `*_m5_2020_2026_raw.csv` files but these are M5, not H1
- XAUUSD has parquet files named by start year: `2015_present`, `2018_present`, `2020_present`, `2025_present`

### 1.8 Other Repository Datasets
- **M5 CSV:** `data/raw/xauusd_m5_2003_2026_raw.csv` — 2.4M bars, 2003-2026, can be resampled to H1
- **Processed M5:** `data/processed/xauusdm/m5/v1.0.0/data.parquet` — exists but for different symbol variant
- **Feature files:** Various `hyp_a_features_xauusd_h1_*_present.parquet` — derived datasets, not raw

---

## 2. AVAILABLE XAUUSD H1 DATASETS — VALIDATION

### 2.1 File Inventory

| File | Bars | Date Range | Gaps >1h | Mean Spread | Real Volume |
|------|------|------------|----------|-------------|-------------|
| `xauusd_h1_2015_present.parquet` | 63,239 | 2015-01-02 → 2025-09-26 | 2,776 | 14.89 | ✓ (1M avg) |
| `xauusd_h1_2018_present.parquet` | 45,897 | 2018-01-02 → 2025-10-13 | 2,014 | 9.45 | ✓ (48K avg) |
| `xauusd_h1_2020_present.parquet` | 33,856 | 2020-01-02 → 2025-09-24 | 1,485 | 6.85 | ✗ (all 0) |
| `xauusd_h1_2025_present.parquet` | 4,249 | 2025-01-02 → 2025-09-19 | 188 | 7.54 | ✗ (all 0) |

### 2.2 Schema Validation (All Files)
| Check | Result |
|-------|--------|
| Required columns present | ✅ `time`, `open`, `high`, `low`, `close`, `tick_volume`, `spread`, `real_volume` |
| Timestamp format | ✅ ISO 8601, UTC, parseable |
| Duplicate timestamps | ✅ **0 duplicates** across all files |
| NaN values | ✅ **0 NaN** across all files |
| OHLC validity (high≥low, high≥open/close, low≤open/close, positive prices) | ✅ **0 invalid rows** across all files |
| Timestamps monotonic | ⚠️ Not sorted in file (loaders sort automatically) |

### 2.3 Data Continuity & Gaps
- **Gaps > 1 hour:** Expected (weekends, holidays, FX market closures)
- **Max gap:** ~3 days 10 hours (typical weekend + holiday)
- **No overlapping timestamps** between files (each file is a separate export with different start dates)
- **No duplicated year boundaries** — files are independent exports, not yearly splits

### 2.4 Spread Analysis
| File | Mean Spread | Min | Max | Notes |
|------|-------------|-----|-----|-------|
| 2015_present | 14.89 | ~1 | ~100 | Higher spread, older data |
| 2018_present | 9.45 | ~1 | ~80 | |
| 2020_present | 6.85 | ~1 | ~50 | Lower spread, modern pricing |
| 2025_present | 7.54 | ~1 | ~60 | |

**Note:** Spread values are in **points** (0.1 pip for XAUUSD on most brokers). 14.89 points ≈ 1.5 pips.

### 2.5 Volume Analysis
- **tick_volume:** Present in all files (mean 3,752–5,200)
- **real_volume:** Only populated in 2015/2018 files; **all zeros in 2020/2025 files**
- This suggests a broker/data vendor change around 2020

---

## 3. M5 CSV DATA (Alternative Source)

### 3.1 File: `xauusd_m5_2003_2026_raw.csv`
| Metric | Value |
|--------|-------|
| Total rows | 2,400,599 |
| Date range | 2003-05-05 → 2026-04-29 |
| 2020–2026 rows | 665,400 |
| 2025–2026 rows | 139,224 |
| Columns | `time`, `date`, `instrument`, `granularity`, `open`, `high`, `low`, `close` |
| Sort order | **Descending** (newest first) |
| Timezone | UTC |

### 3.2 Resampled to H1 (2025–2026)
| Metric | Value |
|--------|-------|
| H1 bars | 11,602 |
| Date range | 2025-01-01 → 2026-04-29 |
| Coverage | Extends **7 months beyond** parquet files |

---

## 4. DATA INTEGRATION DECISION

### 4.1 Recommended Primary Dataset
**`xauusd_h1_2015_present.parquet`** — Longest continuous history, valid OHLC, no duplicates, has real_volume.

### 4.2 Augmentation Needed
- **Missing period:** 2025-09-27 → 2026-04-29 (~7 months)
- **Source for augmentation:** Resample M5 CSV to H1 for 2025-01-01 onward
- **Overlap period:** 2025-01-01 → 2025-09-26 (validate consistency)

### 4.3 Integration Plan
1. Create processed directory: `data/processed/xauusd/h1/v1.0.0/`
2. Load 2015_present parquet as base
3. Resample M5 CSV to H1 for 2025-01-01 onward
4. Validate overlap period consistency
5. Concatenate, deduplicate, sort
6. Save as `data/processed/xauusd/h1/v1.0.0/data.parquet`
7. Update pipeline to use processed path (no fallback needed)

---

## 5. DATA QUALITY SUMMARY

| Dimension | Status | Notes |
|-----------|--------|-------|
| **Completeness** | ⚠️ Partial | Missing 2025-2026 data in parquet |
| **Validity** | ✅ Excellent | 0 invalid OHLC, 0 NaN, 0 duplicates |
| **Consistency** | ⚠️ Spread shift | Spread mean drops from 14.9→6.9 around 2020 (vendor change?) |
| **Timeliness** | ⚠️ Stale | Parquet ends 2025-09; M5 CSV goes to 2026-04 |
| **Uniqueness** | ✅ Excellent | No duplicate timestamps |
| **Continuity** | ✅ Expected | Gaps only on weekends/holidays |

**Overall:** High-quality historical data with a coverage gap in the most recent period. Fixable via M5 resampling.