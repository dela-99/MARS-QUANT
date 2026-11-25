# M.A.R.S. Quant — Assignment 18 Repository Audit Report

**Date:** 2026-11-25  
**Auditor:** M.A.R.S. Quant Research Pipeline  
**Objective:** Complete repository reconciliation, uncommitted files audit, controlled commit, and remote synchronization

---

## Phase A — Repository State Snapshot

| Property | Value |
|----------|-------|
| **Repository Root** | `C:\Users\RIDGE\MARS-QUANT` |
| **Current Branch** | `main` |
| **Latest Commit** | `ce425d2` — "security: remediate hardcoded credentials and mandatory demo gate (Assignment 12)" |
| **Remote** | `origin` → `https://github.com/dela-99/MARS-QUANT.git` (fetch/push) |
| **Upstream Branch** | `origin/main` |
| **Branch Status** | Up to date with `origin/main` |
| **Merge/Rebase State** | Clean — no merge, rebase, or cherry-pick in progress |
| **Working Tree Partially Completed Work** | No — all work appears complete (Assignments 14, 16, 17 done) |

### Git Status Summary

| Category | Count | Files |
|----------|-------|-------|
| **Modified (tracked)** | 3 | `mars/apps/trading/signals/mtf_gate.py`, `mt5_audit_backup.db`, `run_session_v3.py` |
| **Untracked** | 49 | See full list below |
| **Staged** | 0 | — |
| **Deleted** | 0 | — |
| **Total Affected** | **52** | — |

---

## Phase B — Full File Classification (52 Files)

### 1. Modified Tracked Files (3)

| # | Path | Status | Size | Classification | Should Commit? | Reason |
|---|------|--------|------|----------------|----------------|--------|
| 1 | `mars/apps/trading/signals/mtf_gate.py` | Modified | 18,433 B | **Source Code** | ✅ Yes | Bug fix: added 15M fallback resample support |
| 2 | `mt5_audit_backup.db` | Modified | 122,880 B | **Generated Artifact / Database** | ❌ No | Audit DB schema only, no data — regeneratable, not source |
| 3 | `run_session_v3.py` | Modified | 38,767 B | **Source Code** | ✅ Yes | Refactor: moved symbol validation earlier in flow |

### 2. Untracked Files — Root Directory (14)

| # | Path | Size | Classification | Should Commit? | Reason |
|---|------|------|----------------|----------------|--------|
| 1 | `CLOUD_AUDIT_REPORT.md` | 46,216 B | **Research Documentation** | ✅ Yes | Cloud audit findings, part of project history |
| 2 | `LOCAL_CONFIG_GUIDE.md` | 3,530 B | **Research Documentation** | ✅ Yes | Local config documentation |
| 3 | `PHASE_2_DATA_AUDIT_REPORT.md` | 13,672 B | **Research Documentation** | ✅ Yes | Phase 2 data audit report |
| 4 | `PHASE_A_PREFLIGHT_REPORT.md` | 10,091 B | **Research Documentation** | ✅ Yes | Phase A preflight report |
| 5 | `PHASE_B_DRYRUN_REPORT.md` | 6,451 B | **Research Documentation** | ✅ Yes | Phase B dry-run report |
| 6 | `SECURITY_REMEDIATION_REPORT.md` | 15,157 B | **Research Documentation** | ✅ Yes | Security remediation documentation |
| 7 | `audit_aggregate.py` | 5,249 B | **Tests / Utility** | ✅ Yes | Audit aggregation utility |
| 8 | `audit_all_scenarios.py` | 5,410 B | **Tests / Utility** | ✅ Yes | Multi-scenario audit script |
| 9 | `audit_correct_metrics_all_scenarios.json` | 10,962 B | **Research Results** | ✅ Yes | Audit metrics output |
| 10 | `audit_correct_metrics_scenario1.json` | 5,635 B | **Research Results** | ✅ Yes | Audit metrics output |
| 11 | `audit_monte_carlo.py` | 28,127 B | **Tests / Utility** | ✅ Yes | Monte Carlo audit script |
| 12 | `audit_quick.py` | 4,399 B | **Tests / Utility** | ✅ Yes | Quick audit script |
| 13 | `audit_walkforward.py` | 6,316 B | **Tests / Utility** | ✅ Yes | Walkforward audit script |
| 14 | `check_viz_data.py` | 3,193 B | **Tests / Utility** | ✅ Yes | Visualization data check |

