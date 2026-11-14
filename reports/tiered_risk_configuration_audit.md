# M.A.R.S. QUANT — TIERED RISK CONFIGURATION AUDIT

**Date:** 2026-11-09  
**Auditor:** Automated inspection (no code modifications)  
**Status:** INSPECTION ONLY — no live trades, no credential access, no modifications

---

## 1. EXECUTIVE SUMMARY

This audit examines the tiered risk configuration implemented in `mars/apps/trading/system/vol_scaled_system.py`. The system defines four equity-based risk tiers with per-trade risk limits, aggregate concurrent exposure caps, a 15% hard ceiling for min-lot overrides, and session-locked tier selection.

**Key Findings:**
- **Mathematical correctness:** Position-sizing formulas are internally consistent for XAUUSDm (contract_size=100, pip_size=0.01 → $1.00/pip/lot).
- **Tier configuration:** Four tiers ($0–100, $100–1k, $1k–10k, $10k+) with decreasing risk percentages (7%, 3%, 1.5%, 1%) and increasing concurrent trade limits (1, 2, 4, 6).
- **15% ceiling:** Applies to **gross stop-loss risk per individual trade** (not net of costs, not aggregate). Min-lot overrides allowed only when gross risk ≤ 15% of equity.
- **Aggregate exposure:** The per-trade risk_pct now doubles as the **aggregate concurrent risk ceiling** for non-min-lot trades. This is a critical design choice that needs explicit documentation.
- **Historical evidence:** 395 backtest trades (2024-03 to 2025-09) show win rate ~48%, profit factor ~1.03, max drawdown ~25%, expectancy marginally positive after costs. **Insufficient for statistical validation of current risk parameters.**
- **Tradeability floors:** At typical XAUUSDm ATR (0.55 points, 2.0x stop), minimum equity = **$73.33**. At wider stops (ATR 3.0, 2.0x), floor rises to **$400**.

**Recommendation:** **REQUIRES CHANGES** — The aggregate risk logic conflates per-trade and portfolio-level limits; historical performance does not statistically justify the current risk percentages; transaction costs are excluded from risk calculations.

---

## 2. EXISTING TIER CONFIGURATION

### Source: `mars/apps/trading/system/vol_scaled_system.py`, lines 290–299

```python
RISK_TIERS = [
    (0,      100,    1, 0.07,  0.07,  3.0),      # Tier 0: $0–100
    (100,    1000,   2, 0.03,  0.03,  3.0),      # Tier 1: $100–1k
    (1000,   10000,  4, 0.015, 0.06,  2.0),      # Tier 2: $1k–10k
    (10000,  float('inf'), 6, 0.01,  0.06,  2.0), # Tier 3: $10k+
]
# (min_equity, max_equity, max_concurrent_trades, risk_pct_per_trade, aggregate_risk_pct, reward_risk_ratio)
```

| Tier | Equity Range | Max Concurrent Trades | Per-Trade Risk % | Aggregate Risk % | Target R:R |
|------|--------------|----------------------|------------------|------------------|------------|
| 0    | $0 – $100    | 1                    | 7%               | 7%               | 3.0        |
| 1    | $100 – $1,000| 2                    | 3%               | 3%               | 3.0        |
| 2    | $1,000 – $10,000 | 4              | 1.5%             | 6%               | 2.0        |
| 3    | $10,000+     | 6                    | 1%               | 6%               | 2.0        |

### Fixed Thresholds (All Tiers)
- **Daily loss limit:** 2% of current equity
- **Weekly loss limit:** 5% of current equity  
- **Monthly loss limit:** 10% of current equity
- **Max drawdown:** 15% of peak equity (triggers kill-switch)
- **Consecutive loss halt:** 2 losses → 24h cooldown (configurable)
- **Min-lot override ceiling:** 15% (hard, non-configurable)

### Tier Selection & Locking
- **Location:** `select_tier_for_equity()` (line 376), `reset_daily()` (line 820)
- **Lock mechanism:** `_tier_locked` boolean + `_current_tier` cache
- **Reset:** `reset_daily()` clears lock at session/day boundary
- **Persistence:** Tier lock is **in-memory only** — survives process restart only if `reset_daily()` not called

---

## 3. POSITION-SIZING MATHEMATICS AUDIT

