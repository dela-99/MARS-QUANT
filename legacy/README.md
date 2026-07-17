# Legacy research code

This directory preserves the original experimental codebase that existed before
the M.A.R.S. package refactor. **Nothing here is deleted** — it is archived so
research history, bots, and notebook-aligned scripts remain available.

## Contents

| Path | Description |
|------|-------------|
| `src/` | Original scripts: feature engineering, XGBoost/LSTM/Transformer training, backtest, MT5 bots |
| `src/bots/` | Live/paper XGBoost trading bots (MT5) |
| `*.png`, `yo.ipynb`, `all.txt` | Root research artifacts moved during cleanup |

## Important caveats

1. **PyTorch trainers** (`hyp_a_lstm_*`, `hyp_a_transformer_*`) use
   `sklearn.model_selection.train_test_split` (random shuffle). This is **not**
   time-series safe. Metrics from those runs should be treated as exploratory only.
2. **Session sequence scaler** (`hyp_a_create_session_sequences.py`) fits
   `StandardScaler` on the **full** dataset before splitting → leakage risk.
3. **Relative paths** assume scripts are run from `src/` with `../data` etc.
4. Prefer the new package: `mars.apps.research_lab.xauusd_baseline_pipeline`.

## How to run legacy scripts (if needed)

```bash
cd legacy/src
python hyp_a_feature_engineering.py --year 2018 --symbol xauusd --timeframe h1
```

Paths inside legacy scripts still point to `../data`, `../models`, `../reports`
relative to `legacy/src`, which resolves to the **repo-root** data folders only
if you adjust them — or run with working directory set carefully.

Recommended: migrate any needed logic into `mars/libs/` rather than relying on
these scripts long-term.
