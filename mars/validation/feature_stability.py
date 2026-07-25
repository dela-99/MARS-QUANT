"""Feature stability across time folds."""
 
from __future__ import annotations
 
from typing import Optional
 
import numpy as np
import pandas as pd
 
from mars.validation.walk_forward import WalkForwardSplitter
 
 
def feature_stability_score(
    feature: pd.Series,
    train_size: int = 200,
    test_size: int = 50,
    method: str = "rank_corr",
) -> dict[str, float]:
    """
    Measure stability of a feature's distribution / ranking across folds.
 
    method:
        rank_corr — mean Spearman corr of feature values vs time-index ranks
                    within each train fold (captures regime consistency of ranks)
        mean_cv   — coefficient of variation of fold means
 
    Returns mean stability score and std across folds.
    """
    clean = feature.dropna()
    if len(clean) < train_size + test_size:
        return {"stability_mean": float("nan"), "stability_std": float("nan"), "n_folds": 0.0}
 
    splitter = WalkForwardSplitter(train_size=train_size, test_size=test_size, mode="rolling")
    scores: list[float] = []
 
    values = clean.to_numpy(dtype=float)
    for train_idx, _ in splitter.split(values):
        fold = values[train_idx]
        if method == "mean_cv":
            # accumulate for later — skip per-fold here
            scores.append(float(np.mean(fold)))
        else:
            # Spearman of feature vs position (identity if stable trend; abs for magnitude)
            ranks = pd.Series(fold).rank().to_numpy()
            pos = np.arange(len(fold), dtype=float)
            if len(fold) < 5:
                continue
            corr = pd.Series(ranks).corr(pd.Series(pos), method="spearman")
            # Stability as 1 - |trend corr| for mean-reverting features is domain-specific;
            # we report |corr| as a diagnostic, not a quality score.
            scores.append(float(abs(corr)) if corr == corr else float("nan"))
 
    if method == "mean_cv":
        arr = np.array(scores, dtype=float)
        mu = float(np.nanmean(arr))
        sd = float(np.nanstd(arr))
        cv = float(sd / abs(mu)) if mu != 0 else float("nan")
        return {
            "stability_mean": cv,  # lower CV = more stable means
            "stability_std": sd,
            "n_folds": float(len(scores)),
        }
 
    arr = np.asarray(scores, dtype=float)
    return {
        "stability_mean": float(np.nanmean(arr)) if len(arr) else float("nan"),
        "stability_std": float(np.nanstd(arr)) if len(arr) else float("nan"),
        "n_folds": float(len(arr)),
    }