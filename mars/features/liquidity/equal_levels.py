"""Equal highs / equal lows detection with tolerance-based confidence."""
 
from __future__ import annotations
 
from dataclasses import dataclass
from typing import Literal, Optional
 
import numpy as np
import pandas as pd
 
from mars.features.market_structure.swings import BaseSwingDetector, FractalSwingDetector
 
 
LevelKind = Literal["equal_high", "equal_low"]
 
 
@dataclass(frozen=True)
class LiquidityLevel:
    price: float
    kind: LevelKind
    indices: tuple[pd.Timestamp, ...]
    bar_positions: tuple[int, ...]
    confidence: float
    n_touches: int
 
 
class EqualHighsLowsDetector:
    """
    Cluster swing highs/lows within a relative price tolerance.
 
    Confidence increases with number of touches and decreases with
    price dispersion within the cluster.
    """
 
    name = "equal_highs_lows"
    version = "1.0.0"
 
    def __init__(
        self,
        swing_detector: Optional[BaseSwingDetector] = None,
        tolerance_pct: float = 0.0005,
        min_touches: int = 2,
    ) -> None:
        self.swing_detector = swing_detector or FractalSwingDetector()
        self.tolerance_pct = tolerance_pct
        self.min_touches = min_touches
 
    def detect(self, df: pd.DataFrame) -> list[LiquidityLevel]:
        swings = self.swing_detector.detect(df)
        highs = [s for s in swings if s.kind == "high"]
        lows = [s for s in swings if s.kind == "low"]
        levels: list[LiquidityLevel] = []
        levels.extend(self._cluster(highs, "equal_high"))
        levels.extend(self._cluster(lows, "equal_low"))
        return levels
 
    def _cluster(self, swings, kind: LevelKind) -> list[LiquidityLevel]:
        if not swings:
            return []
        used = set()
        levels: list[LiquidityLevel] = []
        prices = np.array([s.price for s in swings], dtype=float)
 
        for i, s in enumerate(swings):
            if i in used:
                continue
            cluster_idx = [i]
            for j in range(i + 1, len(swings)):
                if j in used:
                    continue
                if abs(prices[j] - prices[i]) / prices[i] <= self.tolerance_pct:
                    cluster_idx.append(j)
            if len(cluster_idx) < self.min_touches:
                continue
            for j in cluster_idx:
                used.add(j)
            cluster = [swings[j] for j in cluster_idx]
            c_prices = np.array([c.price for c in cluster])
            mean_p = float(c_prices.mean())
            dispersion = float(c_prices.std() / mean_p) if mean_p else 0.0
            # confidence: more touches ↑, dispersion ↓
            conf = min(1.0, (len(cluster) / 5.0)) * max(0.0, 1.0 - dispersion / self.tolerance_pct)
            conf = float(np.clip(conf, 0.0, 1.0))
            levels.append(
                LiquidityLevel(
                    price=mean_p,
                    kind=kind,
                    indices=tuple(c.index for c in cluster),
                    bar_positions=tuple(c.bar_position for c in cluster),
                    confidence=conf,
                    n_touches=len(cluster),
                )
            )
        return levels
 
    def to_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        levels = self.detect(df)
        out = pd.DataFrame(
            {
                "eq_high": 0.0,
                "eq_low": 0.0,
                "eq_level_price": np.nan,
                "eq_level_confidence": np.nan,
                "eq_level_touches": np.nan,
            },
            index=df.index,
        )
        for lv in levels:
            for pos in lv.bar_positions:
                if lv.kind == "equal_high":
                    out.iloc[pos, out.columns.get_loc("eq_high")] = 1.0
                else:
                    out.iloc[pos, out.columns.get_loc("eq_low")] = 1.0
                out.iloc[pos, out.columns.get_loc("eq_level_price")] = lv.price
                out.iloc[pos, out.columns.get_loc("eq_level_confidence")] = lv.confidence
                out.iloc[pos, out.columns.get_loc("eq_level_touches")] = lv.n_touches
        return out