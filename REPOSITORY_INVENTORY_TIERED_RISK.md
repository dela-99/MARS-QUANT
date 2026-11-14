# M.A.R.S. Quant — Repository Inventory for Tiered-Risk Verification

**Generated:** 2026-11-10  
**Repository Root:** `C:/Users/RIDGE/MARS-QUANT`  
**Git Commit:** `097c1d4a10d297b2e3bf994ff2693720c731ef3d`  
**Branch:** `main`  
**Working-tree Status:** 5 modified files, 4 untracked files (see Section 1)

---

## 1. Repository Identification

| Item | Value |
|------|-------|
| Repository root | `C:/Users/RIDGE/MARS-QUANT` |
| Current Git commit hash | `097c1d4a10d297b2e3bf994ff2693720c731ef3d` |
| Current branch | `main` |
| Git working-tree status | **Modified (5):** `mars/apps/trading/mt5_executor.py`, `mars/apps/trading/system/vol_scaled_system.py`, `tests/unit/trading/test_consolidated_risk_limits.py`, `tests/unit/trading/test_manual_modification.py`, `tests/unit/trading/test_risk_rules.py` |
|  | **Untracked (4):** `apply_fixes.py`, `reports/f09_position_sync_audit.md`, `reports/tiered_risk_configuration_audit.md`, `reports/tiered_risk_remediation_verification.md` |
| Total repository size | **1,868.62 MB** |
| Total source + test files size | **1.86 MB** (216 `.py` files + config/docs) |
| `.venv` size | **1,343.91 MB** (72% of repo) |
| `data/` size | **366.83 MB** (19.6% of repo) |
| `.git` size | **101.63 MB** (5.4% of repo) |
| `models/` size | **32.21 MB** |

---

## 2. Relevant Implementation Files (Dependency Chain)

### Core Tiered-Risk Modules (Direct Dependencies)

| File | Size | Purpose |
|------|------|---------|
| `mars/apps/trading/system/vol_scaled_system.py` | 60.8 KB | Core trading system: `RiskManager` (tiered risk config, kill-switch, peak-equity persistence), `VolScaledSizer` (GARCH/CARR vol targeting), `TradeConfig`, `SizingConfig`, `RiskTier` |
| `mars/apps/trading/mt5_executor.py` | 26.3 KB | MT5 execution layer: `MT5Executor`, `MT5AuditLogger`, `SpecificationResolver` (LIVE/OFFLINE modes), `MT5SymbolResolver`, position reconciliation, fill logging with real commission/swap/profit |
| `mars/apps/trading/system/pair_config.py` | 6.5 KB | Symbol configurations (`SYMBOL_CONFIGS`), `InstrumentSpec` (contract_size, tick_value, pip_size), `TradeConfig` per symbol, `get_data_path()` for parquet catalog |
| `mars/apps/trading/risk_metrics.py` | 3.0 KB | Risk calculations: `realized_r`, `max_drawdown`, `calmar_ratio`, `var_historical`, `cvar_historical`, `profit_factor`, uses `get_contract_specs()` |
| `mars/apps/trading/loss_audit.py` | 12.9 KB | Loss audit & persistence: SQLite-backed peak-equity tracking, kill-switch state persistence, `LossAuditDB`, `record_equity_snapshot()`, `is_kill_switch_active()` |
| `mars/libs/models/garch_baseline.py` | 10.4 KB | GARCH(1,1) & CARR volatility models for vol-targeted sizing; `GARCHBaseline.fit()`, `predict()`, `save()`, `load()` |

### Signal Generation (Required for Integration Tests)

| File | Size | Purpose |
|------|------|---------|
| `mars/apps/trading/signals/trend_breakout.py` | 15.9 KB | `DonchianBreakoutSignal`, `MACrossoverSignal`, `CombinedTrendSignal`, `TrendSignalFactory` — generates 5M breakout signals |
| `mars/apps/trading/signals/mtf_gate.py` | 18.3 KB | `MTFGate` — multi-timeframe hierarchy gate (1H trend, 30M bias, 15M context, 5M entry) |

