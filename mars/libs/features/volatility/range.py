from __future__ import annotations
import numpy as np
import pandas as pd
from mars.libs.features.base import BaseFeature, FeatureResult


class ATRFeature(BaseFeature):
    name="atr"; category="volatility"; version="1.0.0"; outputs=("atr",); mathematical_definition="rolling mean of true range"
    def __init__(self, window:int=14): super().__init__(window=window); self.window=window; self.lookback=window
    def compute(self, df, **kwargs):
        self.validate_inputs(df); tr=pd.concat([(df.high-df.low),(df.high-df.close.shift()).abs(),(df.low-df.close.shift()).abs()],axis=1).max(axis=1); out=pd.DataFrame({"atr":tr.rolling(self.window).mean()},index=df.index); return FeatureResult(out,self.metadata,self.validation_report(FeatureResult(out,self.metadata)))
class ParkinsonVolatilityFeature(BaseFeature):
    name="parkinson_volatility"; category="volatility"; version="1.0.0"; outputs=("parkinson_vol",); mathematical_definition="sqrt(rolling mean(log(high/low)^2)/(4 ln 2))"
    def __init__(self, window:int=20): super().__init__(window=window); self.window=window; self.lookback=window
    def compute(self, df, **kwargs):
        self.validate_inputs(df); v=np.sqrt((np.log(df.high/df.low)**2).rolling(self.window).mean()/(4*np.log(2))); out=pd.DataFrame({"parkinson_vol":v},index=df.index); return FeatureResult(out,self.metadata,self.validation_report(FeatureResult(out,self.metadata)))
class YangZhangVolatilityFeature(BaseFeature):
    name="yang_zhang_volatility"; category="volatility"; version="1.0.0"; outputs=("yang_zhang_vol",); mathematical_definition="rolling Yang-Zhang OHLC volatility estimator"
    def __init__(self, window:int=20): super().__init__(window=window); self.window=window; self.lookback=window
    def compute(self, df, **kwargs):
        self.validate_inputs(df); oc=np.log(df.open/df.close.shift()); co=np.log(df.close/df.open); rs=np.log(df.high/df.close)*np.log(df.high/df.open)+np.log(df.low/df.close)*np.log(df.low/df.open); k=.34/(1.34+(self.window+1)/(self.window-1)); yz=np.sqrt(oc.rolling(self.window).var()+k*co.rolling(self.window).var()+(1-k)*rs.rolling(self.window).mean()); out=pd.DataFrame({"yang_zhang_vol":yz},index=df.index); return FeatureResult(out,self.metadata,self.validation_report(FeatureResult(out,self.metadata)))
class RollingVarianceFeature(BaseFeature):
    name="rolling_variance"; category="volatility"; version="1.0.0"; outputs=("rolling_variance","garch_return","garch_abs_return","garch_squared_return"); mathematical_definition="rolling variance plus GARCH-ready return transforms"
    def __init__(self, window:int=20): super().__init__(window=window); self.window=window; self.lookback=window
    def compute(self, df, **kwargs):
        self.validate_inputs(df); r=np.log(df.close).diff(); out=pd.DataFrame({"rolling_variance":r.rolling(self.window).var(),"garch_return":r,"garch_abs_return":r.abs(),"garch_squared_return":r.pow(2)},index=df.index); return FeatureResult(out,self.metadata,self.validation_report(FeatureResult(out,self.metadata)))
class RollingEntropyFeature(BaseFeature):
    name="rolling_entropy"; category="volatility"; version="1.0.0"; outputs=("rolling_entropy",); mathematical_definition="rolling Shannon entropy of return signs"
    def __init__(self, window:int=20): super().__init__(window=window); self.window=window; self.lookback=window
    def compute(self, df, **kwargs):
        self.validate_inputs(df); s=np.sign(df.close.diff()).replace(0,np.nan); p=s.rolling(self.window).apply(lambda x: np.mean(x>0), raw=False); ent=-(p*np.log2(p)+(1-p)*np.log2(1-p)); out=pd.DataFrame({"rolling_entropy":ent.replace([np.inf,-np.inf],np.nan)},index=df.index); return FeatureResult(out,self.metadata,self.validation_report(FeatureResult(out,self.metadata)))
