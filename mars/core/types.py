"""Shared enumerations and type aliases."""
 
from __future__ import annotations
 
from enum import Enum
from typing import TypeAlias
 
import numpy as np
import pandas as pd
 
# Common dataframe aliases used across the platform
Frame: TypeAlias = pd.DataFrame
Series: TypeAlias = pd.Series
ArrayLike: TypeAlias = np.ndarray | list[float] | pd.Series
 
 
class DatasetLayer(str, Enum):
    """
    Dataset lifecycle layers.
 
    Raw       → as ingested from the source (immutable once fingerprinted)
    Processed → cleaned, normalized, validated OHLCV
    Research  → experiment-specific intermediate tables
    FeatureStore → versioned feature matrices ready for research
    """
 
    RAW = "raw"
    PROCESSED = "processed"
    RESEARCH = "research"
    FEATURE_STORE = "feature_store"
 
 
class HypothesisStatus(str, Enum):
    """Lifecycle status of a research hypothesis."""
 
    DRAFT = "draft"
    TESTING = "testing"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ARCHIVED = "archived"
 
 
class Side(str, Enum):
    """Market side / directional bias (research labels only)."""
 
    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"
 
 
class ValidationStage(str, Enum):
    """Stages of the formal research methodology."""
 
    IDEA = "idea"
    HYPOTHESIS = "hypothesis"
    FORMAL_MATHEMATICS = "formal_mathematics"
    FEATURE_ENGINEERING = "feature_engineering"
    HISTORICAL_TESTING = "historical_testing"
    WALK_FORWARD = "walk_forward"
    STATISTICAL_TESTS = "statistical_tests"
    RISK_REVIEW = "risk_review"
    APPROVAL = "approval"
    PRODUCTION_CANDIDATE = "production_candidate"