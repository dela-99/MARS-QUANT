# M.A.R.S. Repository Audit Report

**Date:** 2026-07-17  
**Scope:** Original `MARS-QUANT` / Quantitative XAUUSD Session Strategy repository  
**Author of audit:** M.A.R.S. refactor pass

---

## 1. Repository overview (pre-refactor)

### Top-level layout

| Path | Role |
|------|------|
| `data/raw/` | XAUUSD H1 parquet (2015 / 2018 / 2020 / 2025 present) |
| `data/processed/` | Daily features, session sequences (.npy), backtest trade CSVs |
| `models/` | XGBoost `.joblib`, PyTorch `.pth`, scalers |
| `notebooks/` | EDA, FE, training, tuning, backtest, Monte Carlo |
| `reports/` | Metrics text files, confusion matrices, equity plots |
| `src/` | Script-style research + MT5 bots (now → `legacy/src/`) |
| `README.md`, `RESEARCH_PLAN.md` | Project narrative (Hypothesis A–C) |

### Existing functionality (yes / partial / no)

| Capability | Status | Notes |
|------------|--------|-------|
| Data loading (MT5) | Yes | `data_acquisition.py`; requires MT5 credentials |
| Feature engineering | Yes | Hyp-A Asia features; advanced TA for paper model |
| Target labeling | Yes | `london_direction`, `london_return` |
| Train/val/test split | Partial | XGB: chronological 80/20; no val; DL: **random** split |
| Backtesting | Yes | `backtesting.py` MLStrategy + notebooks |
| Risk logic | Minimal | Fixed lot size in bots; commission in BT only |
| Signal generation | Yes | Daily direction from classifier |
| Hyperparameter tuning | Yes | Notebook `hyperparameter_tuning.ipynb` (TimeSeriesSplit) |
| Model serialization | Yes | joblib / torch state_dict |
| Evaluation reports | Yes | `reports/*.txt` |
| Inference / live | Partial | MT5 bots; duplicated FE logic |

---

## 2. Models found

### XGBoost (tabular)

| Artifact pattern | Predicts | Trained in | Data | Pipeline completeness |
|------------------|----------|------------|------|------------------------|
| `xgb_classifier_hyp_a_*` | London session direction (0/1) | `hyp_a_xgboost_train_model.py`, notebooks | Daily Asia features parquet | Complete research path |
| `xgb_regressor_hyp_a_*` | London session return | same | same | Complete research path |
| `xgb_classifier_hyp_a_TUNED_paper_v*` | Direction (expanded features) | notebooks / paper FE | `hyp_a_features_advanced.parquet` | Research-complete; FE not fully scripted in clean package |

### PyTorch LSTM

| Artifact | Predicts | Trained in | Data | Completeness |
|----------|----------|------------|------|--------------|
| `*_pytorch_lstm_classifier.pth` | Session direction | `hyp_a_lstm_train_pytorch_classifier.py` | Padded Asia sequences (10×5) | Trains, but **random split** |
| `*_pytorch_lstm_regressor.pth` | Session return | regressor script | same | same risk |

### PyTorch Transformer

| Artifact | Predicts | Trained in | Data | Completeness |
|----------|----------|------------|------|--------------|
| `*_pytorch_transformer_classifier.pth` | Direction | transformer classifier script | same sequences | **random split** |
| `*_pytorch_transformer_regressor.pth` | Return | transformer regressor script | same | **random split** |

**No** RandomForest / LightGBM production trainers found in `src/`.

---

## 3. Research quality risks

| Risk | Severity | Where | Notes |
|------|----------|-------|-------|
| Random train/test on time series | **High** | All PyTorch train scripts + DL notebooks | Comment claimed "random split is OK" — it is not for OOS claims |
| Scaler fit on full sample | **High** | `hyp_a_create_session_sequences.py` | `StandardScaler.fit` before any split |
| No walk-forward validation | Medium | Overall | Single holdout only (except tuning notebook) |
| Backtest / train period alignment | Medium | backtest script | Uses 80% of **bars** for cut; model trained on **daily** rows — periods may not align exactly |
| Unrealistic costs | Medium | Backtest commission 0.02% | XAUUSD spread often larger; no slippage model |
| No regime segmentation | Medium | All | Single model across all market regimes |
| Target leakage into features | **Low for Hyp-A baseline** | FE script | Features from Asia only; labels from London — correct by design |
| Lookahead via indicators | Low–Med | FE | Indicators at Asia close use only past H1 bars if computed causally (rolling) — OK if no centered windows |
| Duplicate / divergent FE | Medium | Bots vs scripts | Live bots re-implement FE; paper bot uses advanced indicators |
| Broken pipeline entry | Medium | `run_pipeline.py` | Called `hyp_a_train_model.py` but file is `hyp_a_xgboost_train_model.py` |
| Fragile relative paths | Medium | All `src/` scripts | Depend on CWD |
| Inconsistent timezone handling | Low–Med | Sessions | London DST handled; Asia fixed UTC hours — intentional but document |

---

## 4. Keep / refactor / archive decisions

### Keep as-is

- `data/raw/*.parquet` historical XAUUSD H1
- `data/processed/` research outputs (feature parquets, sequences, trade CSVs)
- `models/` trained artifacts (evidence of prior experiments)
- `reports/` historical metrics and plots
- `notebooks/` exploratory research (documented as experimental)
- `LICENSE`, `.env.example`

### Keep but refactor (into `mars/`)

- Hyp-A feature engineering (Asia → London tabular features)
- XGBoost train/eval with **time-aware** split
- Data load / normalize / validate
- PyTorch architectures (LSTM / Transformer nets) behind interfaces
- Session label definitions
- Simple risk sizing skeleton
- Backtest idea (vectorized session BT + pointer to legacy full BT)

### Archive / legacy (`legacy/`)

- Entire former `src/` tree (scripts, bots, HTML plots)
- Root dump images / scratch notebooks
- Interactive `run_pipeline.py` with broken script name
- Paper-tuned bot paths hardcoding model filenames

### Delete

- **Nothing** of research value deleted. Redundant root PNGs moved to `legacy/`.

---

## 5. Post-refactor state

Clean package under `mars/` with:

- Core interfaces: data, features, labels, models, strategies, risk
- V1 end-to-end: `mars.apps.research_lab.xauusd_baseline_pipeline`
- Docs: architecture, this audit, research backlog
- Original work preserved under `legacy/`

### Still incomplete / risky

- Walk-forward & purged CV
- Regime detection
- Production risk engine
- Spread-aware execution backtest
- Hypotheses B & C
- Retrain DL models with chronological splits
- Experiment tracking (MLflow/W&B) not integrated
