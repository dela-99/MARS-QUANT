from __future__ import annotations
import numpy as np
import pandas as pd
from mars.libs.features.base import BaseFeature, FeatureResult


class RateOfChangeFeature(BaseFeature):
    name="roc"; category="momentum"; version="1.0.0"; outputs=("roc",); mathematical_definition="close_t / close_{t-n} - 1"
    def __init__(self, window:int=12): super().__init__(window=window); self.window=window; self.lookback=window
    def compute(self, df, **kwargs):
        self.validate_inputs(df); out=pd.DataFrame({"roc": df["close"].pct_change(self.window)}, index=df.index); return FeatureResult(out,self.metadata,self.validation_report(FeatureResult(out,self.metadata)))
class RSIFeature(BaseFeature):
    name="rsi"; category="momentum"; version="1.0.0"; outputs=("rsi",); mathematical_definition="100 - 100/(1 + rolling_mean(up)/rolling_mean(down))"
    def __init__(self, window:int=14): super().__init__(window=window); self.window=window; self.lookback=window
    def compute(self, df, **kwargs):
        self.validate_inputs(df); d=df.close.diff(); up=d.clip(lower=0).rolling(self.window).mean(); dn=(-d.clip(upper=0)).rolling(self.window).mean(); rsi=100-100/(1+up/dn.replace(0,np.nan)); out=pd.DataFrame({"rsi":rsi},index=df.index); return FeatureResult(out,self.metadata,self.validation_report(FeatureResult(out,self.metadata)))
class MACDFeature(BaseFeature):
    name="macd"; category="momentum"; version="1.0.0"; outputs=("macd","macd_signal","macd_hist"); mathematical_definition="EMA_fast(close)-EMA_slow(close), signal EMA, histogram"
    def __init__(self, fast:int=12, slow:int=26, signal:int=9): super().__init__(fast=fast,slow=slow,signal=signal); self.fast=fast; self.slow=slow; self.signal=signal; self.lookback=max(fast,slow)+signal
    def compute(self, df, **kwargs):
        self.validate_inputs(df); m=df.close.ewm(span=self.fast,adjust=False).mean()-df.close.ewm(span=self.slow,adjust=False).mean(); s=m.ewm(span=self.signal,adjust=False).mean(); out=pd.DataFrame({"macd":m,"macd_signal":s,"macd_hist":m-s},index=df.index); return FeatureResult(out,self.metadata,self.validation_report(FeatureResult(out,self.metadata)))
class ADXFeature(BaseFeature):
    name="adx"; category="momentum"; version="1.0.0"; outputs=("plus_di","minus_di","adx"); mathematical_definition="Wilder directional movement and average directional index"
    def __init__(self, window:int=14): super().__init__(window=window); self.window=window; self.lookback=window*2
    def compute(self, df, **kwargs):
        self.validate_inputs(df); up=df.high.diff(); down=-df.low.diff(); plus_dm=up.where((up>down)&(up>0),0.0); minus_dm=down.where((down>up)&(down>0),0.0); tr=pd.concat([(df.high-df.low),(df.high-df.close.shift()).abs(),(df.low-df.close.shift()).abs()],axis=1).max(axis=1); atr=tr.rolling(self.window).mean(); plus=100*plus_dm.rolling(self.window).mean()/atr; minus=100*minus_dm.rolling(self.window).mean()/atr; dx=100*(plus-minus).abs()/(plus+minus); adx=dx.rolling(self.window).mean(); out=pd.DataFrame({"plus_di":plus,"minus_di":minus,"adx":adx},index=df.index); return FeatureResult(out,self.metadata,self.validation_report(FeatureResult(out,self.metadata)))
class AccelerationFeature(BaseFeature):
    name="acceleration"; category="momentum"; version="1.0.0"; outputs=("momentum_acceleration","momentum_decay"); mathematical_definition="first difference and rolling decay of close returns"
    def __init__(self, window:int=5): super().__init__(window=window); self.window=window; self.lookback=window
    def compute(self, df, **kwargs):
        self.validate_inputs(df); r=df.close.pct_change(); acc=r.diff(); decay=r.abs()/r.abs().rolling(self.window).max(); out=pd.DataFrame({"momentum_acceleration":acc,"momentum_decay":decay},index=df.index); return FeatureResult(out,self.metadata,self.validation_report(FeatureResult(out,self.metadata)))