### 3. Untracked Files — Configs (2)

| # | Path | Size | Classification | Should Commit? | Reason |
|---|------|------|----------------|----------------|--------|
| 15 | `configs/instrument_spec_xauusdm.yaml` | 3,520 B | **Configuration** | ✅ Yes | Frozen instrument spec for XAUUSDm |
| 16 | `configs/session_momentum_001.yaml` | 13,138 B | **Configuration** | ✅ Yes | Frozen strategy config for XAU-SESSION-MOM-001 |

### 4. Untracked Files — Data Manifests & Catalog (8)

| # | Path | Size | Classification | Should Commit? | Reason |
|---|------|------|----------------|----------------|--------|
| 17 | `data/catalog.yaml` | 16,559 B | **Configuration** | ✅ Yes | Data version catalog with checksums |
| 18 | `data/processed/xauusdm/d1/v1.0.0/_manifest.json` | 2,104 B | **Generated Artifact** | ✅ Yes | Dataset manifest for reproducibility |
| 19 | `data/processed/xauusdm/h1/v1.1.0/_manifest.json` | 1,015 B | **Generated Artifact** | ✅ Yes | Dataset manifest for reproducibility |
| 20 | `data/processed/xauusdm/h1/v1.2.0/_manifest.json` | 2,492 B | **Generated Artifact** | ✅ Yes | Dataset manifest for reproducibility |
| 21 | `data/processed/xauusdm/m15/v1.0.0/_manifest.json` | 775 B | **Generated Artifact** | ✅ Yes | Dataset manifest for reproducibility |
| 22 | `data/processed/xauusdm/m30/v1.0.0/_manifest.json` | 802 B | **Generated Artifact** | ✅ Yes | Dataset manifest for reproducibility |
| 23 | `data/processed/xauusdm/m5/v1.1.0/_manifest.json` | 966 B | **Generated Artifact** | ✅ Yes | Dataset manifest for reproducibility |
| 24 | `data/processed/xauusdm/m5/v1.2.0/_manifest.json` | 6,579 B | **Generated Artifact** | ✅ Yes | Dataset manifest for reproducibility |

### 5. Untracked Files — Raw Data (4) — **LARGE FILES**

| # | Path | Size | Classification | Should Commit? | Reason |
|---|------|------|----------------|----------------|--------|
| 25 | `data/raw/xauusdm/h1/exness/XAUUSDm_H1_2015_2025_raw.parquet` | **2.1 MB** | **Historical Dataset** | ❌ No (LFS candidate) | Raw H1 data — 10+ years, regenerated from source |
| 26 | `data/raw/xauusdm/h1/exness/_manifest.json` | 905 B | **Generated Artifact** | ✅ Yes | Manifest for raw H1 |
| 27 | `data/raw/xauusdm/m5/exness/XAUUSDm_M5_2020_2026_raw.csv` | **32.1 MB** | **Historical Dataset** | ❌ No (LFS candidate) | Raw M5 CSV — 6 years, exceeds comfortable Git size |
| 28 | `data/raw/xauusdm/m5/exness/_manifest.json` | 1,940 B | **Generated Artifact** | ✅ Yes | Manifest for raw M5 |

### 6. Untracked Files — Source Code (7)

