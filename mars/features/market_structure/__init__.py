"""
Market structure interfaces and interchangeable detectors.
 
Do NOT hardcode a single BOS implementation.
Swing detectors and structure detectors are pluggable.
"""
 
from mars.features.market_structure.swings import (
    BaseSwingDetector,
    FractalSwingDetector,
    ZigZagSwingDetector,
    AdaptiveSwingDetector,
)
from mars.features.market_structure.structure import (
    BOSDetector,
    CHOCHDetector,
    StructureEvent,
)
 
__all__ = [
    "BaseSwingDetector",
    "FractalSwingDetector",
    "ZigZagSwingDetector",
    "AdaptiveSwingDetector",
    "BOSDetector",
    "CHOCHDetector",
    "StructureEvent",
]