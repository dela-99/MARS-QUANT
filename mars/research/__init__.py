"""
Research Lab workflow support.
 
Hypothesis lifecycle, experiment tracking, and methodology enforcement.
Content lives under research/; code lives here.
"""
 
from mars.research.hypothesis import HypothesisStore, load_hypothesis, save_hypothesis
from mars.research.experiment import ExperimentLog, ExperimentRecord
from mars.research.workflow import ResearchWorkflow, METHODOLOGY_STAGES
 
__all__ = [
    "HypothesisStore",
    "load_hypothesis",
    "save_hypothesis",
    "ExperimentLog",
    "ExperimentRecord",
    "ResearchWorkflow",
    "METHODOLOGY_STAGES",
]