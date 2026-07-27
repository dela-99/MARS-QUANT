# M.A.R.S. Multi-Timeframe Feature Engine

M.A.R.S. means **Mathematical Algorithm Risk System**. The Feature Engine is a pure feature-generation subsystem. It converts validated research hypotheses into deterministic mathematical feature columns.

It does **not** execute trades, make predictions, contain machine-learning models, integrate brokers, or encode trading rules.

## Architecture

Package root: `mars/libs/features/`

```text
base/                 BaseFeature, FeatureMetadata, FeaturePipeline, FeatureRegistry
market_structure/     swings, structure descriptors, BOS/CHOCH proxies
liquidity/            equal levels, sweeps, density, clustering proxies
imbalance/            configurable fair value gap descriptors
momentum/             ROC, RSI, MACD, ADX, acceleration, decay
volatility/           ATR, Parkinson, Yang-Zhang, variance, entropy, GARCH-ready columns
session/              Asia, London, New York, overlaps, boundary distances
microstructure/       OHLCV spread and volume descriptors, placeholders
trend/                moving averages, slope, persistence, confidence
statistical/          z-score, skew, kurtosis, entropy, stationarity proxies
correlation/          rolling, lead/lag, cross-reference correlation
transforms/           log, scaling, normalization, standardization, PCA, wavelet placeholders
multi_timeframe/      AlignmentEngine and MultiTimeframeFeatureEngine
validation/           data quality and feature validation reports
store.py              local versioned Parquet feature store with DuckDB query hook
```

## Feature lifecycle

1. Research validates a hypothesis outside this subsystem.
2. The feature author creates a `BaseFeature` subclass in the correct category.
3. The feature declares metadata: name, version, mathematical definition, parameters, dependencies, inputs, outputs, and lookback.
4. The feature implements `compute(df) -> FeatureResult` using vectorized Pandas/NumPy operations.
5. Tests prove determinism, output correctness, metadata, NaN behavior, and no look-ahead.
6. The feature is registered with `FeatureRegistry` or included in a `FeaturePipeline`.
7. The `MultiTimeframeFeatureEngine` computes features independently per timeframe and aligns them into one dataset.
8. Optional storage writes a versioned Parquet dataset and manifest.

## Multi-timeframe alignment

Supported timeframes are `H1`, `M30`, `M15`, `M5`, and `M3`.

The default context hierarchy is:

```text
H1  -> trend_context
M30 -> market_bias
M15 -> execution_context
M5  -> confirmation_context
M3  -> entry_timing_context
```

These are context labels only. They do not imply entries, exits, predictions, or trading decisions.

`AlignmentEngine` prevents look-ahead by using closed-bar alignment. A higher timeframe row is shifted by its full bar duration before it is as-of joined into the lower timeframe index. For example, an H1 bar timestamped `00:00` is not available to an M3 row until `01:00`.

## Feature versioning

Each feature exposes `FeatureMetadata`:

- `name`
- `version`
- `category`
- `mathematical_definition`
- `parameters`
- `dependencies`
- `inputs`
- `outputs`
- `lookback`
- reproducibility flags

A metadata fingerprint is available through `BaseFeature.fingerprint()`. Bump the version whenever the formula, defaults, inputs, outputs, or NaN behavior changes.

## Creating a new feature

```python
from mars.libs.features.base import BaseFeature, FeatureResult
import pandas as pd

class MyFeature(BaseFeature):
    name = "my_feature"
    version = "1.0.0"
    category = "statistical"
    inputs = ("close",)
    outputs = ("my_feature",)
    mathematical_definition = "close divided by rolling mean close"

    def __init__(self, window: int = 20):
        super().__init__(window=window)
        self.window = window
        self.lookback = window

    def compute(self, df: pd.DataFrame, **kwargs) -> FeatureResult:
        self.validate_inputs(df)
        out = pd.DataFrame(
            {"my_feature": df["close"] / df["close"].rolling(self.window).mean()},
            index=df.index,
        )
        return FeatureResult(out, self.metadata, self.validation_report(FeatureResult(out, self.metadata)))
```

Rules:

- Inherit from `BaseFeature`.
- Keep the feature independent and reusable.
- Use deterministic vectorized transformations.
- Do not reference future bars.
- Do not include prediction, model, execution, broker, order, or strategy concepts.

## Testing methodology

Feature tests should cover:

- deterministic repeated output
- mathematical correctness for a small known input
- metadata and version presence
- expected output columns
- NaN warmup behavior
- validation failures for bad inputs
- multi-timeframe synchronization
- no look-ahead across higher timeframe bars

Run focused tests:

```bash
pytest tests/unit/libs/features/test_feature_engine.py
```

Run all tests:

```bash
pytest
```

## Feature store

`FeatureStore` writes local versioned datasets:

```text
feature_store_root/{dataset_id}/{version}/features.parquet
feature_store_root/{dataset_id}/{version}/manifest.json
```

The manifest includes dataset ID, version, path, rows, columns, metadata, and a deterministic fingerprint. DuckDB querying is supported through `query_duckdb()` when DuckDB is installed.
