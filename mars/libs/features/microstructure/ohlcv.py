from __future__ import annotations
import numpy as np
import pandas as pd
from mars.libs.features.base import BaseFeature, FeatureResult


class MicrostructureFeature(BaseFeature):
    name="ohlcv_microstructure"; category="microstructure"; inputs=("open","high","low","close"); outputs=("spread_proxy","tick_volume","volume_imbalance","bid_ask_spread_placeholder","market_impact_placeholder"); mathematical_definition="OHLCV-derived spread, volume, and placeholder descriptors"
    def __init__(self, volume_column:str="volume"): super().__init__(volume_column=volume_column); self.volume_column=volume_column
    def compute(self,df,**kwargs):
        self.validate_inputs(df); vol=df[self.volume_column] if self.volume_column in df else pd.Series(0,index=df.index,dtype=float); rng=(df.high-df.low); direction=np.sign(df.close-df.open); out=pd.DataFrame({"spread_proxy":rng/df.close,"tick_volume":vol,"volume_imbalance":direction*vol/(vol.rolling(20).mean().replace(0,np.nan)),"bid_ask_spread_placeholder":np.nan,"market_impact_placeholder":np.nan},index=df.index); return FeatureResult(out,self.metadata,self.validation_report(FeatureResult(out,self.metadata)))
