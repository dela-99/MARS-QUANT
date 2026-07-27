from __future__ import annotations
import numpy as np
import pandas as pd
from mars.libs.features.base import BaseFeature, FeatureResult


class StatisticalFeature(BaseFeature):
    name="statistical_moments"; category="statistical"; outputs=("rolling_zscore","rolling_skew","rolling_kurtosis","entropy","hurst_proxy","stationarity_proxy"); mathematical_definition="rolling normalized moments, entropy, Hurst and stationarity proxies"
    def __init__(self, window:int=50): super().__init__(window=window); self.window=window; self.lookback=window
    def compute(self,df,**kwargs):
        self.validate_inputs(df); r=np.log(df.close).diff(); mu=r.rolling(self.window).mean(); sd=r.rolling(self.window).std(); z=(r-mu)/sd; p=(r>0).rolling(self.window).mean(); ent=-(p*np.log2(p)+(1-p)*np.log2(1-p)); hurst=(np.log(r.rolling(self.window).std())/np.log(self.window)).replace([np.inf,-np.inf],np.nan); stat=(mu.abs()/sd).replace([np.inf,-np.inf],np.nan); out=pd.DataFrame({"rolling_zscore":z,"rolling_skew":r.rolling(self.window).skew(),"rolling_kurtosis":r.rolling(self.window).kurt(),"entropy":ent,"hurst_proxy":hurst,"stationarity_proxy":stat},index=df.index); return FeatureResult(out,self.metadata,self.validation_report(FeatureResult(out,self.metadata)))
