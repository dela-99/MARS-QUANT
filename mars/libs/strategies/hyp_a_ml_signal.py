"""Hypothesis A ML direction strategy — maps model predictions to trade setups."""

from __future__ import annotations

from typing import Any, List, Optional

import numpy as np
import pandas as pd

from mars.libs.models.base import BaseModel
from mars.libs.strategies.base import BaseStrategy, TradeSetup


class HypAMLDirectionStrategy(BaseStrategy):
    """
    One decision per day: long if model predicts bullish London, short if bearish.

    Expects a feature matrix aligned by date and a fitted classifier.
    """

    def __init__(
        self,
        model: BaseModel,
        symbol: str = "XAUUSD",
        min_confidence: Optional[float] = None,
    ) -> None:
        super().__init__(name="hyp_a_ml_direction", symbol=symbol)
        self.model = model
        self.min_confidence = min_confidence

    def generate_setups(
        self,
        market_data: pd.DataFrame,
        *,
        features: Optional[pd.DataFrame] = None,
        **kwargs: Any,
    ) -> List[TradeSetup]:
        if features is None:
            raise ValueError("HypAMLDirectionStrategy requires `features=` DataFrame.")

        preds = self.model.predict(features)
        confidences: Optional[np.ndarray] = None
        try:
            proba = self.model.predict_proba(features)
            # binary: column 1 = P(bullish)
            if proba.ndim == 2 and proba.shape[1] >= 2:
                confidences = proba[:, 1]
            else:
                confidences = proba.ravel()
        except NotImplementedError:
            confidences = None

        setups: List[TradeSetup] = []
        for i, (idx, row_pred) in enumerate(zip(features.index, preds)):
            conf = float(confidences[i]) if confidences is not None else None
            if self.min_confidence is not None and conf is not None:
                # for shorts, confidence is distance from 0.5 toward predicted class
                side_conf = conf if int(row_pred) == 1 else 1.0 - conf
                if side_conf < self.min_confidence:
                    continue

            side = "long" if int(row_pred) == 1 else "short"
            ts = pd.Timestamp(idx).to_pydatetime()
            setups.append(
                TradeSetup(
                    timestamp=ts,
                    symbol=self.symbol,
                    side=side,
                    confidence=conf,
                    rationale=(
                        f"Hyp-A Asia→London model predicts "
                        f"{'bullish' if side == 'long' else 'bearish'} London session."
                    ),
                    metadata={"feature_date": str(idx), "raw_prediction": int(row_pred)},
                )
            )
        return setups
