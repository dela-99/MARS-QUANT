from __future__ import annotations
import numpy as np
import pandas as pd
from mars.libs.features.base import BaseFeature, FeatureResult

def _fr(res):
    return FeatureResult(res[0], res[1], res[1].validation_report(FeatureResult(res[0], res[1].metadata)))


class FractalSwingFeature(BaseFeature):
    name="fractal_swings"; category="market_structure"; outputs=("swing_high","swing_low","swing_strength"); mathematical_definition="centered local extrema confirmed after right_window bars"
    def __init__(self,left:int=2,right:int=2): super().__init__(left=left,right=right); self.left=left; self.right=right; self.lookback=left+right
    def compute(self,df,**kwargs):
        self.validate_inputs(df); h=df.high; l=df.low; sh=(h==h.rolling(self.left+self.right+1,center=True).max()).shift(self.right).fillna(False).astype(float); sl=(l==l.rolling(self.left+self.right+1,center=True).min()).shift(self.right).fillna(False).astype(float); strength=((h-h.rolling(self.left+self.right+1).min())/(h.rolling(self.left+self.right+1).max()-h.rolling(self.left+self.right+1).min())).where(sh.eq(1), np.nan); out=pd.DataFrame({"swing_high":sh,"swing_low":sl,"swing_strength":strength},index=df.index); return FeatureResult(out,self.metadata,self.validation_report(FeatureResult(out,self.metadata)))
class ZigZagSwingFeature(BaseFeature):
    name="zigzag_swings"; category="market_structure"; outputs=("zigzag_high","zigzag_low"); mathematical_definition="rolling extrema exceeding configurable percentage threshold"
    def __init__(self,window:int=10,threshold:float=.002): super().__init__(window=window,threshold=threshold); self.window=window; self.threshold=threshold; self.lookback=window
    def compute(self,df,**kwargs):
        self.validate_inputs(df); rh=df.high.rolling(self.window).max(); rl=df.low.rolling(self.window).min(); out=pd.DataFrame({"zigzag_high":((df.high.eq(rh))&(df.high/df.close.shift(self.window)-1>self.threshold)).astype(float),"zigzag_low":((df.low.eq(rl))&(df.close.shift(self.window)/df.low-1>self.threshold)).astype(float)},index=df.index); return FeatureResult(out,self.metadata,self.validation_report(FeatureResult(out,self.metadata)))
class StructureBreakFeature(BaseFeature):
    name="structure_breaks"; category="market_structure"; outputs=("bos_up","bos_down","choch_proxy","structure_quality","swing_persistence"); mathematical_definition="close crossing prior confirmed rolling swing levels"
    def __init__(self,window:int=20): super().__init__(window=window); self.window=window; self.lookback=window
    def compute(self,df,**kwargs):
        self.validate_inputs(df); prior_high=df.high.shift(1).rolling(self.window).max(); prior_low=df.low.shift(1).rolling(self.window).min(); bos_up=(df.close>prior_high).astype(float); bos_down=(df.close<prior_low).astype(float); direction=bos_up.replace(0,np.nan).ffill().fillna(0)-bos_down.replace(0,np.nan).ffill().fillna(0); choch=(direction.diff().abs()>0).astype(float); rng=(prior_high-prior_low); quality=(df.close-prior_low)/rng; persist=direction.rolling(self.window).sum().abs()/self.window; out=pd.DataFrame({"bos_up":bos_up,"bos_down":bos_down,"choch_proxy":choch,"structure_quality":quality,"swing_persistence":persist},index=df.index); return FeatureResult(out,self.metadata,self.validation_report(FeatureResult(out,self.metadata)))
AdaptiveSwingFeature=FractalSwingFeature