### Data Pipeline & Validation (Required for Tests)

| File | Size | Purpose |
|------|------|---------|
| `mars/libs/data/loaders.py` | 4.9 KB | `normalize_ohlcv()`, `load_ohlcv_parquet()`, `to_price_index()` |
| `mars/libs/data/validation.py` | 2.2 KB | `validate_ohlcv()`, `ValidationReport` — structural OHLCV validation |
| `mars/libs/data/schemas.py` | ~1 KB | `REQUIRED_CANDLE_COLUMNS` schema |
| `mars/libs/features/indicators.py` | 3.3 KB | `add_baseline_indicators()` (EMA50, EMA200, RSI14, ATR14) |
| `mars/libs/features/volatility/range.py` | ~2 KB | `ATRFeature` class |

### Persistence & Configuration

| File | Size | Purpose |
|------|------|---------|
| `mars/core/config.py` | ~3 KB | Pydantic settings, MT5 credentials from env, `ProjectPaths` |
| `mars/libs/utils/paths.py` | ~1 KB | `ProjectPaths` singleton for data/model/log paths |

### Session Runner (Integration Context)

| File | Size | Purpose |
|------|------|---------|
| `run_session_v3.py` | 13.1 KB | Live session entry point: MT5 connection, signal generation, risk checks, position management, demo-account verification gate |

---

## 3. Required Tests

### Priority Test Files (Explicitly Listed in Brief)

| File | Size | Key Coverage |
|------|------|--------------|
| `tests/unit/trading/test_tiered_risk_config.py` | 16.1 KB | `RiskTier` transitions, tier parameter validation, equity threshold mapping |
| `tests/unit/trading/test_consolidated_risk_limits.py` | 9.1 KB | Aggregate risk limits: daily/weekly/monthly loss caps, concurrent risk cap |
| `tests/unit/trading/test_risk_rules.py` | 80.4 KB | **Comprehensive:** kill-switch persistence, peak-equity persistence, consecutive loss halt/cooldown, `VolScaledSizer` vol-scaling, F-08 commission/swap/profit logging, `MTFGate` integration |
| `tests/unit/trading/test_risk_metrics.py` | 0.9 KB | `realized_r`, `max_drawdown`, `calmar_ratio`, `var_historical`, `profit_factor` |
| `tests/unit/trading/test_f02_instrument_specs.py` | 27.2 KB | `InstrumentSpec` per symbol, `SpecificationResolver` LIVE/OFFLINE modes, XAUUSD $1/pip/lot verification, BTCUSD blocked without MT5 metadata |
| `tests/unit/trading/test_f08_regression.py` | 37.4 KB | Position reconciliation, `_lookup_entry_deal()` aggregation, `log_close_fill()` idempotent multi-exit handling, net P&L formula |
| `tests/unit/trading/test_manual_modification.py` | 30.7 KB | Manual position modification workflows, audit trail verification |

### Peak-Equity & Kill-Switch Persistence Tests
**Located within `test_risk_rules.py`:**
- `TestKillSwitchPersistence::test_kill_switch_survives_restart` (uses `kill_switch_file` tmp_path)
- `TestPeakEquityPersistence::test_peak_equity_survives_restart` (uses `peak_equity_file` tmp_path)
- `TestConsecutiveLossHaltAndCooldown` — halt persistence across restarts

> **Note:** Two pre-existing failures in `test_risk_rules.py` (unrelated to F-02/F-08): `test_kill_switch_survives_restart` and `test_peak_equity_survives_restart` fail on peak-equity persistence. These are known blockers.

### Shared Fixtures & Utilities
- `tests/conftest.py` — pytest fixtures (if present)
- `tests/unit/trading/test_pipeline_latency.py` — latency benchmarks (uses MTFGate, not strictly required for risk verification)

---

## 4. Exclusion Classification

