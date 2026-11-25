# M.A.R.S. Quant — Large File and Storage Report

**Date:** 2026-11-25  
**Assignment:** 18 — Repository Reconciliation  
**Scope:** All files ≥ 1 MB in the working tree (tracked, modified, untracked)

---

## Large File Inventory

| # | Path | Size | Status | Git/Git LFS Suitability | Recommended Storage |
|---|------|------|--------|------------------------|---------------------|
| 1 | `data/raw/xauusdm/m5/exness/XAUUSDm_M5_2020_2026_raw.csv` | **32.1 MB** | Untracked | **Git LFS Required** — Exceeds 10 MB comfort zone; under 50 MB warning but best practice for LFS | **Git LFS** with manifest in Git |
| 2 | `reports/assignment14/ledger/equity_curve_in_sample.csv` | **11.0 MB** | Untracked | **Git LFS Required** — Exceeds 10 MB; not regeneratable without full backtest | **Git LFS** with manifest in Git |
| 3 | `data/processed/xauusdm/m5/v1.2.0/data.parquet` | **11.1 MB** | Ignored (`.gitignore`) | **Keep Ignored** — Regeneratable from raw data; manifest tracks version | External (not in Git) |
| 4 | `reports/assignment14/ledger/equity_curve_out_of_sample.csv` | **5.7 MB** | Untracked | **Git LFS Recommended** — Under 10 MB but large for regular Git; not regeneratable | **Git LFS** |
| 5 | `data/raw/xauusdm/h1/exness/XAUUSDm_H1_2015_2025_raw.parquet` | **2.1 MB** | Untracked | **Git LFS Recommended** — Under 10 MB; raw data regeneratable from broker | **Git LFS** or keep in Git |
| 6 | `reports/programme_01/session_momentum_001/mc/mc_results.json` | **818 KB** | Untracked | **Regular Git OK** — Under 1 MB threshold | Regular Git |
| 7 | `reports/assignment14/monte_carlo_equity_fan.png` | **245 KB** | Untracked | **Regular Git OK** | Regular Git |
| 8 | `reports/assignment14/monte_carlo_distributions.png` | **73 KB** | Untracked | **Regular Git OK** | Regular Git |
| 9 | `reports/assignment14/ledger/trades_out_of_sample.csv` | **698 KB** | Untracked | **Regular Git OK** | Regular Git |
| 10 | `reports/assignment14/ledger/trades_in_sample.csv` | **650 KB** | Untracked | **Regular Git OK** | Regular Git |
| 11 | `reports/paper_trading/ma_tsm_001/PAPER_TRADING_READINESS_REPORT.md` | **25.8 KB** | Untracked | **Regular Git OK** | Regular Git |
| 12 | `mt5_audit_backup.db` | **123 KB** | Modified | **Exclude** — Empty schema, regeneratable | Not in Git |

---

## Git vs Git LFS vs External Storage Decision Matrix

| File Type | Size Range | Git | Git LFS | External (S3/GCS) | Rationale |
|-----------|------------|-----|---------|-------------------|-----------|
| Source code, configs, docs | < 1 MB | ✅ | ❌ | ❌ | Standard |
| Research reports, manifests | < 1 MB | ✅ | ❌ | ❌ | Standard |
| Trade ledgers, results CSVs | 100 KB – 1 MB | ✅ | ⚠️ | ❌ | Git OK; LFS if > 1 MB |
| Large equity curves, MC results | 1 – 50 MB | ⚠️ | ✅ | ⚠️ | LFS preferred; external for > 50 MB |
| Raw OHLCV datasets | 2 – 100+ MB | ❌ | ✅ | ✅ | LFS for < 50 MB; external for > 50 MB |
| Processed parquet datasets | 10 – 500+ MB | ❌ | ⚠️ | ✅ | Regeneratable — keep external/ignored |

---

## Current .gitignore Coverage

### Covered ✅
- `data/processed/**/*.parquet` — Line 211
- `__pycache__/`, `*.pyc`, `.pytest_cache/`, etc. — Standard patterns
- `.env`, `.venv`, `venv/` — Lines 140-147
- `risk_kill_switch*.db` — Lines 219-221

### Gaps ⚠️
- `data/raw/**/*.csv` — **NOT ignored** (32 MB file untracked)
- `data/raw/**/*.parquet` — **NOT ignored** (2.1 MB file untracked)
- `reports/assignment14/ledger/equity_curve_*.csv` — **NOT ignored** (11 MB + 5.7 MB)
- `reports/programme_01/**/mc_results.json` — **NOT ignored** (818 KB, OK for Git but should be explicit)
- `*_audit*.db` — **NOT ignored** (audit databases)

### Recommended .gitignore Additions

```gitignore
# Raw data files — use Git LFS instead of committing directly
data/raw/**/*.csv
data/raw/**/*.parquet

# Large research outputs — use Git LFS
reports/assignment14/ledger/equity_curve_*.csv
reports/programme_01/**/mc_results.json

# Audit databases
*_audit*.db
*_audit*.db-*
```

