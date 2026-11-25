# M.A.R.S. Quant — Research Programme 01
## Phase F: Formal Strategy Specification — XAU-SESSION-MOM-001

**Strategy ID:** XAU-SESSION-MOM-001  
**Name:** Asian-Session Momentum Continuation  
**Version:** 1.0 (Frozen for IS Research)  
**Date:** 2026-11-25  
**Status:** SPECIFICATION FROZEN — Ready for Implementation  
**Research Hypothesis:** CSM-001 (Cross-Session Momentum) from Wei (2026)

---

## 1. Market Conditions

**Instrument:** Exness XAUUSDm (Spot Gold vs USD)  
**Account Type:** Standard (observed spread ~200 points median = 20 pips)  
**Timeframes:** 
- **Signal Generation:** H1 (session bars: Asia 00-08, Europe 08-14:30, US 14:30-24 UTC)
- **Execution:** M5 (entry at session open, exit at session close)
- **Regime Context:** H1 realized volatility, FOMC calendar (optional filter)

**Sessions (Fixed UTC — No DST Adjustment):**
| Session | UTC Range | Duration | Bars (H1) | Bars (M5) |
|---------|-----------|----------|-----------|-----------|
| Asia | 00:00 – 08:00 | 8h | 8 | 96 |
| Europe | 08:00 – 14:30 | 6.5h | 6-7 | 78 |
| US | 14:30 – 24:00 | 9.5h | 9-10 | 114 |

**Data:** Exness M5 v1.2.0 (2021-07-16 → 2026-10-09), H1 resampled from M5  
**Session Mapping:** Each M5 bar assigned to session by UTC hour/minute (per `cross_session_momentum.py`)

---

## 2. Signal Generation

### 2.1 Session Return Computation
For each trading day and session:
```
session_open  = first M5 bar's open in session
session_close = last M5 bar's close in session
session_return = (session_close - session_open) / session_open
session_direction = sign(session_return)  // +1, 0, -1
```

### 2.2 Cross-Session Momentum Signal
**Rule (Paper 12):** Previous session return predicts next session return.

```
signal_for_session_N = 1 if session_return_{N-1} > threshold else 0
```

**Threshold:** `0.0` (Paper 12: "positive previous-session return")  
**Signal Mode:** `direction` (sign only) — per Paper 12 and `cross_session_momentum.py` default

**Signal Timeline (No Look-Ahead):**
```
Session N-1 closes (e.g., Asia 08:00 UTC)
    → session_return_{N-1} observable
    → signal_for_session_N computed
Session N opens (e.g., Europe 08:00 UTC)
    → ENTRY at first M5 bar open (08:00 UTC)
Session N closes (e.g., Europe 14:30 UTC)
    → EXIT at last M5 bar close (14:25 UTC)
```

**Session Transitions:**
| Previous Session (Signal Source) | Next Session (Execution) |
|----------------------------------|--------------------------|
| Asia (00-08) | Europe (08:00-14:30) |
| Europe (08-14:30) | US (14:30-24:00) |
| US (14:30-24:00) | Next Day Asia (00:00-08:00) |

**First Session:** No previous session → signal = 0 (flat)

### 2.3 Signal Output
For each session N (starting from 2nd session in dataset):
- `signal`: 1 (long) or 0 (flat)
- `entry_session`: session N name
- `exit_session`: session N name (exit at same session close)
- `entry_time`: session N open timestamp (first M5 bar)
- `exit_time`: session N close timestamp (last M5 bar)

---

## 3. Entry Conditions

**Entry Trigger:** Signal = 1 for current session  
**Entry Time:** First M5 bar of session (session open)  
**Entry Price:** 
- Long: `open + spread` (pay ask = bid + observed spread)
- *Note: Dataset OHLC are bid prices per Assignment 14 convention*

**Position Direction:** Long only (signal = 1 → long; signal = 0 → flat)  
**No Short Signals:** Paper 12 long-only variant survives costs; long/short fails

---

## 4. Exit Conditions

### 4.1 Primary Exit (Time-Based)
**Exit Time:** Last M5 bar of session (session close)  
**Exit Price:** 
- Long: `close` (receive bid)
- *No spread on exit for long — already paid on entry*

