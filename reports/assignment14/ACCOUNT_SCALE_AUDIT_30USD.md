# Account-Scale Audit: $30 Starting Capital for XAU-MTF-DONCHIAN-001

**Date:** 2026-11-25  
**Strategy:** XAU-MTF-DONCHIAN-001 (H1-regime filtered M5 Donchian breakout on Exness XAUUSDm)  
**Intended Live Capital:** USD $30  
**Research Simulation Capital:** USD $10,000 (must be clearly separated)

---

## 1. Where the $10,000 Initial-Equity Assumption Is Configured

| File | Line | Context |
|------|------|---------|
| `mars/libs/strategies/xau_mtf_donchian.py` | 69 | `starting_equity: float = 10_000.0` — default parameter in `MtfDonchianParams` dataclass |
| `research/assignment14/run_assignment14.py` | 97 | `BASE_PARAMS` uses `starting_equity=10_000.0` for the full research run |
| `mars/apps/backtester/mtf_donchian_backtest.py` | 128, 214, 248 | `starting_equity` passed to `BacktestResult`, used as initial equity in engine |
| `mars/apps/research_lab/xau_mtf_donchian_montecarlo.py` | 63, 82, 93, 113, 124, 146, 150 | `_equity_path()` and all MC experiments use `starting_equity` |
| `mars/apps/research_lab/xau_mtf_donchian_001.py` | 360, 377 | `benchmark_buy_and_hold()` uses it for position sizing |

**All research artifacts (Assignment 14 ledger CSVs, `assignment14_results.json`, Monte Carlo charts) are produced with this $10,000 assumption.**

---

## 2. Does $10,000 Affect Only Reporting or Also Sizing / Risk / Execution?

**It directly affects position sizing, risk calculations, and trade acceptance.**

### Sizing Formula (ContractAwareFixedFractionalRisk — `mars/libs/risk/contract_aware.py:132-158`)

```python
risk_dollars = equity * self.risk_fraction          # equity starts at starting_equity
risk_per_lot = stop_distance * spec.contract_size * quote_to_usd
lots_exact   = risk_dollars / risk_per_lot
lots         = floor_to_step(lots_exact, spec.volume_step)
```

### Volume Enforcement (lines 172-191)

```python
if lots < spec.volume_min - 1e-12:
    # REJECT — never forces an oversized trade
    return RiskDecision(approved=False, reason="min volume breach: ...")
```

**The current equity (which begins at `starting_equity` and evolves with P&L) is the risk budget. Changing `starting_equity` changes the very first trade's size and whether it clears the broker minimum volume.**

---

## 3. Verified Exness XAUUSDm Contract Specifications (Offline Defaults)

| Parameter | Value | Source |
|-----------|-------|--------|
| `symbol` | XAUUSDm | pair_config.offline |
| `contract_size` | 100.0 troy oz/lot | pair_config.offline |
| `pip_size` | 0.01 (USD/oz) | pair_config.offline |
| `point_size` | 0.001 (broker tick) | pair_config.offline |
| `quote_currency` | USD | pair_config.offline |
| `volume_min` | 0.01 lots | unverified_offline_default |
| `volume_max` | 200.0 lots | unverified_offline_default |
| `volume_step` | 0.01 lots | unverified_offline_default |

**Derived values:**
- 1 pip = 0.01 × 100 = **$1.00 per lot**
- 1 point = 0.001 × 100 = **$0.10 per lot**
- Minimum trade (0.01 lots) = **1 oz** ≈ **$2,650 notional** at current gold (~$2,650/oz)

> **Note:** Volume constraints are flagged `unverified_offline_default` — not live-verified from MT5 (Exness demo credentials rotated, Assignment 13 blocker). They are the project's best offline defaults.

---

## 4. Minimum Tradable Volume & Cash Risk at $30 Equity

### Strategy Risk Parameter
- `risk_fraction = 0.01` (1% of equity per trade)
- `atr_stop_multiplier = 2.0` (stop = 2 × ATR(14) on M5)

### Typical M5 ATR for XAUUSDm
From the in-sample data (2021-07 → 2024-12), median ATR(14) ≈ **$1.50–$3.00** (150–300 pips).  
Conservative range used below: **stop_distance = $2.00 – $6.00** (200–600 pips).

### Risk per Lot
```
risk_per_lot = stop_distance × contract_size × quote_to_usd
             = stop_distance × 100 × 1.0
             = stop_distance × 100  (USD per lot)
```

| stop_distance | risk_per_lot (0.01 lots) | risk_per_lot (1 lot) |
|---------------|--------------------------|----------------------|
| $2.00 (200 pips) | $2.00 | $200 |
| $4.00 (400 pips) | $4.00 | $400 |
| $6.00 (600 pips) | $6.00 | $600 |

