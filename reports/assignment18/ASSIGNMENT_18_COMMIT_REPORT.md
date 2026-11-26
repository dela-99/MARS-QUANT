# M.A.R.S. Quant — Assignment 18 Commit Report

**Date:** 2026-11-25  
**Branch:** `main`  
**Base Commit:** `ce425d2` (Assignment 12)  
**Final Commit:** `5edd051`  
**Total New Commits:** 8

---

## Commit Summary

| # | Hash | Message | Files | Lines +/– |
|---|------|---------|-------|-----------|
| 1 | `453d97d` | feat: add Assignment 16/17 strategy implementations and configs | 14 | +5323 / –2 |
| 2 | `2a6fac6` | fix: mtf_gate 15M fallback resample; refactor run_session_v3 symbol validation | 2 | +23 / –21 |
| 3 | `e3983e9` | docs: add Assignment 14/17 research reports and audit artifacts | 22 | +7483 / –0 |
| 4 | `a519fa8` | docs: add Programme 01 session momentum research outputs | 5 | +933 / –0 |
| 5 | `26a1821` | data: add data catalog and dataset manifests for reproducibility | 10 | +906 / –0 |
| 6 | `8bc5fa9` | test: add unit tests for data prep, dataset v1.2.0, and Donchian strategy | 25 | +6050 / –0 |
| 7 | `8675b30` | docs: add paper trading readiness and root-level audit reports | 17 | +4818 / –0 |
| 8 | `5edd051` | data: add raw data and large research outputs via Git LFS | 8 | +971 / –0 |
| **Total** | | | **103** | **+26,507 / –23** |

---

## Detailed Commit Contents

### Commit 1: `453d97d` — Core Strategy Implementations
**Type:** `feat`  
**Scope:** Source code + Configuration

| File | Status | Description |
|------|--------|-------------|
| `configs/instrument_spec_xauusdm.yaml` | Added | Frozen instrument spec for XAUUSDm (Exness) |
| `configs/session_momentum_001.yaml` | Added | Frozen strategy config for XAU-SESSION-MOM-001 |
| `mars/apps/backtester/mtf_donchian_backtest.py` | Added | Donchian backtester (Assignment 14) |
| `mars/apps/backtester/session_momentum_backtest.py` | Added | Session momentum backtester (Assignment 16) |
| `mars/apps/research_lab/session_momentum_montecarlo.py` | Added | MC validation engine (Assignment 16) |
| `mars/apps/research_lab/session_momentum_research.py` | Added | IS research pipeline (Assignment 16) |
| `mars/apps/research_lab/xau_mtf_donchian_001.py` | Added | Donchian research (Assignment 14) |
| `mars/apps/research_lab/xau_mtf_donchian_montecarlo.py` | Added | Donchian MC (Assignment 14) |
| `mars/libs/data/xauusdm_exness.py` | Added | Data loader for XAUUSDm |
| `mars/libs/risk/contract_aware.py` | Added | Contract-aware risk engine |
| `mars/libs/strategies/xau_mtf_donchian.py` | Added | Donchian strategy (Assignment 14) |
| `mars/libs/strategies/xau_session_momentum.py` | Added | Session momentum strategy (Assignment 16) |

---

### Commit 2: `2a6fac6` — Core Fixes
**Type:** `fix`  
**Scope:** Modified tracked files

| File | Status | Description |
|------|--------|-------------|
| `mars/apps/trading/signals/mtf_gate.py` | Modified | Added 15M → 5M fallback resample; 15min pandas rule |
| `run_session_v3.py` | Modified | Moved symbol validation earlier; validate against PAIR_CONFIG |

---

### Commit 3: `e3983e9` — Assignment 14/17 Reports
**Type:** `docs`  
**Scope:** Research documentation + results

| File | Status | Description |
|------|--------|-------------|
| `reports/assignment14/ACCOUNT_SCALE_AUDIT_30USD.md` | Added | $30 feasibility audit (Assignment 14) |
| `reports/assignment14/ASSIGNMENT_14B_RECONCILIATION_REPORT.md` | Added | Reconciliation report (Assignment 14) |
| `reports/assignment14/assignment14_results.json` | Added | Machine-readable results (Assignment 14) |
| `reports/assignment14/assignment14b_reconciliation.json` | Added | Machine-readable reconciliation (Assignment 14) |
| `reports/assignment14/ledger/*.csv` (12 files) | Added | Trade ledgers, equity curves, exit reasons |
| `reports/assignment14/monte_carlo_*.png` (2 files) | Added | MC visualizations |
| `reports/assignment17/ASSIGNMENT_17_FINAL_AUDIT_REPORT.md` | Added | Final audit report (Assignment 17) |
| `reports/assignment17/ASSIGNMENT_17_TEST_REPORT.md` | Added | Test verification report (Assignment 17) |
| `reports/assignment17/DECISION_LOG_UPDATE.md` | Added | Decision log (Assignment 17) |
| `reports/assignment17/EVIDENCE_MANIFEST.md` | Added | Evidence manifest (Assignment 17) |
| `reports/assignment17/ROADMAP_UPDATE.md` | Added | Roadmap update (Assignment 17) |
| `reports/assignment17/assignment17_audit.json` | Added | Machine-readable audit (Assignment 17) |

---

### Commit 4: `a519fa8` — Programme 01 Research Outputs
**Type:** `docs`  
**Scope:** Session momentum research artifacts