### 4.2 Stop-Loss (Risk Control)
**Stop Type:** Fixed distance in price units (configurable)  
**Stop Distance:** `SL_points` (default: 200 points = 20 pips = 0.2 price)  
**Stop Price:** `entry_price - SL_distance`  
**Fill Convention (Gap-Aware Conservative):**
- If bar opens beyond stop → fill at `bar_open` (worse price)
- Else → fill at `stop_price`
- *Same as Assignment 14 `ExecutionModel.stop_fill = "gap_aware_conservative"`*

### 4.3 Exit Priority (Same-Bar Ambiguity)
If both stop and session-close exit trigger on same bar:
- Choose **worse price** for the position (long: lower of stop_fill vs close)
- Record exit reason as the event producing that price

### 4.4 End-of-Data Exit
If position open at final bar → close at last close price (long: receive bid)

---

## 5. Risk & Position Sizing

### 5.1 Risk Policy
**Model:** `ContractAwareFixedFractionalRisk` (exact reuse from Assignment 14)  
**Risk Fraction:** `1.0%` of equity per trade (programme constraint)  
**Equity:** Configurable (IS: $10,000 for normalization; $30 for feasibility)

### 5.2 Sizing Formula
```
risk_dollars = equity × risk_fraction
risk_per_lot = stop_distance × contract_size × quote_to_usd
lots_exact = risk_dollars / risk_per_lot
lots = floor(lots_exact / volume_step) × volume_step
```

### 5.3 Instrument Specification (Exness XAUUSDm Standard)
| Parameter | Value | Source |
|-----------|-------|--------|
| symbol | XAUUSDm | `pair_config.offline` |
| contract_size | 100.0 oz | Verified |
| pip_size | 0.01 | Verified |
| point_size | 0.001 | Verified (spread column unit) |
| quote_currency | USD | Verified |
| volume_min | 0.01 lots | Verified |
| volume_max | 200.0 lots | Verified |
| volume_step | 0.01 lots | Verified |
| volume_spec_source | pair_config.offline | Documented |

### 5.4 Volume Constraints (Hard Rules)
- **Min volume breach → REJECT trade** (never force oversized position)
- **Max volume breach → REJECT trade**
- **Computed size ≤ 0 → REJECT trade**

### 5.5 $30 Feasibility Check (Per Programme Constraint)
| Parameter | Value |
|-----------|-------|
| Equity | $30.00 |
| Risk fraction | 1% = $0.30 |
| Stop distance | 200 points = 0.2 price |
| Risk per lot | 0.2 × 100 × 1.0 = $20.00 |
| Lots exact | $0.30 / $20.00 = 0.015 |
| Lots (floored to step) | 0.01 lots |
| Risk at min volume | 0.01 × $20.00 = $0.20 ≤ $0.30 ✅ |
| **Verdict** | **FEASIBLE at $30** (0.01 lots, SL=200 pts) |

**Note:** If SL increased beyond 300 points, min-volume breach occurs at $30 equity.

---

## 6. Transaction Cost Model

### 6.1 Observed Costs (Data-Driven)
- **Spread:** Per-bar observed spread (points) × `point_size` = price distance
  - Long entry: pays spread (buy at ask = bid + spread)
  - Long exit: receives bid (no spread)
  - **Round-trip = 1 × observed spread**
- **Spread stats (M5 v1.2.0):** Median 200 points, Mean 201 points, Max 3,352 points

### 6.2 Configurable Assumptions (Labelled as Assumptions)
| Cost | Default | Notes |
|------|---------|-------|
| Commission per lot (round-trip) | $0.00 | Exness Standard: no commission |
| Slippage (per side) | 0 points | Conservative: 0; sensitivity: 5-10 pts |
| Swap per lot per night | $0.00 | Intraday holds (exit same session) |
| Spread multiplier | 1.0 | Sensitivity: 1.0, 1.5, 2.0 |

### 6.3 Cost Application
```
spread_cost = spread_points × point_size × contract_size × lots
commission = commission_per_lot × lots
slippage_cost = 2 × slippage_points × point_size × contract_size × lots
total_cost = spread_cost + commission + slippage_cost + swap
net_pnl = gross_pnl - total_cost
```

---

