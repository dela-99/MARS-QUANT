# M.A.R.S. — Full Repo Audit & Structure

**Generated:** 2026-08-29
**Repo:** `dela-99/MARS-QUANT`
**Local path:** `C:\Users\RIDGE\OneDrive\Desktop\MARS-QUANT`
**Branch:** `main` @ `6510a7c` (clean, in sync with `origin/main`)

---

## 1. Headline

MARS-QUANT is a **research-stage quantitative trading foundation** for XAUUSD session dynamics (Asia → London → NY). It's been refactored into a modular package layout, but the migration is **partial**: two parallel packages (`mars.features/` and `mars.libs.features/`) coexist, and a full **`mars.libs.learning/`** subsystem is mostly **empty scaffolding** (stubs only). The V1 end-to-end pipeline is real and works (39/39 tests pass), but anything beyond Hypothesis A is either research plan only or skeleton.

- **Tests:** 39 passed in 18.7s on Python 3.14 (the project's actual runtime — `cpython-314.pyc` files everywhere).
- **LOC (Python, all `mars/` + `legacy/` + `tests/`):** 5,135 code + 1,119 comment lines across 140 files (pygount).
- **Codebase size:** ~50 MB on disk, dominated by `models/` (30 MB of `.joblib`/`.pth`) and `data/` (8 MB of parquets + `.npy` session sequences).
- **Git:** 7 commits on `main`; latest is a docs-only `md` commit.

---

## 2. Top-level layout (cleaned up)

```
MARS-QUANT/
├── README.md            # Project narrative
├── IDEA.md              # 1-line: "build a quantitative trading firm"
├── LICENSE              # MIT, 2025
├── pyproject.toml       # mars-quant 0.1.0, requires-python >=3.10
├── requirements.txt     # pandas/numpy/xgboost/sklearn/pyarrow/pytest
├── .env.example         # DEMO MT5 credentials
├── .gitignore           # standard Python
├── .jcode_learning_*.py # ← scratch one-off bootstrap scripts for the empty learning/ dirs (see §6)
│
├── mars/                # ← Refactored package (7,407 LOC of Python)
│   ├── __init__.py      # version 0.1.0 (note: also defines 0.2.0 — duplicate, see §6)
│   ├── core/            # types, schemas, timeframes, config
│   ├── data/            # Data Platform (ingest → normalize → validate → store → catalog)
│   ├── features/        # Feature Engine v1 (documented in architecture.md)
│   ├── validation/      # performance / bootstrap / purged CV / walk-forward
│   ├── research/        # HypothesisStore, ExperimentLog, ResearchWorkflow
│   ├── apps/            # Entry-point scripts (CLI runners)
│   └── libs/            # Mirror feature engine with full BaseFeature/subclass system
│       ├── data/  evaluation/  utils/
│       ├── features/    # Full feature library + BaseFeature/FeatureMetadata/FeaturePipeline
│       ├── labels/      # Direction + return label generators (Hyp A)
│       ├── models/      # XGBoost, PyTorch LSTM/Transformer model wrappers
│       ├── strategies/  # Base + HypA ML signal strategy stub
│       ├── risk/        # Fixed-fractional position sizing stub
│       └── learning/    # ⚠ EMPTY SCAFFOLDING — see §6
│
├── tests/               # 569 LOC, 39 tests, all passing
│   ├── conftest.py      # Shared OHLCV + returns fixtures
│   ├── test_schemas.py, test_splits.py
│   └── unit/
│       ├── data/        # normalization, validation, fingerprint store
│       ├── features/    # base features, market structure, MTF alignment
│       ├── validation/  # performance metrics
│       ├── libs/features/  # feature engine
│       └── research/    # hypothesis lifecycle
│
├── data/                # 8 MB total
│   ├── raw/             # 4 XAUUSD H1 parquets: 2015 / 2018 / 2020 / 2025-present
│   └── processed/       # Hyp-A features parquets, padded session sequences (.npy), backtest trade CSVs
│
├── models/              # 30 MB trained artifacts (NOT in gitignore — checked in!)
│   ├── *pytorch_lstm_*.pth, *pytorch_transformer_*.pth (with old random-split runs)
│   ├── *xgb_classifier/regressor_hyp_a_*.joblib (many variants)
│   ├── xgb_classifier_hyp_a_TUNED_paper_v*.joblib (paper experiments)
│   └── mars_hyp_a_xgb_*_20260717_*.joblib (latest from new pipeline)
│
├── reports/             # 4 MB — training metric .txt files + many .png plots + 1 HTML backtest
├── notebooks/           # 14 .ipynb + pytorch_utils.py (exploratory only, see README)
├── docs/                # 56 KB — architecture, audit, migration, testing, feature_engine, research plan
├── research/            # EMPTY on disk (the docs reference `research/hypotheses/`, `research/literature/`,
│                        #   `research/mathematics/` but they're under mars/research/, not here)
├── legacy/              # 2.8 MB — preserved pre-refactor code (READ-ONLY archive)
│   └── src/             # original scripts + MT5 bots
└── artifacts/           # EMPTY (just an empty `reports/` subdir)
```

---

## 3. What the repo actually does (status table)

| Capability | Status | Where |
|---|---|---|
| Load / validate XAUUSD H1 parquet | ✅ Working | `mars.data.ingestion` + `mars.libs.data.loaders` |
| Hyp-A Asia→London feature engineering | ✅ Working | `mars.libs.features.hyp_a_asia_london` |
| Direction + return labels | ✅ Working | `mars.libs.labels.hyp_a_labels` |
| Chronological train/val/test split | ✅ Working | `mars.libs.evaluation.splits.time_series_split` |
| Baseline XGBoost train + OOS metrics | ✅ Working | `mars.apps.research_lab.xauusd_baseline_pipeline` |
| Session-level backtest (vectorized) | ✅ Working | `mars.apps.backtester.run_hyp_a_backtest` |
| Multi-timeframe feature engine + alignment | ✅ Working | `mars.features.multi_timeframe` + `mars.libs.features.multi_timeframe` |
| Feature registry + metadata + fingerprinting | ✅ Working | `mars.libs.features.base` (`BaseFeature`, `FeatureRegistry`, `FeatureStore`) |
| Market structure (swings / BOS / CHOCH) | ✅ Working | `mars.features.market_structure` |
| Liquidity (equal levels / sweeps / density) | ✅ Working | `mars.features.liquidity` |
| Order blocks | ⚠ Experimental | `mars.features.order_blocks` — explicitly marked "experimental only" |
| PyTorch LSTM / Transformer architectures | ✅ Present, ⚠ Random-split legacy | `mars.libs.models.pytorch_models` + `legacy/src/hyp_a_*lstm/transformer*` |
| Statistical validation (Sharpe/Sortino/Calmar, bootstrap, purged CV, walk-forward, feature stability) | ✅ Modules present | `mars.validation.*` |
| HypothesisStore + ExperimentLog + ResearchWorkflow | ✅ Modules present | `mars.research.*` |
| Regime engine | ❌ Skeleton/backlog | `docs/research_backlog.md` P2 |
| Full risk engine | ❌ Skeleton/backlog | `mars.libs.risk.fixed_fractional` is a stub |
| Hypothesis B (London morning → LON/NY overlap) | ❌ Plan only | `HYP-B-001.json` exists but no code |
| Hypothesis C (Asia+London → NY) | ❌ Plan only | `HYP-C-001.json` exists but no code |
| Spread/slippage-aware backtest | ❌ Not yet | `docs/research_backlog.md` P1 |
| Live MT5 trading bots | ⚠ Legacy only | `legacy/src/bots/` — not wired to `mars.libs` |
| Experiment tracking (MLflow/W&B) | ❌ Not integrated | `docs/research_backlog.md` P3 |

---

## 4. The two parallel feature engines — **major design issue**

There are **two distinct feature packages** doing essentially the same job, and they don't talk to each other:

| Aspect | `mars.features/` (Feature Engine v1, documented in `docs/architecture.md`) | `mars.libs.features/` (Feature Engine v2, documented in `docs/feature_engine.md`) |
|---|---|---|
| Base class | `mars.features.base.BaseFeature` (155 LOC, generic) | `mars.libs.features.base.feature.BaseFeature` (richer, has `FeatureResult`, `FeaturePipeline`, `FeatureRegistry`, fingerprint) |
| Domain modules | market_structure, liquidity, momentum, volatility, session, microstructure, time, correlation, alignment, multi_timeframe, order_blocks, validation | momentum, volatility, trend, statistical, correlation, session, microstructure, market_structure, liquidity, imbalance, transforms, multi_timeframe, validation |
| Multi-TF | `MultiTimeframeFeatureEngine` + `AlignmentEngine` | `MultiTimeframeFeatureEngine` + `AlignmentEngine` (duplicate) |
| Used by V1 pipeline? | ❌ No | ✅ Yes (`HypAAsiaLondonFeatures`) |
| Has FeatureStore? | ❌ | ✅ (`FeatureStore` + DuckDB query hook) |
| Has hypothesis A FE? | ❌ | ✅ `hyp_a_asia_london.py` |

**Why both exist:** The architecture doc and feature_engine doc describe two different visions. The README only mentions one (`mars.libs.features`). The actual V1 pipeline uses the libs one. The features/ one is **dead code from a parallel refactor** — never imported by the working pipeline, and not referenced by the README.

**Files using each (sample):**
- `mars.features/`: only used internally — `mars.features.base`, `mars.features.registry`, `mars.features.alignment`, `mars.features.multi_timeframe`. No app imports it.
- `mars.libs.features/`: imported by `mars.apps.research_lab.xauusd_baseline_pipeline` and `tests/unit/libs/features/test_feature_engine.py`.

There's also a **typo file**: `mars/features/time/calender.py` (British spelling) sits next to `calendar.py` — only one is imported.

---

## 5. The `mars.libs.learning/` subsystem — **almost entirely empty**

`mars/libs/learning/` contains 23 subdirectories (`base/`, `datasets/`, `labels/`, `pipelines/`, `preprocessing/`, `feature_selection/`, `models/{xgboost,lightgbm,catboost,random_forest,logistic,svm,pytorch,lstm,transformer}/`, `training/`, `evaluation/`, `registry/`, `serving/`, `artifacts/`, `validation/`, `calibration/`, `explainability/`, `optimisation/`, `ensembles/`, `inference/`, `persistence/`).

**Total: 1 Python file.** That's `base/metadata.py` (the `LearningMetadata` dataclass). Every other subdirectory contains only `__init__.py` with no code.

**Root cause:** Look at the four `.jcode_learning_*.py` files at repo root. They're scratch bootstrap scripts used to scaffold these empty dirs and dump placeholder files into them. They're accidentally committed to the repo.

This is the biggest gap between the architecture docs (which describe a full model training/serving subsystem with calibration, explainability, ensembles, etc.) and the actual code.

---

## 6. Other findings

### Duplicate / inconsistent config
- `mars/__init__.py` defines `__version__ = "0.1.0"` AND `"0.2.0"` — both literals in the same file (the 0.1.0 block is the first 9 lines; 0.2.0 block starts at line 24).
- `pyproject.toml` says `version = "0.1.0"`.

### Repo hygiene
- `.pytest_cache/` is present (correctly gitignored but already populated on disk).
- `__pycache__/` directories everywhere — fine, gitignored.
- `.jcode_learning_*.py` are scratch/dev scripts in the repo root. Should either be deleted or moved to a `scripts/` or `tools/` folder.
- `artifacts/` is empty (only `artifacts/reports/` empty subdir exists). README references `artifacts/` but nothing writes there.
- `research/` (top-level) is **empty on disk**, but docs reference it (e.g. `research/hypotheses/`, `research/literature/`, `research/mathematics/`). The actual content lives under `mars/research/hypotheses/`, `mars/research/literature/`, `mars/research/mathematics/`. Confusing.

### Artifacts checked in that probably shouldn't be
- All 30 MB of `models/*.joblib` and `*.pth` are committed to git (`.gitignore` doesn't exclude `models/`). These will bloat the repo over time. Worth considering a git-lfs or release-artifact strategy.
- `notebooks/` are committed — fine for research continuity.
- `reports/*.png` and HTML backtests are committed — fine for reproducibility.

### Documentation
- 7 docs in `docs/`: `architecture.md`, `audit_report.md`, `MIGRATION.md`, `TESTING.md`, `feature_engine.md`, `research_backlog.md`, `RESEARCH_PLAN.md`. All coherent and detailed. The `audit_report.md` (2026-07-17) is honest about pre-refactor risks.
- `README.md` is clean, claims the right scope, and links to architecture + migration docs.

### Dependencies
- `requirements.txt` is minimal: pandas, numpy, pytz, pyarrow, scikit-learn, xgboost, joblib, matplotlib, seaborn, python-dotenv, pytest.
- Optional/legacy deps commented out: pandas-ta, torch, backtesting, mplfinance, MetaTrader5.
- `pyproject.toml` requires Python ≥ 3.10, but every `__pycache__` is `cpython-314.pyc` and the working test run used Python 3.14.

### Git activity
- 7 commits total, last 4 in chronological order:
  1. `c607ba8 feat_features_mtf_engine`
  2. `df4bb4c research labs`
  3. `2804a8a Repo-Audit + Co`
  4. `13a1905 mtf engine update`
  5. `6510a7c md` (HEAD)
- Work is happening in clear, single-purpose commits.

---

## 7. Verification

```
$ /c/Python314/python.exe -m pytest tests/ -q --no-header
.......................................                                  [100%]
39 passed in 18.70s
```

All tests green on Python 3.14 (the actual project runtime).

```
$ pygount --format=summary --folders-to-skip=".git,__pycache__,..." .
┌───────────────┬───────┬───────┬──────┬───────┬─────────┬──────┐
│ Language      │ Files │     % │ Code │     % │ Comment │    % │
├───────────────┼───────┼───────┼──────┼───────┼─────────┼──────┤
│ Python        │   140 │  80.5 │ 5135 │  64.1 │    1119 │ 14.0 │
│ HTML+Genshi   │     2 │   1.1 │  104 │  85.2 │       0 │  0.0 │
│ TOML          │     1 │   0.6 │   15 │  83.3 │       0 │  0.0 │
│ Batchfile     │     1 │   0.6 │    6 │ 100.0 │       0 │  0.0 │
│ INI           │     1 │   0.6 │    2 │ 100.0 │       0 │  0.0 │
│ Text only     │     2 │   1.1 │    0 │   0.0 │     497 │ 79.8 │
│ Markdown      │     3 │   1.7 │    0 │   0.0 │      95 │ 43.2 │
│ __unknown__   │     5 │   2.9 │    0 │   0.0 │       0 │  0.0 │
│ __empty__     │     1 │   0.6 │    0 │   0.0 │       0 │  0.0 │
│ __duplicate__ │    13 │   7.5 │    0 │   0.0 │       0 │  0.0 │
│ __binary__    │     5 │   2.9 │    0 │   0.0 │       0 │  0.0 │
├───────────────┼───────┼───────┼──────┼───────┼─────────┼──────┤
│ Sum           │   174 │ 100.0 │ 5262 │  58.5 │    1711 │ 19.0 │
└───────────────┴───────┴───────┴──────┴───────┴─────────┴──────┘
```

---

## 8. Recommendations (priority order)

### P0 — Clean up
1. **Pick one feature engine.** `mars.libs.features/` is the active one (the README and pipeline use it). Delete `mars/features/` entirely OR delete `mars.libs.features/` and refactor the V1 pipeline onto `mars.features/`. This is the single biggest cleanup.
2. **Delete `.jcode_learning_*.py`** from the repo root (or move to a `scripts/` folder).
3. **Decide on `mars.libs.learning/`.** Either remove the empty scaffolding or commit to filling it. Right now it's a misleading skeleton.
4. **Fix `mars/__init__.py`** — pick one `__version__`.
5. **Delete `mars/features/time/calender.py`** (typo file) once you confirm `calendar.py` is canonical.

### P1 — Hygiene
6. **Reconcile top-level `research/` vs `mars/research/`.** Docs reference the former but only the latter has content.
7. **Add `models/` to `.gitignore`** (or move to git-lfs). 30 MB of binary artifacts in main is rough.
8. **Delete `artifacts/`** if unused, or wire it up to the pipeline (currently the pipeline writes to `reports/`, `models/`, `data/processed/`).

### P2 — Engineering debt (matches `docs/research_backlog.md`)
9. Wire walk-forward + purged CV into the V1 baseline pipeline.
10. Build Hypothesis B and C on the cleaned-up feature engine.
11. Add spread/slippage to the backtest.

---

**Bottom line:** The V1 Hyp-A pipeline works end-to-end and is honest about its limitations. The refactor is incomplete: there are two feature engines, an empty `learning/` subsystem, scratch scripts in the root, and a typo'd module. A focused cleanup pass (P0 items above) would make this feel like a coherent, single-purpose repo instead of a refactor in progress.