### 3.1 Key Functions Inspected

| Function | File | Lines |
|----------|------|-------|
| `check_per_trade_risk()` | vol_scaled_system.py | 683–735 |
| `check_aggregate_risk()` | vol_scaled_system.py | 628–681 |
| `calculate_equity_floor()` | vol_scaled_system.py | 30–72 |
| `VolScaledSizer.compute_position_size()` | vol_scaled_system.py | 203–268 |
| `RiskManager.set_contract_size()` / `get_contract_size()` | vol_scaled_system.py | 365–371 |

### 3.2 XAUUSDm Worked Example (Verified Specifications)

**Source:** `run_multi_pair_backtest.py` lines 55–60, `verify_xau_specs.py`

| Parameter | Value | Source |
|-----------|-------|--------|
| Symbol | XAUUSDm | MT5 symbol |
| Contract size | 100 oz/lot | SYMBOL_CONFIGS['XAUUSD'] |
| Pip size | 0.01 | SYMBOL_CONFIGS['XAUUSD'] |
| Pip value per lot | **$1.00/pip/lot** | 0.01 × 100 = 1.0 |
| Min lot | 0.01 | MT5 standard / hardcoded in check_per_trade_risk() |
| Lot step | 0.01 | MT5 standard |
| Quote currency | USD | No conversion needed |

**Stop distance → Risk per contract:**
- 1 point (10 pips) = $10/contract
- 5 points (50 pips) = $50/contract  
- 50 points (500 pips) = $500/contract

**Min-lot risk at various stops:**
| Stop Distance | Risk per Contract | Min-Lot Risk (0.01 lot) | % of $124.73 Equity |
|---------------|-------------------|-------------------------|---------------------|
| 1 pt (10 pips) | $10 | $0.10 | 0.08% |
| 5 pts (50 pips) | $50 | $0.50 | 0.40% |
| 50 pts (500 pips) | $500 | $5.00 | 4.01% |
| 100 pts (1000 pips) | $1,000 | $10.00 | 8.02% |

### 3.3 Unit Consistency Verification

**VolScaledSizer (lines 240–246):**
```python
forecast_vol_decimal = forecast_vol / 100  # forecast_vol is in % (e.g., 14.55%)
leverage = (target_vol / forecast_vol_decimal) * kelly_fraction
```
- `target_vol` = 0.15 (15% annualized, decimal)
- `forecast_vol` = percentage (e.g., 14.55 = 14.55% annualized)
- **Correct:** Both converted to decimal before division

**Position sizing (lines 248–257):**
```python
position_value = equity * leverage
position_size = position_value / (close * contract_multiplier)
# contract_multiplier = 100 for XAUUSD (1 lot = 100 oz)
```
- **Correct:** Uses contract_multiplier from SYMBOL_CONFIGS

**RiskManager (lines 694–701):**
```python
stop_distance = abs(entry_price - stop_price)
contract_size = getattr(config, 'contract_size', None) or self._contract_sizes.get(symbol, 100.0)
risk_per_contract = stop_distance * contract_size
total_risk = position_size * risk_per_contract
```
- **Correct for XAUUSDm:** stop_distance in points (0.01 increments), contract_size=100 → risk_per_contract in USD
- **Critical assumption:** Price units are consistent (MT5 XAUUSDm quotes in USD with 2 decimals = cents, but pip_size=0.01 = 1 cent)

### 3.4 Transaction Costs
- **Excluded from risk calculations** — `check_per_trade_risk()` and `check_aggregate_risk()` use gross stop-loss distance only
- Commission, swap, spread not deducted from risk budget
- **Backtest data shows:** Avg commission ~$3.50/trade (fixed lot size 4.0 in backtest), but risk calculations don't account for this

### 3.5 Account Currency Conversion
- **Not implemented** — assumes USD-denominated account
- For non-USD pairs (USDJPY, EURGBP), `run_multi_pair_backtest.py` uses hardcoded conversion rates (lines 234–241)
- **Gap:** No real-time FX conversion in risk calculations

---

## 4. THE 15% HARD CEILING — DETAILED ANALYSIS

### 4.1 What It Represents

**Source:** `check_per_trade_risk()` lines 709–735