## 7. Execution Model

| Convention | Value | Rationale |
|------------|-------|-----------|
| Entry fill | `next_bar_open` | Signal at session N-1 close → entry at session N open (first M5 bar) |
| Stop fill | `gap_aware_conservative` | Gap opens beyond stop → fill at open (available price) |
| Exit fill | `next_bar_open` | Session close = last M5 bar close; exit at that price |
| Same-bar priority | `worst_price` | Stop vs session-close → worse price for position |
| Reversal policy | `opposite_signal_ignored` | No short signals; long-only strategy |

---

## 8. Holding Period & Constraints

- **Holding Period:** Exactly 1 session (6.5–9.5 hours = 78–114 M5 bars)
- **Max 1 trade per session** (long or flat)
- **No pyramiding** (one position max)
- **No same-session re-entry** after stop/exit
- **Weekend gap risk:** US session Friday close → Asia session Monday open (signal uses Friday US return)

---

## 9. No-Trade Conditions

| Condition | Action |
|-----------|--------|
| Signal = 0 (prev session return ≤ 0) | Flat (no trade) |
| Risk engine rejects (min volume breach, etc.) | Flat; log rejection reason |
| Insufficient bars in session (< 10 M5 bars) | Flat; data quality filter |
| FOMC day (optional filter) | Flat if `block_fomc=True` (sensitivity only) |
| High spread regime (optional filter) | Flat if session median spread > p80 (sensitivity only) |
| High volatility regime (optional filter) | Flat if H1 realized vol > p80 (sensitivity only) |

---

## 10. Research Configuration (Frozen for IS)

### 10.1 Data Splits (Chronological)
| Split | Ratio | Period (approx) | Sessions |
|-------|-------|-----------------|----------|
| Train (IS) | 70% | 2021-07-16 → 2023-10 | ~2,700 |
| Validation | 15% | 2023-10 → 2024-04 | ~580 |
| Test (OOS) | 15% | 2024-04 → 2024-12 | ~580 |
| **Future OOS** | — | 2025-01 → 2025-10 | ~780 (reserved for Phase H) |

*Split by session index (not calendar) to preserve session sequence integrity*

### 10.2 Parameter Grid (IS Sensitivity Only — No Optimization)
| Parameter | Values Tested | Selection Rule |
|-----------|---------------|----------------|
| `threshold` | [0.0] | Fixed per Paper 12 |
| `signal_mode` | ["direction"] | Fixed per Paper 12 |
| `SL_points` | [200, 300, 500] | Sensitivity only |
| `spread_multiplier` | [1.0, 1.5, 2.0] | Sensitivity only |
| `risk_fraction` | [0.01] | Fixed per programme |
| `block_fomc` | [False, True] | Sensitivity only |
| `block_high_vol` | [False, True] | Sensitivity only |
| `block_high_spread` | [False, True] | Sensitivity only |

**NO GRID SEARCH** — One-factor-at-a-time from baseline (Paper 12 config). Selection rule: **Fixed before run** — baseline = Paper 12 config (threshold=0, direction, SL=200, spread_mult=1.0, no filters).

### 10.3 Baselines (Predeclared)
1. **Buy-and-Hold:** Long XAUUSDm from first session open to last session close
2. **Flat:** Zero return (risk-free)
3. **Random Signal:** Permuted signal sequence (Monte Carlo reshuffle baseline)

---

## 11. Performance Metrics (Required for All Runs)

### 11.1 Trade-Level
- Trade count (total, long, win, loss)
- Win rate (gross, net)
- Expectancy per trade (gross, net) in USD and % equity
- Profit Factor (gross, net)
- Average R-multiple
- Holding period distribution (sessions, minutes)

### 11.2 Equity Curve
- Total return (gross, net)
- Annualized return (gross, net)
- Annualized volatility (gross, net)
- Sharpe Ratio (risk-free = 0)
- Maximum Drawdown (gross, net, in USD and %)
- Max Drawdown Duration (sessions)
- Calmar Ratio

### 11.3 Session/Regime Breakdown
- By session type (Asia→Europe, Europe→US, US→Asia)
- By year
- By volatility regime (low/med/high H1 realized vol)
- By FOMC vs non-FOMC
- By spread regime (low/med/high)

