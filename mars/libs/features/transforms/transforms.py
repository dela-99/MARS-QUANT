from __future__ import annotations
import numpy as np
import pandas as pd
from mars.libs.features.base import BaseFeature, FeatureResult


class LogTransformFeature(BaseFeature):
    name="log_transform"; category="transforms"; inputs=("close",); outputs=("log_close","log_return"); mathematical_definition="natural log and first difference"
    def compute(self,df,**kwargs):
        if not isinstance(df.index,pd.DatetimeIndex):
            raise ValueError("feature input must use a DatetimeIndex")
        lc=np.log(df.close)
        out=pd.DataFrame({"log_close":lc,"log_return":lc.diff()},index=df.index)
        return FeatureResult(out,self.metadata,self.validation_report(FeatureResult(out,self.metadata)))
class ScalingFeature(BaseFeature):
    name="scaling"; category="transforms"; outputs=("normalized_close","standardized_close"); mathematical_definition="rolling min-max normalization and z-score standardization"
    def __init__(self, window:int=100): super().__init__(window=window); self.window=window; self.lookback=window
    def compute(self,df,**kwargs):
        self.validate_inputs(df); mn=df.close.rolling(self.window).min(); mx=df.close.rolling(self.window).max(); mu=df.close.rolling(self.window).mean(); sd=df.close.rolling(self.window).std(); out=pd.DataFrame({"normalized_close":(df.close-mn)/(mx-mn),"standardized_close":(df.close-mu)/sd},index=df.index); return FeatureResult(out,self.metadata,self.validation_report(FeatureResult(out,self.metadata)))
class PCAFeature(BaseFeature):
    name="pca_transform"; category="transforms"; outputs=("pca_1",); mathematical_definition="deterministic first principal component of selected columns over full provided matrix"
    def __init__(self, columns=("open","high","low","close")): super().__init__(columns=tuple(columns)); self.columns=tuple(columns); self.inputs=tuple(columns)
    def compute(self,df,**kwargs):
        self.validate_inputs(df); x=df.loc[:,self.columns].astype(float); z=(x-x.mean())/x.std().replace(0,np.nan); filled=z.fillna(0); _,_,vt=np.linalg.svd(filled.to_numpy(), full_matrices=False); out=pd.DataFrame({"pca_1":filled.to_numpy()@vt[0]},index=df.index); return FeatureResult(out,self.metadata,self.validation_report(FeatureResult(out,self.metadata)))
class WaveletPlaceholderFeature(BaseFeature):
    name="wavelet_placeholder"; category="transforms"; outputs=("wavelet_low_frequency_proxy","wavelet_high_frequency_proxy"); mathematical_definition="rolling mean and residual placeholders compatible with future wavelet backend"
    def __init__(self, window:int=8): super().__init__(window=window); self.window=window
    def compute(self,df,**kwargs):
        self.validate_inputs(df); low=df.close.rolling(self.window).mean(); out=pd.DataFrame({"wavelet_low_frequency_proxy":low,"wavelet_high_frequency_proxy":df.close-low},index=df.index); return FeatureResult(out,self.metadata,self.validation_report(FeatureResult(out,self.metadata)))
