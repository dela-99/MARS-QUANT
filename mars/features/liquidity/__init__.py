"""
Liquidity research modules.
 
Do not assume retail definitions. Each detector exposes confidence scores.
"""
 
from mars.features.liquidity.equal_levels import EqualHighsLowsDetector
from mars.features.liquidity.density import DensityLiquidityDetector
from mars.features.liquidity.sweeps import LiquiditySweepDetector
 
__all__ = [
    "EqualHighsLowsDetector",
    "DensityLiquidityDetector",
    "LiquiditySweepDetector",
]