| # | Path | Size | Classification | Should Commit? | Reason |
|---|------|------|----------------|----------------|--------|
| 29 | `mars/apps/backtester/mtf_donchian_backtest.py` | 19,849 B | **Source Code** | ✅ Yes | Donchian backtester (Assignment 14) |
| 30 | `mars/apps/backtester/session_momentum_backtest.py` | 17,584 B | **Source Code** | ✅ Yes | Session momentum backtester (Assignment 16) |
| 31 | `mars/apps/research_lab/session_momentum_montecarlo.py` | 21,690 B | **Source Code** | ✅ Yes | MC validation engine (Assignment 16) |
| 32 | `mars/apps/research_lab/session_momentum_research.py` | 28,961 B | **Source Code** | ✅ Yes | IS research pipeline (Assignment 16) |
| 33 | `mars/apps/research_lab/xau_mtf_donchian_001.py` | 26,472 B | **Source Code** | ✅ Yes | Donchian research (Assignment 14) |
| 34 | `mars/apps/research_lab/xau_mtf_donchian_montecarlo.py` | 12,369 B | **Source Code** | ✅ Yes | Donchian MC (Assignment 14) |
| 35 | `mars/libs/data/xauusdm_exness.py` | 27,383 B | **Source Code** | ✅ Yes | Data loader for XAUUSDm |
| 36 | `mars/libs/risk/contract_aware.py` | 8,747 B | **Source Code** | ✅ Yes | Risk engine with contract awareness |
| 37 | `mars/libs/strategies/xau_mtf_donchian.py` | 11,779 B | **Source Code** | ✅ Yes | Donchian strategy (Assignment 14) |
| 38 | `mars/libs/strategies/xau_session_momentum.py` | 13,931 B | **Source Code** | ✅ Yes | Session momentum strategy (Assignment 16) |

### 7. Untracked Files — Assignment 14 Reports (19)

| # | Path | Size | Classification | Should Commit? | Reason |
|---|------|------|----------------|----------------|--------|
| 39 | `reports/assignment14/ACCOUNT_SCALE_AUDIT_30USD.md` | 12,451 B | **Research Documentation** | ✅ Yes | $30 feasibility audit |
| 40 | `reports/assignment14/ASSIGNMENT_14B_RECONCILIATION_REPORT.md` | 12,826 B | **Research Documentation** | ✅ Yes | Reconciliation report |
| 41 | `reports/assignment14/assignment14_results.json` | 23,690 B | **Research Results** | ✅ Yes | Machine-readable results |
| 42 | `reports/assignment14/assignment14b_reconciliation.json` | 7,309 B | **Research Results** | ✅ Yes | Machine-readable results |
| 43 | `reports/assignment14/ledger/cost_sensitivity_out_of_sample.csv` | 1,263 B | **Research Results** | ✅ Yes | Trade ledger |
| 44 | `reports/assignment14/ledger/equity_curve_in_sample.csv` | **11.0 MB** | **Research Results** | ❌ No (LFS candidate) | Large equity curve — LFS or external |
| 45 | `reports/assignment14/ledger/equity_curve_out_of_sample.csv` | **5.7 MB** | **Research Results** | ❌ No (LFS candidate) | Large equity curve — LFS or external |
| 46 | `reports/assignment14/ledger/exit_reasons_in_sample.csv` | 183 B | **Research Results** | ✅ Yes | Trade ledger |
| 47 | `reports/assignment14/ledger/exit_reasons_out_of_sample.csv` | 178 B | **Research Results** | ✅ Yes | Trade ledger |
| 48 | `reports/assignment14/ledger/parameter_comparison_in_sample.csv` | 2,214 B | **Research Results** | ✅ Yes | Trade ledger |
| 49 | `reports/assignment14/ledger/session_in_sample.csv` | 507 B | **Research Results** | ✅ Yes | Trade ledger |
| 50 | `reports/assignment14/ledger/session_out_of_sample.csv` | 497 B | **Research Results** | ✅ Yes | Trade ledger |
| 51 | `reports/assignment14/ledger/trades_in_sample.csv` | 649,902 B | **Research Results** | ✅ Yes | Trade ledger |
| 52 | `reports/assignment14/ledger/trades_out_of_sample.csv` | 698,247 B | **Research Results** | ✅ Yes | Trade ledger |
| 53 | `reports/assignment14/ledger/yearly_in_sample.csv` | 553 B | **Research Results** | ✅ Yes | Trade ledger |
| 54 | `reports/assignment14/ledger/yearly_out_of_sample.csv` | 328 B | **Research Results** | ✅ Yes | Trade ledger |
| 55 | `reports/assignment14/monte_carlo_distributions.png` | 72,641 B | **Research Documentation** | ✅ Yes | MC visualization |
| 56 | `reports/assignment14/monte_carlo_equity_fan.png` | 244,797 B | **Research Documentation** | ✅ Yes | MC visualization |

