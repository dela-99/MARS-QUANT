# Assignment 21: Phase G — XAU-VOL-REGIME-SESSION-005 Implementation and In-Sample Research

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Candidate 005 (XAU-VOL-REGIME-SESSION-005) per frozen Assignment 20 specification, run frozen in-sample research with mandatory three-way comparison (unconditional baseline vs regime-filtered vs null permutation), execute FC-005-2 interaction regression, and evaluate all 8 pre-registered falsification criteria.

**Architecture:** Extend existing `xau_session_momentum.py` / `session_momentum_backtest.py` / `session_momentum_research.py` architecture. New strategy module adds regime filters on top of unconditional session momentum base. Research pipeline adds comparison framework and statistical tests.

**Tech Stack:** Python 3.11+, pandas, numpy, scipy (regression), statsmodels (HAC standard errors), existing M.A.R.S. libraries.

## Global Constraints

- **Frozen Specification:** Use Assignment 20 deliverables as authoritative source — no parameter changes
- **IS Period:** 2021-10-01 to 2024-12-31 (chronological, no overlap with OOS)
- **Data:** M5 v1.2.0, H1 v1.2.0 (resampled from M5)
- **Cost Model:** Per-bar observed spread, 1× RT, $0 commission, 0 slippage base, swap $0 intraday
- **Account:** $30 equity, 1% risk ($0.30), min lot 0.01, SL cap 200 pts, min-volume breach → REJECT
- **No OOS/MC:** Only IS research + 10,000-rep null permutation (authorized)
- **Three-Way Comparison:** Mandatory — unconditional baseline, regime-filtered, null permutation
- **FC-005-2:** Interaction regression with HAC standard errors (serial dependence)
- **Reproducibility:** Seed 20261125, config hash, data version pinned

---

### Task 1: Create Candidate 005 Strategy Module

**Files:**
- Create: `mars/libs/strategies/xau_vol_regime_session_005.py`

**Interfaces:**
- Consumes: `mars.libs.strategies.xau_session_momentum` (base functions), `mars.libs.data.loaders`, `mars.libs.risk.contract_aware`
- Produces: `SignalFrame` compatible with `SessionMomentumBacktester`

**Requirements from Frozen Spec (Assignment 20 Research Brief §1.4):**
- **Signal:** Asian session return > 0 (close > open) — same as unconditional baseline
- **Volatility Regime:** H1 realized vol (20-bar lookback) ≤ 40th percentile (trailing, expanding window from burn-in)
- **Spread Regime:** Asian session avg spread ≤ 40th percentile (IS distribution, frozen at IS end)
- **FOMC Filter:** Exclude FOMC days (FRED calendar)
- **Entry:** 08:00 UTC (first M5 bar Europe open)
- **Exit:** 14:30 UTC (time stop) or stop-loss
- **Stop-Loss:** Session low (Asia or Europe) OR 200 pts, whichever tighter
- **Position Sizing:** Fixed fractional 1%, min 0.01 lot
- **Starting Equity:** $30.00 (for feasibility) but IS research uses $10,000 normalized

**Key Implementation Details:**
- Regime filters must be computed **without look-ahead** (trailing/expanding windows only)
- H1 volatility: 20-bar trailing realized vol on H1 Asian session bars (00:00-08:00 UTC)
- Spread regime: Use IS-period (2021-10-01 to 2024-12-31) 40th percentile as frozen threshold
- FOMC: Fetch from FRED `FOMCMEETINGS` series or use pre-downloaded calendar
- All regime inputs must be available at decision time (08:00 UTC)

- [ ] Step 1.1: Create `XAUVolRegimeSession005Params` dataclass (frozen parameters from spec)
- [ ] Step 1.2: Implement `compute_h1_realized_vol` (20-bar trailing on H1 Asian session bars)
- [ ] Step 1.3: Implement `compute_asian_session_avg_spread` (M5 00:00-08:00 mean spread)
- [ ] Step 1.4: Implement `load_fomc_calendar` (FRED or cached CSV)
- [ ] Step 1.5: Implement `compute_vol_regime` (trailing 40th percentile)
- [ ] Step 1.6: Implement `compute_spread_regime` (frozen IS 40th percentile)
- [ ] Step 1.7: Implement `generate_session_signals_with_regime_filters` (extends base)
- [ ] Step 1.8: Implement `XAUVolRegimeSession005Strategy` class with `compute_signals` method
- [ ] Step 1.9: Add convenience function `compute_signals` matching existing interface
- [ ] Step 1.10: Export all public symbols

---

### Task 2: Extend Backtester for Regime-Filtered Strategy

**Files:**
- Create: `mars/apps/backtester/xau_vol_regime_session_005_backtest.py`

**Interfaces:**
- Consumes: New strategy module, existing `ContractAwareFixedFractionalRisk`, `InstrumentSpec`
- Produces: `BacktestResult` compatible with research pipeline

