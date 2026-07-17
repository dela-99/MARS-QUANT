# M.A.R.S. — Mathematical Algorithm Risk System

![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**M.A.R.S.** is a quantitative trading research and execution foundation focused on
**time-series correctness**, modular strategy/risk interfaces, and reproducible
experiment workflows.

This repository originated as a **XAUUSD session-dynamics research project**
(Hypothesis A: Asian session → London session prediction) and has been reorganized
into a maintainable research platform without discarding prior work.

---

## What M.A.R.S. is (and is not)

**Is:**

- A research layer for data → features → labels → models → evaluation
- A trading-core foundation: strategy setups, risk policy stubs, backtest hooks
- Explicit about leakage risks and incomplete components

**Is not (yet):**

- An autonomous multi-strategy hedge fund
- A “fully AI trader” product UI
- A claim that legacy model metrics are production-ready

---

## What the repo currently supports

| Capability | Status |
|------------|--------|
| Load / validate XAUUSD H1 parquet | Supported |
| Hyp-A Asia→London feature engineering | Supported (`mars.libs.features`) |
| Direction + return labels | Supported |
| Chronological train/val/test split | Supported |
| Baseline XGBoost train + OOS metrics report | Supported |
| Simple session-level backtest | Supported (vectorized) |
| PyTorch LSTM / Transformer architectures | Present (use chronological splits only) |
| Live MT5 bots | Legacy only (`legacy/src/bots`) |
| Hypotheses B & C | Research plan only |
| Regime engine / full risk engine | Skeleton / backlog |

Historical notebooks, models, and reports remain for research continuity.

---

## Repository layout (short)

```
mars/           # Clean package (apps + libs)
data/           # raw + processed market data
models/         # trained artifacts
reports/        # metrics & plots
notebooks/      # exploratory (experimental)
docs/           # architecture, audit, backlog
legacy/         # original src/ and research artifacts
tests/          # smoke / unit tests
```

See [docs/architecture.md](docs/architecture.md) for full detail.

---

## Setup

```bash
# From repo root
python -m venv .venv

# Windows
.\.venv\Scripts\activate

# Unix
source .venv/bin/activate

pip install -r requirements.txt
```

Optional: copy `.env.example` → `.env` for MetaTrader 5 downloads / live bots.

```env
DEMO_ACCOUNT_NUMBER=YOUR_ACCOUNT_NUMBER
PASSWORD=YOUR_PASSWORD
SERVER=MetaQuotes-Demo
```

---

## Run the baseline XAUUSD workflow

Requires existing raw data, e.g. `data/raw/xauusd_h1_2018_present.parquet`
(already present in this repo for several start years).

```bash
# End-to-end: load → features → labels → time split → XGBoost → report
python -m mars.apps.research_lab.xauusd_baseline_pipeline --year 2018

# Equivalent trainer entry point
python -m mars.apps.trainer.train_xgb_baseline --year 2018
```

Outputs:

- Report: `reports/mars_hyp_a_xgb_baseline_*.txt`
- Models: `models/mars_hyp_a_xgb_classifier_*.joblib`, `models/mars_hyp_a_xgb_regressor_*.joblib`
- Features: `data/processed/mars_hyp_a_features_*.parquet`

Optional download (MT5):

```bash
python -m mars.apps.research_lab.download_data --symbol XAUUSD --year 2018 --timeframe H1
```

Optional session backtest on a processed feature file:

```bash
python -m mars.apps.backtester.run_hyp_a_backtest \
  --model models/mars_hyp_a_xgb_classifier_XXXX.joblib \
  --features data/processed/mars_hyp_a_features_XXXX.parquet
```

---

## What is still experimental

- All **notebooks/** and **legacy/** training scripts
- **PyTorch** metrics from the original repo (random train/test split — not trustworthy OOS)
- Paper-tuned advanced-feature XGBoost models (artifacts kept; pipeline not fully ported)
- Live trading bots (duplicated feature logic; not wired to `mars.libs`)
- Monte Carlo notebooks (useful diagnostics; not integrated into apps)

Read [docs/audit_report.md](docs/audit_report.md) and [docs/research_backlog.md](docs/research_backlog.md).

---

## Research context (Hypothesis A)

- **Features:** Asian session return/range + indicators at Asia close  
- **Labels:** London session direction (close ≷ open) and return  
- **Decision time:** After Asia, before London open  

Original research plan: [docs/RESEARCH_PLAN.md](docs/RESEARCH_PLAN.md).

---

## Author

**RIDGE DELA TORJAGBO**  
[LinkedIn](https://www.linkedin.com/in/ridge-dela-torjagbo-32963b366)