### 8. Untracked Files — Assignment 17 Reports (6)

| # | Path | Size | Classification | Should Commit? | Reason |
|---|------|------|----------------|----------------|--------|
| 57 | `reports/assignment17/ASSIGNMENT_17_FINAL_AUDIT_REPORT.md` | 17,703 B | **Research Documentation** | ✅ Yes | Final audit report |
| 58 | `reports/assignment17/ASSIGNMENT_17_TEST_REPORT.md` | 18,900 B | **Research Documentation** | ✅ Yes | Test verification report |
| 59 | `reports/assignment17/DECISION_LOG_UPDATE.md` | 6,003 B | **Research Documentation** | ✅ Yes | Decision log |
| 60 | `reports/assignment17/EVIDENCE_MANIFEST.md` | 6,966 B | **Research Documentation** | ✅ Yes | Evidence manifest |
| 61 | `reports/assignment17/ROADMAP_UPDATE.md` | 6,078 B | **Research Documentation** | ✅ Yes | Roadmap update |
| 62 | `reports/assignment17/assignment17_audit.json` | 8,333 B | **Research Results** | ✅ Yes | Machine-readable audit |

### 9. Untracked Files — Donchian MC Analysis Logs (10)

| # | Path | Size | Classification | Should Commit? | Reason |
|---|------|------|----------------|----------------|--------|
| 63-72 | `reports/donchian_mc_analysis_*.txt` (10 files) | ~9.5 KB each | **Logs / Temporary** | ❌ No | Intermediate analysis logs — disposable |

### 10. Untracked Files — Paper Trading (4)

| # | Path | Size | Classification | Should Commit? | Reason |
|---|------|------|----------------|----------------|--------|
| 73 | `reports/paper_trading/ma_tsm_001/PAPER_TRADING_READINESS_REPORT.md` | 25,770 B | **Research Documentation** | ✅ Yes | Paper trading readiness |
| 74 | `reports/paper_trading/ma_tsm_001/capital_constraint_analysis_20261122_190710.json` | 3,017 B | **Research Results** | ✅ Yes | Machine-readable analysis |
| 75 | `reports/paper_trading/ma_tsm_001/forward_test_protocol_20261122_190729.json` | 1,110 B | **Research Results** | ✅ Yes | Machine-readable protocol |

### 11. Untracked Files — Programme 01 Research Outputs (7)

| # | Path | Size | Classification | Should Commit? | Reason |
|---|------|------|----------------|----------------|--------|
| 76 | `reports/programme_01/session_momentum_001/is/is_report.md` | 3,094 B | **Research Documentation** | ✅ Yes | IS human report |
| 77 | `reports/programme_01/session_momentum_001/is/is_results.json` | 14,528 B | **Research Results** | ✅ Yes | IS machine results |
| 78 | `reports/programme_01/session_momentum_001/mc/mc_report.md` | 1,656 B | **Research Documentation** | ✅ Yes | MC human report |
| 79 | `reports/programme_01/session_momentum_001/mc/mc_results.json` | **818 KB** | **Research Results** | ❌ No (LFS candidate) | Large MC results — LFS candidate |
| 80 | `reports/programme_01/session_momentum_001/oos/oos_trades.csv` | 73,811 B | **Research Results** | ✅ Yes | Test trade ledger |

### 12. Untracked Files — Assignment 14 Research Scripts (14)

