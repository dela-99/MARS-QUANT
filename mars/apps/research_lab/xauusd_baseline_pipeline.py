"""
M.A.R.S. V1 baseline pipeline: XAUUSD H1 Asia → London (Hypothesis A).

Steps
-----
1. Load & validate OHLCV
2. Engineer Asia-session features (no London leakage into X)
3. Generate London direction / return labels
4. Chronological train / val / test split
5. Train baseline XGBoost classifier (+ optional regressor)
6. Evaluate out-of-sample
7. Write metrics report

This is the first coherent end-to-end research workflow for M.A.R.S.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from mars.libs.data.loaders import load_ohlcv_parquet
from mars.libs.evaluation.metrics import classification_metrics, regression_metrics
from mars.libs.evaluation.report import write_text_report
from mars.libs.evaluation.splits import time_series_split
from mars.libs.features.hyp_a_asia_london import HypAAsiaLondonFeatures
from mars.libs.labels.hyp_a_labels import HypALondonLabels
from mars.libs.models.xgboost_model import XGBoostClassifierModel, XGBoostRegressorModel
from mars.libs.utils.paths import ProjectPaths


def run_baseline_pipeline(
    data_path: str | Path,
    *,
    symbol: str = "XAUUSD",
    timeframe: str = "h1",
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
    test_ratio: float = 0.15,
    save_artifacts: bool = True,
    n_estimators: int = 500,
    paths: Optional[ProjectPaths] = None,
) -> Dict[str, Any]:
    """
    Execute the full Hyp-A XGBoost baseline workflow.

    Returns a dict with metrics, paths, and a human-readable summary string.
    """
    paths = paths or ProjectPaths.from_root()
    data_path = Path(data_path)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # --- 1. Load & validate ---
    print(f"[1/7] Loading OHLCV from {data_path} ...")
    ohlcv = load_ohlcv_parquet(data_path, symbol=symbol.lower(), timeframe=timeframe)
    print(f"      rows={len(ohlcv)}  range={ohlcv['timestamp'].min()} → {ohlcv['timestamp'].max()}")

    # --- 2–3. Features + labels ---
    print("[2/7] Engineering Asia-session features ...")
    feat_pipe = HypAAsiaLondonFeatures()
    features, session_meta = feat_pipe.transform_with_sessions(ohlcv)
    print(f"      feature days={len(features)}  columns={list(features.columns)}")

    print("[3/7] Generating London labels ...")
    labels = HypALondonLabels().generate(session_meta)
    # Align
    common_idx = features.index.intersection(labels.index)
    X = features.loc[common_idx]
    y_class = labels.loc[common_idx, "london_direction"]
    y_reg = labels.loc[common_idx, "london_return"]
    print(f"      aligned samples={len(X)}")

    if len(X) < 50:
        raise RuntimeError(
            f"Insufficient daily samples ({len(X)}). Check raw data coverage and session logic."
        )

    # Persist processed table for research reuse
    processed_path = None
    if save_artifacts:
        paths.processed_data.mkdir(parents=True, exist_ok=True)
        processed = X.copy()
        processed["london_direction"] = y_class
        processed["london_return"] = y_reg
        processed["symbol"] = symbol.lower()
        processed["timeframe"] = timeframe
        processed_path = (
            paths.processed_data
            / f"mars_hyp_a_features_{symbol.lower()}_{timeframe}_{stamp}.parquet"
        )
        processed.to_parquet(processed_path)
        print(f"      saved processed features → {processed_path}")

    # --- 4. Time-series split (NO shuffle) ---
    print("[4/7] Time-series split (chronological) ...")
    split = time_series_split(
        X.index, train_ratio=train_ratio, val_ratio=val_ratio, test_ratio=test_ratio
    )
    print(split.describe())

    X_train, y_train_c = X.loc[split.train_idx], y_class.loc[split.train_idx]
    X_val, y_val_c = (
        (X.loc[split.val_idx], y_class.loc[split.val_idx])
        if len(split.val_idx)
        else (None, None)
    )
    X_test, y_test_c = X.loc[split.test_idx], y_class.loc[split.test_idx]
    y_train_r = y_reg.loc[split.train_idx]
    y_test_r = y_reg.loc[split.test_idx]

    # --- 5. Train ---
    # Note: unconstrained original runs often overfit (~99% train / ~50% test).
    # Regularization + early stopping on validation improve research honesty.
    print("[5/7] Training XGBoost classifier + regressor ...")
    common_xgb = dict(
        n_estimators=n_estimators,
        learning_rate=0.05,
        max_depth=3,
        min_child_weight=5,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_lambda=1.0,
        random_state=42,
    )
    clf = XGBoostClassifierModel(name="mars_hyp_a_xgb_classifier", **common_xgb)
    reg = XGBoostRegressorModel(name="mars_hyp_a_xgb_regressor", **common_xgb)

    if X_val is not None and len(X_val) > 0:
        y_val_r = y_reg.loc[split.val_idx]
        clf.params["early_stopping_rounds"] = 30
        reg.params["early_stopping_rounds"] = 30
        try:
            clf.fit(X_train, y_train_c, eval_set=[(X_val, y_val_c)], verbose=False)
            reg.fit(X_train, y_train_r, eval_set=[(X_val, y_val_r)], verbose=False)
        except TypeError:
            # Older xgboost without early_stopping in constructor/fit
            clf.params.pop("early_stopping_rounds", None)
            reg.params.pop("early_stopping_rounds", None)
            clf.fit(X_train, y_train_c)
            reg.fit(X_train, y_train_r)
    else:
        clf.fit(X_train, y_train_c)
        reg.fit(X_train, y_train_r)

    # --- 6. Evaluate ---
    print("[6/7] Evaluating out-of-sample ...")
    test_pred_c = clf.predict(X_test)
    test_pred_r = reg.predict(X_test)
    test_cls = classification_metrics(y_test_c, test_pred_c)
    test_reg = regression_metrics(y_test_r, test_pred_r)

    val_cls = None
    if X_val is not None and len(X_val) > 0:
        val_pred_c = clf.predict(X_val)
        val_cls = classification_metrics(y_val_c, val_pred_c)

    train_pred_c = clf.predict(X_train)
    train_cls = classification_metrics(y_train_c, train_pred_c)

    # --- 7. Report + save models ---
    print("[7/7] Writing report and models ...")
    classifier_path = paths.models / f"mars_hyp_a_xgb_classifier_{stamp}.joblib"
    regressor_path = paths.models / f"mars_hyp_a_xgb_regressor_{stamp}.joblib"
    report_path = paths.reports / f"mars_hyp_a_xgb_baseline_{stamp}.txt"

    if save_artifacts:
        paths.models.mkdir(parents=True, exist_ok=True)
        paths.reports.mkdir(parents=True, exist_ok=True)
        clf.save(classifier_path)
        reg.save(regressor_path)

    assumptions = """
