"""
Break of Structure (BOS) and Change of Character (CHOCH) detectors.
 
Built on top of an interchangeable BaseSwingDetector.
These are research structure labels — not trading signals.
"""
 
from __future__ import annotations
 
from dataclasses import dataclass
from typing import Literal, Optional
 
import numpy as np
import pandas as pd
 
from mars.features.market_structure.swings import BaseSwingDetector, FractalSwingDetector, SwingPoint
 
 
StructureKind = Literal["bos_bull", "bos_bear", "choch_bull", "choch_bear"]
 
 
@dataclass(frozen=True)
class StructureEvent:
    index: pd.Timestamp
    kind: StructureKind
    level: float
    bar_position: int
    confidence: float = 1.0
 
 
class BOSDetector:
    """
    Break of Structure: close beyond the most recent opposite swing.
 
    Bullish BOS: close > last swing high while trend context is bullish
    (last swing sequence HH/HL). Simplified research definition.
    """
 
    name = "bos"
    version = "1.0.0"
 
    def __init__(self, swing_detector: Optional[BaseSwingDetector] = None) -> None:
        self.swing_detector = swing_detector or FractalSwingDetector()
 
    def detect(self, df: pd.DataFrame) -> list[StructureEvent]:
        swings = self.swing_detector.detect(df)
        if len(swings) < 2:
            return []
 
        events: list[StructureEvent] = []
        last_sh: Optional[SwingPoint] = None
        last_sl: Optional[SwingPoint] = None
        close = df["close"].to_numpy(dtype=float)
 
        # Process bars in order; update swing memory when swings confirm
        swing_by_bar = {s.bar_position: s for s in swings}
 
        for i in range(len(df)):
            if i in swing_by_bar:
                s = swing_by_bar[i]
                if s.kind == "high":
                    last_sh = s
                else:
                    last_sl = s
 
            if last_sh is not None and close[i] > last_sh.price:
                # only emit once per level
                events.append(
                    StructureEvent(
                        index=df.index[i],
                        kind="bos_bull",
                        level=last_sh.price,
                        bar_position=i,
                        confidence=last_sh.confidence,
                    )
                )
                last_sh = None  # consume level
            if last_sl is not None and close[i] < last_sl.price:
                events.append(
                    StructureEvent(
                        index=df.index[i],
                        kind="bos_bear",
                        level=last_sl.price,
                        bar_position=i,
                        confidence=last_sl.confidence,
                    )
                )
                last_sl = None
 
        return events
 
    def to_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        events = self.detect(df)
        out = pd.DataFrame(
            {
                "bos_bull": 0.0,
                "bos_bear": 0.0,
                "bos_level": np.nan,
                "bos_confidence": np.nan,
            },
            index=df.index,
        )
        for e in events:
            if e.kind == "bos_bull":
                out.iloc[e.bar_position, out.columns.get_loc("bos_bull")] = 1.0
            elif e.kind == "bos_bear":
                out.iloc[e.bar_position, out.columns.get_loc("bos_bear")] = 1.0
            out.iloc[e.bar_position, out.columns.get_loc("bos_level")] = e.level
            out.iloc[e.bar_position, out.columns.get_loc("bos_confidence")] = e.confidence
        return out
 
 
class CHOCHDetector:
    """
    Change of Character: first break against the prior structure bias.
 
    Research heuristic:
        After a bullish BOS sequence, a break of last swing low → CHOCH bear.
        After a bearish BOS sequence, a break of last swing high → CHOCH bull.
    """
 
    name = "choch"
    version = "1.0.0"
 
    def __init__(self, swing_detector: Optional[BaseSwingDetector] = None) -> None:
        self.swing_detector = swing_detector or FractalSwingDetector()
        self.bos = BOSDetector(self.swing_detector)
 
    def detect(self, df: pd.DataFrame) -> list[StructureEvent]:
        bos_events = self.bos.detect(df)
        if not bos_events:
            return []
 
        swings = self.swing_detector.detect(df)
        last_sh: Optional[SwingPoint] = None
        last_sl: Optional[SwingPoint] = None
        bias: Optional[str] = None  # "bull" | "bear"
        close = df["close"].to_numpy(dtype=float)
        swing_by_bar = {s.bar_position: s for s in swings}
        bos_by_bar = {e.bar_position: e for e in bos_events}
 
        events: list[StructureEvent] = []
        for i in range(len(df)):
            if i in swing_by_bar:
                s = swing_by_bar[i]
                if s.kind == "high":
                    last_sh = s
                else:
                    last_sl = s
            if i in bos_by_bar:
                be = bos_by_bar[i]
                if be.kind == "bos_bull":
                    bias = "bull"
                elif be.kind == "bos_bear":
                    bias = "bear"
 
            if bias == "bull" and last_sl is not None and close[i] < last_sl.price:
                events.append(
                    StructureEvent(
                        index=df.index[i],
                        kind="choch_bear",
                        level=last_sl.price,
                        bar_position=i,
                        confidence=last_sl.confidence,
                    )
                )
                bias = "bear"
                last_sl = None
            elif bias == "bear" and last_sh is not None and close[i] > last_sh.price:
                events.append(
                    StructureEvent(
                        index=df.index[i],
                        kind="choch_bull",
                        level=last_sh.price,
                        bar_position=i,
                        confidence=last_sh.confidence,
                    )
                )
                bias = "bull"
                last_sh = None
 
        return events
 
    def to_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        events = self.detect(df)
        out = pd.DataFrame(
            {
                "choch_bull": 0.0,
                "choch_bear": 0.0,
                "choch_level": np.nan,
                "choch_confidence": np.nan,
            },
            index=df.index,
        )
        for e in events:
            if e.kind == "choch_bull":
                out.iloc[e.bar_position, out.columns.get_loc("choch_bull")] = 1.0
            elif e.kind == "choch_bear":
                out.iloc[e.bar_position, out.columns.get_loc("choch_bear")] = 1.0
            out.iloc[e.bar_position, out.columns.get_loc("choch_level")] = e.level
            out.iloc[e.bar_position, out.columns.get_loc("choch_confidence")] = e.confidence
        return out