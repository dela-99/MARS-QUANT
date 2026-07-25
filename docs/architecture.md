# M.A.R.S. Architecture
 
**Mathematical Algorithm Risk System**
 
Institutional-grade quantitative **research** infrastructure.  
This document covers Stage 1: Data Platform, Research Lab, Feature Engine.
 
---
 
## Design philosophy
 
Inspired by the *engineering culture* of firms such as Jane Street, Citadel, Two Sigma and investment-bank quant platforms — not their proprietary strategies.
 
| Principle | Implementation |
|-----------|----------------|
| Modular architecture | Separate packages per system; interfaces over monoliths |
| Reproducible research | Dataset fingerprints, experiment logs, hypothesis IDs |
| Rigorous statistical validation | Sharpe/Sortino/Calmar, bootstrap CI, purged CV, walk-forward |
| Deterministic features | Pure functions, versioned, unit tested |
| Strong software engineering | Type hints, Pydantic schemas, pytest |
| Risk-first design | Validation gates before production-candidate status |
 
**Out of scope for this stage:** production trading logic, order routing, live risk engines.
 
---
 
## System map
 
```
┌─────────────────────────────────────────────────────────────┐
│                     Research Lab (content)                   │
│   research/{hypotheses, mathematics, experiments, ...}       │
└───────────────────────────┬─────────────────────────────────┘
                            │ workflow / status
┌───────────────────────────▼─────────────────────────────────┐
│                     mars.research                            │
│   HypothesisStore · ExperimentLog · ResearchWorkflow         │
└───────────┬─────────────────────────────┬───────────────────┘
            │                             │
┌───────────▼───────────┐     ┌───────────▼───────────────────┐
│   mars.data           │     │   mars.features               │
│   Data Platform       │────▶│   Feature Engine              │
│                       │     │   + MultiTimeframe            │
│   ingest→normalize→   │     │   + AlignmentEngine           │
│   validate→version→   │     │   + market structure / liq.   │
│   store→catalog       │     └───────────┬───────────────────┘
└───────────────────────┘                 │
                            ┌─────────────▼───────────────────┐
                            │   mars.validation               │
                            │   Performance · Bootstrap ·     │
                            │   Purged CV · Walk-Forward      │
                            └─────────────────────────────────┘
```
 
---
 
## SYSTEM 1 — Data Platform (`mars.data`)
 
### Layers
 
| Layer | Path | Purpose |
|-------|------|---------|
| Raw | `data/raw/` | As-ingested; immutable once fingerprinted |
| Processed | `data/processed/` | Cleaned, normalized, validated OHLCV |
| Research | `data/research/` | Experiment-specific intermediates |
| Feature Store | `data/feature_store/` | Versioned feature matrices |
 
### Versioned storage layout
 
```
data/{layer}/{symbol}/{timeframe}/v{version}/
    data.parquet
    metadata.json
    data.parquet.fingerprint.json
```
 
DuckDB-compatible:
 
```sql
SELECT * FROM read_parquet('data/processed/xauusd/h1/v1.0.0/data.parquet');
```
 
### Interfaces
 
| Interface | Responsibility |
|-----------|----------------|
| `DataIngestor` | Pull bars from MT5 / parquet / future vendors |
| `DataNormalizer` | Canonical OHLCV + UTC index |
| `DataValidator` | Missing candles, duplicates, bad ticks, spread, OHLC |
| `DatasetStore` | Parquet write/read with metadata |
| `DatasetCatalog` | Register / discover datasets |
 
### Quality checks
 
- Schema (required columns, datetime index)
- Duplicate timestamps
- OHLC consistency
- Missing candle / gap detection
- Bad tick (non-positive price, extreme z-return)
- Spread validation (if present)
 
### Pipeline
 
```python
from mars.data.ingestion import IngestionPipeline, ParquetIngestor
from mars.core.timeframes import Timeframe
from datetime import datetime
 
pipeline = IngestionPipeline(ingestor=ParquetIngestor("data/raw/xauusd_h1_2018_present.parquet"))
path, meta, report = pipeline.run(
    symbol="XAUUSD",
    timeframe=Timeframe.H1,
    start=datetime(2018, 1, 1),
    end=datetime.utcnow(),
    version="1.0.0",
    source_name="legacy_mt5",
)
```
 
