# FC-005-2 Interaction Regression Report
**Strategy:** XAU-VOL-REGIME-SESSION-005
**Date:** 2026-11-25T14:11:34.724150+00:00

## Regression Specification
- Equation: PnL = β_0 + β_1×Signal + β_2×Regime + β_3×(Signal×Regime) + ε
- Dependent Variable: net_pnl_per_session
- Independent Variables: ['signal', 'regime', 'interaction']
- Interaction Term: Signal × Regime
- Observations: 2684

## Coefficient Estimates
| Variable | Coefficient | Std Error | t-value | p-value (2-sided) |
|----------|-------------|-----------|---------|-------------------|
| const | -0.0000 | 0.0000 | -0.0000 | 1.0000 |
| signal | -0.0000 | 0.0000 | -0.0000 | 1.0000 |
| regime | 0.0000 | nan | nan | nan |
| interaction | -21.7912 | 3.1600 | -6.8960 | 0.0000 |

## Interaction Term (beta_3) — Primary Test
- beta_3 = -21.7912
- SE = 3.1600
- 95% CI: [-27.9848, -15.5976]
- p (one-sided) = 1.0000
- **PASS (beta_3 > 0, p < 0.05)**: False

## Model Diagnostics
- R^2 = 0.1761
- Adj R^2 = 0.1752
- Durbin-Watson = 1.4098
- Breusch-Pagan LM = 230.2723 (p = 0.0000)

## Standard Error Treatment
- Method: HAC (Newey-West, maxlags=5)
- Serial Correlation: checked via Durbin-Watson
- Heteroskedasticity: checked via Breusch-Pagan

## Economic Interpretation
The interaction coefficient beta_3 measures the incremental net expectancy of the
regime filter when the base signal (Asian return > 0) is active. A positive
and statistically significant beta_3 indicates the regime filter adds genuine
predictive value beyond random chance.