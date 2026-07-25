"""Composite market-data validation pipeline."""
 
from __future__ import annotations
 
import pandas as pd
 
from mars.core.timeframes import Timeframe
from mars.data.interfaces import DataValidator, ValidationReport
from mars.data.validation.checks import (
    check_bad_ticks,
    check_duplicates,
    check_missing_candles,
    check_ohlc_consistency,
    check_schema,
    check_spread,
)
 
 
class MarketDataValidator(DataValidator):
    """
    Run the full suite of research-grade OHLCV checks.
 
    Order:
        1. schema
        2. duplicates
        3. OHLC consistency
        4. missing candles
        5. bad ticks
        6. spread
    """
 
    def __init__(
        self,
        bad_tick_z: float = 8.0,
        max_spread_pct: float = 0.01,
    ) -> None:
        self.bad_tick_z = bad_tick_z
        self.max_spread_pct = max_spread_pct
 
    def validate(self, df: pd.DataFrame, timeframe: Timeframe) -> ValidationReport:
        report = ValidationReport()
        report.row_count = len(df)
 
        for issue in check_schema(df):
            report.add(issue)
        # If schema is broken, still attempt remaining checks carefully
        for issue in check_duplicates(df):
            report.add(issue)
        for issue in check_ohlc_consistency(df):
            report.add(issue)
        for issue in check_missing_candles(df, timeframe):
            report.add(issue)
        for issue in check_bad_ticks(df, z_threshold=self.bad_tick_z):
            report.add(issue)
        for issue in check_spread(df, max_spread_pct=self.max_spread_pct):
            report.add(issue)
 
        return report