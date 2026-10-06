# M.A.R.S. Quant — Backlog

Pre-Nov 3 checkpoint (priority-ordered):

---

## 🔴 HARD BLOCKER before account size > ~$1,500–2,000

### BUG: JPY pip_value_per_lot missing JPY→USD conversion

**Reported**: 2026-10-05 (post-fix verification of USDJPYm stop/target distances)
**Severity**: High — silently under-sizes all JPY-cross positions by ~158×
**Where**: `run_session_v3.py:478-485` (fallback path) and `run_session_v3.py:431-466`
(GARCH sizer `contract_multiplier` math in poll_cycle).

**Root cause**: `pip_value_per_lot = pip_size * contract_size` is treated as USD,
but for JPY-quoted pairs the result is JPY. Example for USDJPYm at entry 158.233:

```
pip_value_per_lot (current/buggy) = 0.01 × 100,000 = $1000.0
pip_value_per_lot (correct)      = 0.01 × 100,000 / 158.233 = $6.32
```

Same problem in any JPY-cross pair (USDJPYm, EURJPYm, GBPJPYm, AUDJPYm, etc.).

**Live impact**:
- At ~$190 equity: pre-floor `position_size = 1.92 / (32.7 × 1000) = 0.000059 lots`
- Correct pre-floor: `1.92 / (32.7 × 6.32) = 0.0093 lots`
- Both clamp to 0.01 minimum lot → live trade sizing is currently CORRECT only
  because the broker's 0.01 min lot happens to be ≥ the buggy result.
- At equity ≥ ~$2,066: the buggy formula produces `position_size < 0.01` after
  division, the floor rounds to 0.01, and the CORRECT formula would have
  produced 0.01+. Trade is silently under-sized by 158×.

**Why this matters at scale**: at $10k equity, correct = 0.046 lots, buggy = 0.0003
lots → 158× under-sizing → real per-trade risk on USDJPYm is 158× smaller than
configured → protective position sizing is silently disabled exactly when it
matters most.

**Fix** (small, ~10 lines):
- In `pair_config.py:get_contract_specs()`, return `quote_currency` (already present
  for USDJPYm = `'JPY'`)
- In sizing math, when `quote_currency != 'USD'`, divide `pip_value_per_lot` by
  current entry price to convert from quote-currency-pip-value to USD-pip-value.
- Same conversion in the GARCH sizer's `position_size = position_value /
  (entry_price * contract_multiplier)` math — `contract_multiplier` already encodes
  units, but the `position_value` in USD needs to be matched to contract-size-in-base
  units, not contract-size-in-pip-units.

**Validation**:
- Add a unit test: `pip_value_per_lot("USDJPYm", entry_price=158.233) ≈ $6.32`
- Add a check in `calculate_equity_floor()` (already accepts `quote_to_usd`
  parameter — just plumb it through).

**Status**: Filed. NOT urgent on $190 demo. MUST fix before any equity ≥ $1,500
on a JPY-cross pair.

---

## 🟡 Deferred (do not lose)

### DEFERRED — XAUUSDm GARCH fit deterministic check

**Originally reported as**: "XAUUSDm forecast_vol() fails with NaN/inf in y" — this
was a flaky test artifact (GARCH library state accumulation when looping through
multiple symbols in one process). On Oct 5's live session, XAUUSDm fitted and
ran cleanly through every polling cycle (no `[WARN] Sizer forecast error` lines
in `sizer_fix_session.log`). Standalone re-tests also pass.

**No action required for v1 baseline.** If it does fail in a future live session,
the same `[WARN] *** FALLBACK SIZING ***` lines added in this round will surface it
loudly. Just monitor for that string.

---

## ✓ Done (closed this round, do not re-open unless regression)

- `forecast_vol()` handles int64 DatetimeIndex / timestamp-column / row-position
  cases defensively (`mars/apps/trading/system/vol_scaled_system.py:165-178`)
- `run_session_v3.py:411-415` promotes `timestamp` column to DatetimeIndex on
  parquet load
- All 4 fallback sizing paths in `poll_cycle` print
  `[WARN] *** FALLBACK SIZING *** {symbol}: …`
- `fills.degraded_sizing` column added; tickets 3325045333 and 3325060832 tagged=1
- `compute_expectancy_breakdown()` partitions clean vs degraded; new "⚠️ Degraded
  sizing" panel in dashboard (`dashboard.py`)
- USDJPYm SL/TP distance vs pair_config: confirmed 1 pip = bid/ask spread cost on
  entry, NOT a signal-logic bug; realized RR ~2.87 vs configured 3.0 is the cost
  of spread, not a sizing or signal error.