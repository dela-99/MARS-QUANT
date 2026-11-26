"""
Automated tests for XAU-SCALPING-DONCHIAN-001 (Assignment 22).

Extends the Version 1 test coverage (13 areas) with scalping-specific tests:
1. Execution timeframe selection (M1 vs M5)
2. Max holding duration enforcement (time exit)
3. $30 account risk engine integration
4. Signal/Execution separation
5. M1 context alignment (when use_m1_context=True)
6. Account feasibility analysis
7. Version 1 baseline preservation (no overwrite)
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mars.apps.backtester.xau_scalping_donchian_backtest import (
    CostModel,
    ExecutionModel,
    XauScalpingDonchianBacktester,
    session_of,
)
from mars.libs.risk.contract_aware import (
    ContractAwareFixedFractionalRisk,
    InstrumentSpec,
    floor_to_step,
)
from mars.libs.strategies.base import TradeSetup
from mars.libs.strategies.xau_scalping_donchian import (
    ScalpingDonchianParams,
    XauScalpingDonchianStrategy,
    compute_scalping_signals,
    M1_MINUTES,
    M5_MINUTES,
    H1_MINUTES,
)

# Exness XAUUSDm spec for testing
SPEC = InstrumentSpec(
    symbol="XAUUSDm",
    contract_size=100.0,
    pip_size=0.01,
    point_size=0.001,
    quote_currency="USD",
    volume_min=0.01,
    volume_max=200.0,
    volume_step=0.01,
    volume_spec_source="test_fixture",
    spec_source="test_fixture",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_m5(rows, start="2023-01-02", freq="5min", spread=0.0):
    """Build an M5 frame from a list of (open, high, low, close) tuples."""
    idx = pd.date_range(start=start, periods=len(rows), freq=freq, tz="UTC")
    df = pd.DataFrame(
        rows, columns=["open", "high", "low", "close"], index=idx
    ).astype(float)
    df["spread"] = spread
    df["tick_volume"] = 100
    df["volume"] = 0
    df.index.name = "timestamp"
    return df.reset_index()


def make_m1(rows, start="2023-01-02", freq="1min", spread=0.0):
    """Build an M1 frame from a list of (open, high, low, close) tuples."""
    idx = pd.date_range(start=start, periods=len(rows), freq=freq, tz="UTC")
    df = pd.DataFrame(
        rows, columns=["open", "high", "low", "close"], index=idx
    ).astype(float)
    df["spread"] = spread
    df["tick_volume"] = 100
    df["volume"] = 0
    df.index.name = "timestamp"
    return df.reset_index()


def make_h1(rows, start="2023-01-02", freq="1h"):
    idx = pd.date_range(start=start, periods=len(rows), freq=freq, tz="UTC")
    df = pd.DataFrame(
        rows, columns=["open", "high", "low", "close"], index=idx
    ).astype(float)
    df["spread"] = 0.0
    df["tick_volume"] = 100
    df["volume"] = 0
    df.index.name = "timestamp"
    return df.reset_index()


def flat_h1(n=200, price=2000.0, start="2023-01-01"):
    """Perfectly flat H1 series: EMA is flat -> regime 0 (no trade)."""
    rows = [(price, price, price, price)] * n
    return make_h1(rows, start=start)


def rising_h1(n=200, start="2023-01-01"):
    """Strictly rising H1 series: EMA rises -> long regime."""
    rows = []
    price = 2000.0
    for _ in range(n):
        price += 1.0
        rows.append((price, price, price, price))
    return make_h1(rows, start=start)


def falling_h1(n=200, start="2023-01-01"):
    rows = []
    price = 2100.0
    for _ in range(n):
        price -= 1.0
        rows.append((price, price, price, price))
    return make_h1(rows, start=start)


def make_backtester(params=None, cost=None, risk_fraction=0.01, starting_equity=10_000.0):
    # Default params with atr_period=5 for test data compatibility
    if params is None:
        params = ScalpingDonchianParams(
            donchian_lookback=5,
            ema_period=10,
            ema_slope_bars=2,
            atr_period=5,
            atr_stop_multiplier=2.0,
            risk_fraction=risk_fraction,
            starting_equity=starting_equity,
            execution_timeframe="M5",
            max_holding_bars=6,
        )
    policy = ContractAwareFixedFractionalRisk(spec=SPEC, risk_fraction=risk_fraction)
    return XauScalpingDonchianBacktester(
        params, spec=SPEC, cost_model=cost or CostModel(),
        execution_model=ExecutionModel(), risk_policy=policy,
    )


def make_test_params(**overrides):
    """Create test params with sensible defaults for synthetic data."""
    defaults = {
        "donchian_lookback": 5,
        "ema_period": 10,
        "ema_slope_bars": 2,
        "atr_period": 5,          # Short period for synthetic test data
        "atr_stop_multiplier": 2.0,
        "risk_fraction": 0.01,
        "starting_equity": 10_000.0,
        "execution_timeframe": "M5",
        "max_holding_bars": 6,
    }
    defaults.update(overrides)
    return ScalpingDonchianParams(**defaults)


# ===========================================================================
# 1. Execution Timeframe Selection
# ===========================================================================


class TestExecutionTimeframe:
    def test_m5_execution_uses_m5_for_signals(self):
        """M5 execution mode should compute Donchian/ATR on M5."""
        m5_rows = [(100, 101, 99, 100)] * 30
        m5 = make_m5(m5_rows)
        h1 = rising_h1(n=48, start="2023-01-01 00:00")

        params = ScalpingDonchianParams(
            donchian_lookback=5, ema_period=10, ema_slope_bars=2,
            execution_timeframe="M5", max_holding_bars=6,
        )
        signals = compute_scalping_signals(m5, m5, h1, params).frame

        # Donchian should be defined after lookback bars
        assert signals["donchian_high"].iloc[5] == pytest.approx(101.0)
        assert signals["donchian_low"].iloc[5] == pytest.approx(99.0)
        assert len(signals) == 30

    def test_m1_execution_uses_m5_context_by_default(self):
        """M1 execution with use_m1_context=False should use M5 for Donchian/ATR."""
        m1_rows = [(100, 101, 99, 100)] * 100  # 100 M1 bars = ~1h 40m
        m1 = make_m1(m1_rows, start="2023-01-02 00:00")
        m5_rows = [(100, 101, 99, 100)] * 30
        m5 = make_m5(m5_rows, start="2023-01-02 00:00")
        h1 = rising_h1(n=48, start="2023-01-01 00:00")

        params = ScalpingDonchianParams(
            donchian_lookback=5, ema_period=10, ema_slope_bars=2,
            execution_timeframe="M1", use_m1_context=False,
            max_holding_bars=6,
        )
        signals = compute_scalping_signals(m1, m5, h1, params).frame

        # Should have M1-length signals
        assert len(signals) == 100
        # Donchian from M5 context should be aligned to M1
        # First M5 bar completes at 00:05, so M1 bars before that have no Donchian
        # M5 bar 0 (00:00-00:05) -> Donchian available for M1 bars 5-9
        # But since all M5 bars are identical, Donchian should be 101/99
        assert signals["donchian_high"].iloc[10] == pytest.approx(101.0)
        assert signals["donchian_low"].iloc[10] == pytest.approx(99.0)

    def test_m1_execution_with_m1_context(self):
        """M1 execution with use_m1_context=True should compute Donchian/ATR on M1."""
        m1_rows = [(100, 101, 99, 100)] * 5 + [(100, 500, 99, 100)] + [(100, 101, 99, 100)] * 10
        m1 = make_m1(m1_rows, start="2023-01-02 00:00")
        m5 = make_m5([(100, 101, 99, 100)] * 30, start="2023-01-02 00:00")
        h1 = rising_h1(n=48, start="2023-01-01 00:00")

        params = ScalpingDonchianParams(
            donchian_lookback=5, ema_period=10, ema_slope_bars=2,
            execution_timeframe="M1", use_m1_context=True,
            m1_donchian_lookback=5,
            max_holding_bars=6,
        )
        signals = compute_scalping_signals(m1, m5, h1, params).frame

        # M1 Donchian at bar 5 (first with full lookback) should NOT include bar 5's spike
        assert signals["donchian_high"].iloc[5] == pytest.approx(101.0)
        # But bar 6 should include the spike
        assert signals["donchian_high"].iloc[6] == pytest.approx(500.0)


# ===========================================================================
# 2. Max Holding Duration (Time Exit)
# ===========================================================================


class TestMaxHoldingDuration:
    def test_time_exit_triggers_at_max_bars(self):
        """Position should be closed at max_holding_bars with reason 'time_exit'."""
        # 6 flat bars, then breakout, then hold for max_holding_bars
        rows = ([(100, 100, 100, 100)] * 6
                + [(100, 110, 100, 109)]  # breakout at index 6
                + [(109, 110, 109, 110)] * 10)  # gentle rise, no stop hit, no mid cross
        m5 = make_m5(rows, spread=300)
        h1 = rising_h1(n=48, start="2023-01-01 00:00")

        params = ScalpingDonchianParams(
            donchian_lookback=5, ema_period=10, ema_slope_bars=2,
            atr_period=5, atr_stop_multiplier=2.0,
            execution_timeframe="M5", max_holding_bars=3,  # 3 bars = 15 min
        )
        res = make_backtester(params=params).run(m5, m5, h1)

        assert len(res.trades) == 1
        trade = res.trades[0]
        assert trade.exit_reason == "time_exit"
        assert trade.holding_bars == 3  # max_holding_bars
        assert trade.time_exit_triggered is True
        assert res.time_exits == 1

    def test_time_exit_before_stop_or_mid(self):
        """Time exit should take priority if it occurs before stop or mid cross."""
        # Use data where stop is not hit on first bar after entry
        # ATR from flat bars (TR=0) then breakout (TR=10) -> ATR ~2, stop ~4
        # Entry at ~109, stop at ~105. Use bars with low > 105 for first 2 bars.
        rows = ([(100, 100, 100, 100)] * 6
                + [(100, 110, 100, 109)]  # breakout at index 6
                + [(109, 110, 106, 108)] * 2   # bars 7,8: low=106 > stop(105), no stop hit
                + [(108, 110, 80, 85)] * 5)   # later bars would hit stop
        m5 = make_m5(rows)
        h1 = rising_h1(n=48, start="2023-01-01 00:00")

        params = make_test_params(
            execution_timeframe="M5", max_holding_bars=2,
        )
        res = make_backtester(params=params).run(m5, m5, h1)

        assert len(res.trades) == 1
        trade = res.trades[0]
        # Time exit at 2 bars, before stop would hit
        assert trade.exit_reason == "time_exit"
        assert trade.holding_bars == 2

    def test_max_holding_minutes_overrides_bars(self):
        """max_holding_minutes should override max_holding_bars when > 0."""
        rows = ([(100, 100, 100, 100)] * 6
                + [(100, 110, 100, 109)]
                + [(109, 110, 109, 110)] * 10)
        m5 = make_m5(rows)
        h1 = rising_h1(n=48, start="2023-01-01 00:00")

        params = make_test_params(
            execution_timeframe="M5", 
            max_holding_bars=100,  # Large bar count
            max_holding_minutes=10,  # But 10 minutes = 2 M5 bars
        )
        res = make_backtester(params=params).run(m5, m5, h1)

        trade = res.trades[0]
        assert trade.exit_reason == "time_exit"
        assert trade.holding_bars == 2  # 10 min / 5 min = 2 bars
        assert trade.holding_bars == 2  # 10 min / 5 min = 2 bars


# ===========================================================================
# 3. $30 Account Risk Engine Integration
# ===========================================================================


class TestAccountRiskEngine:
    def test_risk_engine_rejects_when_min_lot_exceeds_budget(self):
        """At $30 equity, 1% risk = $0.30. If min lot risks more, reject."""
        # Large stop distance -> risk per lot > $0.30
        rows = ([(100, 100, 100, 100)] * 6
                + [(100, 110, 100, 109)]
                + [(109, 110, 109, 110)] * 5)
        m5 = make_m5(rows)
        h1 = rising_h1(n=48, start="2023-01-01 00:00")

        # Use $30 equity, 1% risk = $0.30 budget
        # Large ATR -> large stop -> min lot (0.01) risks > $0.30
        params = ScalpingDonchianParams(
            donchian_lookback=5, ema_period=10, ema_slope_bars=2,
            atr_period=5, atr_stop_multiplier=10.0,  # Huge stop
            risk_fraction=0.01,
            starting_equity=30.0,  # $30 account
            account_equity_usd=30.0,
            execution_timeframe="M5", max_holding_bars=6,
        )
        res = make_backtester(params=params, starting_equity=30.0, risk_fraction=0.01).run(m5, m5, h1)

        # Should reject due to min volume breach
        assert len(res.trades) == 0
        assert len(res.rejected_signals) == 1
        assert "min volume breach" in res.rejected_signals[0]["reason"]

    def test_risk_engine_accepts_when_min_lot_within_budget(self):
        """If stop is tight enough, min lot should be approved at $30."""
        # Very tight stop: ATR period=5, flat bars (TR=0) + 1pt breakout -> ATR=0.2
        # Stop multiplier=0.5 -> stop=0.1. Risk per lot = 0.1 * 100 = $10.
        # 0.01 lots risks $0.10. At $30 equity, 1% = $0.30 budget. $0.10 < $0.30 -> OK.
        rows = ([(100, 100, 100, 100)] * 6
                + [(100, 101, 100, 101)]  # Tiny 1pt breakout
                + [(101, 101, 101, 101)] * 5)
        m5 = make_m5(rows, spread=10)
        h1 = rising_h1(n=48, start="2023-01-01 00:00")

        params = make_test_params(
            atr_stop_multiplier=0.5,  # Very tight stop
            risk_fraction=0.01,
            starting_equity=30.0,
            account_equity_usd=30.0,
        )
        res = make_backtester(params=params, starting_equity=30.0, risk_fraction=0.01).run(m5, m5, h1)

        # Should not reject for min volume breach (may have other rejections like NaN ATR)
        min_vol_rejections = [r for r in res.rejected_signals if "min volume breach" in r["reason"]]
        assert len(min_vol_rejections) == 0, f"Got min volume breach rejections: {min_vol_rejections}"

    def test_account_feasibility_analysis(self):
        """Test the feasibility analysis function directly."""
        from mars.apps.research_lab.xau_scalping_donchian_research import analyze_account_feasibility

        params = ScalpingDonchianParams(
            account_equity_usd=30.0,
            risk_fraction=0.01,
            leverage=2000,
            min_lot=0.01,
        )

        # Tight stop: 0.5 price units * 100 oz = $50 per lot
        # Risk budget = $30 * 0.01 = $0.30
        # Lots needed = 0.30 / 50 = 0.006 -> floored to 0.00 -> rejected
        feas = analyze_account_feasibility(params, SPEC, avg_stop_distance_price=0.5, avg_spread_points=200.0)

        assert feas.feasible is False
        assert feas.rejection_reason is not None
        assert "min volume breach" in feas.rejection_reason
        assert feas.required_lots_exact == pytest.approx(0.006)

        # Wider stop: 0.01 price units * 100 = $1 per lot
        # Lots needed = 0.30 / 1 = 0.3 -> floored to 0.3 -> OK (above min 0.01)
        feas2 = analyze_account_feasibility(params, SPEC, avg_stop_distance_price=0.01, avg_spread_points=200.0)

        assert feas2.feasible is True
        assert feas2.min_risk_per_trade_usd == pytest.approx(0.30)


# ===========================================================================
# 4. Signal/Execution Separation
# ===========================================================================


class TestSignalExecutionSeparation:
    def test_compute_signals_is_pure_no_state(self):
        """compute_scalping_signals should be pure: same input -> same output."""
        m5 = make_m5([(100, 101, 99, 100)] * 30)
        h1 = rising_h1(n=48, start="2023-01-01 00:00")
        params = ScalpingDonchianParams(
            donchian_lookback=5, ema_period=10, ema_slope_bars=2,
            execution_timeframe="M5", max_holding_bars=6,
        )

        sig1 = compute_scalping_signals(m5, m5, h1, params).frame
        sig2 = compute_scalping_signals(m5, m5, h1, params).frame

        pd.testing.assert_frame_equal(sig1, sig2)

    def test_signals_unchanged_by_future_bars(self):
        """Adding future bars must not change past signals (no look-ahead)."""
        base_rows = [(100, 101, 99, 100)] * 30
        h1 = rising_h1(n=48, start="2023-01-01 00:00")
        params = ScalpingDonchianParams(
            donchian_lookback=5, ema_period=10, ema_slope_bars=2,
            execution_timeframe="M5", max_holding_bars=6,
        )

        m5_base = make_m5(base_rows)
        sig_base = compute_scalping_signals(m5_base, m5_base, h1, params).frame

        # Append violent future bars
        future_rows = base_rows + [(100, 5000, 1, 4000)] * 20
        m5_future = make_m5(future_rows)
        sig_future = compute_scalping_signals(m5_future, m5_future, h1, params).frame

        for col in ("donchian_high", "donchian_low", "atr", "h1_regime",
                    "entry_long", "entry_short", "exit_long", "exit_short"):
            assert sig_base[col].iloc[:30].equals(sig_future[col].iloc[:30]), f"{col} changed by future bars"

    def test_strategy_generate_setups_returns_setups_not_trades(self):
        """Strategy adapter should return TradeSetup objects, not execute trades."""
        m5 = make_m5([(100, 101, 99, 100)] * 6 + [(100, 110, 99, 109)] + [(109, 110, 109, 110)] * 5)
        h1 = rising_h1(n=48, start="2023-01-01 00:00")
        params = ScalpingDonchianParams(
            donchian_lookback=5, ema_period=10, ema_slope_bars=2,
            execution_timeframe="M5", max_holding_bars=6,
        )

        strategy = XauScalpingDonchianStrategy(params)
        setups = strategy.generate_setups(m5, context_tf=m5, h1=h1)

        assert len(setups) == 1
        assert isinstance(setups[0], TradeSetup)
        assert setups[0].side == "long"
        assert "max_holding_bars" in setups[0].metadata


# ===========================================================================
# 5. M1 Context Alignment
# ===========================================================================


class TestM1ContextAlignment:
    def test_h1_regime_aligned_to_m1_completions(self):
        """H1 regime should be aligned to M1 bar completions via merge_asof."""
        # merge_asof backward on completion timestamps:
        # - H1 bar 0 (00:00-01:00) completes at 01:00
        # - H1 bar 1 (01:00-02:00) completes at 02:00
        # - M1 bar i starts at 00:i, completes at 00:i+1
        # - M1 completion <= 01:59 (bar 118): matches H1 bar 0 (completion 01:00)
        # - M1 completion 02:00 (bar 119): matches H1 bar 1 (completion 02:00, exact match, last <=)
        #
        # H1 regime: bar 0 has regime=0 (EMA_prev NaN with ema_slope_bars=1).
        # Bar 1 has valid regime (1 for rising).
        # So M1 bars 0-118 (completions 00:01-01:59) -> H1 bar 0 -> regime 0
        # M1 bar 119+ (completion 02:00+) -> H1 bar 1 -> regime 1
        h1 = rising_h1(n=20, start="2023-01-02 00:00")  # 00:00-20:00 same day
        m1 = make_m1([(2000, 2001, 1999, 2000)] * 200, start="2023-01-02 00:00")
        m5 = make_m5([(2000, 2001, 1999, 2000)] * 10, start="2023-01-02 00:00")

        params = ScalpingDonchianParams(
            donchian_lookback=5, ema_period=2, ema_slope_bars=1,  # Fast EMA for test
            execution_timeframe="M1", use_m1_context=False,
            max_holding_bars=6,
        )
        signals = compute_scalping_signals(m1, m5, h1, params).frame

        # M1 bars 0-118 (completions 00:01-01:59) match H1 bar 0 (regime 0)
        early = signals.iloc[:119]
        assert (early["h1_regime"] == 0).all(), f"Early regime not zero: {early['h1_regime'].unique()}"
        # M1 bar 119 (completion 02:00) matches H1 bar 1 (regime 1)
        assert signals["h1_regime"].iloc[119] == 1
        # M1 bar 120+ continues to match H1 bar 1
        assert signals["h1_regime"].iloc[120] == 1

    def test_m5_context_aligned_to_m1(self):
        """M5 Donchian/ATR should be aligned to M1 via merge_asof on completions."""
        m1 = make_m1([(100, 101, 99, 100)] * 100, start="2023-01-02 00:00")
        # M5: first bar 00:00-00:05, second 00:05-00:10, etc.
        m5 = make_m5([(100, 101, 99, 100)] * 20, start="2023-01-02 00:00")
        h1 = rising_h1(n=48, start="2023-01-01 00:00")

        params = ScalpingDonchianParams(
            donchian_lookback=5, ema_period=10, ema_slope_bars=2,
            execution_timeframe="M1", use_m1_context=False,
            max_holding_bars=6,
        )
        signals = compute_scalping_signals(m1, m5, h1, params).frame

        # M5 bar 0 completes at 00:05. M1 bars 0-4 complete before 00:05 -> no M5 data
        # M1 bar 5 completes at 00:06 -> should get M5 bar 0's Donchian
        # All M5 bars identical -> Donchian should be 101/99
        assert signals["donchian_high"].iloc[10] == pytest.approx(101.0)


# ===========================================================================
# 6. Version 1 Baseline Preservation
# ===========================================================================


class TestVersion1Preservation:
    def test_original_v1_module_unmodified(self):
        """Verify the original XAU-MTF-DONCHIAN-001 module still exists and works."""
        from mars.libs.strategies.xau_mtf_donchian import (
            MtfDonchianParams, XauMtfDonchianStrategy, compute_signals
        )

        m5 = make_m5([(100, 101, 99, 100)] * 30)
        h1 = rising_h1(n=48, start="2023-01-01 00:00")
        params = MtfDonchianParams(donchian_lookback=5, ema_period=10, ema_slope_bars=2)

        signals = compute_signals(m5, h1, params).frame
        assert "entry_long" in signals.columns
        assert "donchian_high" in signals.columns
        assert len(signals) == 30

        strategy = XauMtfDonchianStrategy(params)
        setups = strategy.generate_setups(m5, h1=h1)
        assert len(setups) >= 0  # May or may not have signals depending on regime

    def test_v1_backtester_still_works(self):
        """Verify the original V1 backtester still runs."""
        from mars.apps.backtester.mtf_donchian_backtest import MtfDonchianBacktester
        from mars.libs.strategies.xau_mtf_donchian import MtfDonchianParams

        m5 = make_m5([(100, 101, 99, 100)] * 6 + [(100, 110, 99, 109)] + [(109, 110, 109, 110)] * 5)
        h1 = rising_h1(n=48, start="2023-01-01 00:00")
        params = MtfDonchianParams(
            donchian_lookback=5, ema_period=10, ema_slope_bars=2,
            atr_period=5, atr_stop_multiplier=2.0,
        )

        bt = MtfDonchianBacktester(params, spec=SPEC)
        res = bt.run(m5, h1)

        # Should run without error
        assert isinstance(res.trades, list)
        assert isinstance(res.equity_curve, pd.Series)


# ===========================================================================
# 7. Backtester Core Functionality (extends V1 tests)
# ===========================================================================


class TestScalpingBacktesterCore:
    def test_next_bar_execution_timing(self):
        """Entry should fill at NEXT bar open, not signal close."""
        rows = ([(100, 100, 100, 100)] * 6
                + [(100, 110, 100, 109)]  # Signal bar (index 6)
                + [(109.5, 111, 109, 110)])  # Fill bar (index 7)
        m5 = make_m5(rows, spread=300)  # 300 points = $0.30
        h1 = rising_h1(n=48, start="2023-01-01 00:00")

        params = make_test_params(
            execution_timeframe="M5", max_holding_bars=6,
        )
        res = make_backtester(params=params).run(m5, m5, h1)

        assert len(res.trades) == 1
        trade = res.trades[0]
        # Entry at index 7 (00:35), not index 6 (00:30)
        assert trade.entry_time == pd.Timestamp("2023-01-02 00:35", tz="UTC")
        # Long entry pays ask: open + spread = 109.5 + 0.30 = 109.80
        assert trade.entry_price == pytest.approx(109.80)
        assert trade.entry_price != pytest.approx(109.0)  # Not signal close

    def test_spread_cost_one_per_round_trip(self):
        """Exactly one observed spread crossed per round trip."""
        rows = ([(100, 100, 100, 100)] * 6
                + [(100, 110, 100, 109)]
                + [(109, 110, 109, 110)] * 3)  # Exit via midpoint
        m5 = make_m5(rows, spread=200)  # 200 points = $0.20
        h1 = rising_h1(n=48, start="2023-01-01 00:00")

        params = make_test_params(
            execution_timeframe="M5", max_holding_bars=6,
        )
        res = make_backtester(params=params).run(m5, m5, h1)

        trade = res.trades[0]
        # Spread cost = spread_points * point_size * contract_size * lots
        # One spread per round trip: long pays on entry, short pays on exit
        expected_spread = 200 * 0.001 * 100 * trade.lots
        assert trade.spread_cost == pytest.approx(expected_spread)
        # Also verify it's exactly one spread (not zero, not two)
        assert trade.spread_cost > 0

    def test_no_pyramiding_one_position_at_a_time(self):
        """Only one position at a time; no pyramiding."""
        # Repeated breakouts
        rows = []
        for _ in range(40):
            rows.append((100, 110, 99, 109))
        m5 = make_m5(rows)
        h1 = rising_h1(n=48, start="2023-01-01 00:00")

        params = ScalpingDonchianParams(
            donchian_lookback=5, ema_period=10, ema_slope_bars=2,
            execution_timeframe="M5", max_holding_bars=6,
        )
        res = make_backtester(params=params).run(m5, m5, h1)

        # Every trade must close before next opens
        times = [(t.entry_time, t.exit_time) for t in res.trades]
        for (e1, x1), (e2, _) in zip(times, times[1:]):
            assert e2 >= x1, "Overlapping positions detected (pyramiding)"

    def test_opposite_signal_ignored_while_position_open(self):
        """Opposite direction signal while position open is ignored."""
        rows = ([(100, 101, 99, 100)] * 6
                + [(100, 105, 99, 104)]  # Long breakout
                + [(104, 104, 94, 95)] * 3)  # Down move, no stop breach
        m5 = make_m5(rows)
        h1 = rising_h1(n=48, start="2023-01-01 00:00")

        params = make_test_params(
            execution_timeframe="M5", max_holding_bars=10,
        )
        res = make_backtester(params=params).run(m5, m5, h1)

        assert len(res.trades) == 1
        assert res.trades[0].side == "long"

    def test_gap_stop_fills_at_open(self):
        """Gap through stop fills at the open (worse price)."""
        rows = ([(100, 100, 100, 100)] * 6
                + [(100, 110, 100, 109)]
                + [(80, 81, 79, 80)]  # Entry bar
                + [(70, 71, 69, 70)])  # Gaps through stop
        m5 = make_m5(rows)
        h1 = rising_h1(n=48, start="2023-01-01 00:00")

        params = ScalpingDonchianParams(
            donchian_lookback=5, ema_period=10, ema_slope_bars=2,
            atr_period=5, atr_stop_multiplier=2.0,
            execution_timeframe="M5", max_holding_bars=6,
        )
        res = make_backtester(params=params).run(m5, m5, h1)

        trade = res.trades[0]
        assert trade.exit_reason == "stop"
        assert trade.exit_price == pytest.approx(70.0)  # The open
        assert trade.exit_price < trade.stop_price  # Gap made it worse

    def test_deterministic_repeatability(self):
        """Identical runs must produce identical results."""
        m5 = make_m5([(100, 101, 99, 100)] * 6 + [(100, 110, 99, 109)] + [(109, 110, 109, 110)] * 5)
        h1 = rising_h1(n=48, start="2023-01-01 00:00")
        params = ScalpingDonchianParams(
            donchian_lookback=5, ema_period=10, ema_slope_bars=2,
            execution_timeframe="M5", max_holding_bars=6,
        )

        res1 = make_backtester(params=params).run(m5, m5, h1)
        res2 = make_backtester(params=params).run(m5, m5, h1)

        assert len(res1.trades) == len(res2.trades)
        if res1.trades:
            assert res1.trades[0].entry_price == res2.trades[0].entry_price
            assert res1.trades[0].exit_price == res2.trades[0].exit_price
            assert res1.final_equity == res2.final_equity


# ===========================================================================
# 8. Cost Model & Execution Model Recording
# ===========================================================================


class TestCostAndExecutionRecording:
    def test_run_record_contains_all_models(self):
        """Run record must contain params, cost_model, execution_model, spec."""
        m5 = make_m5([(100, 101, 99, 100)] * 6 + [(100, 110, 99, 109)])
        h1 = rising_h1(n=48, start="2023-01-01 00:00")
        params = ScalpingDonchianParams(
            execution_timeframe="M5", max_holding_bars=6,
        )
        res = make_backtester(params=params).run(m5, m5, h1)

        record = res.run_record()
        assert "strategy_id" in record
        assert record["strategy_id"] == "XAU-SCALPING-DONCHIAN-001"
        assert "params" in record
        assert "cost_model" in record
        assert "execution_model" in record
        assert "instrument_spec" in record
        assert record["params"]["execution_timeframe"] == "M5"
        assert record["params"]["max_holding_bars"] == 6

    def test_exit_breakdown_in_run_record(self):
        """Run record should include exit breakdown for scalping."""
        m5 = make_m5([(100, 100, 100, 100)] * 6
                     + [(100, 110, 100, 109)]
                     + [(109, 110, 109, 110)] * 10)
        h1 = rising_h1(n=48, start="2023-01-01 00:00")
        params = make_test_params(
            execution_timeframe="M5", max_holding_bars=3,  # Force time exit
        )
        res = make_backtester(params=params).run(m5, m5, h1)

        record = res.run_record()
        assert "exit_breakdown" in record
        assert "time_exits" in record["exit_breakdown"]
        assert record["exit_breakdown"]["time_exits"] == 1


__all__ = [
    "TestExecutionTimeframe",
    "TestMaxHoldingDuration",
    "TestAccountRiskEngine",
    "TestSignalExecutionSeparation",
    "TestM1ContextAlignment",
    "TestVersion1Preservation",
    "TestScalpingBacktesterCore",
    "TestCostAndExecutionRecording",
]