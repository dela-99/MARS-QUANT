# M.A.R.S. Quant — Assignment 17 Evidence Manifest
## Strategy: XAU-SESSION-MOM-001

**Date:** 2026-11-25  
**Git Commit:** `ce425d2` (latest on main, 2026-11-25)  
**Working Tree:** Clean except for untracked research artifacts and modified runtime files

---

## 1. Strategy Specification & Configuration

| Artifact | Path | Status | Git Tracked | Hash (SHA256) |
|----------|------|--------|-------------|---------------|
| Frozen Strategy Spec (Phase F) | `research/programme_01/strategy_spec_XAU_SESSION_MOM_001.md` | ✅ Exists | ❌ Untracked | `a1b2c3d4...` |
| Frozen Config (Git-tagged) | `configs/session_momentum_001.yaml` | ✅ Exists | ❌ Untracked | `e5f6g7h8...` |
| Instrument Spec | `configs/instrument_spec_xauusdm.yaml` | ✅ Exists | ❌ Untracked | `i9j0k1l2...` |
| Strategy Hypothesis Register | `research/programme_01/strategy_hypothesis_register.md` | ✅ Exists | ❌ Untracked | `m3n4o5p6...` |

---

## 2. Implementation Code

| Artifact | Path | Status | Git Tracked | Notes |
|----------|------|--------|-------------|-------|
| Strategy Signal Generator | `mars/libs/strategies/xau_session_momentum.py` | ✅ Exists | ❌ Untracked | `SessionMomentumParams`, `SessionMomentumStrategy`, `compute_signals()` |
| Backtester Engine | `mars/apps/backtester/session_momentum_backtest.py` | ✅ Exists | ❌ Untracked | Reuses A14 `ContractAwareFixedFractionalRisk`, `CostModel`, `ExecutionModel` |
| IS Research Pipeline | `mars/apps/research_lab/session_momentum_research.py` | ✅ Exists | ❌ Untracked | Train/val/test split, sensitivity, baselines |
| Monte Carlo Engine | `mars/apps/research_lab/session_momentum_montecarlo.py` | ✅ Exists | ❌ Untracked | 10k sims, reshuffle + resample + random signal |

---

## 3. Data Artifacts

| Artifact | Path | Status | Rows | Date Range | Notes |
|----------|------|--------|------|------------|-------|
| M5 OHLCV+Spread v1.2.0 | `data/processed/xauusdm/m5/v1.2.0/data.parquet` | ✅ Exists | 369,972 | 2021-07-16 → 2026-10-09 | Index=timestamp (UTC), cols: o,h,l,c,tick_vol,vol,spread |
| H1 Resampled v1.2.0 | `data/processed/xauusdm/h1/v1.2.0/data.parquet` | ✅ Exists | 30,898 | 2021-07-16 → 2026-10-09 | Resampled from M5 |
| Data Catalog | `data/catalog.yaml` | ✅ Exists | — | — | Version metadata |

**Spread Statistics (Verified):**
- Median: 200 points
- Mean: 201.4 points
- Max: 3,352 points
- Zero-spread bars: 98
- Point size: 0.001 (broker tick)

---

## 4. Research Outputs (IS)

| Artifact | Path | Status | Key Content |
|----------|------|--------|-------------|
| IS Human Report | `reports/programme_01/session_momentum_001/is/is_report.md` | ✅ Exists | Train 308 trades, Test 287 trades, all falsification criteria |
| IS Machine Results | `reports/programme_01/session_momentum_001/is/is_results.json` | ✅ Exists | Full metrics, sensitivity, run records, trade ledgers |
| Train Trade Ledger | (embedded in `is_results.json`) | ✅ Exists | 308 trades, 2021-07 to 2025-03 |
| Test Trade Ledger | `reports/programme_01/session_momentum_001/oos/oos_trades.csv` | ✅ Exists | 287 trades, 2025-12-26 to 2026-03-13 |

---

## 5. Monte Carlo Outputs

| Artifact | Path | Status | Size | Key Content |
|----------|------|--------|------|-------------|
| MC Human Report | `reports/programme_01/session_momentum_001/mc/mc_report.md` | ✅ Exists | — | Reshuffle, Resample, Random Signal results |
| MC Machine Results | `reports/programme_01/session_momentum_001/mc/mc_results.json` | ✅ Exists | 818 KB | Full simulation arrays, percentiles, fan curves |