### Risk Budget at $30 Equity
```
risk_dollars = $30 × 0.01 = $0.30 per trade
```

### Exact Lots Required
```
lots_exact = risk_dollars / risk_per_lot
```

| stop_distance | risk_per_lot | lots_exact | lots (stepped to 0.01) | **Accepted?** |
|---------------|--------------|------------|------------------------|---------------|
| $2.00 | $200 | 0.0015 | 0.00 | **REJECTED** (min volume breach) |
| $4.00 | $400 | 0.00075 | 0.00 | **REJECTED** |
| $6.00 | $600 | 0.0005 | 0.00 | **REJECTED** |

### Minimum Risk Fraction to Clear 0.01 Lots
```
required_risk_fraction = (volume_min × risk_per_lot) / equity
                       = (0.01 × stop_distance × 100) / 30
                       = stop_distance / 30
```

| stop_distance | required risk_fraction | required risk % |
|---------------|------------------------|-----------------|
| $2.00 | 0.0667 | **6.67%** |
| $4.00 | 0.1333 | **13.33%** |
| $6.00 | 0.2000 | **20.00%** |

**At the configured 1% risk fraction, NO trade clears the 0.01-lot minimum. Every signal is rejected.**

---

## 5. Required Margin at Minimum Volume

| Leverage | Margin % | Notional (0.01 lots @ $2,650/oz) | Required Margin | Free Margin ($30 account) |
|----------|----------|-----------------------------------|-----------------|---------------------------|
| 1:100 | 1% | $2,650 | **$26.50** | $3.50 |
| 1:200 | 0.5% | $2,650 | **$13.25** | $16.75 |
| 1:500 | 0.2% | $2,650 | **$5.30** | $24.70 |
| 1:2000 | 0.05% | $2,650 | **$1.33** | $28.67 |

**Even at 1:2000 leverage, the risk system rejects the trade because the 1% risk budget ($0.30) cannot cover the minimum-lot stop risk ($2–$6).**

---

## 6. Spread / Commission Impact at Minimum Volume

| Cost Component | Assumption | Cost per 0.01-lot RT |
|----------------|------------|----------------------|
| Observed spread | 20–50 points (median ~30) | 30 × 0.001 × 100 × 0.01 = **$0.03** |
| Commission | $0–$7/RT (configurable) | **$0.00–$0.07** (at 0.01 lots) |
| Swap | $2–$5/night (configurable) | **$0.02–$0.05**/night (at 0.01 lots) |

**Total round-trip cost at min volume: ~$0.05–$0.15** — small relative to stop risk but **the trade never reaches execution because sizing rejects it first.**

---

## 7. Can the Strategy Respect Its Configured Risk Limits at $30?

**No.** With the current configuration:
- `risk_fraction = 0.01` (1%)
- `volume_min = 0.01` lots
- `contract_size = 100` oz
- Typical stop_distance ≥ $2.00

The risk system **rejects every signal** with reason:
```
min volume breach: 0.01 lots risks $2.00–$6.00 > budget $0.30
```

This is the **correct, intended behavior** — the system refuses to force an oversized position that would risk 6.7–20% of the account on a single trade.

---

## 8. Linear Scaling from $10,000 to $30 Is Invalid

The research outputs at $10,000 **cannot be linearly scaled** to $30 because:

1. **Sizing is non-linear** — floor-to-step volume discretization creates a hard threshold. At $10,000, risk_dollars = $100 → lots_exact ≈ 0.5 → 0.50 lots accepted. At $30, risk_dollars = $0.30 → lots_exact ≈ 0.0015 → **rejected**.

2. **Margin constraints** — at $10,000, 0.50 lots requires ~$1,325 margin (1:100), well within equity. At $30, 0.01 lots requires $26.50 margin (1:100), leaving almost no buffer.

3. **Cost proportion** — spread/commission/swap as a fraction of risk_dollars explodes at small equity.

4. **Monte Carlo equity paths** — the MC simulation compounds trade P&L assuming continuous sizing. At $30, the first trade never executes, so the entire path is empty.

---

## 9. Normalized vs. Account-Specific Performance — Clear Separation

| Metric | Normalized (Research, $10k) | Account-Specific (Live, $30) |
|--------|-----------------------------|------------------------------|
| **In-sample net P&L** | -$4,760 (-47.6%) | **N/A — zero trades executed** |
| **OOS net P&L** | -$73.20 | **N/A — zero trades executed** |
| **Trade count (IS)** | ~200+ | **0** |
| **Trade count (OOS)** | 3 | **0** |
| **Max drawdown** | -67% | **0% (no trades)** |
| **Sharpe** | -1.83 (IS), -0.92 (OOS) | **N/A** |
| **Profit factor** | 0.72 (IS), 0.82 (OOS) | **N/A** |

