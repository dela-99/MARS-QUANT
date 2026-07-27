from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np
import pandas as pd

@dataclass
class DataQualityReport:
    row_count:int
    missing_candles:int=0
    duplicate_timestamps:int=0
    nan_values:int=0
    outlier_values:int=0
    timezone_consistent:bool=True
    data_gaps:int=0
    weekend_rows:int=0
    session_boundary_warnings:list[str]=field(default_factory=list)
    passed:bool=True
    details:dict=field(default_factory=dict)

class DataQualityValidator:
    def __init__(self, expected_frequency:str|None=None, zscore_threshold:float=8.0, allow_weekends:bool=False):
        self.expected_frequency=expected_frequency; self.zscore_threshold=zscore_threshold; self.allow_weekends=allow_weekends
    def validate(self, df:pd.DataFrame)->DataQualityReport:
        if not isinstance(df.index,pd.DatetimeIndex): raise ValueError('data must use DatetimeIndex')
        dup=int(df.index.duplicated().sum()); nan=int(df.isna().sum().sum()); tz_ok=df.index.tz is not None
        freq=self.expected_frequency or pd.infer_freq(df.index)
        missing=gaps=0
        if freq and len(df)>1:
            full=pd.date_range(df.index.min(), df.index.max(), freq=freq, tz=df.index.tz)
            missing=int(len(full.difference(df.index))); gaps=missing
        numeric=df.select_dtypes(include=[np.number]); z=((numeric-numeric.mean())/numeric.std()).abs(); out=int((z>self.zscore_threshold).sum().sum()) if not numeric.empty else 0
        weekend=int((df.index.dayofweek>=5).sum())
        passed=dup==0 and nan==0 and out==0 and tz_ok and gaps==0 and (self.allow_weekends or weekend==0)
        return DataQualityReport(len(df),missing,dup,nan,out,tz_ok,gaps,weekend,[],passed,{"frequency":freq})
