# Unit Testing Strategy
 
## Goals
 
1. **Correctness** of interfaces and pure functions  
2. **Determinism** of features (same input → same output)  
3. **No look-ahead** in alignment and swing confirmation  
4. **Reproducibility** of fingerprints and experiment records  
 
## Layout
 
```
tests/
├── conftest.py              # shared OHLCV fixtures
├── unit/
│   ├── data/                # normalize, validate, store, fingerprint
│   ├── features/            # each feature domain + MTF + structure
│   ├── validation/          # metrics, CV, walk-forward
│   └── research/            # hypothesis + workflow
├── integration/             # end-to-end pipelines (add as needed)
└── fixtures/                # small sample parquet if required
```
 
## Rules for feature tests
 
Every new `BaseFeature` subclass must have tests that assert:
 
| Check | Why |
|-------|-----|
| Determinism | `compute(df)` twice is equal |
| Output length | Aligns to input index |
| Lookback NaNs | First `lookback` rows are NaN where expected |
| No future leakage | Alignment uses backward asof only |
| Metadata | `name`, `version`, `outputs` populated |
 
## Market structure tests
 
- Detectors are **interchangeable**: `BOSDetector(FractalSwingDetector())` vs ZigZag
- Confirmed swings only after confirmation window
 
## Data platform tests
 
- Schema failures are errors
- Fingerprint changes when data changes
- Store round-trip preserves row count and columns
 
## Running
 
```bash
pip install -r requirements.txt
pip install -e .
pytest tests/ -q
```
 
## Coverage targets (aspirational)
 
| Package | Target |
|---------|--------|
| `mars.core` | high |
| `mars.data` | high |
| `mars.features` (core) | high |
| `mars.validation` | high |
| `mars.research` | medium |
| experimental order blocks | smoke only |