from __future__ import annotations
from dataclasses import dataclass, field
import pandas as pd
from mars.core.timeframes import Timeframe, TIMEFRAME_MINUTES, TIMEFRAME_ROLES

@dataclass
class AlignedFeatureRepresentation:
    data: pd.DataFrame
    base_timeframe: Timeframe
    source_timeframes: list[Timeframe]
    context_roles: dict[str,str]
    metadata: dict = field(default_factory=dict)

class AlignmentEngine:
    def __init__(self, base_timeframe:Timeframe=Timeframe.M3, closed_bar_only:bool=True):
        self.base_timeframe=base_timeframe; self.closed_bar_only=closed_bar_only
    def _closed_index(self, frame:pd.DataFrame, tf:Timeframe)->pd.DataFrame:
        out=frame.copy().sort_index()
        if self.closed_bar_only:
            out.index=out.index+pd.to_timedelta(TIMEFRAME_MINUTES[tf], unit='m')
        return out
    def align(self, features_by_tf:dict[Timeframe,pd.DataFrame], base_timeframe:Timeframe|None=None)->AlignedFeatureRepresentation:
        base_tf=base_timeframe or self.base_timeframe
        if base_tf not in features_by_tf: raise ValueError(f'missing base timeframe {base_tf}')
        base=features_by_tf[base_tf].sort_index().copy()
        aligned=base.copy()
        left=pd.DataFrame(index=base.index).reset_index(names='timestamp')
        for tf, frame in features_by_tf.items():
            if tf==base_tf: continue
            right=self._closed_index(frame, tf).reset_index(names='timestamp').sort_values('timestamp')
            merged=pd.merge_asof(left.sort_values('timestamp'), right, on='timestamp', direction='backward')
            merged=merged.set_index('timestamp').reindex(base.index)
            aligned=aligned.join(merged, how='left')
        return AlignedFeatureRepresentation(aligned, base_tf, list(features_by_tf), {tf.value:TIMEFRAME_ROLES.get(tf,'context') for tf in features_by_tf}, {"closed_bar_only":self.closed_bar_only})
