from __future__ import annotations
import numpy as np
import pandas as pd
from mars.libs.features.base import BaseFeature, FeatureResult


class RollingCorrelationFeature(BaseFeature):
    name="rolling_correlation"; category="correlation"; inputs=("close",); outputs=("rolling_corr","lead_corr","lag_corr","cointegration_placeholder"); mathematical_definition="rolling correlation and lead-lag correlation against supplied reference series"
    def __init__(self, window:int=50, reference_column:str="reference_close"): super().__init__(window=window,reference_column=reference_column); self.window=window; self.reference_column=reference_column; self.lookback=window
    def compute(self,df,**kwargs):
        if self.reference_column not in df: ref=df.close
        else: ref=df[self.reference_column]
        if not isinstance(df.index,pd.DatetimeIndex): raise ValueError("feature input must use a DatetimeIndex")
        r1=df.close.pct_change(); r2=ref.pct_change(); out=pd.DataFrame({"rolling_corr":r1.rolling(self.window).corr(r2),"lead_corr":r1.shift(1).rolling(self.window).corr(r2),"lag_corr":r1.rolling(self.window).corr(r2.shift(1)),"cointegration_placeholder":np.nan},index=df.index); return FeatureResult(out,self.metadata,self.validation_report(FeatureResult(out,self.metadata)))
