from __future__ import annotations
import numpy as np
import pandas as pd
from mars.libs.features.base import BaseFeature, FeatureResult

def _fr(res):
    return FeatureResult(res[0], res[1], res[1].validation_report(FeatureResult(res[0], res[1].metadata)))


class FairValueGapFeature(BaseFeature):
    name="fair_value_gap"; category="imbalance"; outputs=("fvg_up","fvg_down","gap_size","gap_age","gap_mitigated","gap_persistence","gap_confidence"); mathematical_definition="configurable three-candle or body gap imbalance descriptors"
    def __init__(self,definition:str="wick",min_size:float=0.0): super().__init__(definition=definition,min_size=min_size); self.definition=definition; self.min_size=min_size; self.lookback=3
    def compute(self,df,**kwargs):
        self.validate_inputs(df); upper_prev=df.high.shift(2) if self.definition=="wick" else df.open.shift(2).combine(df.close.shift(2),max); lower_prev=df.low.shift(2) if self.definition=="wick" else df.open.shift(2).combine(df.close.shift(2),min); up_gap=df.low-upper_prev; down_gap=lower_prev-df.high; up=(up_gap>self.min_size).astype(float); down=(down_gap>self.min_size).astype(float); size=up_gap.where(up.eq(1), down_gap.where(down.eq(1))); active=(up+down).replace(0,np.nan); age=active.groupby(active.notna().cumsum()).cumcount().where(active.notna()); mitigated=((up.shift().eq(1)&(df.low<=upper_prev.shift()))|(down.shift().eq(1)&(df.high>=lower_prev.shift()))).astype(float); persistence=age.where(mitigated.eq(0)); conf=size.abs()/(df.high-df.low).replace(0,np.nan); out=pd.DataFrame({"fvg_up":up,"fvg_down":down,"gap_size":size,"gap_age":age,"gap_mitigated":mitigated,"gap_persistence":persistence,"gap_confidence":conf},index=df.index); return FeatureResult(out,self.metadata,self.validation_report(FeatureResult(out,self.metadata)))