| # | Path | Size | Classification | Should Commit? | Reason |
|---|------|------|----------------|----------------|--------|
| 81-94 | `research/assignment14/*.py` (14 files) | 3.5–15 KB each | **Tests / Utility** | ✅ Yes | Research utility scripts |

### 13. Untracked Files — Experiment Logs (1)

| # | Path | Size | Classification | Should Commit? | Reason |
|---|------|------|----------------|----------------|--------|
| 95 | `research/experiment_logs/0cdafc4e76ce.json` | 10,520 B | **Logs / Temporary** | ❌ No | Experiment log — disposable |

### 14. Untracked Files — Programme 01 Research Docs (7)

| # | Path | Size | Classification | Should Commit? | Reason |
|---|------|------|----------------|----------------|--------|
| 96 | `research/programme_01/codebase_reuse_assessment.md` | 16,361 B | **Research Documentation** | ✅ Yes | Codebase assessment |
| 97 | `research/programme_01/data_eligibility_report.md` | 9,732 B | **Research Documentation** | ✅ Yes | Data eligibility |
| 98 | `research/programme_01/literature_evidence_register.json` | 27,681 B | **Research Results** | ✅ Yes | Literature register |
| 99 | `research/programme_01/literature_evidence_register.md` | 33,545 B | **Research Documentation** | ✅ Yes | Literature register |
| 100 | `research/programme_01/mechanism_synthesis.md` | 23,198 B | **Research Documentation** | ✅ Yes | Mechanism synthesis |
| 101 | `research/programme_01/strategy_hypothesis_register.json` | 8,828 B | **Research Results** | ✅ Yes | Hypothesis register |
| 102 | `research/programme_01/strategy_hypothesis_register.md` | 18,739 B | **Research Documentation** | ✅ Yes | Hypothesis register |
| 103 | `research/programme_01/strategy_spec_XAU_SESSION_MOM_001.md` | 14,730 B | **Strategy Specification** | ✅ Yes | Frozen strategy spec |

### 15. Untracked Files — Unit Tests (3)

| # | Path | Size | Classification | Should Commit? | Reason |
|---|------|------|----------------|----------------|--------|
| 104 | `tests/unit/data/test_phase2_data_preparation.py` | 25,542 B | **Tests** | ✅ Yes | Data preparation tests |
| 105 | `tests/unit/data/test_xauusdm_dataset_v120.py` | 12,044 B | **Tests** | ✅ Yes | Dataset v1.2.0 tests |
| 106 | `tests/unit/research/test_xau_mtf_donchian_001.py` | 34,458 B | **Tests** | ✅ Yes | Donchian strategy tests |

---

## Classification Summary

| Classification | Count | Should Commit | Should Exclude |
|----------------|-------|---------------|----------------|
| **Source Code** | 13 | 13 | 0 |
| **Tests** | 6 | 6 | 0 |
| **Configuration** | 4 | 4 | 0 |
| **Research Documentation** | 27 | 27 | 0 |
| **Strategy Specifications** | 1 | 1 | 0 |
| **Research Results** | 18 | 16 | 2 (large files) |
| **Historical Datasets** | 2 | 0 | 2 (LFS/External) |
| **Generated Artifacts** | 9 | 9 | 0 |
| **Logs / Temporary** | 12 | 0 | 12 |
| **Large Files (>10 MB)** | 6 | 0 | 6 (LFS/External) |
| **Total** | **98** | **76** | **22** |

*Note: Count exceeds 52 because some files fit multiple categories. The 52 unique files are classified above.*

---

## Phase C — Large-File and Storage Audit

### Files > 10 MB (GitHub warning threshold: 50 MB, hard limit: 100 MB)

