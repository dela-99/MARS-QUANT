"""
Interchangeable swing detectors.
 
Implementations:
    FractalSwingDetector  — classic N-bar fractal highs/lows
    ZigZagSwingDetector   — threshold-based zigzag pivots
    AdaptiveSwingDetector — ATR-scaled zigzag threshold
"""
 
from __future__ import annotations
 
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal, Optional
 
import numpy as np
import pandas as pd
 
 
SwingKind = Literal["high", "low"]
 
 
@dataclass(frozen=True)
class SwingPoint:
    """A confirmed swing high or low (confirmed only after lookback)."""
 
    index: pd.Timestamp
    price: float
    kind: SwingKind
    bar_position: int  # integer location in the source frame
    confidence: float = 1.0
 
 
class BaseSwingDetector(ABC):
    """Interface for swing high/low detection."""
 
    name: str = "base_swing"
    version: str = "0.1.0"
 
    @abstractmethod
    def detect(self, df: pd.DataFrame) -> list[SwingPoint]:
        """
        Detect swing points.
 
        CRITICAL: A swing at bar i may only be *confirmed* after sufficient
        future bars exist relative to the detector's confirmation window.
        Implementations must not emit unconfirmed swings as final.
        For research features that attach to bar t, use only swings
        confirmed at or before t (no look-ahead in feature series).
        """
        ...
 
    def to_series(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Encode swings as columns aligned to ``df.index``.
 
        Columns:
            swing_high: price at confirmed swing high else NaN
            swing_low:  price at confirmed swing low else NaN
            swing_high_conf / swing_low_conf: confidence scores
        """
        swings = self.detect(df)
        out = pd.DataFrame(
            {
                "swing_high": np.nan,
                "swing_low": np.nan,
                "swing_high_conf": np.nan,
                "swing_low_conf": np.nan,
            },
            index=df.index,
        )
        for s in swings:
            if s.kind == "high":
                out.iloc[s.bar_position, out.columns.get_loc("swing_high")] = s.price
                out.iloc[s.bar_position, out.columns.get_loc("swing_high_conf")] = s.confidence
            else:
                out.iloc[s.bar_position, out.columns.get_loc("swing_low")] = s.price
                out.iloc[s.bar_position, out.columns.get_loc("swing_low_conf")] = s.confidence
        return out
 
 
class FractalSwingDetector(BaseSwingDetector):
    """
    N-bar fractal: a high is a swing high if it is strictly greater than
    ``left`` bars before and ``right`` bars after.
 
    Confirmation lag = ``right`` bars (no look-ahead when labeling at confirm bar).
    """
 
    name = "fractal_swing"
    version = "1.0.0"
 
    def __init__(self, left: int = 2, right: int = 2) -> None:
        if left < 1 or right < 1:
            raise ValueError("left and right must be >= 1")
        self.left = left
        self.right = right
 
    def detect(self, df: pd.DataFrame) -> list[SwingPoint]:
        high = df["high"].to_numpy(dtype=float)
        low = df["low"].to_numpy(dtype=float)
        n = len(df)
        swings: list[SwingPoint] = []
 
        for i in range(self.left, n - self.right):
            window_h = high[i - self.left : i + self.right + 1]
            window_l = low[i - self.left : i + self.right + 1]
            # Confirm at bar i+right (no future beyond confirmation)
            confirm_i = i + self.right
 
            if high[i] == window_h.max() and (window_h == high[i]).sum() == 1:
                swings.append(
                    SwingPoint(
                        index=df.index[confirm_i],
                        price=float(high[i]),
                        kind="high",
                        bar_position=confirm_i,
                        confidence=1.0,
                    )
                )
            if low[i] == window_l.min() and (window_l == low[i]).sum() == 1:
                swings.append(
                    SwingPoint(
                        index=df.index[confirm_i],
                        price=float(low[i]),
                        kind="low",
                        bar_position=confirm_i,
                        confidence=1.0,
                    )
                )
        return swings
 
 
class ZigZagSwingDetector(BaseSwingDetector):
    """
    ZigZag pivots: reverse when price moves ``threshold_pct`` from last pivot.
 
    Confirmation is approximate (pivot confirmed when reverse occurs).
    """
 
    name = "zigzag_swing"
    version = "1.0.0"
 
    def __init__(self, threshold_pct: float = 0.005) -> None:
        if threshold_pct <= 0:
            raise ValueError("threshold_pct must be > 0")
        self.threshold_pct = threshold_pct
 
    def detect(self, df: pd.DataFrame) -> list[SwingPoint]:
        high = df["high"].to_numpy(dtype=float)
        low = df["low"].to_numpy(dtype=float)
        close = df["close"].to_numpy(dtype=float)
        n = len(df)
        if n < 2:
            return []
 
        swings: list[SwingPoint] = []
        # Start with direction unknown; track last pivot
        last_pivot_price = close[0]
        last_pivot_i = 0
        direction: Optional[int] = None  # +1 up, -1 down
 
        for i in range(1, n):
            move = (close[i] - last_pivot_price) / last_pivot_price
            if direction is None:
                if abs(move) >= self.threshold_pct:
                    direction = 1 if move > 0 else -1
                    last_pivot_price = close[i]
                    last_pivot_i = i
                continue
 
            if direction == 1:
                # tracking up-leg; update extreme high
                if high[i] > last_pivot_price:
                    last_pivot_price = high[i]
                    last_pivot_i = i
                elif (last_pivot_price - low[i]) / last_pivot_price >= self.threshold_pct:
                    # confirm swing high at last extreme
                    swings.append(
                        SwingPoint(
                            index=df.index[i],
                            price=float(last_pivot_price),
                            kind="high",
                            bar_position=i,
                            confidence=min(1.0, abs(move) / self.threshold_pct),
                        )
                    )
                    direction = -1
                    last_pivot_price = low[i]
                    last_pivot_i = i
            else:
                if low[i] < last_pivot_price:
                    last_pivot_price = low[i]
                    last_pivot_i = i
                elif (high[i] - last_pivot_price) / last_pivot_price >= self.threshold_pct:
                    swings.append(
                        SwingPoint(
                            index=df.index[i],
                            price=float(last_pivot_price),
                            kind="low",
                            bar_position=i,
                            confidence=min(1.0, abs(move) / self.threshold_pct),
                        )
                    )
                    direction = 1
                    last_pivot_price = high[i]
                    last_pivot_i = i
 
        return swings
 
 
class AdaptiveSwingDetector(BaseSwingDetector):
    """
    ZigZag with ATR-scaled threshold.
 
    threshold = atr_mult * ATR / price  (percentage-like)
    """
 
    name = "adaptive_swing"
    version = "1.0.0"
 
    def __init__(self, atr_window: int = 14, atr_mult: float = 1.5) -> None:
        self.atr_window = atr_window
        self.atr_mult = atr_mult
 
    def detect(self, df: pd.DataFrame) -> list[SwingPoint]:
        # Compute simple ATR for threshold
        high = df["high"].astype(float)
        low = df["low"].astype(float)
        close = df["close"].astype(float)
        prev = close.shift(1)
        tr = pd.concat(
            [(high - low).abs(), (high - prev).abs(), (low - prev).abs()],
            axis=1,
        ).max(axis=1)
        atr = tr.rolling(self.atr_window, min_periods=self.atr_window).mean()
        # Use median ATR/price as a stable threshold for the series
        ratio = (atr / close).dropna()
        if ratio.empty:
            thr = 0.005
        else:
            thr = float(ratio.median() * self.atr_mult)
            thr = max(thr, 1e-6)
 
        zz = ZigZagSwingDetector(threshold_pct=thr)
        swings = zz.detect(df)
        # Tag as adaptive
        return [
            SwingPoint(
                index=s.index,
                price=s.price,
                kind=s.kind,
                bar_position=s.bar_position,
                confidence=s.confidence,
            )
            for s in swings
        ]