---
 
## SYSTEM 2 — Research Lab
 
### Content tree
 
```
research/
    hypotheses/       # HYP-*.json
    mathematics/
    literature/
    experiments/
    notebooks/
    datasets/
    validation/
    experiment_logs/
```
 
### Hypothesis contract
 
Every hypothesis requires:
 
- Unique ID (`HYP-A-001`)
- Problem statement
- Mathematical formulation
- Required datasets
- Features required
- Experiments
- Statistical validation plan
- Status: `draft | testing | accepted | rejected | archived`
 
### Methodology stages
 
```
Idea → Hypothesis → Formal mathematics → Feature engineering
  → Historical testing → Walk-forward → Statistical tests
  → Risk review → Approval → Production candidate
```
 
Enforced by `mars.research.ResearchWorkflow`.
 
### Statistical validation (`mars.validation`)
 
| Metric / method | Module |
|-----------------|--------|
| Sharpe, Sortino, Calmar, Max DD | `performance.py` |
| Bootstrap CI | `bootstrap.py` |
| Purged K-Fold CV | `cross_validation.py` |
| Walk-forward / OOS | `walk_forward.py` |
| Feature stability | `feature_stability.py` |
| IC, ADF, VIF, importance | `mars.features.validation` |
 
---
 
## SYSTEM 3 — Feature Engine (`mars.features`)
 
### Rules
 
1. **No monolithic `feature.py`**
2. Each feature is a `BaseFeature` subclass
3. Deterministic, vectorized, unit tested
4. Versioned via `FeatureMetadata`
5. No look-ahead bias
 
### Domain interfaces
 
```
BaseFeature
├── MarketStructureFeature
├── LiquidityFeature
├── MomentumFeature
├── VolatilityFeature
├── SessionFeature
├── MicrostructureFeature
├── TimeFeature
└── CorrelationFeature
```
 
### Multi-timeframe
 
Supported: **H1, M30, M15, M5, M3**
 
```
MultiTimeframeFeatureEngine
    → computes features independently per TF
AlignmentEngine
    → merge_asof(backward) onto base TF
    → trend context / market bias / execution / confirmation
```
 
**Do not** train separate models per timeframe.  
Align features → single synchronized representation.
 
### Market structure (pluggable)
 
```
BaseSwingDetector
├── FractalSwingDetector
├── ZigZagSwingDetector
└── AdaptiveSwingDetector
 
BOSDetector(swing_detector=...)
CHOCHDetector(swing_detector=...)
```
 
### Liquidity (research modules)
 
- Equal highs / equal lows (confidence scores)
- Density clustering (DBSCAN + KDE)
- Liquidity sweeps / pools
 
### Order blocks
 
**Experimental only** — `mars.features.order_blocks`  
Not core assumptions until statistically validated.
 
---
 
## Package layout
 
```
mars/
├── core/           # types, schemas, timeframes, config
├── data/           # Data Platform
├── features/       # Feature Engine
├── research/       # Hypothesis / experiment / workflow
└── validation/     # Statistical validation
```
 
Legacy code: `legacy/` (preserved, not deleted).
 
---
 
## Testing strategy
 
| Layer | Location | Focus |
|-------|----------|-------|
| Unit | `tests/unit/data` | normalize, validate, fingerprint, store |
| Unit | `tests/unit/features` | determinism, lookback, MTF align, structure |
| Unit | `tests/unit/validation` | metrics, CV, walk-forward |
| Unit | `tests/unit/research` | hypothesis lifecycle, workflow gates |
| Integration | `tests/integration` | end-to-end ingest → features → validate |
 
Run:
 
```bash
pytest tests/ -q
```
 
---
 
## Explicit non-goals (this stage)
 
- Inventing trading rules
- Optimizing for high accuracy / overfitting
- Production execution / bots (legacy bots remain in `legacy/src/bots`)
- Unnecessary AI wrappers
- Monolithic classes