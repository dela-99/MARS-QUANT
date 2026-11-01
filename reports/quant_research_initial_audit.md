# QUANT RESEARCH — INITIAL CODEBASE AND DATA AUDIT

## 1. Executive Summary

This audit inspects the M.A.R.S. (Multi-Asset Research System) repository at `C:\Users\RIDGE\MARS-QUANT` as of 2026-10-31. The system targets XAUUSD and BTCUSD across H1/M5 timeframes with institutional-grade standards (Jane Street / Jump / SIG).

**Key findings:**
- **XAUUSD M5 data exists**: 2,400,599 bars (2003-05-05 to 2026-04-29) — cataloged, validated, suitable for intraday research with documented gaps (17,280 missing bars = ~0.7%, 5 multi-day outages).
- **BTCUSD data**: **NOT PRESENT** — no raw or processed BTCUSD datasets found anywhere in the repository.
- **M.A.R.S. Donchian strategy**: Fully implemented in `trend_breakout.py` with MTF gate (`mtf_gate.py`). Live path uses 5M Donchian breakout (window=20, exit_window=10, ATR stop 2.0x) + 1H/30M/15M confirmation gate.
- **Backtesting infrastructure**: Two parallel engines exist — (a) research vectorized backtests (`run_hyp_a_backtest.py`, `spread_aware_backtest.py`) and (b) multi-pair bar-by-bar simulation (`run_multi_pair_backtest.py`). The live executor (`mt5_executor.py`) is production-grade but has cross-pair bugs.
- **Broker integration**: MT5/Exness demo account `#476944496` hardcoded. Demo-account safety gate enforced. No BTCUSD broker configured.
- **Critical blockers**: JPY pip_value bug (F-01), hard-coded XAUUSD contract_size in 4 live-execution locations (F-02), multi-pair position sync broken (F-09), commission/swap not logged in audit DB (F-08), credentials committed to git (F-12).
- **Test status**: 107/109 tests pass. Two failures are production defects (F-07, F-08).

**Bottom line**: XAUUSD infrastructure is ~80% production-ready for research. BTCUSD requires data ingestion + broker integration from scratch. Six research priorities can be tested for XAUUSD; none for BTCUSD until data exists.

---

## 2. Repository and Architecture Overview

### 2.1 Directory Structure (verified)

```
MARS-QUANT/
├── .env                          # ⚠️ COMMITTED with real credentials (F-12)
├── .env.example                  # Template with real FRED key
├── pyproject.toml                # mars-quant, requires-python>=3.10
├── requirements.txt              # Runtime deps (some commented as "not required for live")
├── requirements_actual.txt       # Pinned versions (Python 3.14.7, pandas 3.0.5, arch 8.0.0)
├── run_session_v3.py             # LIVE entry point (762 lines) — MultiSymbolSession, MockMT5
├── run_multi_pair_backtest.py    # Backtest runner + SYMBOL_CONFIGS (canonical contract specs)
├── dashboard.py                  # Streamlit monitor (port 8765, read-only audit DB)
├── mars/
│   ├── apps/
│   │   ├── trading/              # PRODUCTION PATH
│   │   │   ├── mt5_executor.py   # 1935 lines — MT5Executor, AuditLogger, OrderRouter, DemoAccountGate
│   │   │   ├── system/
│   │   │   │   ├── vol_scaled_system.py  # 1049 lines — VolScaledSizer(GARCH), RiskManager, TradeExecutor
│   │   │   │   └── pair_config.py        # PAIR_CONFIG, get_data_path, get_contract_specs
│   │   │   ├── signals/
│   │   │   │   ├── trend_breakout.py     # DonchianBreakoutSignal, MACrossoverSignal, CombinedTrendSignal
│   │   │   │   └── mtf_gate.py           # MTFGate (1H/30M/15M confirmation)
│   │   │   ├── demo_trading_system.py    # Paper wrapper (NOT used by live)
│   │   │   ├── latency.py, loss_audit.py, risk_metrics.py
│   │   ├── backtester/          # RESEARCH PATH
│   │   │   ├── run_hyp_a_backtest.py
│   │   │   ├── spread_aware_backtest.py
│   │   │   └── run_hyp_a_spread_backtest.py
│   │   ├── research_lab/        # Hyp-A/B/C pipelines
│   │   └── trainer/             # XGBoost training
│   ├── core/                    # config, schemas, timeframes, types
│   ├── data/                    # ingestion, validation, storage, versioning, normalization
│   ├── features/                # 20+ subpackages — mostly empty stubs (F-03)
│   ├── libs/                    # models (GARCH, XGBoost), learning (empty stubs), risk, strategies, utils
│   ├── research/                # hypothesis, experiment, workflow, validation
│   └── validation/              # bootstrap, cross_validation, performance, walk_forward, feature_stability
├── data/
│   ├── raw/                     # CSV inputs (XAUUSD 2.4M rows, EURUSD/USDJPY/EURGBP ~385K each)
│   └── processed/               # Parquet catalog (xauusd/m5/v1.0.0 = 45 MB, catalog.json)
├── reports/                     # Audit artifacts, backtest results
├── tests/                       # 109 tests (107 pass, 2 fail)
└── legacy/                      # Empty
```