**Requirements:**
- Reuse `SessionMomentumBacktester` logic entirely (cost model, execution, risk)
- Only difference: strategy class and signal generation
- Ensure regime filter metadata tracked in rejected signals

- [ ] Step 2.1: Create backtester class extending or wrapping `SessionMomentumBacktester`
- [ ] Step 2.2: Ensure `CostModel`, `ExecutionModel`, `Trade`, `BacktestResult` reused
- [ ] Step 2.3: Verify risk engine uses $30 equity for feasibility, $10k for IS research
- [ ] Step 2.4: Add regime filter metadata to rejected signals logging

---

### Task 3: Create Research Pipeline for Candidate 005

**Files:**
- Create: `mars/apps/research_lab/xau_vol_regime_session_005_research.py`

**Interfaces:**
- Consumes: New strategy/backtester, data loaders, evaluation metrics
- Produces: IS research artifacts (JSON, Markdown, trade ledgers)

**Three-Way Comparison Implementation:**

**Model A — Unconditional Baseline:**
- Reproduce XAU-SESSION-MOM-001 exactly per Assignment 17 config
- Use `SessionMomentumParams` with no regime filters
- Run on IS period (2021-10-01 to 2024-12-31)

**Model B — Regime-Filtered Candidate 005:**
- Use new `XAUVolRegimeSession005Params` with all filters active
- Run on same IS period

**Model C — Null Permutation (10,000 reps):**
- Take regime-filtered trade set (Model B trades)
- Permute regime labels (favorable/unfavorable) across sessions 10,000 times
- For each permutation, recompute net expectancy using same trade P&L values
- p-value = proportion of permutations where null expectancy ≥ observed expectancy
- Seed: 20261126 (per Assignment 20)

**Primary Interaction Test (FC-005-2):**
```
PnL_i = β_0 + β_1 × Signal_i + β_2 × Regime_i + β_3 × (Signal_i × Regime_i) + ε_i
```
- Signal_i = 1 if Asian return > 0, 0 otherwise
- Regime_i = 1 if all regime filters favorable, 0 otherwise
- Interaction = Signal_i × Regime_i (regime-filtered trades)
- **H₀: β_3 ≤ 0** vs **H₁: β_3 > 0** (one-sided)
- Use **HAC (Newey-West) standard errors** for serial dependence
- Pass: β_3 > 0 AND p < 0.05 (one-sided)

**Sensitivity Analyses (Pre-registered):**
1. Spread multiplier: 1.0×, 1.5×, 2.0×
2. Vol percentile threshold: 30th, 40th, 50th
3. Spread percentile threshold: 30th, 40th, 50th
4. FOMC filter: ON, OFF
5. SL distance: 150, 200, 250, 300 pts
6. DST-adjusted sessions: ±1 hour shift

**Falsification Criteria (All 8 Must Pass):**
1. FC-005-1: IS Conditional Expectancy > $0.00/trade
2. FC-005-2: Regime Interaction β_3 > 0, p < 0.05 (one-sided)
3. FC-005-3: OOS Expectancy > $0.00/trade (not run in Assignment 21 — documented)
4. FC-005-4: Cost Sensitivity PASS at 1.0× AND 1.5×
5. MIN_TRADES_IS: IS trades ≥ 50 (after regime filter)
6. MIN_TRADES_OOS: OOS trades ≥ 20 (not run — documented)
7. MAX_DD_IS: IS Max DD < 30% (at $30 equity)
8. MIN_EXPECTANCY_IS: IS Net Expectancy > $0.05/trade

- [ ] Step 3.1: Create `Candidate005ResearchConfig` dataclass with frozen IS period, data paths, seeds
- [ ] Step 3.2: Implement data loading with exact IS period filtering (2021-10-01 to 2024-12-31)
- [ ] Step 3.3: Implement Model A (unconditional baseline) runner
- [ ] Step 3.4: Implement Model B (regime-filtered) runner
- [ ] Step 3.5: Implement Model C (null permutation, 10,000 reps)
- [ ] Step 3.6: Implement FC-005-2 interaction regression with HAC standard errors
- [ ] Step 3.7: Implement sensitivity analysis runner (6 dimensions)
- [ ] Step 3.8: Implement all 8 falsification criteria evaluation
- [ ] Step 3.9: Implement comprehensive metrics computation (matching Assignment 17)
- [ ] Step 3.10: Implement results serialization (JSON + Markdown + trade ledgers CSV)
- [ ] Step 3.11: Implement chart generation (equity curve, drawdown, regime performance, cost sensitivity, baseline vs filtered comparison)

---

### Task 4: Write Tests

**Files:**
- Create: `tests/test_xau_vol_regime_session_005.py`

