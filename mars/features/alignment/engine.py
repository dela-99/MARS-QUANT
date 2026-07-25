"""
AlignmentEngine — synchronize multi-timeframe features onto a base grid.
 
Responsibilities:
    - Determine trend context (coarser TF, typically H1)
    - Determine market bias (M30)
    - Determine execution context (M15)
    - Determine confirmation context (M5 / M3)
    - Output a single synchronized feature representation
 
Look-ahead control:
    Coarser TF features are forward-filled onto the finer base index using
    only values whose timestamp <= base bar timestamp (merge_asof backward).
"""
 
from __future__ import annotations
 
from dataclasses import dataclass, field
from typing import Optional
 
import pandas as pd
 
from mars.core.timeframes import TIMEFRAME_ROLES, Timeframe
from mars.core.types import Side
from mars.features.multi_timeframe.engine import MTFFeatureBundle
 
 
@dataclass
class AlignedContext:
    """Synchronized multi-timeframe feature matrix + context labels."""
 
    features: pd.DataFrame
    base_timeframe: Timeframe
    trend_context: Optional[pd.Series] = None  # e.g. +1 / 0 / -1
    market_bias: Optional[pd.Series] = None
    execution_context: Optional[pd.Series] = None
    confirmation_context: Optional[pd.Series] = None
    roles: dict[str, str] = field(default_factory=dict)
 
    def as_model_frame(self) -> pd.DataFrame:
        """Return features only (drop pure context labels if stored separately)."""
        return self.features.copy()
 
 
class AlignmentEngine:
    """
    Align MTF features onto a base (finest) timeframe without look-ahead.
 
    Default role mapping (overridable):
        H1  → trend_context
        M30 → market_bias
        M15 → execution_context
        M5  → confirmation_context
        M3  → entry_timing_context
    """
 
    def __init__(
        self,
        base_timeframe: Timeframe = Timeframe.M5,
        role_map: Optional[dict[Timeframe, str]] = None,
    ) -> None:
        self.base_timeframe = base_timeframe
        self.role_map = role_map or dict(TIMEFRAME_ROLES)
 
    def align(self, bundle: MTFFeatureBundle) -> AlignedContext:
        if self.base_timeframe not in bundle.features:
            # fall back to finest available
            available = sorted(bundle.features.keys(), key=lambda t: t.minutes)
            if not available:
                raise ValueError("MTFFeatureBundle has no features to align")
            base_tf = available[0]
        else:
            base_tf = self.base_timeframe
 
        base = bundle.features[base_tf].copy()
        base_idx = base.index
 
        aligned_parts = [base]
        for tf, frame in bundle.features.items():
            if tf == base_tf:
                continue
            aligned_parts.append(self._asof_align(frame, base_idx))
 
        features = pd.concat(aligned_parts, axis=1)
        # Drop duplicate columns if any
        features = features.loc[:, ~features.columns.duplicated()]
 
        ctx = AlignedContext(
            features=features,
            base_timeframe=base_tf,
            roles={tf.value: role for tf, role in self.role_map.items()},
        )
 
        # Derive simple context series from momentum-like columns if present
        ctx.trend_context = self._infer_sign_context(
            features, prefix=Timeframe.H1.value.lower()
        )
        ctx.market_bias = self._infer_sign_context(
            features, prefix=Timeframe.M30.value.lower()
        )
        ctx.execution_context = self._infer_sign_context(
            features, prefix=Timeframe.M15.value.lower()
        )
        ctx.confirmation_context = self._infer_sign_context(
            features, prefix=Timeframe.M5.value.lower()
        )
        return ctx
 
    @staticmethod
    def _asof_align(frame: pd.DataFrame, base_index: pd.DatetimeIndex) -> pd.DataFrame:
        """Backward asof-join: only past/present coarser bars."""
        left = pd.DataFrame({"timestamp": base_index}).sort_values("timestamp")
        right = frame.copy()
        right = right.reset_index()
        # normalize index column name
        ts_col = right.columns[0]
        right = right.rename(columns={ts_col: "timestamp"})
        right = right.sort_values("timestamp")
 
        # Ensure timezone consistency
        if hasattr(left["timestamp"].dtype, "tz") or str(left["timestamp"].dtype).startswith("datetime64"):
            left["timestamp"] = pd.to_datetime(left["timestamp"], utc=True)
            right["timestamp"] = pd.to_datetime(right["timestamp"], utc=True)
 
        merged = pd.merge_asof(
            left,
            right,
            on="timestamp",
            direction="backward",
        )
        merged = merged.set_index("timestamp")
        merged.index.name = base_index.name or "timestamp"
        return merged
 
    @staticmethod
    def _infer_sign_context(
        features: pd.DataFrame,
        prefix: str,
    ) -> Optional[pd.Series]:
        """
        Infer a simple directional context from the first matching
        log_return / momentum column for a timeframe prefix.
        """
        candidates = [
            c
            for c in features.columns
            if c.startswith(f"{prefix}__")
            and ("log_return" in c or "momentum" in c)
        ]
        if not candidates:
            return None
        series = features[candidates[0]]
        return series.apply(
            lambda x: Side.LONG.value
            if x > 0
            else (Side.SHORT.value if x < 0 else Side.NEUTRAL.value)
            if pd.notna(x)
            else Side.NEUTRAL.value
        )