### 2.2 Architecture Relationships (verified by import analysis)

**Live execution path**: `run_session_v3.py` → `MultiSymbolSession` → `MT5Executor` → `MT5OrderRouter` + `RiskManager` + `VolScaledSizer` + `DonchianBreakoutSignal` + `MTFGate`

**Backtesting path**: `run_multi_pair_backtest.py` → `VolScaledSizer` + `RiskManager` + `TradeExecutor` + `create_signal_generator()` (uses `PAIR_CONFIG`)

**Research path**: `mars/apps/research_lab/*.py` → `mars/libs/features/*` + `mars/libs/models/*` → `mars/validation/*`

**Dashboard path**: `dashboard.py` → read-only SQLite on `mt5_audit_real.db`

**Separation assessment**: 
- ✅ Live vs. research code is separated by module hierarchy (`apps/trading` vs `apps/backtester`/`research_lab`)
- ⚠️ `SYMBOL_CONFIGS` (contract specs) defined in `run_multi_pair_backtest.py` (backtest entry) but imported by live path via `pair_config.py:get_data_path()` → circular but functional
- ⚠️ `DemoTradingSystem` exists but is NOT invoked by live session — paper trading not exercised
- ❌ No formal strategy registry/plugin contract — new strategies require hand-wiring in `MultiSymbolSession.__init__`

### 2.3 Architectural Weaknesses

| Issue | Location | Severity |
|-------|----------|----------|
| No broker abstraction — MT5 calls inline | `mt5_executor.py` throughout | High (blocks crypto migration) |
| 29 empty stub packages in `mars/libs/learning/*` | `mars/libs/learning/**/__init__.py` | Medium (dead code) |
| `docs/architecture.md` claims production is "out of scope" but it's implemented | `docs/architecture.md` | Medium (doc drift) |
| Circular `SYMBOL_CONFIGS` dependency | `run_multi_pair_backtest.py` ↔ `pair_config.py` | Low |
| `loss_audit` schema created but never called from production | `loss_audit.py`, `mt5_executor.py` | Medium |

---

## 3. Historical Data Inventory

### 3.1 Raw Data (`data/raw/`)

| File | Instrument | Source | Format | Rows | Date Range | Size |
|------|------------|--------|--------|------|------------|------|
| `xauusd_m5_2003_2026_raw.csv` | XAUUSD | Dukascopy (via histdata) | CSV | 2,400,599 | 2003-05-05 to 2026-04-29 | 193 MB |
| `eurusd_m5_2020_2026_raw.csv` | EURUSD | Dukascopy | CSV | 2,400,599* | 2020-01-02 to 2026-09-15 | 23 MB |
| `usdjpy_m5_2020_2026_raw.csv` | USDJPY | Dukascopy | CSV | 2,400,599* | 2020-01-02 to 2026-09-15 | 23 MB |
| `eurgbp_m5_2020_2026_raw.csv` | EURGBP | Dukascopy | CSV | 2,400,599* | 2020-01-02 to 2026-09-15 | 23 MB |
| `xauusd_h1_2015_present.parquet` | XAUUSD | Dukascopy | Parquet | ~ | 2015-present | 1.9 MB |
| `xauusd_h1_2018_present.parquet` | XAUUSD | Dukascopy | Parquet | ~ | 2018-present | 1.3 MB |
| `xauusd_h1_2020_present.parquet` | XAUUSD | Dukascopy | Parquet | ~ | 2020-present | 0.9 MB |
| `xauusd_h1_2025_present.parquet` | XAUUSD | Dukascopy | Parquet | ~ | 2025-present | 0.1 MB |

*FX raw CSVs appear to have same row count as XAUUSD but different date ranges — likely truncated on load.

**BTCUSD**: **NO FILES FOUND** in raw or processed directories.

### 3.2 Processed Data (`data/processed/`)

| Dataset ID (catalog.json) | Symbol | Timeframe | Version | Source | Rows | Date Range | Columns |
|---------------------------|--------|-----------|---------|--------|------|------------|---------|
| `xauusd_m5_v1.0.0_5578cedd` | XAUUSD | M5 | 1.0.0 | csv_dukascopy | 2,400,599 | 2003-05-05 to 2026-04-29 | open,high,low,close,volume |
| `xauusd_m5_1.0.0_b28cd6d3` | XAUUSD | M5 | 1.0.0 | histdata_dukascopy | 2,400,599 | 2003-05-05 to 2026-04-29 | +date,instrument,granularity |
| `eurusd_m5_1.0.0_cbadb347` | EURUSD | M5 | 1.0.0 | histdata_dukascopy | 385,694 | 2020-01-02 to 2026-09-15 | +spread,<DATE>,<TIME> |
| `usdjpy_m5_1.0.0_12e5dd2c` | USDJPY | M5 | 1.0.0 | histdata_dukascopy | 385,700 | 2020-01-02 to 2026-09-15 | +spread,<DATE>,<TIME> |
| `eurgbp_m5_1.0.0_fed3368f` | EURGBP | M5 | 1.0.0 | histdata_dukascopy | 385,822 | 2020-01-02 to 2026-09-15 | +spread,<DATE>,<TIME> |
| `dxy_daily_v1.0.0_*` | DXY | D | 1.0.0 | FRED | 1,304 / 5,395 | 2020-2024 / 2006-2026 | close,volume |
| `real_yield_10y_daily_v1.0.0_*` | REAL_YIELD_10Y | D | 1.0.0 | FRED | 1,304 / 6,181 | 2020-2024 / 2003-2026 | close,volume |
| `vix_daily_v1.0.0_*` | VIX | D | 1.0.0 | FRED | 1,304 / 6,182 | 2020-2024 / 2003-2026 | close,volume |

