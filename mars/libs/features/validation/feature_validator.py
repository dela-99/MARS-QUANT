from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
import pandas as pd
from mars.libs.features.base import BaseFeature, FeatureResult

@dataclass
class FeatureValidationReport:
    feature:str
    rows:int
    output_columns:list[str]
    missing_outputs:list[str]
    nan_count:dict[str,int]
    deterministic:bool
    version:str
    metadata:dict[str,Any]
    passed:bool

class FeatureValidator:
    def validate(self, feature:BaseFeature, df:pd.DataFrame)->FeatureValidationReport:
        a=feature.compute(df); b=feature.compute(df)
        deterministic=a.data.equals(b.data)
        expected=feature.output_columns(); missing=[c for c in expected if c not in a.data]
        passed=deterministic and not missing and feature.metadata.deterministic and bool(feature.metadata.version)
        return FeatureValidationReport(feature.metadata.qualified_name(),len(a.data),list(a.data.columns),missing,{c:int(a.data[c].isna().sum()) for c in a.data.columns},deterministic,feature.metadata.version,feature.metadata.to_dict(),passed)
