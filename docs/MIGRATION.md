# Migration Plan — Legacy → M.A.R.S. Platform
 
**Policy:** Do not destroy research history. Move deprecated code to `legacy/`. Refactor only.
 
---
 
## What was moved
 
| Legacy location | New location |
|-----------------|--------------|
| `src/` | `legacy/src/` |
| `notebooks/` | `legacy/notebooks/` |
| `models/` | `legacy/models/` |
| `reports/` | `legacy/reports/` |
| `RESEARCH_PLAN.md` | `legacy/RESEARCH_PLAN.md` |
| Root output plots / bots scripts | `legacy/` |
 
| Preserved in place | Notes |
|--------------------|-------|
| `data/raw/` | Historical parquet retained |
| `data/processed/` | Feature parquet / npy retained |
| `LICENSE` | Unchanged |
 
---
 
## Module mapping
 
### Data
 
| Legacy | M.A.R.S. replacement |
|--------|----------------------|
| `src/data_acquisition.py` | `mars.data.ingestion.MT5Ingestor` + `IngestionPipeline` |
| Ad-hoc parquet load | `mars.data.ingestion.ParquetIngestor` |
| Manual timezone localize in hyp-A script | `mars.data.normalization.OHLCVNormalizer` |
| (none) | `mars.data.validation.MarketDataValidator` |
| `df.to_parquet(...)` | `mars.data.storage.ParquetDatasetStore` |
| (none) | fingerprints + `LocalDatasetCatalog` |
 
### Features
 
| Legacy | M.A.R.S. replacement |
|--------|----------------------|
| `src/hyp_a_feature_engineering.py` | Split into `SessionFeature`, `MomentumFeature`, `VolatilityFeature`, etc. |
| `src/feature_engineering_utils.py` | Domain modules under `mars/features/*` |
| Single H1 loop | `MultiTimeframeFeatureEngine` + `AlignmentEngine` |
| Implicit BOS / structure (if any) | `BaseSwingDetector` + `BOSDetector` / `CHOCHDetector` |
 
### Research / models
 
| Legacy | M.A.R.S. replacement |
|--------|----------------------|
| `RESEARCH_PLAN.md` Hyp A/B/C | `research/hypotheses/HYP-A-001.json` (etc.) |
| `src/hyp_a_xgboost_train_model.py` | Keep in legacy; future model lab (Stage 2) |
| `src/hyp_a_*_lstm_*` / transformer | Keep in legacy; re-wire later to Feature Store |
| `src/utils.generate_report` | `mars.research.ExperimentLog` + `research/validation/` |
| `src/bots/*` | **Not migrated** — production trading is out of scope |
 
### Validation
 
| Legacy | M.A.R.S. replacement |
|--------|----------------------|
| Train/test 80/20 split | `WalkForwardSplitter`, `PurgedKFold` |
| Monte Carlo notebook | `bootstrap_confidence_interval` + research notebooks |
| Backtest HTML reports | Keep under `legacy/reports/`; formal metrics in `mars.validation` |
 
---
 
## Phased migration
 
### Phase 0 — Complete (this refactor)
 
- [x] Create `mars/` package architecture
- [x] Move old code to `legacy/`
- [x] Interfaces + base implementations
- [x] Unit tests for core paths
- [x] Migrate Hyp A/B/C records to `research/hypotheses/`
- [x] Documentation (`ARCHITECTURE.md`, this file, README)
 
### Phase 1 — Reprocess data under new platform
 
1. For each file in `data/raw/*.parquet`:
   - Run `ParquetIngestor` → `OHLCVNormalizer` → `MarketDataValidator`
   - Write to `data/processed/{symbol}/{tf}/v1.0.0/` via `ParquetDatasetStore`
   - Register in catalog
2. Keep original raw files untouched (fingerprinted).
 
### Phase 2 — Rebuild Hypothesis A features
 
1. Port session feature logic from `legacy/src/hyp_a_feature_engineering.py` into:
   - `mars.features.session` (Asia/London windows with DST-aware logic)
   - `mars.features.momentum` / `volatility` for indicators
2. Register feature versions in Feature Store.
3. Re-run feature validation suite (ADF, IC, VIF, stability).
 
### Phase 3 — Re-validate models (no new strategies)
 
1. Point training scripts at Feature Store matrices (or keep temporary adapters).
2. Replace random split with purged CV + walk-forward.
3. Log every run via `ExperimentLog` linked to `HYP-A-001`.
4. Only then consider status transitions (testing → accepted / rejected).
 
### Phase 4 — Multi-timeframe expansion
 
1. Ingest M30, M15, M5, M3 for research universe.
2. Use `MultiTimeframeFeatureEngine` + `AlignmentEngine`.
3. Do **not** train separate models per TF.
 
### Phase 5 — Deprecate legacy entry points
 
1. Stop recommending `legacy/src/run_pipeline.py` in docs.
2. Keep `legacy/` indefinitely for audit / reproducibility.
3. Optional: read-only archive tag in git.
 
---
 
## Adapter pattern (recommended)
 
While porting Hyp A, use a thin adapter so old notebooks still run:
 
```python
# future: mars/compat/legacy_hyp_a.py
# load legacy parquet → normalize → expose DataFrame
# matching old column names for notebook compatibility
```
 
Do **not** copy strategy code into the new core.  
Adapters are temporary and belong under `mars/compat/` (create when needed).
 
---
 
## Data path compatibility
 
Old scripts often used:
 
```
../data/raw/{symbol}_{tf}_{year}_present.parquet
../data/processed/hyp_a_features_*.parquet
```
 
These files remain where they are. New writes should use the versioned layout.  
A one-time copy into versioned paths is preferred over in-place mutation.
 
---
 
## Acceptance criteria for “migration complete”
 
1. All new research uses `mars.*` imports.
2. Every dataset used in a paper/report has a fingerprint.
3. Every experiment has an `experiment_id` log.
4. Hypotheses A/B/C have formal records with status.
5. `pytest tests/` is green in CI.
6. `legacy/` is never required for new feature development.
 
---
 
## What we will not do during migration
 
- Delete `legacy/`
- “Improve” model accuracy as a goal
- Promote order blocks to core features without validation
- Add production trading to the research platform