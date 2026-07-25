"""
Base feature interface.
 
Every feature implementation MUST:
    - be deterministic
    - be vectorized (prefer NumPy / Polars / Pandas vector ops)
    - avoid look-ahead bias (only use data available at bar t)
    - declare version and lookback via FeatureMetadata
    - be unit tested
"""
 
from __future__ import annotations
 
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional
 
import pandas as pd
 
from mars.core.schemas import FeatureMetadata
from mars.core.timeframes import Timeframe
 
 
@dataclass
class FeatureResult:
    """Output of a feature computation."""
 
    data: pd.DataFrame
    metadata: FeatureMetadata
    timeframe: Optional[Timeframe] = None
    extras: dict[str, Any] = field(default_factory=dict)
 
    @property
    def columns(self) -> list[str]:
        return list(self.data.columns)
 
 
class BaseFeature(ABC):
    """
    Abstract base for all features.
 
    Subclasses implement ``compute`` and expose ``metadata``.
    """
 
    # Override in subclasses (or via property)
    name: str = "base"
    version: str = "0.1.0"
    category: str = "base"
    lookback: int = 0
    experimental: bool = False
 
    @property
    def metadata(self) -> FeatureMetadata:
        return FeatureMetadata(
            name=self.name,
            version=self.version,
            category=self.category,
            description=self.__doc__ or "",
            lookback=self.lookback,
            outputs=self.output_columns(),
            experimental=self.experimental,
        )
 
    def output_columns(self) -> list[str]:
        """Declared output column names (override when fixed)."""
        return []
 
    @abstractmethod
    def compute(
        self,
        df: pd.DataFrame,
        timeframe: Optional[Timeframe] = None,
        **kwargs: Any,
    ) -> FeatureResult:
        """
        Compute feature columns from OHLCV (or prior features).
 
        Args:
            df: bars with DatetimeIndex and open/high/low/close [/volume]
            timeframe: optional context for multi-timeframe engines
            **kwargs: feature-specific parameters
 
        Returns:
            FeatureResult with one or more columns aligned to ``df.index``
        """
        ...
 
    def validate_inputs(self, df: pd.DataFrame) -> None:
        """Raise ValueError if required columns are missing."""
        required = set(self.metadata.inputs)
        missing = required - set(df.columns)
        if missing:
            raise ValueError(
                f"{self.metadata.qualified_name()} missing inputs: {sorted(missing)}"
            )
        if self.lookback > 0 and len(df) < self.lookback + 1:
            raise ValueError(
                f"{self.metadata.qualified_name()} needs at least "
                f"{self.lookback + 1} rows, got {len(df)}"
            )
 
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.metadata.qualified_name()})"
 
 
# ---------------------------------------------------------------------------
# Domain abstract bases (interfaces for interchangeable implementations)
# ---------------------------------------------------------------------------
 
 
class MarketStructureFeature(BaseFeature):
    """Features derived from swing structure, BOS, CHOCH, etc."""
 
    category = "market_structure"
 
 
class LiquidityFeature(BaseFeature):
    """Liquidity pools, equal highs/lows, sweeps, density."""
 
    category = "liquidity"
 
 
class MomentumFeature(BaseFeature):
    """Momentum / oscillator-style features."""
 
    category = "momentum"
 
 
class VolatilityFeature(BaseFeature):
    """Volatility regime and range features."""
 
    category = "volatility"
 
 
class SessionFeature(BaseFeature):
    """Session-window features (Asia / London / NY)."""
 
    category = "session"
 
 
class MicrostructureFeature(BaseFeature):
    """Microstructure proxies from OHLCV (spread, wick ratios, etc.)."""
 
    category = "microstructure"
 
 
class TimeFeature(BaseFeature):
    """Calendar / clock features (hour, day-of-week, etc.)."""
 
    category = "time"
 
 
class CorrelationFeature(BaseFeature):
    """Cross-asset or rolling auto-correlation features."""
 
    category = "correlation"