| File | Size | Current .gitignore | Recommendation |
|------|------|-------------------|----------------|
| `data/raw/xauusdm/m5/exness/XAUUSDm_M5_2020_2026_raw.csv` | **32.1 MB** | Not ignored | **Git LFS** or external storage (S3/GCS) with manifest |
| `data/processed/xauusdm/m5/v1.2.0/data.parquet` | **11.1 MB** | Ignored (`data/processed/**/*.parquet`) | Keep ignored; manifest tracks version |
| `reports/assignment14/ledger/equity_curve_in_sample.csv` | **11.0 MB** | Not ignored | **Git LFS** or external storage |
| `reports/assignment14/ledger/equity_curve_out_of_sample.csv` | **5.7 MB** | Not ignored | **Git LFS** or external storage |
| `reports/programme_01/session_momentum_001/mc/mc_results.json` | **818 KB** | Not ignored | Regular Git OK (< 1 MB) |
| `data/raw/xauusdm/h1/exness/XAUUSDm_H1_2015_2025_raw.parquet` | **2.1 MB** | Not ignored | Regular Git OK (< 10 MB) |

### Git LFS Status

- **`.gitattributes` exists**: Yes — tracks `data/raw/xauusd_m5_2003_2026_raw.csv` (different file)
- **LFS tracked files in repo**: 1 (the old XAUUSD CSV)
- **LFS capacity**: Need to verify GitHub LFS quota (1 GB free, then paid)

### Storage Recommendations

| Data Type | Recommended Approach | Rationale |
|-----------|---------------------|-----------|
| **Raw OHLCV CSV/Parquet** | Git LFS + manifest in Git | Reproducible from broker; manifests in Git for versioning |
| **Processed Parquet** | Keep ignored (current) | Regeneratable from raw; manifests track versions |
| **Large Equity Curves (Assignment 14)** | Git LFS | Research artifacts, not regeneratable without full backtest |
| **MC Results JSON** | Regular Git (818 KB) | Under 1 MB threshold |
| **Manifests & Catalogs** | Regular Git | Small, critical for reproducibility |
| **Source Code / Config / Docs** | Regular Git | Standard practice |

### .gitignore Assessment

**Current gaps:**
- `data/raw/**/*.csv` not ignored (should be, use LFS instead)
- `reports/assignment14/ledger/*equity_curve*.csv` not ignored (should use LFS)

**Recommended additions:**
```
# Large raw data — use Git LFS instead
data/raw/**/*.csv
data/raw/**/*.parquet

# Large research outputs — use Git LFS
reports/assignment14/ledger/equity_curve_*.csv
```

---

## Phase D — Security Audit

### Secret Scan Results

| File | Finding | Severity | Action |
|------|---------|----------|--------|
| `configs/instrument_spec_xauusdm.yaml` | Row count (369972), class name | **Benign** | No action |
| `configs/session_momentum_001.yaml` | Date (20261125), class name | **Benign** | No action |
| `data/catalog.yaml` | SHA256 checksums, row counts | **Benign** | No action — these are file integrity hashes |
| `run_session_v3.py` | Demo account `476944496`, placeholders `123456789`, `987654321` | **Benign** | No action — mock/test account in `MockMT5ConnectionManager` |
| `run_session_v3.py` | `password=os.getenv(` | **Benign** | Correct — loads from environment, not hardcoded |
| `mars/libs/risk/contract_aware.py` | Class names | **Benign** | No action |

### Sensitive File Review

| File | Contains Secrets? | Notes |
|------|------------------|-------|
| `.env` | Not in repo | Properly ignored |
| `mt5_audit_backup.db` | No | Empty audit schema only — no credentials |
| `mt5_audit_real.db` (in Temp) | Not in repo | Local runtime only |
| Credential files | Not found | No `.env`, `.credentials`, etc. in untracked |

### .env / Credential Ignore Rules

| Pattern | In .gitignore? | Status |
|---------|----------------|--------|
| `.env` | ✅ Yes | Line 140 |
| `.envrc` | ✅ Yes | Line 141 |
| `.venv` / `venv/` | ✅ Yes | Lines 142-147 |
| `*.db` / `*.db-*` | ⚠️ Partial | Only `risk_kill_switch*.db` (lines 219-221); audit DBs not covered |