ASSUMPTIONS & LEAKAGE NOTES
---------------------------
- Features use only Asia session OHLCV + indicators at Asia close.
- Labels use London open/close (known only after London session).
- Split is chronological (train → val → test); no random shuffle.
- Indicators (EMA200) require warm-up; early NaN rows dropped.
- No spread / slippage model in this ML evaluation (classification only).
- Commission-aware backtest lives in apps/backtester (separate step).
- Regime segmentation and walk-forward validation are NOT yet applied.
- Prior legacy PyTorch scripts used random splits; do not mix those metrics.
""".strip()

    sections = [
        f"Symbol: {symbol}  Timeframe: {timeframe}",
        f"Source data: {data_path}",
        f"Processed features: {processed_path}",
        "",
        "PERIODS",
        split.describe(),
        "",
        "TRAIN classification metrics",
        f"accuracy={train_cls['accuracy']:.4f}  f1={train_cls['f1']:.4f}",
        train_cls["report"],
        "",
        "VALIDATION classification metrics"
        if val_cls
        else "VALIDATION: (empty — val_ratio=0)",
        (
            f"accuracy={val_cls['accuracy']:.4f}  f1={val_cls['f1']:.4f}\n{val_cls['report']}"
            if val_cls
            else ""
        ),
        "",
        "TEST (out-of-sample) classification metrics",
        f"accuracy={test_cls['accuracy']:.4f}  precision={test_cls['precision']:.4f}  "
        f"recall={test_cls['recall']:.4f}  f1={test_cls['f1']:.4f}",
        test_cls["report"],
        "",
        "TEST regression metrics (london_return)",
        f"MAE={test_reg['mae']:.6f}  RMSE={test_reg['rmse']:.6f}  R2={test_reg['r2']:.4f}",
        "",
        f"Classifier saved: {classifier_path if save_artifacts else '(not saved)'}",
        f"Regressor saved:  {regressor_path if save_artifacts else '(not saved)'}",
        "",
        assumptions,
    ]

    if save_artifacts:
        write_text_report(report_path, sections, title="M.A.R.S. Hyp-A XGBoost Baseline")

    summary = (
        f"M.A.R.S. baseline complete | test acc={test_cls['accuracy']:.4f} "
        f"f1={test_cls['f1']:.4f} | MAE={test_reg['mae']:.6f} | n_test={len(X_test)}"
    )

    return {
        "summary": summary,
        "train_metrics": train_cls,
        "val_metrics": val_cls,
        "test_metrics": test_cls,
        "test_regression": test_reg,
        "split": split,
        "report_path": str(report_path) if save_artifacts else None,
        "classifier_path": str(classifier_path) if save_artifacts else None,
        "regressor_path": str(regressor_path) if save_artifacts else None,
        "processed_path": str(processed_path) if processed_path else None,
        "n_samples": len(X),
        "feature_names": list(X.columns),
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run M.A.R.S. XAUUSD Hyp-A baseline pipeline.")
    parser.add_argument("--year", type=int, default=2018)
    parser.add_argument("--symbol", type=str, default="xauusd")
    parser.add_argument("--timeframe", type=str, default="h1")
    parser.add_argument("--train-ratio", type=float, default=0.70)
    parser.add_argument("--val-ratio", type=float, default=0.15)
    parser.add_argument("--test-ratio", type=float, default=0.15)
    args = parser.parse_args()

    paths = ProjectPaths.from_root()
    data_path = (
        paths.raw_data
        / f"{args.symbol.lower()}_{args.timeframe.lower()}_{args.year}_present.parquet"
    )
    result = run_baseline_pipeline(
        data_path,
        symbol=args.symbol.upper(),
        timeframe=args.timeframe.lower(),
        train_ratio=args.train_ratio,
        val_ratio=args.val_ratio,
        test_ratio=args.test_ratio,
    )
    print(result["summary"])
    print(f"Report: {result['report_path']}")


if __name__ == "__main__":
    main()
