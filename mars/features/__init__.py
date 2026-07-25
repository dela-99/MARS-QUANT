"""
M.A.R.S. Feature Engine
 
Deterministic, versioned, vectorized feature modules.
No monolithic feature.py — each domain is an independent module.
 
Categories:
    MarketStructure, Liquidity, Momentum, Volatility,
    Session, Microstructure, Time, Correlation,
    OrderBlocks (experimental research only)
 
Multi-timeframe:
    MultiTimeframeFeatureEngine + AlignmentEngine
"""
 
from mars.features.base import BaseFeature, FeatureResult
from mars.features.registry import FeatureRegistry
 
__all__ = [
    "BaseFeature",
    "FeatureResult",
    "FeatureRegistry",
]