---

## Git LFS Configuration Status

### Current `.gitattributes`
```gitattributes
data/raw/xauusd_m5_2003_2026_raw.csv filter=lfs diff=lfs merge=lfs -text
```

**Issues:**
1. Tracks `xauusd_m5_2003_2026_raw.csv` (old file) — **not the current 32 MB file**
2. Current raw file is `data/raw/xauusdm/m5/exness/XAUUSDm_M5_2020_2026_raw.csv` — different path
3. No LFS tracking for equity curves or H1 raw data

### Required `.gitattributes` Updates

```gitattributes
# Raw data (LFS)
data/raw/xauusdm/m5/exness/XAUUSDm_M5_2020_2026_raw.csv filter=lfs diff=lfs merge=lfs -text
data/raw/xauusdm/h1/exness/XAUUSDm_H1_2015_2025_raw.parquet filter=lfs diff=lfs merge=lfs -text

# Large research outputs (LFS)
reports/assignment14/ledger/equity_curve_in_sample.csv filter=lfs diff=lfs merge=lfs -text
reports/assignment14/ledger/equity_curve_out_of_sample.csv filter=lfs diff=lfs merge=lfs -text
reports/programme_01/session_momentum_001/mc/mc_results.json filter=lfs diff=lfs merge=lfs -text
```

---

## Dataset Reproducibility Strategy

### Manifest-Driven Approach (Current)

| Dataset | Manifest Location | Contains |
|---------|------------------|----------|
| M5 v1.2.0 | `data/processed/xauusdm/m5/v1.2.0/_manifest.json` | SHA256, row count, date range, columns |
| H1 v1.2.0 | `data/processed/xauusdm/h1/v1.2.0/_manifest.json` | SHA256, row count, date range, columns |
| Raw M5 | `data/raw/xauusdm/m5/exness/_manifest.json` | SHA256, source, date range |
| Raw H1 | `data/raw/xauusdm/h1/exness/_manifest.json` | SHA256, source, date range |
| Catalog | `data/catalog.yaml` | All versions, checksums, metadata |

### Verification Commands

```bash
# Verify processed M5 v1.2.0
python -c "
import pandas as pd, hashlib, json
df = pd.read_parquet('data/processed/xauusdm/m5/v1.2.0/data.parquet')
with open('data/processed/xauusdm/m5/v1.2.0/_manifest.json') as f:
    m = json.load(f)
print('Rows:', len(df), 'vs manifest:', m['rows'])
print('SHA256:', hashlib.sha256(df.to_parquet()).hexdigest()[:16], 'vs manifest:', m['sha256'][:16])
"

# Verify raw M5 CSV
python -c "
import hashlib, json
with open('data/raw/xauusdm/m5/exness/_manifest.json') as f:
    m = json.load(f)
with open('data/raw/xauusdm/m5/exness/XAUUSDm_M5_2020_2026_raw.csv', 'rb') as f:
    h = hashlib.sha256(f.read()).hexdigest()
print('SHA256 match:', h == m['sha256'])
"
```

---

## GitHub LFS Quota Considerations

| Metric | Value |
|--------|-------|
| Free LFS storage | 1 GB |
| Free LFS bandwidth | 1 GB/month |
| Current LFS files (estimated) | ~47 MB (5 files) |
| Projected after Assignment 18 | ~47 MB |
| Remaining quota | ~953 MB |

**Verdict:** Well within free tier. No paid LFS needed currently.

---

## Recommended Actions

### Immediate (Before Commit)
1. **Add `.gitignore` entries** for raw CSV/Parquet and equity curves
2. **Update `.gitattributes`** with LFS patterns for 5 large files
3. **Run `git lfs install`** and `git lfs track` for each large file
4. **Verify LFS tracking** with `git lfs ls-files`

### During Commit
1. Stage manifests and catalogs in regular Git
2. Stage LFS-tracked files via `git add` (LFS handles pointer files)
3. Do NOT stage ignored files (processed parquet, audit DB)

### Post-Sync Verification
1. `git lfs ls-files` — confirm 5 LFS files tracked
2. `git ls-files | grep -E "\.(csv|parquet)$"` — confirm no large files in regular Git
3. Clone fresh repo and run `git lfs pull` — verify large files download

---

## Total Repository Size Estimate

| Component | Size (MB) | In Git | In LFS |
|-----------|-----------|--------|--------|
| Source code, configs, docs | ~5 | ✅ | — |
| Research reports, manifests | ~5 | ✅ | — |
| Test files | ~1 | ✅ | — |
| Trade ledgers (small) | ~2 | ✅ | — |
| **Large files (LFS)** | **~47** | — | ✅ |
| **Ignored (processed parquet)** | **~11** | — | — |
| **Total tracked** | **~13** | ✅ | — |
| **Total with LFS** | **~60** | — | — |

---

**End of Large File and Storage Report**  
**Next Step:** Implement .gitignore and .gitattributes updates, then execute staging plan.