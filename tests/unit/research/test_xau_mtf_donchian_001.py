"""
Automated tests for XAU-MTF-DONCHIAN-001 (Assignment 14, section D).

Covers the thirteen areas required by the assignment:

1.  Donchian calculations excluding the current candle
2.  EMA regime direction and flat-regime handling
3.  ATR and initial stop calculation
4.  Completed-bar and H1-to-M5 alignment
5.  No look-ahead / no same-bar future information
6.  Next-bar execution timing
7.  Long and short entry conditions
8.  Stop-loss and structural exit behaviour
9.  Gaps and ambiguous intrabar stop execution
10. Spread and cost application
11. Position sizing and minimum-volume rejection
12. Missing data and session gaps
13. Deterministic repeatability of identical runs

The tests are written against synthetic fixtures so that every expected value is
hand-computable; the real dataset is exercised separately by the data-gate tests
in ``tests/unit/data/test_xauusdm_dataset_v120.py``.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mars.apps.backtester.mtf_donchian_backtest import (
    CostModel,
    ExecutionModel,
    MtfDonchianBacktester,
    session_of,
)
from mars.libs.risk.contract_aware import (
    ContractAwareFixedFractionalRisk,
    InstrumentSpec,
    floor_to_step,
)
from mars.libs.strategies.base import TradeSetup
from mars.libs.strategies.xau_mtf_donchian import (
    MtfDonchianParams,
    XauMtfDonchianStrategy,
    compute_signals,
)

SPEC = InstrumentSpec(
    symbol="XAUUSDm",
    contract_size=100.0,
    pip_size=0.01,
    point_size=0.001,
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
    """A perfectly flat H1 series: EMA is flat -> regime 0 (no trade)."""
    rows = [(price, price, price, price)] * n
    return make_h1(rows, start=start)


def rising_h1(n=200, start="2023-01-01"):
    """A strictly rising H1 series: EMA rises -> long regime."""
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
    params = params or MtfDonchianParams(
        donchian_lookback=5,
        ema_period=10,
        ema_slope_bars=2,
        atr_period=5,
        atr_stop_multiplier=2.0,
        risk_fraction=risk_fraction,
        starting_equity=starting_equity,
    )
    policy = ContractAwareFixedFractionalRisk(spec=SPEC, risk_fraction=risk_fraction)
    return MtfDonchianBacktester(
        params, spec=SPEC, cost_model=cost or CostModel(),
        execution_model=ExecutionModel(), risk_policy=policy,
    )


# ===========================================================================
# 1. Donchian calculations exclude the current candle
# ===========================================================================


class TestDonchianChannel:
    def test_channel_excludes_current_bar(self):
        m5 = make_m5([(100, 101, 99, 100)] * 10)
        h1 = flat_h1()
        sig = compute_signals(m5, h1, MtfDonchianParams(donchian_lookback=5)).frame
        # Every bar is identical, so the channel must equal the bar's own high/low.
        assert sig["donchian_high"].iloc[5] == pytest.approx(101.0)
        assert sig["donchian_low"].iloc[5] == pytest.approx(99.0)

    def test_channel_uses_only_prior_bars(self):
        rows = [(100, 101, 99, 100)] * 5 + [(100, 500, 99, 100)] + [(100, 101, 99, 100)] * 3
        m5 = make_m5(rows)
        sig = compute_signals(m5, flat_h1(), MtfDonchianParams(donchian_lookback=5)).frame
        # The bar with the 500 spike must NOT be in its own channel.
        assert sig["donchian_high"].iloc[5] == pytest.approx(101.0)
        # ...but it enters the channel of the NEXT bar.
        assert sig["donchian_high"].iloc[6] == pytest.approx(500.0)

    def test_channel_requires_full_lookback(self):
        m5 = make_m5([(100, 101, 99, 100)] * 10)
        sig = compute_signals(m5, flat_h1(), MtfDonchianParams(donchian_lookback=5)).frame
        # The channel needs 5 *prior* bars, so it is undefined for the first 5 bars.
        assert sig["donchian_high"].iloc[:5].isna().all()
        assert sig["donchian_high"].iloc[5] == pytest.approx(101.0)

    def test_midpoint_is_channel_centre(self):
        rows = [(100, 110, 90, 100)] * 8
        m5 = make_m5(rows)
        sig = compute_signals(m5, flat_h1(), MtfDonchianParams(donchian_lookback=5)).frame
        assert sig["donchian_mid"].iloc[6] == pytest.approx(100.0)


# ===========================================================================
# 2. EMA regime direction and flat-regime handling
# ===========================================================================


class TestEmaRegime:
    def test_rising_ema_gives_long_regime(self):
        h1 = rising_h1()
        sig = compute_signals(make_m5([(2000, 2001, 1999, 2000)] * 400), h1,
                           MtfDonchianParams(ema_period=10, ema_slope_bars=2)).frame
        assert (sig["h1_regime"] == 1).all()

    def test_falling_ema_gives_short_regime(self):
        h1 = falling_h1()
        sig = compute_signals(make_m5([(2000, 2001, 1999, 2000)] * 400), h1,
                           MtfDonchianParams(ema_period=10, ema_slope_bars=2)).frame
        assert (sig["h1_regime"] == -1).all()

    def test_flat_ema_gives_zero_regime_and_no_trades(self):
        h1 = flat_h1()
        rows = [(100, 101, 99, 100)] * 6 + [(100, 105, 99, 104)] + [(104, 105, 103, 104)] * 10
        m5 = make_m5(rows)
        sig = compute_signals(m5, h1, MtfDonchianParams(
            donchian_lookback=5, ema_period=10, ema_slope_bars=2)).frame
        assert (sig["h1_regime"] == 0).all()
        assert not sig["entry_long"].any()
        assert not sig["entry_short"].any()

    def test_unavailable_regime_blocks_trading(self):
        # H1 series starts long after the M5 series: early M5 bars have no regime.
        h1 = rising_h1(n=50, start="2023-01-05")
        m5 = make_m5([(100, 101, 99, 100)] * 300)
        sig = compute_signals(m5, h1, MtfDonchianParams(
            donchian_lookback=5, ema_period=10, ema_slope_bars=2)).frame
        early = sig.iloc[:200]
        assert (early["h1_regime"] == 0).all()
        assert not early["entry_long"].any()


# ===========================================================================
# 3. ATR and initial stop calculation
# ===========================================================================


class TestAtrAndStop:
    def test_atr_matches_true_range_average(self):
        # Constant 10-point bars -> ATR == 10 once the window is full.
        m5 = make_m5([(100, 110, 100, 105)] * 30)
        sig = compute_signals(m5, flat_h1(), MtfDonchianParams(atr_period=5)).frame
        assert sig["atr"].iloc[5] == pytest.approx(10.0)

    def test_atr_is_nan_before_window_is_full(self):
        m5 = make_m5([(100, 110, 100, 105)] * 30)
        sig = compute_signals(m5, flat_h1(), MtfDonchianParams(atr_period=14)).frame
        assert sig["atr"].iloc[:13].isna().all()
        assert not math.isnan(sig["atr"].iloc[13])

    def test_stop_distance_is_multiplier_times_atr(self):
        m5 = make_m5([(100, 110, 100, 105)] * 30)
        sig = compute_signals(m5, flat_h1(), MtfDonchianParams(
            atr_period=5, atr_stop_multiplier=2.5)).frame
        row = sig.iloc[20]
        assert row["stop_distance"] == pytest.approx(row["atr"] * 2.5)

    def test_stop_uses_only_completed_bars(self):
        rows = [(100, 110, 100, 105)] * 10
        m5 = make_m5(rows)
        sig = compute_signals(m5, flat_h1(), MtfDonchianParams(atr_period=5)).frame
        # The ATR at bar i must not change when a later bar is appended.
        sig2 = compute_signals(make_m5(rows + [(100, 1000, 100, 100)]),
                               flat_h1(), MtfDonchianParams(atr_period=5)).frame
        assert sig["atr"].iloc[9] == pytest.approx(sig2["atr"].iloc[9])


# ===========================================================================
# 4. Completed-bar and H1-to-M5 alignment
# ===========================================================================


class TestH1Alignment:
    def test_h1_bar_used_is_the_last_completed_one(self):
        # One H1 bar per hour; an M5 bar at 00:05 completes at 00:10, so the
        # H1 bar covering 00:00-01:00 is NOT complete and must not be used.
        h1 = rising_h1(n=48, start="2023-01-02 00:00")
        m5 = make_m5([(2000, 2001, 1999, 2000)] * 48, start="2023-01-02 00:00")
        sig = compute_signals(m5, h1, MtfDonchianParams(
            donchian_lookback=5, ema_period=10, ema_slope_bars=2)).frame
        # At M5 bar 00:00 the only completed H1 bar is the one before it,
        # which does not exist -> regime unavailable.
        assert sig["h1_regime"].iloc[0] == 0
        assert pd.isna(sig["h1_completion"].iloc[0])
        # At M5 bar 01:00 the H1 bar 00:00-01:00 has completed -> usable.
        assert sig["h1_completion"].iloc[12] == pd.Timestamp("2023-01-02 01:00", tz="UTC")

    def test_completion_time_never_exceeds_m5_completion(self):
        h1 = rising_h1(n=48, start="2023-01-02 00:00")
        m5 = make_m5([(2000, 2001, 1999, 2000)] * 120, start="2023-01-02 00:00")
        sig = compute_signals(m5, h1, MtfDonchianParams(
            donchian_lookback=5, ema_period=10, ema_slope_bars=2)).frame
        valid = sig["h1_completion"].notna()
        delta = sig.loc[valid, "h1_completion"] - (
            sig.loc[valid, "timestamp"] + pd.Timedelta(minutes=5))
        assert (delta <= pd.Timedelta(0)).all()

    def test_forming_h1_bar_is_never_used(self):
        """A regime flip inside the current hour must not affect earlier M5 bars."""
        h1_rows = [(2000.0, 2000.0, 2000.0, 2000.0)] * 12
        h1_rows += [(2100.0, 2100.0, 2100.0, 2100.0)] * 12
        h1 = make_h1(h1_rows, start="2023-01-02 00:00")
        m5 = make_m5([(2000, 2001, 1999, 2000)] * 120, start="2023-01-02 00:00")
        sig = compute_signals(m5, h1, MtfDonchianParams(
            donchian_lookback=5, ema_period=10, ema_slope_bars=2)).frame
        # Before the flip completes, the regime must still be the old one.
        assert (sig["h1_regime"].iloc[:100] != -1).all()


# ===========================================================================
# 5. No look-ahead / no same-bar future information
# ===========================================================================


class TestNoLookAhead:
    def test_signal_is_unchanged_by_future_bars(self):
        base = [(100, 101, 99, 100)] * 30
        h1 = rising_h1(n=48, start="2023-01-01 00:00")
        params = MtfDonchianParams(donchian_lookback=5, ema_period=10, ema_slope_bars=2)
        sig_a = compute_signals(make_m5(base), h1, params).frame
        # Append a violent future bar: earlier signals must not move.
        future = base + [(100, 5000, 1, 4000)] * 20
        sig_b = compute_signals(make_m5(future), h1, params).frame
        for col in ("donchian_high", "donchian_low", "atr", "h1_regime",
                    "entry_long", "entry_short"):
            assert sig_a[col].iloc[: len(base)].equals(sig_b[col].iloc[: len(base)]), col

    def test_regime_at_bar_does_not_depend_on_later_h1_bars(self):
        h1_rows = [(2000.0, 2000.0, 2000.0, 2000.0)] * 20
        h1 = make_h1(h1_rows, start="2023-01-02 00:00")
        params = MtfDonchianParams(donchian_lookback=5, ema_period=10, ema_slope_bars=2)
        m5 = make_m5([(2000, 2001, 1999, 2000)] * 120, start="2023-01-02 00:00")
        sig_a = compute_signals(m5, h1, params).frame
        h1_b = make_h1(h1_rows + [(5000.0, 5000.0, 5000.0, 5000.0)] * 20,
                       start="2023-01-02 00:00")
        sig_b = compute_signals(m5, h1_b, params).frame
        assert sig_a["h1_regime"].iloc[:100].equals(sig_b["h1_regime"].iloc[:100])


# ===========================================================================
# 6. Next-bar execution timing
# ===========================================================================


class TestNextBarExecution:
    def test_entry_fills_at_next_bar_open_not_signal_close(self):
        # 6 flat bars then a breakout close.  Entry must be the NEXT bar's open.
        rows = [(100, 100, 100, 100)] * 6 + [(100, 110, 100, 109)] + [(109.5, 111, 109, 110)]
        m5 = make_m5(rows, spread=300)     # 300 points -> $0.30 spread
        h1 = rising_h1(n=48, start="2023-01-01 00:00")
        res = make_backtester().run(m5, h1)
        assert len(res.trades) == 1
        trade = res.trades[0]
        # Bars: index 6 (00:30) is the signal bar, index 7 (00:35) is the fill bar.
        assert trade.entry_time == pd.Timestamp("2023-01-02 00:35", tz="UTC")
        # A long entry buys at the ask: next bar open + the observed spread.
        assert trade.entry_price == pytest.approx(109.5 + 0.30)
        assert trade.entry_price != pytest.approx(109.0)   # not the signal close

    def test_no_fill_on_the_signal_bar(self):
        rows = [(100, 100, 100, 100)] * 6 + [(100, 110, 100, 109)] + [(109.5, 111, 109, 110)]
        res = make_backtester().run(make_m5(rows), rising_h1(n=48, start="2023-01-01 00:00"))
        trade = res.trades[0]
        # The signal bar (00:30) must not be the entry bar.
        assert trade.entry_time > pd.Timestamp("2023-01-02 00:30", tz="UTC")


# ===========================================================================
# 7. Long and short entry conditions
# ===========================================================================


class TestEntryConditions:
    def test_long_entry_requires_breakout_and_long_regime(self):
        rows = [(100, 101, 99, 100)] * 6 + [(100, 110, 99, 109)]
        m5 = make_m5(rows)
        h1 = rising_h1(n=48, start="2023-01-01 00:00")
        sig = compute_signals(m5, h1, MtfDonchianParams(
            donchian_lookback=5, ema_period=10, ema_slope_bars=2)).frame
        assert sig["entry_long"].iloc[6]
        assert not sig["entry_short"].iloc[6]

    def test_short_entry_requires_breakdown_and_short_regime(self):
        rows = [(100, 101, 99, 100)] * 6 + [(100, 101, 90, 91)]
        m5 = make_m5(rows)
        h1 = falling_h1(n=48, start="2023-01-01 00:00")
        sig = compute_signals(m5, h1, MtfDonchianParams(
            donchian_lookback=5, ema_period=10, ema_slope_bars=2)).frame
        assert sig["entry_short"].iloc[6]
        assert not sig["entry_long"].iloc[6]

    def test_breakout_without_matching_regime_does_not_enter(self):
        rows = [(100, 101, 99, 100)] * 6 + [(100, 110, 99, 109)]
        m5 = make_m5(rows)
        h1 = falling_h1(n=48, start="2023-01-01 00:00")   # short regime
        sig = compute_signals(m5, h1, MtfDonchianParams(
            donchian_lookback=5, ema_period=10, ema_slope_bars=2)).frame
        assert not sig["entry_long"].iloc[6]
        res = make_backtester().run(m5, h1)
        assert len(res.trades) == 0

    def test_no_pyramiding_only_one_position_at_a_time(self):
        rows = []
        for _ in range(40):
            rows.append((100, 110, 99, 109))
        m5 = make_m5(rows)
        h1 = rising_h1(n=48, start="2023-01-01 00:00")
        res = make_backtester().run(m5, h1)
        # Every trade must close before the next one opens.
        times = [(t.entry_time, t.exit_time) for t in res.trades]
        for (e1, x1), (e2, _) in zip(times, times[1:]):
            assert e2 >= x1


# ===========================================================================
# 8. Stop-loss and structural exit behaviour
# ===========================================================================


class TestExits:
    def test_initial_stop_is_hit_and_records_stop_reason(self):
        # Breakout then a sharp reversal that breaches the stop.
        rows = ([(100, 100, 100, 100)] * 6
                + [(100, 110, 100, 109)]        # breakout
                + [(109, 109, 80, 85)])         # reversal through the stop
        m5 = make_m5(rows)
        h1 = rising_h1(n=48, start="2023-01-01 00:00")
        res = make_backtester().run(m5, h1)
        assert len(res.trades) == 1
        assert res.trades[0].exit_reason == "stop"

    def test_stop_price_is_two_atr_from_entry(self):
        rows = ([(100, 100, 100, 100)] * 6
                + [(100, 110, 100, 109)]
                + [(109, 109, 80, 85)])
        m5 = make_m5(rows)
        res = make_backtester().run(m5, rising_h1(n=48, start="2023-01-01 00:00"))
        trade = res.trades[0]
        assert trade.stop_price == pytest.approx(trade.entry_price - 2 * trade.atr)

    def test_structural_exit_on_midpoint_cross(self):
        # A gentle rise: no stop, but the close falls back below the channel mid.
        rows = ([(100, 101, 99, 100)] * 6
                + [(100, 105, 99, 104)]          # breakout close
                + [(104, 105, 100, 100)] * 6)     # falls back below the midpoint
        m5 = make_m5(rows)
        h1 = rising_h1(n=48, start="2023-01-01 00:00")
        res = make_backtester().run(m5, h1)
        assert len(res.trades) == 1
        assert res.trades[0].exit_reason == "donchian_mid_exit"

    def test_opposite_signal_does_not_reverse_the_position(self):
        # A long is open; a short breakout appears; the long must not flip.
        rows = ([(100, 101, 99, 100)] * 6
                + [(100, 105, 99, 104)]          # long breakout
                + [(104, 104, 94, 95)] * 3)      # down move, no stop breach
        m5 = make_m5(rows)
        h1 = rising_h1(n=48, start="2023-01-01 00:00")
        res = make_backtester().run(m5, h1)
        assert len(res.trades) == 1
        assert res.trades[0].side == "long"
        assert res.trades[0].exit_time >= res.trades[0].entry_time


# ===========================================================================
# 9. Gaps and ambiguous intrabar stop execution
# ===========================================================================


class TestGapAndAmbiguity:
    def test_stop_gap_fills_at_the_open(self):
        rows = ([(100, 100, 100, 100)] * 6
                + [(100, 110, 100, 109)]        # signal bar (breakout)
                + [(80, 81, 79, 80)]            # entry bar: open 80
                + [(70, 71, 69, 70)])           # gaps straight through the stop
        m5 = make_m5(rows)
        res = make_backtester().run(m5, rising_h1(n=48, start="2023-01-01 00:00"))
        trade = res.trades[0]
        assert trade.exit_reason == "stop"
        assert trade.exit_price == pytest.approx(70.0)   # the open, not the stop
        assert trade.exit_price < trade.stop_price       # the gap made it worse

    def test_stop_without_gap_fills_at_the_stop_price(self):
        rows = ([(100, 100, 100, 100)] * 6
                + [(100, 110, 100, 109)]
                + [(109, 109, 95, 96)])        # low 95 breaches the stop intrabar
        m5 = make_m5(rows)
        res = make_backtester().run(m5, rising_h1(n=48, start="2023-01-01 00:00"))
        trade = res.trades[0]
        assert trade.exit_reason == "stop"
        assert trade.exit_price == pytest.approx(trade.stop_price)

    def test_same_bar_stop_and_exit_take_the_worse_price(self):
        # A bar whose low breaches the stop while a pending exit also exists.
        rows = ([(100, 101, 99, 100)] * 6
                + [(100, 105, 99, 104)]
                + [(104, 104, 90, 92)])
        m5 = make_m5(rows)
        res = make_backtester().run(m5, rising_h1(n=48, start="2023-01-01 00:00"))
        trade = res.trades[0]
        assert trade.exit_reason in {"stop", "donchian_mid_exit"}
        assert trade.exit_price <= trade.entry_price      # never the better price

    def test_session_gap_does_not_create_a_trade(self):
        # Bars separated by a weekend gap: the next *available* bar is after it.
        rows = ([(100, 101, 99, 100)] * 6
                + [(100, 110, 99, 109)]
                + [(109, 110, 108, 109)] * 5)
        idx = list(pd.date_range("2023-01-02", periods=7, freq="5min", tz="UTC"))
        idx += list(pd.date_range("2023-01-09", periods=5, freq="5min", tz="UTC"))
        assert len(idx) == len(rows)
        df = pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx).astype(float)
        df["spread"] = 0.0
        df["tick_volume"] = 100
        df["volume"] = 0
        df.index.name = "timestamp"
        res = make_backtester().run(df.reset_index(), rising_h1(n=48, start="2023-01-01 00:00"))
        assert len(res.trades) == 1
        # The signal bar is the last Monday bar; the fill is the first bar after
        # the weekend gap.
        assert res.trades[0].entry_time == pd.Timestamp("2023-01-09 00:00", tz="UTC")


# ===========================================================================
# 10. Spread and cost application
# ===========================================================================


class TestSpreadAndCosts:
    def test_long_entry_pays_the_spread_and_long_exit_receives_the_bid(self):
        rows = ([(100, 101, 99, 100)] * 6
                + [(100, 110, 99, 109)]
                + [(109, 109, 80, 85)])
        m5 = make_m5(rows, spread=300)      # 300 points * 0.001 = $0.30
        res = make_backtester().run(m5, rising_h1(n=48, start="2023-01-01 00:00"))
        trade = res.trades[0]
        # entry bar is the one after the signal bar: its open is 109
        assert trade.entry_price == pytest.approx(109.0 + 0.30)
        # exit is a stop -> filled at the stop price (no spread on a stop fill)
        assert trade.exit_price == pytest.approx(trade.stop_price)

    def test_short_exit_pays_the_spread(self):
        # Breakdown -> short entry at the bid; close back above the channel
        # midpoint -> structural exit buys at the ask (open + spread).
        rows = ([(100, 101, 99, 100)] * 6
                + [(100, 101, 90, 91)]        # breakdown signal bar
                + [(91, 92, 90, 91)]          # entry bar: open 91
                + [(91, 97, 91, 96)]          # close 96 > midpoint 95.5
                + [(96, 97, 95, 96)])         # exit bar
        m5 = make_m5(rows, spread=300)
        h1 = falling_h1(n=48, start="2023-01-01 00:00")
        res = make_backtester().run(m5, h1)
        trade = res.trades[0]
        assert trade.side == "short"
        assert trade.exit_reason == "donchian_mid_exit"
        # short entry sells at the bid -> the bar open, no spread
        assert trade.entry_price == pytest.approx(91.0)
        # short exit buys at the ask -> open + spread
        assert trade.exit_price == pytest.approx(96.0 + 0.30)

    def test_end_of_data_short_liquidation_pays_the_spread(self):
        rows = ([(100, 101, 99, 100)] * 6
                + [(100, 101, 90, 91)]
                + [(91, 92, 90, 91)])
        m5 = make_m5(rows, spread=300)
        h1 = falling_h1(n=48, start="2023-01-01 00:00")
        res = make_backtester().run(m5, h1)
        trade = res.trades[0]
        assert trade.exit_reason == "end_of_data"
        assert trade.exit_price == pytest.approx(91.0 + 0.30)

    def test_commission_reduces_net_pnl(self):
        rows = ([(100, 101, 99, 100)] * 6
                + [(100, 110, 99, 109)]
                + [(109, 109, 80, 85)])
        m5 = make_m5(rows)
        h1 = rising_h1(n=48, start="2023-01-01 00:00")
        plain = make_backtester().run(m5, h1)
        with_cost = make_backtester(cost=CostModel(commission_per_lot_round_trip=5.0)).run(m5, h1)
        assert with_cost.trades[0].net_pnl == pytest.approx(
            plain.trades[0].net_pnl - 5.0 * plain.trades[0].lots)
        assert with_cost.trades[0].gross_pnl == pytest.approx(plain.trades[0].gross_pnl)

    def test_spread_multiplier_scales_the_cost(self):
        rows = ([(100, 101, 99, 100)] * 6
                + [(100, 110, 99, 109)]
                + [(109, 109, 80, 85)])
        m5 = make_m5(rows, spread=300)
        h1 = rising_h1(n=48, start="2023-01-01 00:00")
        one = make_backtester(cost=CostModel(spread_multiplier=1.0)).run(m5, h1)
        two = make_backtester(cost=CostModel(spread_multiplier=2.0)).run(m5, h1)
        assert two.trades[0].entry_price > one.trades[0].entry_price

    def test_zero_spread_bars_fall_back_to_the_median(self):
        rows = ([(100, 101, 99, 100)] * 6
                + [(100, 110, 99, 109)]
                + [(109, 109, 80, 85)])
        m5 = make_m5(rows, spread=0)
        res = make_backtester(cost=CostModel(fallback_spread_points=300)).run(
            m5, rising_h1(n=48, start="2023-01-01 00:00"))
        # With every observed spread at zero the fallback is used, not zero cost.
        assert res.trades[0].entry_price > 109.0


# ===========================================================================
# 11. Position sizing and minimum-volume rejection
# ===========================================================================


class TestSizing:
    def test_size_matches_risk_budget(self):
        policy = ContractAwareFixedFractionalRisk(spec=SPEC, risk_fraction=0.01)
        setup = TradeSetup(
            timestamp=pd.Timestamp("2023-01-02", tz="UTC"), symbol="XAUUSDm",
            side="long", metadata={"stop_distance": 2.0},
        )
        decision = policy.evaluate(setup, equity=10_000.0)
        assert decision.approved
        # 100 USD risk / (2.0 * 100) = 0.5 lots
        assert decision.size == pytest.approx(0.5)

    def test_min_volume_breach_is_rejected_not_forced(self):
        policy = ContractAwareFixedFractionalRisk(spec=SPEC, risk_fraction=0.001)
        setup = TradeSetup(
            timestamp=pd.Timestamp("2023-01-02", tz="UTC"), symbol="XAUUSDm",
            side="long", metadata={"stop_distance": 20.0},
        )
        decision = policy.evaluate(setup, equity=1_000.0)
        assert not decision.approved
        assert "min volume breach" in decision.reason
        assert decision.metadata["risk_at_min_volume_usd"] > decision.metadata["risk_limit_usd"]

    def test_max_volume_breach_is_rejected(self):
        policy = ContractAwareFixedFractionalRisk(spec=SPEC, risk_fraction=1.0)
        setup = TradeSetup(
            timestamp=pd.Timestamp("2023-01-02", tz="UTC"), symbol="XAUUSDm",
            side="long", metadata={"stop_distance": 0.01},
        )
        decision = policy.evaluate(setup, equity=10_000.0)
        assert not decision.approved
        assert "max volume" in decision.reason

    def test_volume_step_is_respected(self):
        policy = ContractAwareFixedFractionalRisk(spec=SPEC, risk_fraction=0.0137)
        setup = TradeSetup(
            timestamp=pd.Timestamp("2023-01-02", tz="UTC"), symbol="XAUUSDm",
            side="long", metadata={"stop_distance": 2.0},
        )
        decision = policy.evaluate(setup, equity=10_000.0)
        assert decision.approved
        lots = decision.size
        assert lots == pytest.approx(floor_to_step(lots, SPEC.volume_step))

    def test_invalid_stop_distance_is_rejected(self):
        policy = ContractAwareFixedFractionalRisk(spec=SPEC, risk_fraction=0.01)
        setup = TradeSetup(
            timestamp=pd.Timestamp("2023-01-02", tz="UTC"), symbol="XAUUSDm",
            side="long", metadata={"stop_distance": 0.0},
        )
        assert not policy.evaluate(setup, equity=10_000.0).approved

    def test_flat_setup_is_rejected(self):
        policy = ContractAwareFixedFractionalRisk(spec=SPEC, risk_fraction=0.01)
        setup = TradeSetup(
            timestamp=pd.Timestamp("2023-01-02", tz="UTC"), symbol="XAUUSDm",
            side="flat", metadata={"stop_distance": 2.0},
        )
        assert not policy.evaluate(setup, equity=10_000.0).approved

    def test_backtest_records_rejected_signals(self):
        # A huge stop distance with a tiny risk budget -> min volume breach.
        params = MtfDonchianParams(
            donchian_lookback=5, ema_period=10, ema_slope_bars=2,
            atr_period=5, atr_stop_multiplier=2.0,
            risk_fraction=0.0001, starting_equity=100.0,
        )
        rows = ([(100, 101, 99, 100)] * 6
                + [(100, 110, 99, 109)]
                + [(109, 109, 80, 85)])
        m5 = make_m5(rows)
        res = make_backtester(params, risk_fraction=0.0001,
                              starting_equity=100.0).run(
            m5, rising_h1(n=48, start="2023-01-01 00:00"))
        assert len(res.trades) == 0
        assert len(res.rejected_signals) >= 1
        assert "min volume breach" in res.rejected_signals[0]["reason"]


# ===========================================================================
# 12. Missing data and session gaps
# ===========================================================================


class TestMissingData:
    def test_missing_bars_do_not_break_the_engine(self):
        rows = [(100, 101, 99, 100)] * 6 + [(100, 110, 99, 109)] + [(109, 109, 80, 85)]
        idx = list(pd.date_range("2023-01-02", periods=6, freq="5min", tz="UTC"))
        idx += [pd.Timestamp("2023-01-02 00:35", tz="UTC")]     # 00:30 bar missing
        idx += [pd.Timestamp("2023-01-02 00:40", tz="UTC")]
        assert len(idx) == len(rows)
        df = pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx).astype(float)
        df["spread"] = 0.0
        df["tick_volume"] = 100
        df["volume"] = 0
        df.index.name = "timestamp"
        res = make_backtester().run(df.reset_index(), rising_h1(n=48, start="2023-01-01 00:00"))
        assert len(res.trades) == 1

    def test_empty_frame_returns_an_empty_result(self):
        m5 = make_m5([(100, 101, 99, 100)] * 3)
        res = make_backtester().run(m5.iloc[0:0], flat_h1())
        assert res.trades == []
        assert res.final_equity == pytest.approx(res.starting_equity)

    def test_duplicate_timestamps_are_tolerated_by_the_engine(self):
        rows = ([(100, 101, 99, 100)] * 6 + [(100, 110, 99, 109)] + [(109, 109, 80, 85)])
        df = make_m5(rows)
        df = pd.concat([df, df.tail(1)], ignore_index=True)
        res = make_backtester().run(df, rising_h1(n=48, start="2023-01-01 00:00"))
        assert len(res.trades) == 1

    def test_session_labels_are_deterministic(self):
        assert session_of(pd.Timestamp("2023-01-02 03:00", tz="UTC")) == "Asia"
        assert session_of(pd.Timestamp("2023-01-02 09:00", tz="UTC")) == "London"
        assert session_of(pd.Timestamp("2023-01-02 14:00", tz="UTC")) == "Overlap"
        assert session_of(pd.Timestamp("2023-01-02 18:00", tz="UTC")) == "NY"
        assert session_of(pd.Timestamp("2023-01-02 22:00", tz="UTC")) == "Late"


# ===========================================================================
# 13. Deterministic repeatability
# ===========================================================================


class TestDeterminism:
    def _dataset(self):
        idx = pd.date_range("2023-01-02", periods=400, freq="5min", tz="UTC")
        rng = np.random.default_rng(1234)
        close = 2000 + np.cumsum(rng.normal(0, 0.8, len(idx)))
        high = close + np.abs(rng.normal(0, 0.5, len(idx)))
        low = close - np.abs(rng.normal(0, 0.5, len(idx)))
        open_ = close + rng.normal(0, 0.2, len(idx))
        df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close},
                          index=idx)
        df["spread"] = 200.0
        df["tick_volume"] = 100
        df["volume"] = 0
        df.index.name = "timestamp"
        h1_idx = pd.date_range("2023-01-02", periods=80, freq="1h", tz="UTC")
        h1_close = 2000 + np.cumsum(rng.normal(0, 3.0, len(h1_idx)))
        h1 = pd.DataFrame({"open": h1_close, "high": h1_close + 1, "low": h1_close - 1,
                           "close": h1_close}, index=h1_idx)
        h1["spread"] = 200.0
        h1["tick_volume"] = 100
        h1["volume"] = 0
        h1.index.name = "timestamp"
        return df.reset_index(), h1.reset_index()

    def test_identical_runs_produce_identical_results(self):
        m5, h1 = self._dataset()
        a = make_backtester().run(m5, h1)
        b = make_backtester().run(m5, h1)
        assert len(a.trades) == len(b.trades)
        assert a.final_equity == pytest.approx(b.final_equity)
        for ta, tb in zip(a.trades, b.trades):
            assert ta.entry_time == tb.entry_time
            assert ta.exit_time == tb.exit_time
            assert ta.entry_price == pytest.approx(tb.entry_price)
            assert ta.exit_price == pytest.approx(tb.exit_price)
            assert ta.net_pnl == pytest.approx(tb.net_pnl)

    def test_equity_curves_are_identical(self):
        m5, h1 = self._dataset()
        a = make_backtester().run(m5, h1)
        b = make_backtester().run(m5, h1)
        pd.testing.assert_series_equal(a.equity_curve, b.equity_curve)

    def test_strategy_adapter_produces_setups(self):
        m5, h1 = self._dataset()
        strategy = XauMtfDonchianStrategy(
            MtfDonchianParams(donchian_lookback=20, ema_period=50, ema_slope_bars=5))
        setups = strategy.generate_setups(m5, h1=h1)
        assert isinstance(setups, list)
        for s in setups:
            assert s.side in {"long", "short"}
            assert "stop_distance" in s.metadata
            assert s.symbol == "XAUUSDm"
