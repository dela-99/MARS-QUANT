"""Evaluation metrics for classification and regression."""

from __future__ import annotations

from typing import Any, Dict

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
)


def classification_metrics(y_true, y_pred) -> Dict[str, Any]:
    """Standard binary/multiclass metrics + full text report."""
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    
    # Determine if binary or multiclass
    unique_classes = np.unique(np.concatenate([y_true, y_pred]))
    is_binary = len(unique_classes) <= 2
    
    average = "binary" if is_binary else "macro"
    
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0, average=average)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0, average=average)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0, average=average)),
        "confusion_matrix": confusion_matrix(y_true, y_pred).tolist(),
        "report": classification_report(
            y_true, y_pred, target_names=[str(c) for c in sorted(np.unique(y_true))], zero_division=0
        ),
    }


def regression_metrics(y_true, y_pred) -> Dict[str, Any]:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    mse = mean_squared_error(y_true, y_pred)
    return {
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "rmse": float(np.sqrt(mse)),
        "r2": float(r2_score(y_true, y_pred)),
    }


def directional_hit_rate(y_true_direction, y_pred_direction) -> float:
    """Share of days where predicted direction matches realized direction."""
    y_true_direction = np.asarray(y_true_direction)
    y_pred_direction = np.asarray(y_pred_direction)
    if len(y_true_direction) == 0:
        return float("nan")
    return float((y_true_direction == y_pred_direction).mean())