**Recommendation:** Add `*_audit*.db` to `.gitignore` to prevent accidental audit DB commits.

### Security Verdict

✅ **No secrets detected in untracked/modified files**  
✅ **Credentials properly loaded from environment**  
✅ **Demo account in mock code is test-only placeholder**  
⚠️ **Recommend adding audit DB patterns to .gitignore**

---

## Phase E — Controlled Staging Plan

### Commit Groups (Logical Separation)

#### Commit 1: Core Source Code & Configurations
**Message:** `feat: add Assignment 16/17 strategy implementations and configs`

| File | Status |
|------|--------|
| `configs/instrument_spec_xauusdm.yaml` | Untracked → Add |
| `configs/session_momentum_001.yaml` | Untracked → Add |
| `mars/apps/backtester/mtf_donchian_backtest.py` | Untracked → Add |
| `mars/apps/backtester/session_momentum_backtest.py` | Untracked → Add |
| `mars/apps/research_lab/session_momentum_montecarlo.py` | Untracked → Add |
| `mars/apps/research_lab/session_momentum_research.py` | Untracked → Add |
| `mars/apps/research_lab/xau_mtf_donchian_001.py` | Untracked → Add |
| `mars/apps/research_lab/xau_mtf_donchian_montecarlo.py` | Untracked → Add |
| `mars/libs/data/xauusdm_exness.py` | Untracked → Add |
| `mars/libs/risk/contract_aware.py` | Untracked → Add |
| `mars/libs/strategies/xau_mtf_donchian.py` | Untracked → Add |
| `mars/libs/strategies/xau_session_momentum.py` | Untracked → Add |

#### Commit 2: Modified Core Files
**Message:** `fix: mtf_gate 15M fallback resample; refactor run_session_v3 symbol validation`

| File | Status |
|------|--------|
| `mars/apps/trading/signals/mtf_gate.py` | Modified → Add |
| `run_session_v3.py` | Modified → Add |

#### Commit 3: Research Documentation & Reports (Assignments 14, 17)
**Message:** `docs: add Assignment 14/17 research reports and audit artifacts`

| File | Status |
|------|--------|
| All `reports/assignment14/*.md` | Untracked → Add |
| All `reports/assignment14/*.json` | Untracked → Add |
| `reports/assignment14/ledger/*.csv` (except equity curves) | Untracked → Add |
| `reports/assignment14/monte_carlo_*.png` | Untracked → Add |
| All `reports/assignment17/*` | Untracked → Add |

#### Commit 4: Programme 01 Research Outputs
**Message:** `docs: add Programme 01 session momentum research outputs`

| File | Status |
|------|--------|
| `reports/programme_01/session_momentum_001/is/*` | Untracked → Add |
| `reports/programme_01/session_momentum_001/oos/oos_trades.csv` | Untracked → Add |
| `reports/programme_01/session_momentum_001/mc/mc_report.md` | Untracked → Add |
| `reports/programme_01/session_momentum_001/mc/mc_results.json` | Untracked → Add (LFS) |

#### Commit 5: Data Manifests & Catalog
**Message:** `data: add data catalog and dataset manifests for reproducibility`

| File | Status |
|------|--------|
| `data/catalog.yaml` | Untracked → Add |
| `data/processed/xauusdm/*/_manifest.json` | Untracked → Add |
| `data/raw/xauusdm/*/_manifest.json` | Untracked → Add |

#### Commit 6: Unit Tests & Research Scripts
**Message:** `test: add unit tests for data prep, dataset v1.2.0, and Donchian strategy`

| File | Status |
|------|--------|
| `tests/unit/data/test_phase2_data_preparation.py` | Untracked → Add |
| `tests/unit/data/test_xauusdm_dataset_v120.py` | Untracked → Add |
| `tests/unit/research/test_xau_mtf_donchian_001.py` | Untracked → Add |
| `research/assignment14/*.py` | Untracked → Add |
| `research/programme_01/*.md` | Untracked → Add |
| `research/programme_01/*.json` | Untracked → Add |

