"""
M.A.R.S. V1 macro regime pipeline: DXY/real yields → regime classification (Hypothesis C).

Steps
-----
1. Fetch macro data from FRED (DXY, real yields, VIX)
2. Normalize & validate
3. Engineer macro regime features
4. Generate DXY momentum regime labels (target)
5. Chronological train / val / test split
6. Train baseline XGBoost classifier + persistence baseline
7. Evaluate out-of-sample with test-set guard
8. Write metrics report
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from mars.libs.data.loaders import load_ohlcv_parquet
from mars.libs.evaluation.metrics import classification_metrics
from mars.libs.evaluation.report import write_text_report
from mars.libs.evaluation.splits import time_series_split
from mars.libs.features.macro_regime import MacroRegimeFeatures
from mars.libs.models.xgboost_model import XGBoostClassifierModel
from mars.libs.utils.paths import ProjectPaths
from mars.research.experiment import ExperimentLog
from mars.core.config import DEFAULT_CONFIG


def run_macro_regime_pipeline(
    macro_data: dict[str, pd.DataFrame],
    *,
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
    test_ratio: float = 0.15,
    save_artifacts: bool = True,
    n_estimators: int = 500,
    paths: Optional[ProjectPaths] = None,
) -> Dict[str, Any]:
    """
    Execute the full Hyp-C macro regime baseline workflow.

    Returns a dict with metrics, paths, and a human-readable summary string.
    """
    paths = paths or ProjectPaths.from_root()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # --- 1-2. Features + labels ---
    print("[1/7] Engineering macro regime features...")
    feat_pipe = MacroRegimeFeatures()
    features, target = feat_pipe.transform_with_target(macro_data)
    print(f"      feature days={len(features)}  columns={list(features.columns)}")

    if len(features) < 50:
        raise RuntimeError(
            f"Insufficient daily samples ({len(features)}). Check macro data coverage."
        )

    # Persist processed table for research reuse
    processed_path = None
    if save_artifacts:
        paths.processed_data.mkdir(parents=True, exist_ok=True)
        processed = features.copy()
        processed["dxy_momentum_regime"] = target
        processed_path = (
            paths.processed_data
            / f"mars_hyp_c_features_{stamp}.parquet"
        )
        processed.to_parquet(processed_path)
        print(f"      saved processed features → {processed_path}")

    # --- 3. Time-series split (NO shuffle) ---
    print("[3/7] Time-series split (chronological)...")
    split = time_series_split(
        features.index, train_ratio=train_ratio, val_ratio=val_ratio, test_ratio=test_ratio
    )
    print(split.describe())

    X_train = features.loc[split.train_idx]
    y_train = target.loc[split.train_idx]
    X_val = features.loc[split.val_idx] if len(split.val_idx) > 0 else None
    y_val = target.loc[split.val_idx] if len(split.val_idx) > 0 else None
    X_test = features.loc[split.test_idx]
    y_test = target.loc[split.test_idx]

    # --- 4. Train XGBoost classifier ---
    print("[4/7] Training XGBoost classifier...")
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
    clf = XGBoostClassifierModel(name="mars_hyp_c_xgb_classifier", **common_xgb)

    if X_val is not None and len(X_val) > 0:
        clf.params["early_stopping_rounds"] = 30
        try:
            clf.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
        except TypeError:
            clf.params.pop("early_stopping_rounds", None)
            clf.fit(X_train, y_train)
    else:
        clf.fit(X_train, y_train)

    # --- 5. Persistence baseline ---
    print("[5/7] Computing persistence baseline...")
    # Persistence: yesterday's regime = today's regime
    persistence_pred = target.shift(1).loc[y_test.index].dropna()
    y_test_aligned = y_test.loc[persistence_pred.index]
    persistence_cls = classification_metrics(y_test_aligned, persistence_pred)

    # --- 5b. Non-overlapping transition baseline ---
    # Standard persistence leverages label overlap (adjacent labels share 19/20 sessions).
    # Report a harder baseline: only count predictions at genuine regime transitions.
    # "Did the regime actually change from 20 sessions ago?"
    regime_transitions = (target != target.shift(20)).astype(int)
    transition_persistence = regime_transitions.shift(1).loc[y_test.index].dropna()
    y_test_trans = (target != target.shift(20)).astype(int).loc[transition_persistence.index]
    transition_persistence_cls = classification_metrics(y_test_trans, transition_persistence)

    # --- 6. Evaluate with TEST SET GUARD ---
    from mars.research.experiment import ExperimentLog
    exp_log = ExperimentLog(hypothesis_root=DEFAULT_CONFIG.paths.hypotheses)
    exp_log.assert_can_evaluate_on_test("HYP-C-001")

    print("[6/7] Evaluating out-of-sample...")
    test_pred = clf.predict(X_test)
    test_cls = classification_metrics(y_test, test_pred)

    val_cls = None
    if X_val is not None and len(X_val) > 0:
        val_pred = clf.predict(X_val)
        val_cls = classification_metrics(y_val, val_pred)

    train_pred = clf.predict(X_train)
    train_cls = classification_metrics(y_train, train_pred)

    # --- 7. Report + save models ---
    print("[7/7] Writing report and models...")
    clf_path = paths.models / f"mars_hyp_c_xgb_classifier_{stamp}.joblib"
    report_path = paths.reports / f"mars_hyp_c_baseline_{stamp}.txt"

    if save_artifacts:
        paths.models.mkdir(parents=True, exist_ok=True)
        paths.reports.mkdir(parents=True, exist_ok=True)
        clf.save(clf_path)

    # Class balance report
    train_dist = y_train.value_counts(normalize=True).to_dict()
    val_dist = y_val.value_counts(normalize=True).to_dict() if y_val is not None else {}
    test_dist = y_test.value_counts(normalize=True).to_dict()

    assumptions = """
