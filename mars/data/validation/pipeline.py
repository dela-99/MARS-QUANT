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
    check_m1_ohlc_consistency,
    check_tick_integrity,
    check_tick_schema,
)


class MarketDataValidator(DataValidator):
    """
    Run the full suite of research-grade OHLCV and tick checks.

    Order for OHLCV:
        1. schema
        2. duplicates
        3. OHLC consistency (M1-specific for M1, standard for others)
        4. missing candles
        5. bad ticks
        6. spread

    Order for Tick data:
        1. tick schema
        2. tick integrity (bid<=ask, positive prices, monotonic timestamps)
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

        # Detect if this is tick data (has bid/ask but no open/high/low/close)
        is_tick_data = (
            "bid" in df.columns
            and "ask" in df.columns
            and not all(c in df.columns for c in ("open", "high", "low", "close"))
        )

        if is_tick_data:
            # Tick validation path
            for issue in check_tick_schema(df):
                report.add(issue)
            for issue in check_tick_integrity(df):
                report.add(issue)
        else:
            # OHLCV validation path
            for issue in check_schema(df):
                report.add(issue)
            # If schema is broken, still attempt remaining checks carefully
            for issue in check_duplicates(df):
                report.add(issue)
            # Use M1-specific OHLC check for M1 timeframe
            if timeframe == Timeframe.M1:
                for issue in check_m1_ohlc_consistency(df):
                    report.add(issue)
            else:
                for issue in check_ohlc_consistency(df):
                    report.add(issue)
            for issue in check_missing_candles(df, timeframe):
                report.add(issue)
            for issue in check_bad_ticks(df, z_threshold=self.bad_tick_z):
                report.add(issue)
            for issue in check_spread(df, max_spread_pct=self.max_spread_pct):
                report.add(issue)

        return report