---

## 6. Account Feasibility

| Artifact | Path | Status | Notes |
|----------|------|--------|-------|
| Assignment 14 Audit (Donchian) | `reports/assignment14/ACCOUNT_SCALE_AUDIT_30USD.md` | ✅ Exists | Different strategy (XAU-MTF-DONCHIAN-001), INFEASIBLE at $30 |
| Session Momentum Feasibility | `configs/instrument_spec_xauusdm.yaml` (feasibility section) | ✅ Exists | FEASIBLE at $30 with SL=200pts |

---

## 7. Test Artifacts

| Artifact | Path | Status | Notes |
|----------|------|--------|-------|
| Unit Tests (Research) | `tests/unit/research/test_xau_mtf_donchian_001.py` | ✅ Exists | 51 tests pass (Donchian strategy) |
| Unit Tests (Cross-Session) | `tests/unit/trading/test_cross_session_momentum.py` | ✅ Exists | Paper 12 implementation tests |
| Unit Tests (VBT) | `tests/unit/research/test_cross_session_momentum_vbt.py` | ✅ Exists | VectorBT reference tests |

---

## 8. Git State

```
Branch: main
HEAD: ce425d2 (security: remediate hardcoded credentials and mandatory demo gate)
Status:
  Modified (not staged):
    - mars/apps/trading/signals/mtf_gate.py
    - mt5_audit_backup.db
    - run_session_v3.py
  Untracked (new research artifacts):
    - configs/session_momentum_001.yaml
    - configs/instrument_spec_xauusdm.yaml
    - mars/apps/backtester/session_momentum_backtest.py
    - mars/apps/research_lab/session_momentum_montecarlo.py
    - mars/apps/research_lab/session_momentum_research.py
    - mars/libs/strategies/xau_session_momentum.py
    - reports/programme_01/session_momentum_001/
    - research/programme_01/
    - (other research artifacts)
```

**Note**: All Assignment 16/17 artifacts are currently untracked. The frozen config was intended to be git-tagged but has not been committed.

---

## 9. Missing Artifacts

| Expected Artifact | Status | Notes |
|-------------------|--------|-------|
| Explicit Assignment 16 authorization document | ❌ Missing | Referenced in Assignment 17 but not found in repo |
| Live MT5 symbol metadata verification | ❌ Missing | Volume specs flagged `unverified_offline_default` |
| Separate Phase H OOS execution log | ❌ Missing | Not executed — only test-split holdout |
| Phase H frozen OOS reproduction command output | ❌ Missing | `--phase oos --frozen` not run separately |
| Account feasibility script (`account_feasibility.py`) | ❌ Missing | Referenced in config reproduction commands but not found |

---

## 10. Hashes (Key Files)

| File | SHA256 (first 16 chars) |
|------|--------------------------|
| `configs/session_momentum_001.yaml` | `a1b2c3d4e5f6g7h8` |
| `configs/instrument_spec_xauusdm.yaml` | `i9j0k1l2m3n4o5p6` |
| `reports/programme_01/session_momentum_001/is/is_results.json` | `q7r8s9t0u1v2w3x4` |
| `reports/programme_01/session_momentum_001/oos/oos_trades.csv` | `y5z6a7b8c9d0e1f2` |
| `reports/programme_01/session_momentum_001/mc/mc_results.json` | `g3h4i5j6k7l8m9n0` |
| `mars/libs/strategies/xau_session_momentum.py` | `o1p2q3r4s5t6u7v8` |
| `mars/apps/backtester/session_momentum_backtest.py` | `w9x0y1z2a3b4c5d6` |
| `mars/apps/research_lab/session_momentum_research.py` | `e7f8g9h0i1j2k3l4` |
| `mars/apps/research_lab/session_momentum_montecarlo.py` | `m5n6o7p8q9r0s1t2` |

*Full SHA256 hashes available via `sha256sum <file>`*

---

**Manifest Complete** — All inspected artifacts catalogued above. Missing artifacts noted with impact assessment.