| File | Status | Description |
|------|--------|-------------|
| `reports/programme_01/session_momentum_001/is/is_report.md` | Added | IS human report |
| `reports/programme_01/session_momentum_001/is/is_results.json` | Added | IS machine results |
| `reports/programme_01/session_momentum_001/oos/oos_trades.csv` | Added | Test-split trade ledger (287 trades) |
| `reports/programme_01/session_momentum_001/mc/mc_report.md` | Added | MC human report |
| `reports/programme_01/session_momentum_001/mc/mc_results.json` | Added | Full MC results (10k sims, 818 KB) |

---

### Commit 5: `26a1821` — Data Catalog & Manifests
**Type:** `data`  
**Scope:** Data reproducibility

| File | Status | Description |
|------|--------|-------------|
| `data/catalog.yaml` | Added | Data version catalog with checksums |
| `data/processed/xauusdm/*/_manifest.json` (8 files) | Added | Processed dataset manifests (D1, H1, M30, M15, M5) |
| `data/raw/xauusdm/*/_manifest.json` (2 files) | Added | Raw data manifests (H1, M5 Exness) |

---

### Commit 6: `8bc5fa9` — Unit Tests & Research Scripts
**Type:** `test`  
**Scope:** Tests + Research utilities

| File | Status | Description |
|------|--------|-------------|
| `tests/unit/data/test_phase2_data_preparation.py` | Added | Data prep tests |
| `tests/unit/data/test_xauusdm_dataset_v120.py` | Added | Dataset v1.2.0 validation |
| `tests/unit/research/test_xau_mtf_donchian_001.py` | Added | Donchian strategy tests |
| `research/assignment14/*.py` (14 files) | Added | Assignment 14 utility scripts |
| `research/programme_01/*.md` (6 files) | Added | Research documentation |
| `research/programme_01/*.json` (2 files) | Added | Literature/hypothesis registers |
| `research/programme_01/strategy_spec_XAU_SESSION_MOM_001.md` | Added | Frozen strategy specification |

---

### Commit 7: `8675b30` — Paper Trading & Root Docs
**Type:** `docs`  
**Scope:** Paper trading + Root audit reports

| File | Status | Description |
|------|--------|-------------|
| `reports/paper_trading/ma_tsm_001/*` (3 files) | Added | Paper trading readiness, capital analysis, protocol |
| `CLOUD_AUDIT_REPORT.md` | Added | Cloud audit findings |
| `LOCAL_CONFIG_GUIDE.md` | Added | Local config documentation |
| `PHASE_2_DATA_AUDIT_REPORT.md` | Added | Phase 2 data audit |
| `PHASE_A_PREFLIGHT_REPORT.md` | Added | Phase A preflight |
| `PHASE_B_DRYRUN_REPORT.md` | Added | Phase B dry-run |
| `SECURITY_REMEDIATION_REPORT.md` | Added | Security remediation |
| `audit_*.py` (6 files) + `audit_*.json` (2 files) + `check_viz_data.py` | Added | Audit utility scripts |

---

### Commit 8: `5edd051` — Large Files via Git LFS + Assignment 18 Deliverables
**Type:** `data`  
**Scope:** LFS-tracked files + Assignment 18 reports

| File | Status | Size | LFS Tracked |
|------|--------|------|-------------|
| `data/raw/xauusdm/m5/exness/XAUUSDm_M5_2020_2026_raw.csv` | Added | 32.1 MB | ✅ Yes |
| `data/raw/xauusdm/h1/exness/XAUUSDm_H1_2015_2025_raw.parquet` | Added | 2.1 MB | ✅ Yes |
| `reports/assignment14/ledger/equity_curve_in_sample.csv` | Added | 11.0 MB | ✅ Yes |
| `reports/assignment14/ledger/equity_curve_out_of_sample.csv` | Added | 5.7 MB | ✅ Yes |
| `reports/programme_01/session_momentum_001/mc/mc_results.json` | Added | 818 KB | ✅ Yes |
| `reports/assignment18/ASSIGNMENT_18_REPOSITORY_AUDIT.md` | Added | 27 KB | No |
| `reports/assignment18/FILE_STAGING_MANIFEST.csv` | Added | 13 KB | No |
| `reports/assignment18/LARGE_FILE_AND_STORAGE_REPORT.md` | Added | 8 KB | No |
| `reports/assignment18/SECURITY_REVIEW.md` | Added | 7 KB | No |

---

## Verification Results

### Pre-Commit Checks (All Passed)
- [x] `git diff --cached --stat` — reviewed staged changes per commit
- [x] `git diff --cached --name-status` — verified file lists
- [x] `git diff --cached --check` — no whitespace errors
- [x] Secret scan on staged files — no credentials detected
- [x] Large file check — LFS used for all files > 10 MB
- [x] Import checks — all modules import without error
- [x] Config validation — YAML configs parse correctly
- [x] Test suite — pre-existing tests pass (no strategy logic modified)

### Post-Commit Verification
- [x] All 8 commits are atomic and descriptive
- [x] No force-push used
- [x] No history rewrite or commit amending
- [x] Existing commit history preserved
- [x] Commit hashes recorded above

---

## Files Excluded (Intentional)

| File / Pattern | Reason |
|----------------|--------|
| `mt5_audit_backup.db` | Empty audit schema, regeneratable |
| `mt5_audit_backup.db-shm` | SQLite WAL file, ignored |
| `reports/donchian_mc_analysis_*.txt` (10 files) | Intermediate logs, disposable |
| `research/experiment_logs/0cdafc4e76ce.json` | Experiment log, disposable |
| `inspect_db.py`, `inspect_db2.py`, `scan_secrets.py` | Temporary inspection scripts |
| `data/processed/xauusdm/m5/v1.2.0/data.parquet` | Already ignored (regeneratable) |

---

**End of Commit Report**  
**Next:** Sync Report with remote synchronization status.