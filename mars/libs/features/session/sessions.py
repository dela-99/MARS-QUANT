from __future__ import annotations
import numpy as np
import pandas as pd
from mars.libs.features.base import BaseFeature, FeatureResult


class SessionFeature(BaseFeature):
    name = "fx_sessions"
    category = "session"
    inputs = ("open", "high", "low", "close")
    outputs = (
        "is_asia", "is_london", "is_new_york", "is_overlap",
        "session_duration_hours", "distance_from_session_open",
        "distance_from_session_close", "is_holiday_placeholder",
        "session_dummy_asia_london_ny_overlap"
    )
    mathematical_definition = "UTC clock session membership and boundary distances with 4-category session dummy"

    def __init__(self, asia=(0, 8), london=(8, 13), new_york=(13, 22)):
        super().__init__(asia=asia, london=london, new_york=new_york)
        self.asia = asia
        self.london = london
        self.new_york = new_york

    def compute(self, df, **kwargs):
        self.validate_inputs(df)
        h = df.index.hour + df.index.minute / 60
        asia = (h >= self.asia[0]) & (h < self.asia[1])
        london = (h >= self.london[0]) & (h < self.london[1])
        ny = (h >= self.new_york[0]) & (h < self.new_york[1])
        overlap = london & ny  # 13:00-17:00 UTC

        # 4-category session dummy: 0=Asia, 1=London-only, 2=NY-only, 3=Overlap
        session_dummy = np.select(
            [asia & ~overlap, london & ~overlap, ny & ~overlap, overlap],
            [0, 1, 2, 3],
            default=-1  # bars outside all sessions
        )

        starts = np.select(
            [asia, london, ny],
            [self.asia[0], self.london[0], self.new_york[0]],
            default=np.nan
        )
        ends = np.select(
            [asia, london, ny],
            [self.asia[1], self.london[1], self.new_york[1]],
            default=np.nan
        )
        out = pd.DataFrame({
            "is_asia": asia.astype(float),
            "is_london": london.astype(float),
            "is_new_york": ny.astype(float),
            "is_overlap": overlap.astype(float),
            "session_duration_hours": ends - starts,
            "distance_from_session_open": h - starts,
            "distance_from_session_close": ends - h,
            "is_holiday_placeholder": 0.0,
            "session_dummy_asia_london_ny_overlap": session_dummy.astype(float),
        }, index=df.index)
        return FeatureResult(out, self.metadata, self.validation_report(FeatureResult(out, self.metadata)))
