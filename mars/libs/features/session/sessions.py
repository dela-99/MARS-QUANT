from __future__ import annotations
import numpy as np
import pandas as pd
from mars.libs.features.base import BaseFeature, FeatureResult


class SessionFeature(BaseFeature):
    name="fx_sessions"; category="session"; inputs=("open","high","low","close"); outputs=("is_asia","is_london","is_new_york","is_london_ny_overlap","session_duration_hours","distance_from_session_open","distance_from_session_close","is_holiday_placeholder"); mathematical_definition="UTC clock session membership and boundary distances"
    def __init__(self, asia=(0,8), london=(7,16), new_york=(12,21)): super().__init__(asia=asia,london=london,new_york=new_york); self.asia=asia; self.london=london; self.new_york=new_york
    def compute(self,df,**kwargs):
        self.validate_inputs(df); h=df.index.hour+df.index.minute/60; asia=((h>=self.asia[0])&(h<self.asia[1])); lon=((h>=self.london[0])&(h<self.london[1])); ny=((h>=self.new_york[0])&(h<self.new_york[1])); starts=np.select([asia,lon,ny],[self.asia[0],self.london[0],self.new_york[0]],default=np.nan); ends=np.select([asia,lon,ny],[self.asia[1],self.london[1],self.new_york[1]],default=np.nan); out=pd.DataFrame({"is_asia":asia.astype(float),"is_london":lon.astype(float),"is_new_york":ny.astype(float),"is_london_ny_overlap":(lon&ny).astype(float),"session_duration_hours":ends-starts,"distance_from_session_open":h-starts,"distance_from_session_close":ends-h,"is_holiday_placeholder":0.0},index=df.index); return FeatureResult(out,self.metadata,self.validation_report(FeatureResult(out,self.metadata)))
