from __future__ import annotations
import numpy as np
import pandas as pd
from mars.libs.features.base import BaseFeature, FeatureResult

def _fr(res):
    return FeatureResult(res[0], res[1], res[1].validation_report(FeatureResult(res[0], res[1].metadata)))


class LiquidityLevelsFeature(BaseFeature):
    name="liquidity_levels"; category="liquidity"; outputs=("equal_high","equal_low","liquidity_density","sweep_up","sweep_down","sweep_confidence"); mathematical_definition="equal level proximity, rolling density, and wick sweep descriptors"
    def __init__(self,window:int=20,tolerance:float=.001): super().__init__(window=window,tolerance=tolerance); self.window=window; self.tolerance=tolerance; self.lookback=window
    def compute(self,df,**kwargs):
        self.validate_inputs(df); rh=df.high.shift(1).rolling(self.window).max(); rl=df.low.shift(1).rolling(self.window).min(); eqh=(df.high.sub(rh).abs()/df.close<=self.tolerance).astype(float); eql=(df.low.sub(rl).abs()/df.close<=self.tolerance).astype(float); sweep_up=((df.high>rh)&(df.close<rh)).astype(float); sweep_down=((df.low<rl)&(df.close>rl)).astype(float); density=(eqh+eql).rolling(self.window).sum()/self.window; conf=((df.high-rh).abs().fillna(0)+(df.low-rl).abs().fillna(0))/(df.high-df.low).replace(0,np.nan); out=pd.DataFrame({"equal_high":eqh,"equal_low":eql,"liquidity_density":density,"sweep_up":sweep_up,"sweep_down":sweep_down,"sweep_confidence":conf.where((sweep_up+sweep_down)>0)},index=df.index); return FeatureResult(out,self.metadata,self.validation_report(FeatureResult(out,self.metadata)))
class LiquidityClusteringFeature(BaseFeature):
    name="liquidity_clustering"; category="liquidity"; outputs=("dbscan_cluster_proxy","kde_density_proxy","liquidity_pool_distance"); mathematical_definition="vectorized clustering proxies over rolling high-low levels"
    def __init__(self,window:int=50,bandwidth:float=.002): super().__init__(window=window,bandwidth=bandwidth); self.window=window; self.bandwidth=bandwidth; self.lookback=window
    def compute(self,df,**kwargs):
        self.validate_inputs(df); mid=(df.high+df.low)/2; m=mid.rolling(self.window).mean(); sd=mid.rolling(self.window).std(); z=(mid-m)/sd; cluster=(z.abs()<1).astype(float); kde=np.exp(-0.5*z.pow(2)); dist=(mid-m).abs()/df.close; out=pd.DataFrame({"dbscan_cluster_proxy":cluster,"kde_density_proxy":kde,"liquidity_pool_distance":dist},index=df.index); return FeatureResult(out,self.metadata,self.validation_report(FeatureResult(out,self.metadata)))