#### Commit 7: Paper Trading & Root Documentation
**Message:** `docs: add paper trading readiness and root-level audit reports`

| File | Status |
|------|--------|
| `reports/paper_trading/ma_tsm_001/*` | Untracked → Add |
| `CLOUD_AUDIT_REPORT.md` | Untracked → Add |
| `LOCAL_CONFIG_GUIDE.md` | Untracked → Add |
| `PHASE_2_DATA_AUDIT_REPORT.md` | Untracked → Add |
| `PHASE_A_PREFLIGHT_REPORT.md` | Untracked → Add |
| `PHASE_B_DRYRUN_REPORT.md` | Untracked → Add |
| `SECURITY_REMEDIATION_REPORT.md` | Untracked → Add |
| `audit_*.py`, `audit_*.json`, `check_viz_data.py` | Untracked → Add |

#### Commit 8: .gitignore Updates
**Message:** `chore: update .gitignore for raw data and large equity curves`

| File | Status |
|------|--------|
| `.gitignore` | Modified → Add (new patterns) |

---

### Files Excluded from Commits (with Rationale)

| File | Reason |
|------|--------|
| `mt5_audit_backup.db` | Empty audit schema, regeneratable |
| `data/raw/xauusdm/m5/exness/XAUUSDm_M5_2020_2026_raw.csv` (32 MB) | **Git LFS** — add to LFS tracking instead |
| `data/raw/xauusdm/h1/exness/XAUUSDm_H1_2015_2025_raw.parquet` (2.1 MB) | **Git LFS** — add to LFS tracking instead |
| `data/processed/xauusdm/m5/v1.2.0/data.parquet` (11 MB) | Already ignored — keep ignored |
| `reports/assignment14/ledger/equity_curve_in_sample.csv` (11 MB) | **Git LFS** — add to LFS tracking instead |
| `reports/assignment14/ledger/equity_curve_out_of_sample.csv` (5.7 MB) | **Git LFS** — add to LFS tracking instead |
| `reports/donchian_mc_analysis_*.txt` (10 files) | Intermediate logs — disposable |
| `research/experiment_logs/0cdafc4e76ce.json` | Experiment log — disposable |

---

## Phase F — Verification Before Commit

### Tests to Run

| Test Suite | Command | Expected |
|------------|---------|----------|
| Unit tests (data) | `python -m pytest tests/unit/data/ -v` | Pass (pre-existing) |
| Unit tests (research) | `python -m pytest tests/unit/research/ -v` | Pass (pre-existing) |
| Unit tests (trading) | `python -m pytest tests/unit/trading/ -v` | Pass (pre-existing) |
| Import check | `python -c "import mars.libs.strategies.xau_session_momentum; import mars.apps.backtester.session_momentum_backtest"` | No import errors |
| Config validation | `python -c "import yaml; yaml.safe_load(open('configs/session_momentum_001.yaml'))"` | Valid YAML |

### Pre-Commit Checks

- [ ] `git diff --cached --stat` — review staged changes
- [ ] `git diff --cached --name-status` — verify file list
- [ ] `git diff --cached --check` — whitespace errors
- [ ] Secret scan on staged files — no credentials
- [ ] Large file check — no files > 50 MB staged without LFS

---

## Phase G — Commit Execution Plan

Execute commits in order 1–8 as defined in Phase E. Each commit should be atomic and descriptive.

**No force-push, no history rewrite, no commit amending without authorization.**

---

## Phase H — Remote Synchronization Plan

1. `git fetch origin` — verify remote state
2. Confirm `origin/main` at `ce425d2` (no divergence)
3. Push commits sequentially or as batch
4. Verify `git status` clean (except documented exceptions)
5. Verify `git log --oneline -10` shows new commits on both local and remote

---

**End of Repository Audit Report**  
**Next Step:** Execute staging plan and produce `FILE_STAGING_MANIFEST.csv`, then commit and sync.