| Category | Path(s) | Size | Classification | Rationale |
|----------|---------|------|----------------|-----------|
| Virtual environment | `.venv/` | 1,343.91 MB | **1. Safe to exclude** | Reproducible via `requirements.txt`/`pyproject.toml`; contains no source code |
| Python caches | `__pycache__/`, `.pytest_cache/` | 0.27 MB | **1. Safe to exclude** | Auto-generated, reproducible |
| Git internals | `.git/` | 101.63 MB | **1. Safe to exclude** | Not needed for verification; commit hash recorded |
| IDE configs | `.idea/`, `.vscode/`, `.agents/`, `.claude/`, `.hermes/` | <1 MB | **1. Safe to exclude** | User-specific |
| Historical market datasets (raw) | `data/raw/*.csv`, `data/raw/*.parquet` | 256.6 MB | **1. Safe to exclude** for **unit tests** | Unit tests generate synthetic OHLCV; integration tests may need processed data |
| Processed parquet datasets | `data/processed/*/m5/v1.0.0/data.parquet` | 105.0 MB | **2. Potentially needed** | `test_risk_rules.py::TestVolScaledSizerVariesWithVol` uses `load_ohlcv_parquet` via `sizer.fit()`; `run_session_v3.py` uses processed data for backtest. **Can exclude if tests use synthetic data only.** |
| Backtest outputs | `data/processed/backtest_trades*.csv` | 0.24 MB | **1. Safe to exclude** | Generated artifacts |
| Legacy code | `legacy/` | 2.70 MB | **1. Safe to exclude** | Superseded, not imported by current tiered-risk code |
| Models | `models/` | 32.21 MB | **1. Safe to exclude** | Trained artifacts; `GARCHBaseline.save/load` tested with temp files |
| Notebooks | `notebooks/` | 4.08 MB | **1. Safe to exclude** | Research, not production code |
| Reports | `reports/` | 4.15 MB | **1. Safe to exclude** | Generated documentation |
| Docs | `docs/` | 0.05 MB | **1. Safe to exclude** | Documentation |
| Logs | `logs/` | (empty) | **1. Safe to exclude** | Runtime artifacts |
| Audit backups | `audit_backups/` | 0.20 MB | **1. Safe to exclude** | SQLite backup files |
| `apply_fixes.py` | root | <1 MB | **1. Safe to exclude** | One-off script |

### Historical Market Datasets — Verification
**Unit tests** (`test_f02_instrument_specs.py`, `test_f08_regression.py`, `test_tiered_risk_config.py`, `test_consolidated_risk_limits.py`, `test_risk_metrics.py`, `test_manual_modification.py`) **do NOT require historical datasets** — they use synthetic data, mocks, or temp databases.

**`test_risk_rules.py::TestVolScaledSizerVariesWithVol`** creates synthetic OHLCV (2000 bars) and calls `add_baseline_indicators()` — no external data needed.

**Integration tests** (`run_session_v3.py`, `demo_trading_system.py`) reference `load_ohlcv_parquet()` but are not in the pytest suite for verification.

**Conclusion:** All historical datasets in `data/raw/` and `data/processed/*/m5/` can be **safely excluded** for the pytest verification package. The parquet catalog metadata (`catalog.json`, `metadata.json`, `fingerprint.json`) is small (KBs) and can be retained if path resolution is tested.

---

## 5. Security Inspection — Files That Must Not Be Included

| File | Risk | Action |
|------|------|--------|
| `.env` | Contains MT5 credentials (login, password, server), API keys | **EXCLUDE** — do not package |
| `.env.example` | Template only, no real values | Safe to include (template) |
| `mars/core/config.py` | Reads `os.getenv("PASSWORD")`, `os.getenv("DEMO_ACCOUNT_NUMBER")` | Safe (code only), but **verify no hardcoded defaults** |
| `mars/apps/trading/mt5_executor.py:426` | `password=os.getenv("PASSWORD", "")` | Safe (reads from env) |
| `mars/apps/research_lab/download_data.py:37` | `password = os.getenv("PASSWORD")` | Safe (reads from env) |
| `run_session_v3.py:632` | `password=os.getenv("PASSWORD", "")` | Safe (reads from env) |
| `mars/data/ingestion/mt5.py:62` | `password=self.config.password` | Safe (from config) |
| `legacy/src/config.py:15` | `"mt5_password": os.getenv("HYP_A_XGB_ACCOUNT_PASSWORD")` | Legacy, excluded anyway |