### 11.4 Exposure & Turnover
- Exposure (fraction of sessions invested)
- Turnover (sum |Δposition| / equity)
- Average leverage

---

## 12. Monte Carlo Validation (Phase I)

**Config:** `MonteCarloConfig(n_simulations=10000, seed=20261125)`  
**Experiments:**
1. **Reshuffle (Sequence Risk):** Permute trade order 10,000× → equity fan, DD distribution
2. **Resample (Outcome Dispersion):** Bootstrap trades 10,000× → terminal equity, DD distribution

**Assumptions (Recorded):**
- i.i.d. trade outcomes (known false for session momentum — upper bound on robustness)
- Position sizing proportional to equity
- Costs embedded in observed net P&L (not re-sampled)
- No regime/clustering modelled

**Outputs:** Equity fan chart, DD distribution, terminal equity distribution, percentile bands, observed vs simulated.

---

## 13. Falsification Criteria (Pre-Registered)

**Strategy REJECTED if ANY hold on OOS (2025) or Frozen IS (2024 Test):**

| Criterion | Threshold | Rationale |
|-----------|-----------|-----------|
| Net expectancy | ≤ $0.00 | No edge after costs |
| Net Profit Factor | ≤ 1.00 | Losses ≥ profits |
| Net Sharpe Ratio | ≤ 0.0 | No risk-adjusted return |
| Max Drawdown (net) | > 20% equity | Excessive risk for $30 account |
| Trade count (OOS) | < 30 trades | Insufficient statistical power |
| Monte Carlo (reshuffle) | Observed DD > p95 of sims | Sequence-dependent (not robust) |
| Monte Carlo (resample) | Observed terminal equity < p05 of sims | Outcome unlikely under i.i.d. |

**Strategy ADVANCES only if ALL pass on frozen OOS.**

---

## 14. Reproduction Commands (Exact)

```bash
# 1. Ensure data exists
ls data/processed/xauusdm/m5/v1.2.0/data.parquet
ls data/processed/xauusdm/h1/v1.2.0/data.parquet

# 2. Run IS research (train/val/test split)
python -m mars.apps.research_lab.session_momentum_research \
    --config configs/session_momentum_001.yaml \
    --phase is

# 3. Freeze specification (record exact config, data version, code commit)
git commit -m "Freeze XAU-SESSION-MOM-001 spec for OOS"

# 4. Run frozen OOS (2025 data)
python -m mars.apps.research_lab.session_momentum_research \
    --config configs/session_momentum_001.yaml \
    --phase oos \
    --frozen

# 5. Run Monte Carlo (10,000 sims)
python -m mars.apps.research_lab.session_momentum_montecarlo \
    --trades reports/session_momentum_001/oos_trades.csv \
    --equity 10000 \
    --n_sims 10000

# 6. Run $30 feasibility
python -m mars.apps.research_lab.account_feasibility \
    --strategy session_momentum_001 \
    --equity 30 \
    --spec configs/instrument_spec_xauusdm.yaml
```

---

## 15. Version Control & Artifacts

| Artifact | Path | Version Control |
|----------|------|-----------------|
| This Specification | `research/programme_01/strategy_spec_XAU_SESSION_MOM_001.md` | Git (frozen at IS start) |
| Strategy Code | `mars/libs/strategies/xau_session_momentum.py` | Git |
| Backtester | `mars/apps/backtester/session_momentum_backtest.py` | Git |
| Research Pipeline | `mars/apps/research_lab/session_momentum_research.py` | Git |
| Config (Frozen) | `configs/session_momentum_001.yaml` | Git (tagged) |
| Data Version | `data/processed/xauusdm/m5/v1.2.0/` | Catalog (immutable) |
| IS Results | `reports/programme_01/session_momentum_001/is/` | Archived |
| OOS Results | `reports/programme_01/session_momentum_001/oos/` | Archived |
| MC Results | `reports/programme_01/session_momentum_001/mc/` | Archived |

---

*End of Formal Strategy Specification*  
*Generated: 2026-11-25*  
*Status: **FROZEN** — No parameter changes permitted during IS research*  
*Next: Implementation (Phase F→G) → In-Sample Research (Phase G)*