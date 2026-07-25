"""
Experimental order-block detector.
 
This is intentionally marked experimental. Definitions vary widely
across discretionary literature; this module exists so researchers can
test a formal, versioned definition — not as a validated edge.
"""
 
from __future__ import annotations
 
from dataclasses import dataclass
from typing import Literal, Optional
 
import numpy as np
import pandas as pd
 
from mars.features.market_structure.structure import BOSDetector
from mars.features.market_structure.swings import BaseSwingDetector, FractalSwingDetector
 
 
OBKind = Literal["bullish_ob", "bearish_ob"]
 
 
@dataclass(frozen=True)
class OrderBlock:
    index: pd.Timestamp
    kind: OBKind
    high: float
    low: float
    bar_position: int
    confidence: float
    experimental: bool = True
 
 
class ExperimentalOrderBlockDetector:
    """
    Research definition (one of many possible):
        After a bullish BOS, the last bearish candle before the impulse
        is a candidate bullish order block (and vice versa).
 
    Always experimental=True. Not registered in the default feature set.
    """
 
    name = "experimental_order_block"
    version = "0.1.0"
    experimental = True
 
    def __init__(self, swing_detector: Optional[BaseSwingDetector] = None) -> None:
        self.swing_detector = swing_detector or FractalSwingDetector()
        self.bos = BOSDetector(self.swing_detector)
 
    def detect(self, df: pd.DataFrame) -> list[OrderBlock]:
        events = self.bos.detect(df)
        if not events:
            return []
 
        o = df["open"].to_numpy(dtype=float)
        h = df["high"].to_numpy(dtype=float)
        l = df["low"].to_numpy(dtype=float)
        c = df["close"].to_numpy(dtype=float)
        blocks: list[OrderBlock] = []
 
        for e in events:
            i = e.bar_position
            # search back up to 10 bars for opposite candle
            start = max(0, i - 10)
            if e.kind == "bos_bull":
                for j in range(i - 1, start - 1, -1):
                    if c[j] < o[j]:  # bearish candle
                        blocks.append(
                            OrderBlock(
                                index=df.index[j],
                                kind="bullish_ob",
                                high=float(h[j]),
                                low=float(l[j]),
                                bar_position=j,
                                confidence=0.5 * e.confidence,  # deliberately low
                            )
                        )
                        break
            elif e.kind == "bos_bear":
                for j in range(i - 1, start - 1, -1):
                    if c[j] > o[j]:  # bullish candle
                        blocks.append(
                            OrderBlock(
                                index=df.index[j],
                                kind="bearish_ob",
                                high=float(h[j]),
                                low=float(l[j]),
                                bar_position=j,
                                confidence=0.5 * e.confidence,
                            )
                        )
                        break
        return blocks
 
    def to_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        blocks = self.detect(df)
        out = pd.DataFrame(
            {
                "ob_bullish": 0.0,
                "ob_bearish": 0.0,
                "ob_high": np.nan,
                "ob_low": np.nan,
                "ob_confidence": np.nan,
            },
            index=df.index,
        )
        for b in blocks:
            if b.kind == "bullish_ob":
                out.iloc[b.bar_position, out.columns.get_loc("ob_bullish")] = 1.0
            else:
                out.iloc[b.bar_position, out.columns.get_loc("ob_bearish")] = 1.0
            out.iloc[b.bar_position, out.columns.get_loc("ob_high")] = b.high
            out.iloc[b.bar_position, out.columns.get_loc("ob_low")] = b.low
            out.iloc[b.bar_position, out.columns.get_loc("ob_confidence")] = b.co