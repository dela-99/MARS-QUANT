from __future__ import annotations
import numpy as np
import pandas as pd
from mars.libs.features.base import BaseFeature, FeatureResult


class TrendFeature(BaseFeature):
    name="trend"; category="trend"; outputs=("ma_fast","ma_slow","ma_distance","linear_slope","trend_persistence","trend_confidence"); mathematical_definition="moving-average distance and rolling least-squares slope descriptors"
    def __init__(self, fast:int=10, slow:int=30): super().__init__(fast=fast,slow=slow); self.fast=fast; self.slow=slow; self.lookback=slow
    def compute(self,df,**kwargs):
        self.validate_inputs(df); ma_f=df.close.rolling(self.fast).mean(); ma_s=df.close.rolling(self.slow).mean(); x=np.arange(self.slow); denom=((x-x.mean())**2).sum(); slope=df.close.rolling(self.slow).apply(lambda y: ((x-x.mean())*(y-y.mean())).sum()/denom, raw=True); sign=np.sign(ma_f-ma_s); persistence=sign.rolling(self.slow).sum().abs()/self.slow; conf=(ma_f-ma_s).abs()/df.close.rolling(self.slow).std(); out=pd.DataFrame({"ma_fast":ma_f,"ma_slow":ma_s,"ma_distance":(ma_f-ma_s)/df.close,"linear_slope":slope,"trend_persistence":persistence,"trend_confidence":conf},index=df.index); return FeatureResult(out,self.metadata,self.validation_report(FeatureResult(out,self.metadata)))
