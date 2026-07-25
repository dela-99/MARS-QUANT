"""Liquidity sweep detection (research definition with confidence)."""
 
from __future__ import annotations
 
from dataclasses import dataclass
from typing import Literal, Optional
 
import numpy as np
import pandas as pd
 
from mars.features.liquidity.equal_levels import EqualHighsLowsDetector, LiquidityLevel
 
 
SweepKind = Literal["sweep_high", "sweep_low"]
 
 
@dataclass(frozen=True)
class LiquiditySweep:
    index: pd.Timestamp
    kind: SweepKind
    level: float
    bar_position: int
    confidence: float
    reclaim: bool
 
 
class LiquiditySweepDetector:
    """
    A sweep is defined (research heuristic) as:
        - high pierces an equal-high pool then close returns below the pool, OR
        - low pierces an equal-low pool then close returns above the pool
 
    ``reclaim`` indicates close reclaimed inside the range (common sweep pattern).
    """
 
    name = "liquidity_sweep"
    version = "1.0.0"
 
    def __init__(
        self,
        level_detector: Optional[EqualHighsLowsDetector] = None,
        pierce_pct: float = 0.0001,
    ) -> None:
        self.level_detector = level_detector or EqualHighsLowsDetector()
        self.pierce_pct = pierce_pct
 
    def detect(self, df: pd.DataFrame) -> list[LiquiditySweep]:
        levels = self.level_detector.detect(df)
        if not levels:
            return []
 
        high = df["high"].to_numpy(dtype=float)
        low = df["low"].to_numpy(dtype=float)
        close = df["close"].to_numpy(dtype=float)
        sweeps: list[LiquiditySweep] = []
 
        # Active levels after they form (max bar position of touches)
        active: list[tuple[int, LiquidityLevel]] = []
        for lv in levels:
            form_bar = max(lv.bar_positions)
            active.append((form_bar, lv))
 
        for form_bar, lv in active:
            for i in range(form_bar + 1, len(df)):
                if lv.kind == "equal_high":
                    pierced = high[i] > lv.price * (1 + self.pierce_pct)
                    reclaimed = close[i] < lv.price
                    if pierced:
                        sweeps.append(
                            LiquiditySweep(
                                index=df.index[i],
                                kind="sweep_high",
                                level=lv.price,
                                bar_position=i,
                                confidence=lv.confidence * (0.8 + 0.2 * float(reclaimed)),
                                reclaim=bool(reclaimed),
                            )
                        )
                        break
                else:
                    pierced = low[i] < lv.price * (1 - self.pierce_pct)
                    reclaimed = close[i] > lv.price
                    if pierced:
                        sweeps.append(
                            LiquiditySweep(
                                index=df.index[i],
                                kind="sweep_low",
                                level=lv.price,
                                bar_position=i,
                                confidence=lv.confidence * (0.8 + 0.2 * float(reclaimed)),
                                reclaim=bool(reclaimed),
                            )
                        )
                        break
        return sweeps
 
    def to_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        sweeps = self.detect(df)
        out = pd.DataFrame(
            {
                "sweep_high": 0.0,
                "sweep_low": 0.0,
                "sweep_level": np.nan,
                "sweep_confidence": np.nan,
                "sweep_reclaim": 0.0,
            },
            index=df.index,
        )
        for s in sweeps:
            if s.kind == "sweep_high":
                out.iloc[s.bar_position, out.columns.get_loc("sweep_high")] = 1.0
            else:
                out.iloc[s.bar_position, out.columns.get_loc("sweep_low")] = 1.0
            out.iloc[s.bar_position, out.columns.get_loc("sweep_level")] = s.level
            out.iloc[s.bar_position, out.columns.get_loc("sweep_confidence")] = s.confidence
            out.iloc[s.bar_position, out.columns.get_loc("sweep_reclaim")] = float(s.reclaim)
        return out