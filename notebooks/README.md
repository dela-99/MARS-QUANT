# Research notebooks (experimental)

These notebooks contain the original exploratory analysis, feature engineering,
hyperparameter tuning, deep learning training, backtests, and Monte Carlo studies.

They are **not** the production M.A.R.S. API. Prefer:

```bash
python -m mars.apps.research_lab.xauusd_baseline_pipeline --year 2018
```

Caveats when re-running notebooks:

- Several DL notebooks use **random** `train_test_split` — not time-series safe.
- Paths may assume an older `src/` layout (now under `legacy/src/`).
- `pytorch_utils.py` here is a notebook helper; package code lives in `mars.libs.models`.
