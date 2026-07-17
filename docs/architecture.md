# M.A.R.S. Architecture

**M.A.R.S.** — Mathematical Algorithm Risk System  
Version: 0.1.0 (Research Layer + Trading Core foundation)

---

## 1. Design principles

1. **Time-series first** — chronological splits; no accidental shuffle on market data.
2. **Point-in-time features** — features only use information available at decision time.
3. **Simple core, intelligent edge** — small interfaces; complexity isolated.
4. **Preserve research evidence** — legacy experiments stay in `legacy/`.
5. **Runnable baseline** — one clean XAUUSD workflow before broader automation.

---

## 2. Repository layout

```
MARS-QUANT/
├── mars/                      # Installable-style Python package
│   ├── apps/
│   │   ├── research_lab/      # Data download, baseline pipeline
│   │   ├── trainer/           # Training entry points
│   │   └── backtester/        # Evaluation / session backtests
│   └── libs/
│       ├── data/              # Schemas, loaders, validation
│       ├── features/          # Feature pipelines
│       ├── labels/            # Target generation
│       ├── models/            # Model interfaces + XGB/Torch wrappers
│       ├── strategies/        # Candidate setup generation
│       ├── risk/              # Sizing / filters
│       ├── evaluation/        # Metrics, splits, reports
│       └── utils/             # Paths, helpers
├── data/
│   ├── raw/                   # Vendor OHLCV (parquet)
│   └── processed/             # Features, sequences, trade logs
├── models/                    # Serialized model artifacts
├── reports/                   # Metrics and plots
├── notebooks/                 # Exploratory research (not production)
├── docs/                      # Architecture, audit, backlog
├── legacy/                    # Pre-refactor source (preserved)
├── tests/                     # Unit / smoke tests
├── artifacts/                 # Optional run outputs
└── requirements.txt
```

---

## 3. Module responsibilities

### `mars.libs.data`

- Candle schema (`timestamp`, OHLCV, optional spread/session/news)
- Load parquet → normalize aliases → validate structure

### `mars.libs.features`

- `FeaturePipeline` ABC: `fit` / `transform` / `feature_names`
- `HypAAsiaLondonFeatures`: daily Asia-session tabular features

### `mars.libs.labels`

- `LabelGenerator` ABC
- `HypALondonLabels`: London direction + return from session meta

### `mars.libs.models`

- `BaseModel`: `fit`, `predict`, `predict_proba`, `save`, `load`
- XGBoost classifier/regressor wrappers
- LSTM / Transformer classifiers (architectures; train carefully)

### `mars.libs.strategies`

- `TradeSetup` dataclass + `BaseStrategy`
- `HypAMLDirectionStrategy`: model predictions → long/short setups

### `mars.libs.risk`

- `BaseRiskPolicy` / `RiskDecision`
- `FixedFractionalRisk` (V1 sizing + optional filters)

### `mars.libs.evaluation`

- Chronological `time_series_split`
- Classification / regression metrics
- Text report writer

### Apps

| App | Role |
|-----|------|
| `research_lab.xauusd_baseline_pipeline` | End-to-end Hyp-A research workflow |
| `research_lab.download_data` | Optional MT5 download |
| `trainer.train_xgb_baseline` | CLI wrapper for baseline training |
| `backtester.run_hyp_a_backtest` | Vectorized session PnL on test slice |

---

## 4. Current workflow (V1)

```
Raw H1 OHLCV (parquet)
        │
        ▼
  load + validate (UTC)
        │
        ▼
  Hyp-A features (Asia only) ──► labels (London dir/return)
        │
        ▼
  chronological train / val / test
        │
        ▼
  XGBoost fit on train
        │
        ▼
  evaluate val + test → report + joblib artifacts
```

Decision point for live/research signals: **end of Asian session**, before London open.

---

## 5. Future M.A.R.S. layers

### Research Layer (current focus)

- Ingestion, FE, labels, training, backtest, experiment tracking

### Trading Core (foundation started)

- Regime detection (TODO)
- Modular strategy engine (`strategies/` skeleton)
- Trade quality scoring (TODO)
- Risk engine (`risk/` V1 skeleton)
- Execution adapters (legacy MT5 bots; not yet refactored)
- Performance analytics (partial via evaluation + backtester)

### Copilot Layer (later)

- Observer / assisted / auto modes
- Chart explanations, trade rationale, operator UX

---

## 6. Explicit non-goals (V1)

- Autonomous multi-strategy hedge fund stack
- Fake “AI trader” marketing surfaces
- Full rewrite of every notebook into production code