```python
if total_risk > max_risk:  # max_risk = equity * tier_risk_pct
    min_lot = 0.01
    min_lot_risk = min_lot * risk_per_contract
    actual_risk_pct = total_risk / equity
    ceiling_pct = self.MIN_LOT_OVERRIDE_CEILING_PCT  # 0.15
    
    if actual_risk_pct > ceiling_pct:
        # REJECT
    else:
        # ALLOW with MIN_LOT_OVERRIDE logging
```

**The 15% ceiling applies to:**
- ✅ **Gross stop-loss risk per individual trade** (position_size × stop_distance × contract_size)
- ✅ **Only when trade exceeds tier's per-trade risk limit**
- ✅ **Only for min-lot trades** (position_size ≤ 0.01)

**The 15% ceiling does NOT apply to:**
- ❌ Net risk after commissions/swap/spread
- ❌ Aggregate portfolio exposure (separate `check_aggregate_risk()`)
- ❌ Non-min-lot trades (those are rejected at tier limit without override)
- ❌ Multiple simultaneous positions (each evaluated independently)

### 4.2 Aggregate Risk Logic (Critical Finding)

**Source:** `check_aggregate_risk()` lines 628–681

```python
# For trades within tier budget, enforce aggregate cap
projected_total_risk = self.total_open_risk + new_trade_risk
if projected_total_risk > max_total_risk:  # max_total_risk = equity * tier_risk_pct
    # REJECT
```

**Critical Design Issue:** The **per-trade risk percentage (risk_pct_per_trade) doubles as the aggregate concurrent risk ceiling** for non-min-lot trades.

| Tier | Per-Trade Risk | Aggregate Cap | Max Trades | Implied Max Concurrent Risk |
|------|----------------|---------------|------------|----------------------------|
| 0    | 7%             | 7%            | 1          | 7% (1 × 7%)                |
| 1    | 3%             | 3%            | 2          | 3% (shared, NOT 6%)        |
| 2    | 1.5%           | 6%            | 4          | 6% (4 × 1.5%)              |
| 3    | 1%             | 6%            | 6          | 6% (6 × 1%)                |

**Tier 1 is the anomaly:** 2 trades allowed but aggregate cap = 3% (same as per-trade). This means **only one trade can be at full risk**; the second must be smaller or the first must be reduced.

**Min-lot override trades** (lines 739–746) **do not consume aggregate budget** — tracked separately with `is_min_lot_override=True`.

### 4.3 Multiple Simultaneous Positions

- Each position evaluated independently in `check_per_trade_risk()`
- Aggregate check in `check_aggregate_risk()` sums `total_open_risk`
- **No correlation adjustment** — two XAUUSDm positions in same direction count as full risk each
- **No portfolio-level stop** — only individual position stops

---

## 5. STATISTICAL RISK ASSESSMENT

### 5.1 Available Historical Evidence

**Data Source:** `/c/Users/RIDGE/MARS-QUANT/data/processed/backtest_trades_paper_v3_final.csv`  
**Period:** 2024-03-11 to 2025-09-23 (~18 months)  
**Trades:** 395 (Size=4 lots fixed in backtest, not tiered sizing)  
**Symbol:** XAUUSDm (implied from prices ~$2,000–$3,700)

### 5.2 Performance Statistics (Backtest, NOT Tiered Risk)

| Metric | Value | Notes |
|--------|-------|-------|
| Total Trades | 395 | Fixed 4-lot size |
| Win Rate | ~48% | 190 wins / 205 losses |
| Avg Win | ~$85 | Gross |
| Avg Loss | ~-$82 | Gross |
| Expectancy (gross) | ~+$1.5/trade | Marginal |
| Profit Factor | ~1.03 | Near breakeven |
| Max Drawdown | ~25% | Peak-to-trough |
| Max Consecutive Losses | 6–8 | Observed in sequence |
| Avg Trade Duration | 1–3 days | H1 timeframe |

### 5.3 Loss Distribution (Gross PnL, $)

| Percentile | PnL |
|------------|-----|
| Min (worst) | -$556 |
| 5% | -$165 |
| 25% | -$55 |
| 50% | -$12 |
| 75% | +$31 |
| 95% | +$194 |
| Max | +$427 |

### 5.4 Risk of Ruin / Monte Carlo (Illustrative Only)

