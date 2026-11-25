# M.A.R.S. Quant — Assignment 13
## Phase A Preflight Inspection Report

**Date:** 2026-11-24
**Git Commit:** `ce425d2` (main, up to date with origin/main)
**Python:** 3.14.7 (`.venv/Scripts/python`)
**MetaTrader5:** 5.0.6180 (imports successfully)
**MT5 Terminal:** `C:\Program Files\MetaTrader 5\terminal64.exe` (exists, requires login)

---

### 1. Python Environment & Dependency Compatibility ✅ VERIFIED

| Component | Version | Status |
|-----------|---------|--------|
| Python | 3.14.7 | ✅ Compatible |
| pandas | 3.x | ✅ |
| numpy | 2.x | ✅ |
| polars | 1.x | ✅ |
| scikit-learn | 1.5+ | ✅ |
| arch (GARCH) | 6.x | ✅ |
| MetaTrader5 | 5.0.6180 | ✅ |
| pytest | 9.1.1 | ✅ |
| pydantic | 2.x | ✅ |

All imports successful. No version conflicts.

---

### 2. MetaTrader 5 Terminal Installation ✅ VERIFIED

| Check | Result |
|-------|--------|
| Terminal executable exists | ✅ `C:\Program Files\MetaTrader 5\terminal64.exe` |
| Python `import MetaTrader5` | ✅ Works |
| `mt5.initialize()` without credentials | ✅ Fails as expected (Authorization failed) |
| Requires running terminal + login | ✅ Standard MT5 behavior |

**Note:** MT5 terminal must be running and logged in for live connection. Python API connects to running terminal.

---

### 3. Exness Demo Account Configuration ⚠️ PENDING USER ACTION

| Item | Status | Details |
|------|--------|---------|
| Credential rotation required | ⚠️ **BLOCKER** | User must obtain fresh Exness demo credentials |
| Old demo account `#476944496` | Rotated | Removed from codebase; was hardcoded default |
| `.env.example` placeholders | ✅ | `YOUR_ACCOUNT_NUMBER`, `YOUR_PASSWORD`, `YOUR_SERVER`, `YOUR_FRED_API_KEY` |
| `MT5Config.is_configured()` | ✅ | Returns `False` without env vars; `True` with all 3 |
| Hardcoded defaults removed | ✅ | `DEFAULT_MT5_CONFIG.login=0`, empty strings |

**Required user action:** Create local `.env` with fresh Exness demo credentials. Never commit `.env`.

---

### 4. Symbol Availability & Live Broker Metadata for XAUUSDm ⚠️ PENDING LIVE CONNECTION

| Spec (OFFLINE mode from `SYMBOL_CONFIGS`) | Value | Source |
|--------------------------------------------|-------|--------|
| Symbol | `XAUUSDm` | `run_multi_pair_backtest.py:55` |
| Contract size | 100 oz/lot | `SYMBOL_CONFIGS['XAUUSD']` |
| Pip size | 0.01 | `SYMBOL_CONFIGS['XAUUSD']` |
| Data path | `data/processed/xauusd/m5/v1.0.0/data.parquet` | 45 MB, 2.4M rows |
| Quote currency | USD (implied) | MT5 metadata will confirm |

**Live metadata (Phase C):** Must be obtained from connected Exness MT5 demo terminal:
- `trade_contract_size` (Exness-specific)
- `volume_min`, `volume_max`, `volume_step`
- `digits`, `point`, `spread`
- `trade_tick_size`, `trade_tick_value`
- `swap_long`, `swap_short`
- `margin_initial`, `margin_maintenance`

**SpecificationResolver** (`mt5_executor.py:142`) supports LIVE mode (MT5 metadata validation) and OFFLINE mode (SYMBOL_CONFIGS only).

---

### 5. Account Currency, Trade Mode, Contract Size, Volume Min/Step, Tick Size/Value ⚠️ PENDING LIVE CONNECTION

