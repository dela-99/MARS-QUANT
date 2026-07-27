from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
import pandas as pd
from mars.core.timeframes import Timeframe, SUPPORTED_TIMEFRAMES
from mars.libs.features.base import BaseFeature
from mars.libs.features.validation import DataQualityValidator
from .alignment import AlignmentEngine, AlignedFeatureRepresentation

@dataclass
class MultiTimeframeFeatureDataset:
    data: pd.DataFrame
    features_by_timeframe: dict[Timeframe,pd.DataFrame]
    metadata: dict
    validation: dict = field(default_factory=dict)

class MultiTimeframeFeatureEngine:
    def __init__(self, features:Iterable[BaseFeature], timeframes:tuple[Timeframe,...]=SUPPORTED_TIMEFRAMES, base_timeframe:Timeframe=Timeframe.M3, prefix_with_timeframe:bool=True, validate_data:bool=True):
        self.features=list(features); self.timeframes=timeframes; self.base_timeframe=base_timeframe; self.prefix_with_timeframe=prefix_with_timeframe; self.validate_data=validate_data; self.alignment_engine=AlignmentEngine(base_timeframe=base_timeframe)
    def load_synchronized_datasets(self, sources:dict[Timeframe,str|Path|pd.DataFrame])->dict[Timeframe,pd.DataFrame]:
        out={}
        for tf, src in sources.items():
            if isinstance(src, pd.DataFrame): df=src.copy()
            else:
                p=Path(src); df=pd.read_parquet(p)
                if 'timestamp' in df.columns: df=df.set_index('timestamp')
            if not isinstance(df.index,pd.DatetimeIndex): raise ValueError(f'{tf} dataset needs DatetimeIndex or timestamp column')
            out[tf]=df.sort_index()
        return out
    def generate_features_independently(self, bars_by_tf:dict[Timeframe,pd.DataFrame])->dict[Timeframe,pd.DataFrame]:
        features_by_tf={}
        for tf in self.timeframes:
            if tf not in bars_by_tf: continue
            bars=bars_by_tf[tf]
            if self.validate_data: DataQualityValidator(allow_weekends=True).validate(bars)
            parts=[]
            for feature in self.features:
                res=feature.compute(bars)
                data=res.data.copy()
                if self.prefix_with_timeframe: data.columns=[f'{tf.value.lower()}__{c}' for c in data.columns]
                parts.append(data)
            features_by_tf[tf]=pd.concat(parts,axis=1) if parts else pd.DataFrame(index=bars.index)
        return features_by_tf
    def synchronize_timestamps(self, features_by_tf:dict[Timeframe,pd.DataFrame])->AlignedFeatureRepresentation:
        return self.alignment_engine.align(features_by_tf, self.base_timeframe)
    def compute(self, sources:dict[Timeframe,str|Path|pd.DataFrame])->MultiTimeframeFeatureDataset:
        bars=self.load_synchronized_datasets(sources); by_tf=self.generate_features_independently(bars); aligned=self.synchronize_timestamps(by_tf)
        return MultiTimeframeFeatureDataset(aligned.data, by_tf, {"features":[f.metadata.to_dict() for f in self.features], "alignment":aligned.metadata, "roles":aligned.context_roles})