**Catalog issues**: 9 entries with duplicates (2× XAUUSD M5, 2× DXY, 2× REAL_YIELD, 2× VIX). EURGBP cataloged but `PAIR_CONFIG` disables `EURGBPm`. `xauusdm` parquet exists as broker-suffix copy of canonical `xauusd`.

### 3.3 XAUUSD M5 Dataset Detail (processed/xauusd/m5/v1.0.0/data.parquet)

- **Rows**: 2,400,599 (matches ~2.4M reported)
- **Columns**: `timestamp` (datetime64[us, UTC]), `open`, `high`, `low`, `close`, `volume`, `date`, `instrument`, `granularity`
- **Date range**: 2003-05-05 00:05:00 UTC → 2026-04-29 09:55:00 UTC
- **Missing observations**: 0 in processed parquet (raw CSV missing 17,280 bars = 0.7% vs continuous 5-min grid)
- **Duplicate timestamps**: 0
- **Volume**: Present but meaning unclear (tick volume from Dukascopy, not real volume)
- **Bid/Ask**: Not available (mid-price only); spread column absent in processed XAUUSD (present in FX pairs)
- **Price representation**: Float64, USD per oz
- **Timezone**: UTC (consistent)
- **Gaps**: 25 weekend/session breaks (expected), 5 anomalous multi-day outages (2004-05-13: 9d, 2006-01-14: 4d, 2009-04-26: 3d, 2009-05-07: 9d, 2011-04-13: 3d)
- **Extreme returns**: 2,336 bars with \|z-return\| > 8.0 (concentrated 2008, 2013, 2020, 2026 — genuine volatility spikes per validation notes)

---

## 4. Data Quality Assessment

### 4.1 XAUUSD M5

| Dimension | Status | Notes |
|-----------|--------|-------|
| Completeness | ⚠️ 0.7% gaps | 17,280 missing bars vs continuous grid; 5 multi-day outages documented |
| Consistency | ✅ | Single source (Dukascopy), validated by ingestion pipeline |
| Timestamp alignment | ✅ | UTC, 5-min boundaries, no duplicates |
| Price fidelity | ✅ | Extreme returns verified as genuine (GFC, COVID, 2026 spikes) |
| Volume reliability | ❌ | Tick volume only, not real volume |
| Bid/Ask spread | ❌ | Not captured for XAUUSD (FX pairs have spread column) |
| Suitable for intraday research | ✅ | With caveats: exclude sessions adjacent to multi-day gaps for realized vol |

### 4.2 FX Pairs (EURUSD, USDJPY, EURGBP M5)

- **Date range**: 2020-01-02 to 2026-09-15 (~6.7 years)
- **Rows**: ~385K each (vs 2.4M for XAUUSD — shorter history)
- **Columns**: Include `spread` column (points), `<DATE>`, `<TIME>` artifacts
- **Volume**: Tick volume
- **Suitability**: Adequate for 2020+ research; insufficient for long-term regime studies

### 4.3 BTCUSD

**NO DATA EXISTS** — no raw CSV, no processed parquet, no catalog entry.

---

## 5. XAUUSD Readiness

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Trend-following research | ✅ | 23 years of M5 data, Donchian implementation live |
| Donchian breakout testing | ✅ | Live strategy uses exactly this; backtest engine supports it |
| Session-based momentum | ✅ | M5 data + session features (Asia/London/NY/Overlap) in `fx_sessions.py` |
| Intraday momentum vs mean-reversion | ✅ | M5 resolution, ATR/vol features, MTF gate |
| Multi-timeframe analysis | ✅ | 1H/30M/15M/5M via MT5 `copy_rates_from_pos` in live; resampling in research |
| Data sufficiency | ✅ | 2.4M bars >> minimum for statistical validity |

**Caveats**: 
- No bid/ask spread history for XAUUSD (FX pairs have it)
- 5 multi-day gaps require session-exclusion logic in realized vol (already documented in catalog)
- First ~20 sessions of 2003 unstable for realized_vol_trailing_20

---