**Test Coverage:**
- Entry conditions (signal + all regime filters)
- Exit conditions (time stop, stop-loss)
- Regime classification (vol, spread, FOMC)
- Volatility lookback (20-bar trailing, expanding window)
- Session boundaries (fixed UTC)
- Timezone conversion (UTC)
- Event filtering (FOMC calendar)
- Spread filtering (IS 40th percentile frozen)
- H1-to-M5 alignment (no future data leakage)
- Missing data handling (feed outages, zero-spread bars)
- Spread conversion (points → price → USD)
- Commission/slippage handling
- Position sizing (fixed fractional 1%, min lot 0.01)
- Volume step (0.01)
- Stop-loss cap (200 pts)
- Maximum risk enforcement ($0.30 budget)
- Min-volume breach rejection (SL > 300 pts)
- Unconditional baseline consistency (reproduce Assignment 17 results)

- [ ] Step 4.1: Write unit tests for regime computation functions
- [ ] Step 4.2: Write integration tests for signal generation
- [ ] Step 4.3: Write backtester tests (rejected signals, sizing, costs)
- [ ] Step 4.4: Write research pipeline tests (splits, metrics, falsification)
- [ ] Step 4.5: Run all tests and verify pass

---

### Task 5: Execute IS Research

**Execution Order:**
1. Run tests (must pass)
2. Run Model A (unconditional baseline) on IS period
3. Run Model B (regime-filtered) on IS period
4. Run Model C (null permutation, 10,000 reps)
5. Run FC-005-2 interaction regression
6. Run sensitivity analyses
7. Evaluate all 8 falsification criteria
8. Generate all deliverables

**Output Directory:** `reports/assignment21/`

**Deliverables (9 total):**
1. `ASSIGNMENT_21_IMPLEMENTATION_REPORT.md`
2. `ASSIGNMENT_21_TEST_REPORT.md`
3. `CANDIDATE_005_IS_RESEARCH_REPORT.md`
4. `BASELINE_VS_REGIME_COMPARISON.md`
5. `FC005_2_INTERACTION_REGRESSION.md`
6. `NULL_PERMUTATION_ANALYSIS.md`
7. `COST_AND_RISK_ANALYSIS.md`
8. `FALSIFICATION_CRITERIA_RESULTS.md`
9. `assignment21_results.json`

- [ ] Step 5.1: Create output directory
- [ ] Step 5.2: Run full IS research pipeline
- [ ] Step 5.3: Generate all 9 deliverables
- [ ] Step 5.4: Verify JSON validity
- [ ] Step 5.5: Record git commit and working tree status

---

## Verification Checklist

After all tasks complete:
- [ ] All 9 deliverables exist in `reports/assignment21/`
- [ ] Strategy module implements frozen spec exactly (no parameter changes)
- [ ] Three-way comparison executed (A: unconditional, B: regime-filtered, C: null)
- [ ] Null permutation: 10,000 reps, seed 20261126, p-value computed correctly
- [ ] FC-005-2: Interaction regression with HAC standard errors, one-sided p-value
- [ ] All 8 falsification criteria evaluated with PASS/FAIL/INDETERMINATE
- [ ] Cost sensitivity: 1.0×, 1.5×, 2.0× reported for both models
- [ ] $30 feasibility: min lot, SL cap, risk budget, rejected trades documented
- [ ] Charts generated from actual results (not illustrative)
- [ ] All seeds recorded, config hash recorded, data version pinned
- [ ] No OOS data accessed, no Monte Carlo run (except authorized null permutation)
- [ ] Original rejected strategy artifacts preserved
- [ ] Git commit recorded in deliverables

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Insufficient IS trades after regime filter (< 50) | MEDIUM | HIGH (FC-005-1 FAIL) | Document honestly; candidate fails if < 50 |
| FOMC calendar unavailable | LOW | MEDIUM | Use cached FOMC dates; sensitivity with FOMC OFF |
| H1/M5 alignment issues | LOW | HIGH | H1 v1.2.0 resampled from M5 v1.2.0 — verified |
| Serial dependence invalidates OLS standard errors | HIGH | HIGH | Use HAC (Newey-West) for FC-005-2 |
| Null permutation exchangeability assumption violated | MEDIUM | MEDIUM | Document limitations; not sole criterion |
| Regime filter overfit to IS | MEDIUM | HIGH | Pre-specified thresholds; OOS in next phase |

---

## Execution Handoff

After saving the plan, offer execution choice:

**"Plan complete and saved to `docs/superpowers/plans/2026-11-25-assignment21-phase-g-implementation.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?"**

**If Subagent-Driven chosen:**
- **REQUIRED SUB-SKILL:** Use superpowers:subagent-driven-development
- Fresh subagent per task + two-stage review

**If Inline Execution chosen:**
- **REQUIRED SUB-SKILL:** Use superpowers:executing-plans
- Batch execution with checkpoints for review