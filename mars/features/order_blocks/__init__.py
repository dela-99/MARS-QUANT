"""
Order block detectors — EXPERIMENTAL RESEARCH ONLY.
 
Do NOT treat as core platform assumptions until statistically validated.
Belong in research modules, not production feature defaults.
"""
 
from mars.features.order_blocks.detector import ExperimentalOrderBlockDetector
 
__all__ = ["ExperimentalOrderBlockDetector"]