## 6. BTCUSD Readiness

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Historical data | ❌ | No files in raw/processed, no catalog entry |
| Broker integration | ❌ | MT5/Exness only; no crypto exchange SDK |
| Symbol handling | ❌ | FX-only `m`-suffix logic, pip_size/contract_size assumptions |
| Session logic | ❌ | FX sessions (Asia/London/NY); crypto trades 24/7 |
| Contract specs | ❌ | No BTCUSDT/perp specs in `SYMBOL_CONFIGS` or `PAIR_CONFIG` |
| Risk metrics | ❌ | `quote_to_usd_at_entry` raises for non-USD/JPY quotes |

**Required to enable BTCUSD**:
1. Data ingestion pipeline (CCXT or exchange REST) → parquet catalog
2. Exchange adapter (replace `MT5Executor` with `CryptoExecutor`)
3. Symbol normalization (Binance `BTCUSDT`, Bybit `BTCUSDT`, Kraken `XBT/USD`)
4. 24/7 session logic + funding rate handling
5. Contract specs: `contract_size=1`, `tick_size=0.01/0.1/1`, `quote_currency=USDT/BTC`
6. Quote→USD conversion for BTC/ETH-quoted pairs

---

## 7. M.A.R.S. Donchian Strategy Audit

### 7.1 Exact Rules (from `trend_breakout.py:DonchianBreakoutSignal`)

**Entry (5M timeframe)**:
- Long: `close > highest_high(20).shift(1)` AND session filter passes
- Short: `close < lowest_low(20).shift(1)` AND session filter passes
- Session filter: configurable (`all`, `london` 08-17 UTC, `ny` 13-22 UTC, `overlap` 13-17 UTC); live uses `"all"`

**Exit**:
- Long exit: `close < lowest_low(10).shift(1)` OR short entry signal
- Short exit: `close > highest_high(10).shift(1)` OR long entry signal
- Stop: ATR(14) × 2.0 (default `stop_mode='atr'`) OR fixed pips (`risk_pips × pip_size`)
- Take-profit: Entry ± (Entry - Stop) × 3.0 (3:1 R:R from tier config)

**Position sizing**: VolScaledSizer (GARCH) → leverage = (target_vol / forecast_vol) × kelly_fraction, clipped [0.01, 3.0], converted to lots via `contract_size` from `SYMBOL_CONFIGS`

**Filters**: 
- MTF gate: 1H trend (EMA50 slope 10-bar) + 30M bias (EMA50 slope 8-bar) + 15M context (spread/ATR checks)
- All three must align with breakout direction; 15M must be `TRADEABLE`

**Risk controls**: Tiered `RiskManager` (per-trade %, aggregate %, daily/weekly/monthly loss limits, max DD kill-switch, consecutive loss circuit breaker)

### 7.2 Implementation Trace (Live Path)

```
poll_cycle() 
  → signal_gen.compute_live(mt5, symbol, equity)  [fetches 5M bars, runs generate()]
  → mtf_gate.evaluate_gate(breakout_signal, price, stop)  [fetches 1H/30M/15M, classifies]
  → if ALLOWED: compute position_size via VolScaledSizer.forecast_vol()
  → TradeConfig → executor.open_position() → risk checks → MT5OrderRouter.send_order()
  → log_fill() → audit DB
```

### 7.3 Identified Issues