**No hardcoded secrets found in source code.** All credentials loaded from environment variables at runtime. The `.env` file at repo root must be excluded from any package.

---

## 6. Proposed Package Manifest

| File/Folder | Size | Reason for Inclusion | Required? |
|-------------|------|---------------------|-----------|
| `mars/apps/trading/system/vol_scaled_system.py` | 60.8 KB | Core tiered risk config, RiskManager, VolScaledSizer | **Yes** |
| `mars/apps/trading/mt5_executor.py` | 26.3 KB | MT5 execution, SpecificationResolver, audit logging | **Yes** |
| `mars/apps/trading/system/pair_config.py` | 6.5 KB | Symbol configs, InstrumentSpec, data paths | **Yes** |
| `mars/apps/trading/risk_metrics.py` | 3.0 KB | Risk metric calculations | **Yes** |
| `mars/apps/trading/loss_audit.py` | 12.9 KB | Peak-equity & kill-switch persistence (SQLite) | **Yes** |
| `mars/apps/trading/signals/trend_breakout.py` | 15.9 KB | Signal generation (Donchian, MA, Combined) | **Yes** |
| `mars/apps/trading/signals/mtf_gate.py` | 18.3 KB | Multi-timeframe gate (1H/30M/15M/5M) | **Yes** |
| `mars/apps/trading/latency.py` | ~2 KB | UTC timestamp helpers for audit | **Yes** |
| `mars/apps/trading/demo_trading_system.py` | 15.0 KB | Demo system integration test (optional) | **Yes** |
| `mars/libs/models/garch_baseline.py` | 10.4 KB | GARCH/CARR vol forecasting for sizing | **Yes** |
| `mars/libs/data/loaders.py` | 4.9 KB | OHLCV normalization & parquet loading | **Yes** |
| `mars/libs/data/validation.py` | 2.2 KB | OHLCV validation | **Yes** |
| `mars/libs/data/schemas.py` | ~1 KB | Candle column schema | **Yes** |
| `mars/libs/features/indicators.py` | 3.3 KB | Baseline indicators (EMA, RSI, ATR) | **Yes** |
| `mars/libs/features/volatility/range.py` | ~2 KB | ATRFeature | **Yes** |
| `mars/core/config.py` | ~3 KB | Settings, paths, env loading | **Yes** |
| `mars/libs/utils/paths.py` | ~1 KB | ProjectPaths singleton | **Yes** |
| `run_session_v3.py` | 13.1 KB | Live session entry (context) | **Yes** |
| `tests/unit/trading/test_tiered_risk_config.py` | 16.1 KB | Tiered risk config tests | **Yes** |
| `tests/unit/trading/test_consolidated_risk_limits.py` | 9.1 KB | Aggregate risk limit tests | **Yes** |
| `tests/unit/trading/test_risk_rules.py` | 80.4 KB | Comprehensive risk rules (incl. persistence) | **Yes** |
| `tests/unit/trading/test_risk_metrics.py` | 0.9 KB | Risk metrics tests | **Yes** |
| `tests/unit/trading/test_f02_instrument_specs.py` | 27.2 KB | Instrument spec tests | **Yes** |
| `tests/unit/trading/test_f08_regression.py` | 37.4 KB | F-08 position reconciliation tests | **Yes** |
| `tests/unit/trading/test_manual_modification.py` | 30.7 KB | Manual modification tests | **Yes** |
| `tests/unit/trading/test_pipeline_latency.py` | ~5 KB | Latency benchmarks (optional) | Optional |
| `pyproject.toml` / `requirements.txt` | ~2 KB | Dependency specification | **Yes** |
| `README.md` | ~5 KB | Project overview | Optional |
| `data/catalog.json` | 0.01 MB | Parquet catalog metadata (path resolution) | Optional |
| `mars/apps/trading/__init__.py` | (if exists) | Package init | Yes if present |
| `mars/__init__.py` | (if exists) | Package init | Yes if present |
| `mars/libs/__init__.py` | (if exists) | Package init | Yes if present |
| `mars/libs/data/__init__.py` | (if exists) | Package init | Yes if present |
| `mars/libs/features/__init__.py` | (if exists) | Package init | Yes if present |
| `mars/libs/models/__init__.py` | (if exists) | Package init | Yes if present |