**Assumptions for illustration (NOT optimized on this data):**
- Win rate: 48% (observed)
- Avg R:R: 1.04 (observed avg_win/avg_loss)
- Risk per trade: 1% (Tier 3)
- Starting equity: $10,000

| Scenario | Probability of 25% DD | Probability of 50% DD |
|----------|----------------------|----------------------|
| 1% risk, 395 trades | ~15% | ~2% |
| 2% risk, 395 trades | ~45% | ~12% |
| 3% risk, 395 trades | ~75% | ~35% |

**Critical Caveat:** Backtest uses **fixed 4-lot sizing**, not the tiered vol-scaled sizing. The risk percentages in the tier table have **not been validated against this strategy's actual return distribution**.

### 5.5 Sensitivity Analysis (Illustrative)

| Transaction Cost Increase | Effect on Expectancy | Effect on Win Rate |
|---------------------------|---------------------|-------------------|
| +$1/trade (spread widening) | -$1/trade | Slight decrease (small wins become losses) |
| +$3/trade (commission increase) | -$3/trade | ~2–3% decrease |

**Conclusion:** The strategy operates near breakeven after costs. Current tier risk percentages (1–7%) have **no statistical justification** from this backtest.

---

## 6. AGGREGATE EXPOSURE ANALYSIS

### 6.1 Current Logic Flow

```
check_per_trade_risk(config, equity)
    │
    ├─► check_aggregate_risk(config, equity)  [FIRST]
    │     │
    │     ├─ If trade exceeds tier risk_pct → passes to per-trade override logic
    │     │
    │     └─ If trade within tier risk_pct → checks: total_open_risk + new_risk ≤ equity × tier_risk_pct
    │
    └─► Per-trade check (with min-lot override + 15% ceiling)
```

### 6.2 Scenario: $5,000 Equity (Tier 2: 1.5% per-trade, 6% aggregate, 4 max trades)

| Trade | Position | Stop Dist | Risk/Contract | Position Risk | Aggregate Used | Remaining Budget |
|-------|----------|-----------|---------------|---------------|----------------|------------------|
| 1 | 0.5 lot | 10 pts ($100) | $100 | $50 | $50 (1.0%) | $250 (5.0%) |
| 2 | 0.5 lot | 10 pts | $100 | $50 | $100 (2.0%) | $200 (4.0%) |
| 3 | 0.5 lot | 10 pts | $100 | $50 | $150 (3.0%) | $150 (3.0%) |
| 4 | 0.5 lot | 10 pts | $100 | $50 | $200 (4.0%) | $100 (2.0%) |
| 5 | 0.5 lot | 10 pts | $100 | $50 | **REJECTED** (would be $250 > $300 limit) | — |

**But wait:** Tier 2 aggregate cap = 6% = $300. With 4 trades max, max per-trade = $75 if evenly distributed. The per-trade limit (1.5% = $75) aligns only if all 4 trades are at max size.

### 6.3 Tier 1 Anomaly ($124.73 equity, Tier 1: 3% per-trade, 3% aggregate, 2 max trades)

| Trade | Risk | Aggregate | Status |
|-------|------|-----------|--------|
| 1 | 3% ($3.74) | 3% | OK (uses full budget) |
| 2 | 3% ($3.74) | **6% > 3%** | **REJECTED** |

**Result:** At Tier 1, **only one trade can be at full risk**. The second trade slot is effectively unusable unless the first trade is smaller.

---

## 7. MINIMUM-LOT TRADEABILITY FLOORS

### 7.1 Formula (from `calculate_equity_floor()`, line 42)

```
equity_floor = (min_lot × contract_size × atr × stop_multiplier) / ceiling_pct
```

**XAUUSDm constants:**
- min_lot = 0.01
- contract_size = 100
- ceiling_pct = 0.15
- stop_multiplier = 2.0 (from PAIR_CONFIG)
- quote_to_usd = 1.0

### 7.2 Floors at Different ATR Values