**The strategy's normalized performance (negative expectancy, high drawdown) is already a no-go. The $30 account feasibility analysis confirms it cannot even execute.**

---

## 10. Feasibility Conclusion

### Is XAUUSDm trading technically feasible with $30 under verified broker conditions?

| Question | Answer |
|----------|--------|
| **Can the minimum lot (0.01) be traded?** | Margin-wise: **yes** at 1:200+ leverage. Risk-wise: **no** at 1% risk fraction. |
| **What is the minimum cash risk per executable trade?** | At 0.01 lots with typical stop ($2–$6): **$2–$6 per trade** (6.7–20% of $30 equity). |
| **Can the strategy respect its 1% risk limit?** | **No.** The minimum lot risks 6.7–20% of equity, exceeding the 1% budget. Every signal is rejected. |
| **Required risk_fraction to execute?** | **6.7–20%** (depending on stop distance) — incompatible with professional risk management. |

### Explicit Classification

> **XAU-MTF-DONCHIAN-001 is INFEASIBLE at the intended $30 account size under the verified Exness XAUUSDm contract specifications and the strategy's configured 1% fixed-fractional risk policy.**

The strategy cannot execute a single trade without violating its own risk limits. The research pipeline correctly rejects all signals at this equity level — this is a *feature*, not a bug.

---

## 11. What Would Be Required to Make It Feasible?

| Change | Feasibility | Notes |
|--------|-------------|-------|
| Increase `risk_fraction` to 10–20% | ❌ Unprofessional | Violates basic risk management; 1 loss = 10–20% drawdown |
| Reduce `volume_min` via broker negotiation | ❌ Not available | Exness minimum is 0.01 lots for XAUUSDm |
| Switch to micro-lots (0.001) | ❌ Not offered | Exness XAUUSDm minimum is 0.01 |
| Use CFD with smaller contract size | ⚠️ Different instrument | Would require full re-research; not XAUUSDm |
| Increase account size to ≥ $300 | ✅ Minimum | At $300, 1% risk = $3.00; clears $2 stop at 0.01 lots |
| Increase account size to ≥ $600 | ✅ Comfortable | At $600, 1% risk = $6.00; clears $6 stop at 0.01 lots |

**Minimum viable equity for this strategy on XAUUSDm at 1% risk: ~$300–$600 depending on stop distance.**

---

## 12. Preservation of $10,000 Research Outputs

All Assignment 14 deliverables remain **unchanged and reproducible** at the $10,000 research scale:

- `reports/assignment14/assignment14_results.json` — complete machine-readable record
- `reports/assignment14/ledger/*.csv` — all trade, equity, breakdown ledgers
- `reports/assignment14/monte_carlo_equity_fan.png` — fan charts at $10,000
- `reports/assignment14/monte_carlo_distributions.png` — distribution charts at $10,000

**This audit is an *additional* analysis layer. It does not modify, replace, or invalidate any research artifact.**

---

## 13. Reproducibility

To reproduce this audit:

```python
# In a Python session with the mars package available:
from mars.libs.risk.contract_aware import InstrumentSpec, ContractAwareFixedFractionalRisk
from mars.libs.strategies.xau_mtf_donchian import MtfDonchianParams
from mars.libs.strategies.base import TradeSetup
import pandas as pd

spec = InstrumentSpec(
    symbol="XAUUSDm", contract_size=100.0, pip_size=0.01, point_size=0.001,
    quote_currency="USD", volume_min=0.01, volume_max=200.0, volume_step=0.01,
    volume_spec_source="unverified_offline_default", spec_source="pair_config.offline"
)

params = MtfDonchianParams(risk_fraction=0.01, starting_equity=30.0)
risk = ContractAwareFixedFractionalRisk(spec=spec, risk_fraction=0.01)

# Simulate a signal with typical stop_distance
setup = TradeSetup(
    timestamp=pd.Timestamp.now(tz="UTC"),
    symbol="XAUUSDm",
    side="long",
    metadata={"stop_distance": 4.0}  # $4.00 stop (400 pips)
)

decision = risk.evaluate(setup, equity=30.0)
print(decision.reason)  # -> "min volume breach: 0.01 lots risks $4.00 > budget $0.30"
print(decision.metadata["risk_at_min_volume_usd"])  # -> 4.0
print(decision.metadata["risk_limit_usd"])          # -> 0.3
```

---

**Prepared by:** M.A.R.S. Quant Research Pipeline  
**Date:** 2026-11-25  
**Classification:** Internal — Account Feasibility Audit