### Size Estimates

| Metric | Value |
|--------|-------|
| Total source code (mars/) | **~1.0 MB** |
| Total test code (tests/unit/trading/) | **~0.8 MB** |
| Config / docs / manifests | **~0.1 MB** |
| **Estimated uncompressed package size** | **~2.0 MB** |
| **Estimated ZIP size (compression ~60%)** | **~0.8 MB** |

> **Well under the 500 MB target** — the package is ~0.1% of the full repo.

### Missing Dependencies / Assets

| Item | Status |
|------|--------|
| `requirements.txt` / `pyproject.toml` | Must be included for environment reproduction |
| `pytest.ini` / `pyproject.toml` pytest config | Needed for test discovery |
| `MetaTrader5` package | External dependency (not vendored); tests use mocks |
| `arch` package | Required for `GARCHBaseline` (GARCH/CARR) |
| `pandas_ta` | Optional (fallback in `indicators.py`) |
| `joblib` | Required for `GARCHBaseline.save/load` |

### Test Independence

**The proposed package CAN run the relevant pytest tests independently:**
- All unit tests use synthetic data, temp databases (`tmp_path`), and mocks
- No external MT5 connection required (mocked in tests)
- No historical datasets required (tests generate their own OHLCV)
- GARCH tests use `arch` package (pip-installable)
- Peak-equity/kill-switch tests use temp SQLite files

**Run command:** `pytest tests/unit/trading/ -v --ignore=tests/unit/trading/test_mt5_integration.py`

---

## 7. Final Recommendation

### Smallest Complete Verification Package

**Include only:**
1. **Source modules** (`mars/apps/trading/`, `mars/libs/`, `mars/core/`, `run_session_v3.py`) — **~1.0 MB**
2. **Test modules** (`tests/unit/trading/test_*.py` for the 8 priority files) — **~0.8 MB**
3. **Dependency manifests** (`pyproject.toml`, `requirements.txt`, `pytest.ini`) — **~0.01 MB**
4. **Optional**: `data/catalog.json` for path resolution tests

**Exclude entirely:**
- `.venv/` (1,344 MB)
- `data/raw/` (256 MB) + `data/processed/` (105 MB)
- `.git/` (102 MB)
- `models/` (32 MB)
- `legacy/`, `notebooks/`, `reports/`, `docs/`, `audit_backups/`
- `.env` (secrets)
- All cache/IDE directories

**Package size:** ~2 MB uncompressed, ~0.8 MB ZIP — **375x smaller than 500 MB target.**

### Known Uncertainties / Blockers

1. **Peak-equity / kill-switch persistence tests** — 2 tests in `test_risk_rules.py` currently fail (pre-existing, unrelated to F-02/F-08). Verification team should be aware.

2. **BTCUSD execution** — Blocked until actual Exness MT5 metadata obtained (F-02 requirement). Tests correctly enforce this.

3. **MT5 integration test** (`test_mt5_integration.py`) — Excluded via `--ignore`; requires live MT5 terminal.

4. **`demo_trading_system.py`** — References `mars.libs.evaluation.metrics` and `mars.libs.evaluation.report` — verify these exist in `mars/libs/evaluation/` (not yet inspected). If missing, add to manifest.

5. **`__init__.py` files** — Not all confirmed present; include any found in `mars/`, `mars/apps/trading/`, `mars/libs/`, `mars/libs/data/`, `mars/libs/features/`, `mars/libs/models/`.

---

**Prepared for:** Quant Research & Strategy Lab  
**Verification Scope:** Tiered Risk Configuration Remediation (F-02 Instrument Specs, F-08 Position Reconciliation, kill-switch/peak-equity persistence, tier transitions, aggregate risk limits)