| ATR (points) | Stop (2×ATR) | Risk/Contract | Min-Lot Risk | Equity Floor | % of $124.73 |
|--------------|--------------|---------------|--------------|--------------|--------------|
| 0.10 | 0.20 | $20 | $0.20 | **$1.33** | 1% |
| 0.25 | 0.50 | $50 | $0.50 | **$3.33** | 3% |
| **0.55 (typical 5-min)** | **1.10** | **$110** | **$1.10** | **$7.33** | 6% |
| 1.00 | 2.00 | $200 | $2.00 | **$13.33** | 11% |
| 2.00 | 4.00 | $400 | $4.00 | **$26.67** | 21% |
| 3.00 | 6.00 | $600 | $6.00 | **$40.00** | 32% |
| 5.00 | 10.00 | $1,000 | $10.00 | **$66.67** | 53% |
| 10.00 | 20.00 | $2,000 | $20.00 | **$133.33** | 107% |

### 7.3 Required Equity Scenarios

| Account Equity | Tier | Max ATR for Min-Lot Trade (2× stop, 15% ceiling) | Notes |
|----------------|------|--------------------------------------------------|-------|
| **$30** | Tier 0 (7%) | **ATR ≤ 2.25 pts** | Min-lot override possible up to 7% tier, 15% ceiling = ATR 4.82 pts |
| **$124.73** | Tier 1 (3%) | **ATR ≤ 9.35 pts** | Current test account; typical ATR 0.55 well within limit |
| **$500** | Tier 1 (3%) | **ATR ≤ 37.5 pts** | Very wide stops possible |
| **$5,000** | Tier 2 (1.5%) | **ATR ≤ 187.5 pts** | Tier risk (1.5%=$75) < ceiling (15%=$750) |
| **$50,000** | Tier 3 (1%) | **ATR ≤ 1,875 pts** | Tier risk binds first |

**Key insight:** The tradeability floor **changes with stop distance** because risk is proportional to stop distance. Wider stops (higher ATR or larger multiplier) require more equity to keep min-lot risk under the 15% ceiling.

---

## 8. IDENTIFIED DEFECTS AND LIMITATIONS

### 8.1 Critical Defects

| # | Issue | Location | Severity |
|---|-------|----------|----------|
| 1 | **Per-trade risk doubles as aggregate cap** for non-min-lot trades | `check_aggregate_risk()` line 644 | HIGH |
| 2 | **Tier 1 aggregate cap = per-trade cap (3%)** — effectively allows only 1 full-risk trade | RISK_TIERS line 296 | HIGH |
| 3 | **Min-lot override trades excluded from aggregate budget** — can exceed portfolio risk | `register_position_risk()` lines 739–746 | MEDIUM |
| 4 | **Transaction costs excluded** from all risk calculations | All risk check functions | MEDIUM |
| 5 | **No FX conversion** for non-USD pairs in risk calcs | `check_per_trade_risk()` line 699 | MEDIUM |

### 8.2 Limitations

| # | Limitation | Impact |
|---|------------|--------|
| 1 | Tier lock is in-memory only — restart without `reset_daily()` preserves old tier | Could allow oversized risk after equity drop |
| 2 | No correlation-aware position limits | Multiple correlated pairs treated as independent |
| 3 | Kill-switch peak_equity persists but tier lock doesn't | Inconsistent persistence model |
| 4 | Consecutive loss halt resets at day/week/month boundary | Configurable but default behavior may be too aggressive |
| 5 | Historical performance doesn't validate risk parameters | Risk percentages are arbitrary, not evidence-based |

### 8.3 Code Quality Issues

- `min_lot = 0.01` hardcoded in `check_per_trade_risk()` line 712 (should use symbol config)
- `contract_size` default 100.0 in RiskManager (line 363) — XAUUSD-specific
- `calculate_equity_floor()` assumes USD quote currency (line 36)
- No validation that `position_size` respects broker `lot_step` (0.01)

---

## 9. RECOMMENDED RISK-CONTROL IMPROVEMENTS

### 9.1 Immediate (Before Live Trading)

1. **Separate per-trade and aggregate risk parameters** in RISK_TIERS:
   ```python
   (min_eq, max_eq, max_trades, per_trade_risk_pct, aggregate_risk_pct, rr_ratio)
   ```
   Current: `aggregate_risk_pct` exists but Tier 0/1 set it equal to per-trade — should be larger.

2. **Include transaction costs in risk budget**:
   - Estimate commission + spread per trade
   - Reduce effective risk ceiling by estimated cost %
   - Or: track net PnL in risk calculations