| Parameter | OFFLINE Config | Live Verification Needed |
|-----------|----------------|-------------------------|
| Account currency | USD (assumed) | ✅ Phase C |
| Trade mode | DEMO (0) | ✅ Phase C — **hard gate** |
| Contract size (XAUUSDm) | 100 | ✅ Phase C |
| Volume min (XAUUSDm) | 0.01 | ✅ Phase C |
| Volume step (XAUUSDm) | 0.01 | ✅ Phase C |
| Tick size (XAUUSDm) | 0.01 | ✅ Phase C |
| Tick value (XAUUSDm) | $1/tick/lot | ✅ Phase C |

**Verification in F-02 tests:** `test_instrument_spec_xauusd_pip_value` confirms $1/pip/lot, $10/lot for 10-pip stop.

---

### 6. RiskManager Configuration & Account-Equity Initialization ✅ VERIFIED

| Component | Status | Details |
|-----------|--------|---------|
| Tiered risk config | ✅ | 4 tiers: $100-1K, $1K-5K, $5K-25K, $25K+ |
| Tier locking | ✅ | Locked at session start based on live equity |
| Contract sizes per symbol | ✅ | `risk_manager.set_contract_size(symbol, size)` called in `run_session_v3.py:692` |
| Min lot override | ✅ | `risk_manager.set_min_lot(symbol, min_lot)` |
| Kill-switch file | ✅ | `tempfile.gettempdir() / 'risk_kill_switch.json'` |
| Peak equity persistence | ✅ | SQLite (`peak_equity` table) — tests pass |
| Daily loss circuit breaker | ✅ | Tested: `test_daily_loss_limit_halts_trading` |
| Concurrent risk cap | ✅ | Tested: `test_concurrent_position_cap` |
| Consecutive loss halt | ✅ | Tested: `test_consecutive_loss_halt_after_two_losses` |

**Tier selected at $500 equity (mock):** $100-1000 tier — 3% risk/trade, 6% aggregate cap, 2 concurrent trades, 3:1 R:R.

---

### 7. DemoAccountGate Enforcement ✅ VERIFIED (MANDATORY)

| Check | Status | Location |
|-------|--------|----------|
| Called in `MT5Executor._initialize()` | ✅ Line 1618 | `DemoAccountGate.verify_demo_account(self.mt5)` |
| Called in `run_session_v3.py` | ✅ Line 694-706 | Explicit check after connection |
| Hard-fails on non-DEMO | ✅ | `trade_mode != 0` → `RuntimeError` |
| Cannot be bypassed by env/config | ✅ | Requires code change to disable |
| Logs account info on startup | ✅ | `print(f"MT5 ACCOUNT CONNECTED: #{account_number}...")` |
| MT5 constants | Verified | 0=DEMO, 1=CONTEST, 2=REAL |

**Test coverage:** 6 tests in `test_mt5_safety_gate.py` — all pass.

---

### 8. Kill-Switch Initialization & Persistence ✅ VERIFIED

| Component | Status | Test |
|-----------|--------|------|
| JSON file persistence | ✅ | `risk_kill_switch.json` |
| Survives process restart | ✅ | `test_kill_switch_survives_restart` PASS |
| Peak equity SQLite persistence | ✅ | `test_peak_equity_survives_restart` PASS |
| Manual reset clears halt | ✅ | `test_manual_reset_clears_halt` PASS |
| Tier lock survives restart | ✅ | Locked equity stored in JSON |

---

### 9. SQLite Audit Logging & Position Reconciliation ✅ VERIFIED

| Feature | Status | Test Coverage |
|---------|--------|---------------|
| WAL mode | ✅ | `PRAGMA journal_mode=WAL` |
| Auto-backup | ✅ | `~/MARS_AUDIT_BACKUP/` + local `mt5_audit_backup.db` |
| Fill logging (open/close) | ✅ | `log_fill()`, `log_close_fill()` |
| Commission/swap/profit | ✅ | F-08: 11 regression tests PASS |
| Multi-entry deal aggregation | ✅ | `_lookup_entry_deal()` via `position_id` |
| Multi-exit deal aggregation | ✅ | `log_close_fill()` aggregates all exits |
| Idempotent reconciliation | ✅ | `test_duplicate_reconciliation` PASS |
| Net P&L formula | ✅ | `entry_profit + exit_profit + entry_comm + exit_comm + entry_swap + exit_swap` |
| Orphan position detection | ✅ | `reconcile_from_broker()` |