| Issue | Location | Severity | Category |
|-------|----------|----------|----------|
| **Look-ahead in `generate()`**: `entry_price = open.shift(-1)` uses next bar's open — correct for backtest, but `compute_live()` uses current close when `entry_price` is NaN | `trend_breakout.py:111, 205-206` | Medium | VERIFIED |
| **Repainting risk**: Donchian channels use `shift(1)` correctly (prior bar's high/low) — no repaint | `trend_breakout.py:82-83` | ✅ OK | VERIFIED |
| **Incomplete bar handling**: `compute_live()` fetches `copy_rates_from_pos(..., 0, n_bars)` — includes current forming bar; `generate()` excludes it via `iloc[:-1]` in trend/bias classification but not in Donchian calc | `trend_breakout.py:180, 300` | Medium | VERIFIED |
| **Duplicate signals**: Idempotency guard in `MT5Executor._is_duplicate_signal()` uses `symbol_bar_signal` key — survives restart via JSON file | `mt5_executor.py:1291-1298` | ✅ OK | VERIFIED |
| **Position management defects**: `_sync_positions_from_mt5()` hardcodes `XAUUSDm` — drops EURUSDm/USDJPYm positions | `mt5_executor.py:1316` | High | VERIFIED (F-09) |
| **MTF gate stale data bug (fixed)**: `fetch_all_timeframes()` now called every cycle (was guarded by `if not self._tf_data`) | `mtf_gate.py:369-374` | ✅ Fixed | VERIFIED |

### 7.4 Backtest vs Live Parity

- **Backtest** (`run_multi_pair_backtest.py`): Uses `signal_generator.generate(df)` on full DataFrame, then `run_simulation()` bar-by-bar with same stop/TP logic
- **Live**: Uses `compute_live()` per cycle with MT5 data fetch
- **Divergence**: Backtest uses pre-computed signals on historical data; live re-fetches last N bars each cycle. MTF gate in backtest is NOT used (only in live `run_session_v3.py`). The `run_hyp_a_backtest.py` is a different (ML) strategy entirely.

---

## 8. Backtesting Infrastructure Audit

### 8.1 Engines

| Engine | File | Type | Features |
|--------|------|------|----------|
| Hyp-A Vectorized | `run_hyp_a_backtest.py` | Session-level (1 trade/day) | ML classifier, mid-price, commission only |
| Spread-Aware | `spread_aware_backtest.py` | Session-level + bid/ask fills | Spread modeling (session multipliers), commission |
| Multi-Pair Bar-by-Bar | `run_multi_pair_backtest.py` | Full simulation | Donchian+MTF, VolScaledSizer, RiskManager, per-pair configs |

### 8.2 Simulation Fidelity

| Aspect | Multi-Pair Backtest | Live Execution |
|--------|---------------------|----------------|
| Data loading | Parquet (processed) | MT5 `copy_rates_from_pos` |
| Indicators | Pre-computed (ATR, Donchian) | Computed live per cycle |
| Signal generation | `generate()` on full frame | `compute_live()` on recent N bars |
| Trade simulation | Bar-by-bar loop with SL/TP/time exit | MT5 `order_send` + `update_position()` |
| Bid/ask spreads | NOT modeled (mid-price only) | Real MT5 bid/ask via `symbol_info_tick` |
| Commissions | 0.02% per side (hardcoded) | Real MT5 commission from deal history |
| Swaps/financing | NOT modeled | Real MT5 swap from deal history |
| Slippage | NOT modeled | MT5 `deviation=20` (points) |
| Partial fills | NOT modeled | MT5 `ORDER_FILLING_IOC` |
| Same-bar signal+trade | Yes (next bar open) | Yes (current tick) |
| End-of-test liquidation | Implicit (loop ends) | Manual/MT5 SL/TP |

### 8.3 Validation Framework Support

| Capability | Status | Location |
|------------|--------|----------|
| Chronological in/out-of-sample | ✅ | `run_hyp_a_backtest.py:94-97` (test_ratio split) |
| Frozen test-set testing | ✅ | `ExperimentLog.assert_can_evaluate_on_test()` + `HypothesisRecord.test_set_locked` |
| Walk-forward analysis | ✅ | `mars/validation/walk_forward.py:WalkForwardSplitter` |
| Parameter sensitivity | ❌ | No automated sweep; manual only |
| Monte Carlo | ✅ | `mars/validation/bootstrap.py:bootstrap_confidence_interval` |
| Trade-level reporting | ✅ | `run_multi_pair_backtest.py` returns trade list |
| Benchmark comparison | ✅ | Buy-and-hold return computed in backtest output |
| Reproducible configs | ⚠️ | `PAIR_CONFIG` + `SYMBOL_CONFIGS` but no experiment versioning in backtest runner |

### 8.4 Test Coverage

- **Unit tests**: 109 tests covering risk rules, kill-switch, MTF gate, latency, data validation, feature engines
- **Integration tests**: `test_integration_simple.py`, `test_real_order*.py` (require live MT5)
- **Failures**: 
  - `test_loss_audit.py::test_broker_close_creates_clean_system_exit_audit_row` — `signals.entry_price NOT NULL` violation (F-07)
  - `test_risk_rules.py::TestFillLogsRealCommissionSwapProfit` — commission=0 in audit DB (F-08)

---

## 9. Broker and Execution Economics

### 9.1 Exness / MT5 Configuration (verified from code)

| Parameter | Value | Source | Verified |
|-----------|-------|--------|----------|
| Broker | Exness | `.env.example`, `MT5Config.server` | REPORTED |
| Demo account | #476944496 | `.env`, `run_session_v3.py:629` | VERIFIED |
| Server | `Exness-MT5Trial9` | `.env` | REPORTED |
| Symbols traded | `XAUUSDm`, `EURUSDm`, `USDJPYm`, `EURGBPm` | `PAIR_CONFIG` keys | VERIFIED |
| Contract size (XAUUSD) | 100 oz/lot | `SYMBOL_CONFIGS['XAUUSD']` | VERIFIED |
| Contract size (FX) | 100,000 units/lot | `SYMBOL_CONFIGS['EURUSD']` etc. | VERIFIED |
| Pip size (XAUUSD) | 0.01 | `PAIR_CONFIG['XAUUSDm']` | VERIFIED |
| Pip size (FX) | 0.0001 | `PAIR_CONFIG['EURUSDm']` | VERIFIED |
| Pip size (JPY) | 0.01 | `PAIR_CONFIG['USDJPYm']` | VERIFIED |
| Min lot | 0.01 | `MT5SymbolInfo.volume_min` mock | REPORTED |
| Spread (XAUUSD) | ~260 points (26 pips) | Mock in `run_session_v3.py:135` | REPORTED |
| Commission | Not in config | MT5 deal history only | UNKNOWN |
| Swap | -1.5 long / -0.5 short (mock) | Mock in `run_session_v3.py:139-140` | REPORTED |
| Leverage | 2000 (demo) | Mock account_info | REPORTED |
| Margin | 1000 initial / 500 maintenance (mock) | Mock | REPORTED |
| Execution mode | `ORDER_FILLING_IOC` | `MT5OrderRouter.send_order:380` | VERIFIED |
| Filling policy | IOC (Immediate or Cancel) | Same | VERIFIED |

### 9.2 Missing / Unverified Information

| Information | Status | Needed For |
|-------------|--------|------------|
| Actual Exness commission per lot (XAUUSD, FX) | UNKNOWN | Accurate backtest costs |
| Actual swap rates (current) | UNKNOWN | Carry cost modeling |
| Minimum stop distance (points) | UNKNOWN | Stop placement validation |
| Trading hours / session breaks | PARTIAL (code assumes 24/5) | Session filter accuracy |
| Symbol contract changes history | UNKNOWN | Continuous contract validity |
| Real spread distribution (XAUUSD) | UNKNOWN | Spread-aware backtest calibration |

**Never invent broker specifications** — all above must be obtained from Exness API/documentation or live MT5 terminal query.

---

## 10. Existing Backtest and Validation Evidence

### 10.1 Documented Results

| Report | Strategy | Instrument | Period | Trades | Key Metrics | Verifiable |
|--------|----------|------------|--------|--------|-------------|------------|
| `hyp_a_backtest_result.txt` | MLStrategy (XGBoost) | XAUUSD H1 | 2024-03 to 2025-09 | 396 | Return 9.03%, Sharpe 0.38, MaxDD -13.96%, PF 1.10, Win% 52.78% | VERIFIED (file exists) |
| `mars_hyp_a_xgb_baseline_*.txt` | XGBoost classifier | XAUUSD H1 | 2015/2018/2020/2025 starts | Various | Accuracy ~65%, R² negative | VERIFIED |
| `hyp_a_xauusd_h1_*_xgboost_*.txt` | XGBoost | XAUUSD H1 | Various | Various | Classification metrics | VERIFIED |
| `usdjpy_result.json` | Multi-pair backtest | USDJPY M5 | 2022-2024 | ~ | Not inspected | REPORTED |

### 10.2 Critical Assessment

- **Hyp-A (Asia→London)**: **REJECTED** per `HYP-A-001.json` — negative R², Sharpe positive but underperforms buy-and-hold by 20-70pp, classification edge ~2pp over majority class
- **Hyp-B (Session vol)**: **DRAFT** — GARCH/CARR baseline defined, no results yet
- **Hyp-C (Macro regime)**: **DRAFT** — DXY/real yield data ingested, no results yet
- **Multi-pair Donchian backtest**: No results file found in `reports/` (only `usdjpy_result.json` exists but not inspected)
- **Live demo trading**: Audit DB shows 16 fills (15 USDJPYm, 1 XAUUSDm open), small losses ~$2 each — consistent with session-end exits

**No strategy has demonstrated statistically validated, economically viable edge after realistic costs.**

---

## 11. Security and Operational Risks

| Risk | Location | Severity | Status |
|------|----------|----------|--------|
| `.env` committed with real `PASSWORD=dela.RIDGE1` and `FRED_API_KEY` | `.env`, `.gitignore` missing `.env` | **CRITICAL** | F-12 |
| `.env.example` contains real FRED API key | `.env.example` | HIGH | F-12 |
| MT5 password may echo in stdout during connect | `MT5ConnectionManager.connect()` | MEDIUM | Unverified |
| Audit DB in temp dir (`tempfile.gettempdir()`) — cleared by Windows cleanup | `MT5AuditLogger.__init__` | MEDIUM | F-04 (backups empty) |
| Kill-switch JSON shared across processes — race condition | `RiskManager.KILL_SWITCH_FILE` | LOW | Unverified |
| No encryption at rest for audit DB | SQLite plaintext | LOW | Acceptable for demo |

---

## 12. Research Hypothesis Readiness Matrix

| Priority | Hypothesis | Required Data | Required Timeframe | Data Exists? | Quality Concerns | Broker Info Needed | Backtest Capability | Major Obstacles |
|----------|------------|---------------|-------------------|--------------|------------------|-------------------|---------------------|-----------------|
| 1 | BTCUSD Donchian breakout baseline | BTCUSD OHLCV + spread | M5/H1 | ❌ NO | N/A | Crypto exchange specs, funding rates | Engine exists but needs crypto adapter | **Data + broker from scratch** |
| 2 | XAUUSD session-to-session momentum | XAUUSD M5/H1 | M5/H1 | ✅ YES (23 yr) | 5 multi-day gaps, no bid/ask | Exness XAUUSDm specs (have) | Full (live + backtest) | Gap handling in vol features |
| 3 | BTCUSD trend vs mean reversion | BTCUSD OHLCV | M5/H1/D | ❌ NO | N/A | Crypto exchange | Engine exists | **Data + broker from scratch** |
| 4 | BTCUSD multi-timeframe trend | BTCUSD OHLCV | M5/M15/H1/H4 | ❌ NO | N/A | Crypto exchange | MTF gate logic portable | **Data + broker from scratch** |
| 5 | BTCUSD volume-weighted momentum | BTCUSD OHLCV + real volume | M5/H1 | ❌ NO | Crypto volume ≠ tick volume | Exchange with real volume | Feature stubs exist | **Data + broker + volume source** |
| 6 | BTCUSD intraday momentum vs reversal | BTCUSD OHLCV | M5/M15 | ❌ NO | N/A | Crypto exchange | MTF gate portable | **Data + broker from scratch** |

**Summary**: Only Priority 2 (XAUUSD session momentum) is testable with current resources. All BTCUSD priorities require data ingestion + exchange integration first.

---

## 13. Critical Defects and Blockers

| ID | Finding | Evidence | Severity | Why It Matters | Next Action |
|----|---------|----------|----------|----------------|-------------|
| **F-01** | JPY `pip_value_per_lot` bug: fallback sizing uses `pip_size * contract_size` without JPY→USD conversion (÷ entry_price) | `run_session_v3.py:503-526`, `risk_metrics.py:32-39` has fix | **CRITICAL** | USDJPYm trades under-sized ~158× at equity >$2k | Wire `quote_to_usd_at_entry` into fallback sizing paths |
| **F-02** | Hard-coded `100` contract_size in 4 live-execution locations (position value, manual-mod risk, PnL estimate) | `mt5_executor.py:1310, 1380, 1684, 1688` | **CRITICAL** | Wrong risk math for EURUSDm/USDJPYm (1000× off) | Replace with `get_contract_specs(symbol)['contract_size']` |
| **F-08** | `fills.commission` = 0 in audit DB — realized P&L wrong | `test_risk_rules.py` failure, DB inspection | **CRITICAL** | Blocks credible P&L accounting, risk metrics | Fix `MT5OrderRouter`/`log_fill` commission capture |
| **F-12** | `.env` committed with real credentials | `.env`, `.gitignore` | **CRITICAL** | Credential leak via git history | Rotate password, `git rm --cached .env`, add to `.gitignore` |
| **F-07** | `signals.entry_price NOT NULL` blocks valid loss-audit insertion | `test_loss_audit.py` failure | HIGH | Schema too strict for production path | Make `entry_price` nullable or provide default |
| **F-09** | `_sync_positions_from_mt5()` hardcodes `XAUUSDm` — drops other pairs | `mt5_executor.py:1316` | HIGH | Multi-pair live trading broken | Filter by `magic=123456` globally |
| **F-14** | `RiskManager.current_positions` not reconciled from MT5 on startup | `vol_scaled_system.py` | MEDIUM | Aggregate risk cap drifts across restarts | Add `_sync_from_broker()` to `RiskManager` |
| **F-05** | `loss_audit.record_loss_audit()` never called from production | Grep shows only test calls | MEDIUM | Live fills lack post-trade analysis | Integrate into `MT5Executor._close_live_position()` |
| **F-18** | `risk_events` table empty despite live code paths | DB inspection (0 rows) | MEDIUM | Manual mod / order failure events not captured | Verify insert path; fix if silent failure |

---

## 14. Missing Information

| Information | Source | Status |
|-------------|--------|--------|
| Exness actual commission per lot (XAUUSD, EURUSD, USDJPY, EURGBP) | Exness API / MT5 terminal | UNKNOWN |
| Exness actual swap rates (current) | Exness API / MT5 terminal | UNKNOWN |
| Minimum stop distance (points) per symbol | Exness specification | UNKNOWN |
| Historical symbol contract changes (Exness) | Exness documentation | UNKNOWN |
| Real XAUUSD spread distribution (bid/ask) | MT5 terminal history / Exness | UNKNOWN |
| BTCUSD data source decision (exchange, spot vs perp) | Research team | NOT DECIDED |
| Crypto exchange selection (Binance, Bybit, Kraken, etc.) | Research team | NOT DECIDED |
| Crypto margin mode (cross vs isolated, USDT vs coin) | Research team | NOT DECIDED |

---

## 15. Recommended Next Actions

### Immediate (before any research)
1. **Rotate Exness demo password** and remove `.env` from git history (`git filter-branch` or BFG)
2. **Fix F-01 (JPY pip_value)** — wire `quote_to_usd_at_entry` into fallback sizing (2 locations)
3. **Fix F-02 (hard-coded 100)** — replace 4 occurrences with `get_contract_specs(symbol)['contract_size']`
4. **Fix F-09 (multi-pair sync)** — change `positions_get(symbol="XAUUSDm")` to global `magic=123456` filter
5. **Fix F-08 (commission logging)** — debug `MT5OrderRouter.send_order` → `log_fill` commission capture
6. **Enable audit DB backups** — verify `MT5AuditLogger.backup()` writes to `audit_backups/`

### Short-term (enable rigorous research)
7. **Run multi-pair backtest** on fixed code to generate baseline Donchian+MTF results for all 3 enabled pairs
8. **Add spread column to XAUUSD processed data** — ingest from MT5 or Dukascopy bid/ask if available
9. **Implement purged CV + walk-forward** in `run_multi_pair_backtest.py` (infrastructure exists in `mars/validation/`)
10. **Document strategy parameters** in a versioned config (separate from `PAIR_CONFIG`) for reproducibility

### BTCUSD Path (parallel track)
11. **Select crypto exchange(s)** and data vendor (CCXT + Binance/Bybit REST)
12. **Build `CryptoDataIngestion`** → parquet catalog with funding rate columns
13. **Design `ExchangeAdapter` interface** — `MT5Adapter` + `CryptoAdapter` (abstract `MT5Executor`)
14. **Extend `SYMBOL_CONFIGS`/`PAIR_CONFIG`** for crypto symbols (contract_size=1, tick_size, quote_currency)
15. **Implement 24/7 session logic + funding rate handling** in `RiskManager` and `MTFGate`

---

## Final Assessment: Answers to Required Questions

### 1. What historical data do we actually have?
- **XAUUSD**: 2,400,599 M5 bars (2003-2026) + 4 H1 parquets (2015/2018/2020/2025 starts) — validated, cataloged, 0.7% gaps documented
- **EURUSD/USDJPY/EURGBP**: ~385K M5 bars each (2020-2026) with spread column
- **Macro**: DXY, Real Yield 10Y, VIX daily from FRED (2003-2026 and 2020-2024 versions)
- **BTCUSD**: **NONE**

### 2. Is the XAUUSD dataset suitable for rigorous intraday research?
**Yes, with caveats**. 23 years of M5 data is sufficient for all six research priority types. Documented gaps (5 multi-day outages, weekend breaks) require session-exclusion in realized vol calculations. No bid/ask spread history limits execution-cost fidelity. First ~20 sessions of 2003 unstable for trailing vol windows.

### 3. Do we have usable BTCUSD historical data?
**No**. Zero BTCUSD files in raw/processed, no catalog entry, no broker integration.

### 4. Is the existing M.A.R.S. Donchian strategy sufficiently understood to serve as a baseline?
**Yes**. Entry/exit rules, MTF gate logic, position sizing (GARCH + fallback), risk controls (tiered), and execution path are all traceable in code. Two parity gaps: (a) MTF gate not used in backtest engine, (b) live `compute_live()` includes forming bar vs backtest on closed bars only.

### 5. Can the existing backtesting engine produce trustworthy results?
**Partially**. The multi-pair bar-by-bar engine (`run_multi_pair_backtest.py`) simulates SL/TP/time exits correctly and uses the same `RiskManager`/`VolScaledSizer` as live. **Critical gaps**: no bid/ask spread modeling (mid-price only), no slippage, no swap/financing, commission hardcoded at 0.02%. The spread-aware engine exists but is not integrated into the multi-pair runner. Commission logging is broken in audit DB (F-08), so live cost validation is impossible.

### 6. What are the most serious technical or data-quality blockers?
1. **F-12**: Credentials in git — security emergency
2. **F-01/F-02**: Cross-pair sizing bugs — would invalidate any multi-pair research
3. **F-08**: Commission not logged — realized P&L untrustworthy
4. **F-09**: Multi-pair position sync broken — live trading not actually multi-pair
5. **No BTCUSD data/broker** — all BTCUSD priorities blocked

### 7. What must be fixed before the first controlled experiment?
**Minimum viable fix set**: F-12, F-01, F-02, F-09, F-08, F-07. After these, the multi-pair backtest can produce credible XAUUSD/EURUSD/USDJPY results with proper risk accounting.

### 8. Which of our six research priorities can realistically be tested with current resources?
**Only Priority 2 (XAUUSD session-to-session momentum)**. All BTCUSD priorities require data + exchange integration from scratch. XAUUSD priorities 1,3,4,5,6 are BTCUSD-specific.

### 9. What information must we obtain from Exness or other external sources?
- Actual commission, swap, min stop distance, trading hours for all 4 symbols
- Real XAUUSD bid/ask spread distribution (for spread-aware backtest calibration)
- Symbol contract change history
- For BTCUSD: exchange selection, contract specs, funding rate schedule, API access

### 10. What is the single most important next action?
**Rotate the Exness demo password and purge `.env` from git history (F-12)** — this is a security incident. Then fix the JPY pip_value bug (F-01) and hard-coded contract_size (F-02) to unblock multi-pair research.

---

## Finding Classification Summary

| Category | Count | Examples |
|----------|-------|----------|
| **VERIFIED** (directly confirmed via code inspection / reproducible test) | 12 | F-01, F-02, F-07, F-08, F-09, F-12, data specs, strategy rules, test failures |
| **REPORTED** (stated in docs/reports but not independently verified) | 5 | Exness server name, mock spread/commission/swap values, leverage, margin |
| **INFERRED** (reasonable interpretation requiring confirmation) | 3 | Raw CSV row counts for FX, MTF gate stale-data fix effectiveness, backtest/live parity |
| **UNKNOWN** (could not be established) | 6 | Exness actual commission/swap/min-stop, BTCUSD exchange decision, crypto margin mode |

---

*Audit completed 2026-10-31. No code modified. All findings evidence-referenced to file paths and line numbers.*