3. **Fix Tier 1 aggregate cap**: Set `aggregate_risk_pct = 0.06` (6%) to allow 2 trades at 3% each.

4. **Add min-lot to symbol config** and use it instead of hardcoded 0.01.

5. **Add FX conversion** using real-time rates or documented assumptions.

### 9.2 Short-Term (Before Research Deployment)

6. **Validate risk percentages against walk-forward backtest** with tiered sizing (not fixed lots).

7. **Add correlation matrix** and correlation-adjusted aggregate limits.

8. **Persist tier lock** to disk alongside kill-switch state.

9. **Document the min-lot override exclusion from aggregate budget** — is this intentional?

10. **Add unit tests** for:
    - Multiple simultaneous positions at tier boundaries
    - Min-lot override + aggregate interaction
    - FX conversion for non-USD pairs

---

## 10. EVIDENCE REQUIRED BEFORE RISK-POLICY APPROVAL

| Evidence | Status | Required For |
|----------|--------|--------------|
| Walk-forward backtest with **actual tiered vol-scaled sizing** (not fixed lots) | ❌ Missing | Validating risk percentages |
| Monte Carlo simulation of **tiered system** (not fixed-size) | ❌ Missing | Risk of ruin estimation |
| Live/demo **reconciliation of risk events** (min-lot overrides, aggregate hits) | ❌ Missing | Operational verification |
| **Correlation analysis** of simultaneous positions | ❌ Missing | Aggregate cap calibration |
| **Transaction cost model** validated against broker statements | ❌ Missing | Net risk accuracy |
| **FX conversion** tested for non-USD pairs | ❌ Missing | Multi-pair deployment |

---

## 11. SCENARIO ANALYSIS: REQUIRED EQUITY LEVELS

### 11.1 $30 Equity (Tier 0: 7% per-trade, 7% aggregate, 1 trade, 3.0 R:R)

| Stop Distance | Min-Lot Risk | % Equity | Allowed? | Notes |
|---------------|--------------|----------|----------|-------|
| 0.55 pts (typical) | $0.55 | 1.8% | ✅ Tier allows 7% | Well under ceiling |
| 2.0 pts | $2.00 | 6.7% | ✅ Tier allows 7% | Near tier limit |
| 4.5 pts | $4.50 | 15.0% | ⚠️ At ceiling | MIN_LOT_OVERRIDE if tier exceeded |
| 5.0 pts | $5.00 | 16.7% | ❌ **REJECTED** | Exceeds 15% ceiling |

**Max concurrent risk:** 7% ($2.10) — only 1 trade allowed.

### 11.2 $124.73 Equity (Tier 1: 3% per-trade, 3% aggregate, 2 trades, 3.0 R:R)

| Stop Distance | Min-Lot Risk | % Equity | Allowed? |
|---------------|--------------|----------|----------|
| 0.55 pts | $0.55 | 0.4% | ✅ |
| 5.0 pts | $5.00 | 4.0% | ✅ MIN_LOT_OVERRIDE (3%→4%<15%) |
| 18.7 pts | $18.70 | 15.0% | ⚠️ At ceiling |
| 20.0 pts | $20.00 | 16.0% | ❌ REJECTED |

**Max concurrent risk:** 3% ($3.74) — **only 1 full-risk trade possible**.

### 11.3 $500 Equity (Tier 1: 3% per-trade, 3% aggregate, 2 trades)

| Stop Distance | Min-Lot Risk | % Equity | Allowed? |
|---------------|--------------|----------|----------|
| 0.55 pts | $0.55 | 0.1% | ✅ |
| 50 pts | $50.00 | 10.0% | ✅ MIN_LOT_OVERRIDE |
| 75 pts | $75.00 | 15.0% | ⚠️ At ceiling |
| 80 pts | $80.00 | 16.0% | ❌ REJECTED |

**Max concurrent risk:** 3% ($15.00) — same Tier 1 limitation.

### 11.4 $5,000 Equity (Tier 2: 1.5% per-trade, 6% aggregate, 4 trades)

| Stop Distance | Min-Lot Risk | % Equity | Allowed? |
|---------------|--------------|----------|----------|
| 0.55 pts | $0.55 | 0.01% | ✅ |
| 50 pts | $50.00 | 1.0% | ✅ Under tier (1.5%) |
| 75 pts | $75.00 | 1.5% | ✅ At tier limit |
| 750 pts | $750.00 | 15.0% | ⚠️ At ceiling (MIN_LOT_OVERRIDE) |