---

### 10. Shutdown & Recovery Behavior ✅ VERIFIED

| Scenario | Status | Evidence |
|----------|--------|----------|
| Clean shutdown | ✅ | `MT5Executor.shutdown()` closes MT5, saves idempotency |
| Process restart | ✅ | Idempotency file (`*.idempotency.json`) survives restart |
| Kill-switch survives restart | ✅ | JSON file read on `RiskManager` init |
| Peak equity survives restart | ✅ | SQLite `peak_equity` table |
| Tier lock survives restart | ✅ | Locked equity in kill-switch JSON |
| Duplicate signal prevention | ✅ | `_processed_signals` set + idempotency file |
| MT5 position sync on startup | ✅ | `_sync_positions_from_mt5()` in `_initialize()` |

---

### Phase A Summary

| Phase A Item | Status |
|--------------|--------|
| 1. Python environment | ✅ PASS |
| 2. MT5 terminal installation | ✅ PASS |
| 3. Exness demo account config | ⚠️ **BLOCKER — User must provide fresh credentials** |
| 4. XAUUSDm symbol metadata (OFFLINE) | ✅ PASS (SYMBOL_CONFIGS) |
| 5. Account specs (OFFLINE) | ✅ PASS (SYMBOL_CONFIGS) |
| 6. RiskManager config | ✅ PASS |
| 7. DemoAccountGate | ✅ PASS (mandatory, hard-fail) |
| 8. Kill-switch persistence | ✅ PASS |
| 9. SQLite audit + reconciliation | ✅ PASS (F-08 verified) |
| 10. Shutdown/recovery | ✅ PASS |

**Overall Phase A:** ✅ **INFRASTRUCTURE READY** — Only live credentials block Phase C

---

### Dry-Run Verification (Phase B) — All Tests Pass

```bash
# Mock MT5 dry-run with XAUUSDm
python run_session_v3.py --symbols XAUUSDm --mock-mt5 --dry-run
# ✅ PASS: Tier selection, demo gate, signal generation, sizer fitting

# Mock MT5 dry-run with multiple symbols
python run_session_v3.py --symbols XAUUSDm,EURUSDm --mock-mt5 --dry-run
# ✅ PASS: Multi-symbol contract sizes, GARCH sizers fit for both
```

**Test Suite Results (Quick):**
- Trading tests: **144 PASS** (incl. 25 F-02, 11 F-08, 6 safety gate, 2 kill-switch persistence)
- Data tests: **9 PASS**
- Validation tests: **6 PASS**
- Feature tests: **12 PASS**
- Research lab tests: **30 PASS**
- Libs tests: **7 PASS**
- **Total: 208 PASS** (139 research validation tests excluded as slow)

---

### Blockers for Phase C (Demo Terminal Connection)

| Blocker | Required Action |
|---------|-----------------|
| Fresh Exness demo credentials | User creates local `.env` with `DEMO_ACCOUNT_NUMBER`, `PASSWORD`, `SERVER` |
| FRED API key rotation | User replaces key exposed in git history (commit `9b839ae`) |
| Running MT5 terminal | User starts MetaTrader 5 and logs in with new demo credentials |

---

### Files Modified in This Session

| File | Change |
|------|--------|
| `run_session_v3.py` | Fixed bug: moved symbol parsing before contract size configuration (removed duplicate parsing at lines 748-767) |

**No other tracked files modified.** Working tree clean except for `run_session_v3.py` and `mt5_audit_backup.db`.

---

### Next Steps

1. **User:** Obtain fresh Exness demo credentials and FRED API key
2. **User:** Create local `.env` with placeholders replaced
3. **User:** Start MT5 terminal and log in with new demo account
4. **Phase C:** Connect to live MT5, verify account identity, trade_mode=DEMO, XAUUSDm metadata
5. **Phase D:** (After Phase C success + explicit authorization) Controlled demo execution test

**Do not proceed to Phase C until user confirms credentials are configured locally.**