ASSUMPTIONS & LEAKAGE NOTES
---------------------------
- Target: DXY 20-session momentum regime (ternary: risk-on/neutral/risk-off)
- Labels derived purely from DXY close prices; no XAUUSD data used in label
- Features: DXY momentum (5/20), real yield level/momentum, VIX level/momentum
- Split is chronological (train → val → test); no random shuffle
- Baseline: naive persistence (yesterday's regime = today's regime)
  NOTE: Label has built-in autocorrelation (19/20 session overlap in 20-session momentum).
  Persistence baseline is artificially high (~90%+). See transition baseline below.
- XGBoost must beat persistence on test accuracy/F1 to justify complexity
- Transition baseline: predicts regime transitions only (regime != 20 sessions ago)
  This removes the built-in autocorrelation and is the true test of skill.
- XGBoost must beat transition persistence on transition accuracy to show real skill.
- FRED data ingested with 1-business-day publication lag (timestamp = available date).
- Features use forward-fill of last known FRED value (last known value as of date).
- Purged CV and walk-forward validation NOT yet applied; planned for next phase
""".strip()

    sections = [
        f"Symbol: Macro Regime (DXY/Real Yields/VIX)",
        f"Source: FRED (DXY, DFII10, VIXCLS)",
        f"Processed features: {processed_path}",
        "",
        "PERIODS",
        split.describe(),
        "",
        "CLASS BALANCE",
        f"Train: {train_dist}",
        f"Val:   {val_dist}" if val_dist else "Val:   (empty)",
        f"Test:  {test_dist}",
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
        "PERSISTENCE BASELINE (test) — uses built-in label autocorrelation",
        f"accuracy={persistence_cls['accuracy']:.4f}  f1={persistence_cls['f1']:.4f}",
        persistence_cls["report"],
        "",
        "TRANSITION BASELINE (test) — genuine regime changes only (no label overlap)",
        f"accuracy={transition_persistence_cls['accuracy']:.4f}  f1={transition_persistence_cls['f1']:.4f}",
        transition_persistence_cls["report"],
        "",
        "MODEL vs BASELINES COMPARISON",
        f"  XGB test accuracy:       {test_cls['accuracy']:.4f}",
        f"  Persistence accuracy:    {persistence_cls['accuracy']:.4f} (with label autocorrelation)",
        f"  Transition accuracy:     {transition_persistence_cls['accuracy']:.4f} (genuine changes only)",
        f"  XGB beats persistence:   {test_cls['accuracy'] > persistence_cls['accuracy']}",
        f"  XGB beats transition:    {test_cls['accuracy'] > transition_persistence_cls['accuracy']}",
        f"  XGB test F1:             {test_cls['f1']:.4f}",
        f"  Persistence F1:          {persistence_cls['f1']:.4f}",
        f"  Transition F1:           {transition_persistence_cls['f1']:.4f}",
        f"  XGB beats transition F1: {test_cls['f1'] > transition_persistence_cls['f1']}",
        "",
        f"XGBoost saved: {clf_path if save_artifacts else '(not saved)'}",
        "",
        assumptions,
    ]

    if save_artifacts:
        write_text_report(report_path, sections, title="M.A.R.S. Hyp-C Macro Regime Baseline")

    summary = (
        f"M.A.R.S. Hyp-C baseline complete | "
        f"XGB test acc={test_cls['accuracy']:.4f} f1={test_cls['f1']:.4f} | "
        f"Persistence acc={persistence_cls['accuracy']:.4f} f1={persistence_cls['f1']:.4f} | "
        f"XGB beats persistence: {test_cls['accuracy'] > persistence_cls['accuracy']} | "
        f"n_test={len(X_test)}"
    )

    return {
        "summary": summary,
        "train_metrics": train_cls,
        "val_metrics": val_cls,
        "test_metrics": test_cls,
        "persistence_metrics": persistence_cls,
        "split": split,
        "report_path": str(report_path) if save_artifacts else None,
        "classifier_path": str(clf_path) if save_artifacts else None,
        "processed_path": str(processed_path) if processed_path else None,
        "n_samples": len(features),
        "feature_names": list(features.columns),
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run M.A.R.S. Hyp-C macro regime baseline pipeline.")
    parser.add_argument("--start", type=str, default="2003-01-01")
    parser.add_argument("--end", type=str, default=None)
    parser.add_argument("--train-ratio", type=float, default=0.70)
    parser.add_argument("--val-ratio", type=float, default=0.15)
    parser.add_argument("--test-ratio", type=float, default=0.15)
    args = parser.parse_args()

    # This pipeline expects macro data to be pre-fetched and loaded
    # In practice, you'd run fetch_macro_data.py first, then load the parquet files
    raise NotImplementedError(
        "This pipeline expects pre-loaded macro_data dict. "
        "Run fetch_macro_data.py first, then load the parquet files, "
        "then call run_macro_regime_pipeline(macro_data=...) directly."
    )


if __name__ == "__main__":
    main()