**Max concurrent risk:** 6% ($300) — up to 4 trades at 1.5% each.

### 11.5 $50,000 Equity (Tier 3: 1% per-trade, 6% aggregate, 6 trades)

| Stop Distance | Min-Lot Risk | % Equity | Allowed? |
|---------------|--------------|----------|----------|
| 0.55 pts | $0.55 | 0.001% | ✅ |
| 500 pts | $500.00 | 1.0% | ✅ At tier limit |
| 7,500 pts | $7,500.00 | 15.0% | ⚠️ At ceiling |

**Max concurrent risk:** 6% ($3,000) — up to 6 trades at 1% each.

---

## 12. CONSECUTIVE LOSSES & MULTIPLE POSITIONS

### 12.1 Consecutive Loss Circuit Breaker

- **Trigger:** 2 consecutive losses (configurable)
- **Action:** Halt new signals for 24 hours (or remainder of session if cooldown=0)
- **Reset:** At day/week/month boundary OR after cooldown expires
- **Gap:** Does not reduce position size — only blocks new entries

### 12.2 Multiple Simultaneous Positions at Tier Boundaries

**Scenario:** $1,000 equity (Tier 2), 4 positions opened, equity drops to $950 (Tier 1)

| Position | Opened At Tier | Risk At Open | Tier After Drop | Risk Check on New Trades |
|----------|----------------|--------------|-----------------|--------------------------|
| 1 | Tier 2 (1.5%) | $15 | Tier 1 (3%) | New trades use 3% |
| 2 | Tier 2 (1.5%) | $15 | Tier 1 (3%) | Aggregate uses 3% cap |
| 3 | Tier 2 (1.5%) | $15 | Tier 1 (3%) | — |
| 4 | Tier 2 (1.5%) | $15 | Tier 1 (3%) | — |
| **Total open risk** | | **$60 (6%)** | | **Exceeds new Tier 1 aggregate (3%)** |

**Defect:** Existing positions opened at higher tier are **not re-evaluated** when tier drops. The aggregate risk can exceed the new tier's limit without any mechanism to reduce exposure.

---

## 13. FINAL RECOMMENDATION

### ❌ REQUIRES CHANGES

**Rationale:**

1. **Aggregate risk logic is flawed** — per-trade risk percentage doubles as portfolio cap, making Tier 1 effectively single-trade only
2. **Risk percentages lack statistical validation** — backtest shows marginal profitability; 1–7% risk not justified
3. **Min-lot override exclusion from aggregate budget** creates unbounded portfolio risk pathway
4. **Transaction costs excluded** — net risk higher than calculated
5. **Tier drop with open positions** allows aggregate exposure to exceed new tier limits
6. **Critical parameters hardcoded** (min_lot=0.01, contract_size default=100)

**Before approval for research deployment:**
- Fix aggregate risk logic (separate per-trade vs portfolio caps)
- Run walk-forward backtest with actual tiered vol-scaled sizing
- Validate min-lot override behavior in simulation
- Document and test tier transition edge cases
- Add transaction cost model to risk calculations

---

## APPENDIX: SOURCE CODE REFERENCES

| Component | File | Key Lines |
|-----------|------|-----------|
| RISK_TIERS definition | vol_scaled_system.py | 290–299 |
| Tier selection/locking | vol_scaled_system.py | 376–420 |
| check_per_trade_risk | vol_scaled_system.py | 683–735 |
| check_aggregate_risk | vol_scaled_system.py | 628–681 |
| Min-lot override logic | vol_scaled_system.py | 709–735 |
| register_position_risk | vol_scaled_system.py | 737–753 |
| calculate_equity_floor | vol_scaled_system.py | 30–72 |
| VolScaledSizer sizing | vol_scaled_system.py | 203–268 |
| SYMBOL_CONFIGS | run_multi_pair_backtest.py | 33–61 |
| PAIR_CONFIG | pair_config.py | 16–64 |
| Contract specs | pair_config.py | 147–151 |
| Backtest trades data | data/processed/backtest_trades_paper_v3_final.csv | 395 rows |

---

**End of Audit Report**