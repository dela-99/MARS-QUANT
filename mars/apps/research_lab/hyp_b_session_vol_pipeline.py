"""
M.A.R.S. V1 baseline pipeline: XAUUSD H1 session volatility prediction (Hypothesis B).

Steps
-----
1. Load & validate OHLCV
2. Engineer session-aware volatility features (no lookahead into target session)
3. Generate next-session ATR% labels
4. Chronological train / val / test split
5. Train baseline XGBoost regressor
6. Train GARCH(1,1) baseline (CARR range-GARCH variant for fair comparison)
7. Evaluate out-of-sample with test-set guard
8. Write metrics report

This is the first coherent end-to-end research workflow for Hyp-B.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from mars.libs.data.loaders import load_ohlcv_parquet
from mars.libs.evaluation.metrics import regression_metrics
from mars.libs.evaluation.report import write_text_report
from mars.libs.evaluation.splits import time_series_split
from mars.libs.features.hyp_b_session_vol import HypBSessionVolFeatures
from mars.libs.labels.hyp_b_labels import HypBNextSessionATRLabels
from mars.libs.models.xgboost_model import XGBoostRegressorModel
from mars.libs.models.garch_baseline import GARCHBaseline
from mars.libs.utils.paths import ProjectPaths
from mars.core.config import DEFAULT_CONFIG
from mars.research.experiment import ExperimentLog


def run_hyp_b_pipeline(
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
    Execute the full Hyp-B XGBoost + GARCH baseline workflow.

    Returns a dict with metrics, paths, and a human-readable summary string.
    """
    paths = paths or ProjectPaths.from_root()
    data_path = Path(data_path)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # --- 1. Load & validate ---
    print(f"[1/8] Loading OHLCV from {data_path} ...")
    ohlcv = load_ohlcv_parquet(data_path, symbol=symbol.lower(), timeframe=timeframe)
    print(f"      rows={len(ohlcv)}  range={ohlcv['timestamp'].min()} → {ohlcv['timestamp'].max()}")

    # --- 2–3. Features + labels ---
    print("[2/8] Engineering session-aware volatility features ...")
    feat_pipe = HypBSessionVolFeatures()
    features, session_meta = feat_pipe.transform_with_sessions(ohlcv)
    print(f"      feature days={len(features)}  columns={list(features.columns)}")

    print("[3/8] Generating next-session ATR% labels ...")
    labels = HypBNextSessionATRLabels().generate(session_meta)
    # Align
    common_idx = features.index.intersection(labels.index)
    X = features.loc[common_idx]
    y = labels.loc[common_idx, "next_session_atr_pct"]
    print(f"      aligned samples={len(X)}")

    if len(X) < 50:
        raise RuntimeError(
            f"Insufficient daily samples ({len(X)}). Check raw data coverage and session logic."
        )

    # Persist processed table for research reuse
    processed_path = None
    if save_artifacts:
        paths.processed_data.mkdir(parents=True, exist_ok=True)
        # y is a Series with same index as X (already aligned by common_idx)
        processed = X.copy()
        processed["next_session_atr_pct"] = y.values  # use values to avoid index alignment issues
        processed["symbol"] = symbol.lower()
        processed["timeframe"] = timeframe
        processed = processed.reset_index()
        processed_path = (
            paths.processed_data
            / f"mars_hyp_b_features_{symbol.lower()}_{timeframe}_{stamp}.parquet"
        )
        processed.to_parquet(processed_path)
        print(f"      saved processed features → {processed_path}")

    # --- 4. Time-series split (NO shuffle) ---
    print("[4/8] Time-series split (chronological) ...")
    split = time_series_split(
        X.index, train_ratio=train_ratio, val_ratio=val_ratio, test_ratio=test_ratio
    )
    print(split.describe())

    X_train = X.loc[split.train_idx]
    y_train = y.loc[split.train_idx]
    X_val = X.loc[split.val_idx] if len(split.val_idx) > 0 else None
    y_val = y.loc[split.val_idx] if len(split.val_idx) > 0 else None
    X_test = X.loc[split.test_idx]
    y_test = y.loc[split.test_idx]

    # --- 5. Train XGBoost regressor ---
    print("[5/8] Training XGBoost regressor ...")
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
    xgb_reg = XGBoostRegressorModel(name="mars_hyp_b_xgb_regressor", **common_xgb)

    if X_val is not None and len(X_val) > 0:
        xgb_reg.params["early_stopping_rounds"] = 30
        try:
            xgb_reg.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
        except TypeError:
            xgb_reg.params.pop("early_stopping_rounds", None)
            xgb_reg.fit(X_train, y_train)
    else:
        xgb_reg.fit(X_train, y_train)

    # --- 6. Train GARCH baseline (CARR range-GARCH for fair ATR comparison) ---
    print("[6/8] Training CARR range-GARCH baseline ...")
    garch = GARCHBaseline(variant="carr", window=20)
    # CARR GARCH operates on daily session data — fit on session-level range series
    # We pass the session meta which has session_open, session_close, session_high, session_low
    garch.fit(session_meta, X_train.index)

    # --- 7. Evaluate with TEST SET GUARD ---
    # Must pass before touching test data for any registered hypothesis
    exp_log = ExperimentLog(hypothesis_root=DEFAULT_CONFIG.paths.hypotheses)
    exp_log.assert_can_evaluate_on_test("HYP-B-001")

    print("[7/8] Evaluating out-of-sample ...")
    xgb_test_pred = xgb_reg.predict(X_test)
    garch_test_pred = garch.predict(session_meta, X_test.index)

    xgb_test_reg = regression_metrics(y_test, xgb_test_pred)
    garch_test_reg = regression_metrics(y_test, garch_test_pred)

    val_metrics = None
    if X_val is not None and len(X_val) > 0:
        xgb_val_pred = xgb_reg.predict(X_val)
        garch_val_pred = garch.predict(session_meta, X_val.index)
        xgb_val_reg = regression_metrics(y_val, xgb_val_pred)
        garch_val_reg = regression_metrics(y_val, garch_val_pred)
        val_metrics = {
            "xgb": xgb_val_reg,
            "garch": garch_val_reg,
        }

    train_pred = xgb_reg.predict(X_train)
    xgb_train_reg = regression_metrics(y_train, train_pred)

    # --- 8. Report + save models ---
    print("[8/8] Writing report and models ...")
    xgb_path = paths.models / f"mars_hyp_b_xgb_regressor_{stamp}.joblib"
    garch_path = paths.models / f"mars_hyp_b_garch_baseline_{stamp}.joblib"
    report_path = paths.reports / f"mars_hyp_b_baseline_{stamp}.txt"

    if save_artifacts:
        paths.models.mkdir(parents=True, exist_ok=True)
        paths.reports.mkdir(parents=True, exist_ok=True)
        xgb_reg.save(xgb_path)
        garch.save(garch_path)

    assumptions = """
ASSUMPTIONS & LEAKAGE NOTES
---------------------------
- Features use only COMPLETED sessions (no partial-session data).
- session:current_session_range = range of the most recently closed session.
- realized_vol_trailing_5/_20 = rolling over COMPLETED sessions only.
- Labels = next_session_atr_pct = ATR of NEXT session / close of current session.
- Features computed at session CLOSE; labels from NEXT session — strict no-lookahead.
- Session boundaries (UTC fixed): Asia 00-08, London 08-17, NY 13-22, Overlap 13-17.
- Overlap is its own 4th session category in session_dummy.
- Split is chronological (train → val → test); no random shuffle.
- GARCH baseline: CARR range-GARCH (not return-GARCH with flat √24 scaling).
  This avoids the unfair return-vol→range conversion and uses the same range target.
- XGBoost gets session-dummy features; GARCH gets session-specific range series.
""".strip()

    sections = [
        f"Symbol: {symbol}  Timeframe: {timeframe}",
        f"Source data: {data_path}",
        f"Processed features: {processed_path}",
        "",
        "PERIODS",
        split.describe(),
        "",
        "TRAIN regression metrics (XGB)",
        f"MAE={xgb_train_reg['mae']:.6f}  RMSE={xgb_train_reg['rmse']:.6f}  R2={xgb_train_reg['r2']:.4f}",
        "",
        "VALIDATION regression metrics"
        if val_metrics
        else "VALIDATION: (empty — val_ratio=0)",
        (
            f"XGB: MAE={val_metrics['xgb']['mae']:.6f}  RMSE={val_metrics['xgb']['rmse']:.6f}  R2={val_metrics['xgb']['r2']:.4f}\n"
            f"GARCH: MAE={val_metrics['garch']['mae']:.6f}  RMSE={val_metrics['garch']['rmse']:.6f}  R2={val_metrics['garch']['r2']:.4f}"
            if val_metrics
            else ""
        ),
        "",
        "TEST (out-of-sample) regression metrics",
        f"XGB: MAE={xgb_test_reg['mae']:.6f}  RMSE={xgb_test_reg['rmse']:.6f}  R2={xgb_test_reg['r2']:.4f}",
        f"GARCH: MAE={garch_test_reg['mae']:.6f}  RMSE={garch_test_reg['rmse']:.6f}  R2={garch_test_reg['r2']:.4f}",
        "",
        "GARCH COMPARISON (primary hypothesis test):",
        f"  XGB beats GARCH on test MAE: {xgb_test_reg['mae'] < garch_test_reg['mae']}",
        f"  XGB beats GARCH on test R²:  {xgb_test_reg['r2'] > garch_test_reg['r2']}",
        f"  MAE difference (GARCH - XGB): {garch_test_reg['mae'] - xgb_test_reg['mae']:.6f}",
        f"  R² difference (XGB - GARCH):  {xgb_test_reg['r2'] - garch_test_reg['r2']:.4f}",
        "",
        f"XGBoost saved: {xgb_path if save_artifacts else '(not saved)'}",
        f"GARCH saved:  {garch_path if save_artifacts else '(not saved)'}",
        "",
        assumptions,
    ]

    if save_artifacts:
        write_text_report(report_path, sections, title="M.A.R.S. Hyp-B Session Volatility Baseline")

    summary = (
        f"M.A.R.S. Hyp-B baseline complete | "
        f"XGB test MAE={xgb_test_reg['mae']:.6f} R2={xgb_test_reg['r2']:.4f} | "
        f"GARCH test MAE={garch_test_reg['mae']:.6f} R2={garch_test_reg['r2']:.4f} | "
        f"n_test={len(X_test)}"
    )

    return {
        "summary": summary,
        "train_metrics": {"xgb": xgb_train_reg},
        "val_metrics": val_metrics,
        "test_metrics": {"xgb": xgb_test_reg, "garch": garch_test_reg},
        "split": split,
        "report_path": str(report_path) if save_artifacts else None,
        "xgb_path": str(xgb_path) if save_artifacts else None,
        "garch_path": str(garch_path) if save_artifacts else None,
        "processed_path": str(processed_path) if processed_path else None,
        "n_samples": len(X),
        "feature_names": list(X.columns),
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run M.A.R.S. XAUUSD Hyp-B baseline pipeline.")
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
    result = run_hyp_b_pipeline(
        data_path,
        symbol=args.symbol.upper(),
        timeframe=args.timeframe.lower(),
        train_ratio=args.train_ratio,
        val_ratio=args.val_ratio,
        test_ratio=args.test_ratio,
        save_artifacts=True,
    )
    print(result["summary"])
    print(f"Report: {result['report_path']}")


if __name__ == "__main__":
    main()