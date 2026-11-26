"""
Unit tests for Assignment 23: M1/Tick Data Acquisition & Short-Horizon Research Foundation.

Tests cover:
1. M1 timeframe enum and MT5Ingestor integration
2. Tick normalization and validation
3. M5→M1 alignment (no look-ahead, correct timing)
4. Cost model (itemized, no double-counting)
5. Feasibility calculator (independent $30 verification)
6. Ingestion pipeline for M1 and ticks
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from mars.core.timeframes import Timeframe, TIMEFRAME_MINUTES, SUPPORTED_TIMEFRAMES, TIMEFRAME_ROLES
from mars.data.ingestion.mt5 import MT5Ingestor
from mars.data.normalization.ticks import TickNormalizer, validate_tick_integrity, resample_ticks_to_m1
from mars.data.validation.checks import (
    check_tick_schema,
    check_tick_integrity as check_tick_integrity_checks,
    check_m1_ohlc_consistency,
)
from mars.data.validation.pipeline import MarketDataValidator
from mars.data.ingestion.pipeline import IngestionPipeline
from mars.libs.execution.alignment import M5ToM1Alignment, create_aligned_execution_frame, AlignmentConfig
from mars.libs.execution.cost_model import ExnessXAUUSDmCostModel, CostBreakdown, create_cost_model_from_spec
from mars.libs.risk.feasibility import AccountFeasibilityAnalyzer, FeasibilityResult
from mars.libs.risk.contract_aware import InstrumentSpec


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sample_ticks() -> pd.DataFrame:
    """Create sample tick data for testing."""
    n = 1000
    idx = pd.date_range("2024-01-01", periods=n, freq="100ms", tz="UTC")
    np.random.seed(42)
    
    # Generate realistic bid/ask with spread
    base_price = 2000.0
    bid = base_price + np.cumsum(np.random.randn(n) * 0.01)
    spread = np.abs(np.random.randn(n) * 10) + 20  # 20-40 points spread
    ask = bid + spread * 0.001  # point_size = 0.001
    
    df = pd.DataFrame({
        "timestamp": idx,
        "bid": bid,
        "ask": ask,
        "last": bid,
        "volume": np.random.randint(1, 10, n),
        "flags": 0,
    }).set_index("timestamp")
    
    return df


@pytest.fixture
def sample_m1() -> pd.DataFrame:
    """Create sample M1 OHLCV data."""
    n = 500
    idx = pd.date_range("2024-01-01", periods=n, freq="1min", tz="UTC")
    np.random.seed(42)
    
    base = 2000.0
    closes = base + np.cumsum(np.random.randn(n) * 0.1)
    opens = np.roll(closes, 1)
    opens[0] = base
    highs = np.maximum(opens, closes) + np.abs(np.random.randn(n) * 0.05)
    lows = np.minimum(opens, closes) - np.abs(np.random.randn(n) * 0.05)
    spread = np.abs(np.random.randn(n) * 10) + 20
    
    df = pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": np.random.randint(100, 1000, n),
        "spread": spread,
    }, index=idx)
    df.index.name = "timestamp"
    
    return df


@pytest.fixture
def sample_m5() -> pd.DataFrame:
    """Create sample M5 OHLCV data."""
    n = 200
    idx = pd.date_range("2024-01-01", periods=n, freq="5min", tz="UTC")
    np.random.seed(42)
    
    base = 2000.0
    closes = base + np.cumsum(np.random.randn(n) * 0.2)
    opens = np.roll(closes, 1)
    opens[0] = base
    highs = np.maximum(opens, closes) + np.abs(np.random.randn(n) * 0.1)
    lows = np.minimum(opens, closes) - np.abs(np.random.randn(n) * 0.1)
    spread = np.abs(np.random.randn(n) * 15) + 25
    
    df = pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": np.random.randint(500, 5000, n),
        "spread": spread,
    }, index=idx)
    df.index.name = "timestamp"
    
    return df


@pytest.fixture
def sample_h1() -> pd.DataFrame:
    """Create sample H1 OHLCV data."""
    n = 50
    idx = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    np.random.seed(42)
    
    base = 2000.0
    closes = base + np.cumsum(np.random.randn(n) * 0.5)
    opens = np.roll(closes, 1)
    opens[0] = base
    highs = np.maximum(opens, closes) + np.abs(np.random.randn(n) * 0.3)
    lows = np.minimum(opens, closes) - np.abs(np.random.randn(n) * 0.3)
    spread = np.abs(np.random.randn(n) * 20) + 30
    
    df = pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": np.random.randint(5000, 50000, n),
        "spread": spread,
    }, index=idx)
    df.index.name = "timestamp"
    
    return df


@pytest.fixture
def exness_spec() -> InstrumentSpec:
    """Exness XAUUSDm verified spec."""
    return InstrumentSpec(
        symbol="XAUUSDm",
        contract_size=100.0,
        pip_size=0.01,
        point_size=0.001,
        quote_currency="USD",
        volume_min=0.01,
        volume_max=200.0,
        volume_step=0.01,
        volume_spec_source="mt5.live",
        spec_source="mt5.live",
    )


# ============================================================================
# 1. Timeframe Enum Tests
# ============================================================================

class TestM1Timeframe:
    def test_m1_in_enum(self):
        """M1 should be a valid Timeframe enum value."""
        assert Timeframe.M1 == "M1"
        assert Timeframe("M1") == Timeframe.M1
    
    def test_m1_minutes(self):
        """M1 should have 1 minute."""
        assert TIMEFRAME_MINUTES[Timeframe.M1] == 1
        assert Timeframe.M1.minutes == 1
    
    def test_m1_in_supported(self):
        """M1 should be in SUPPORTED_TIMEFRAMES."""
        assert Timeframe.M1 in SUPPORTED_TIMEFRAMES
        # Should be the finest (last)
        assert SUPPORTED_TIMEFRAMES[-1] == Timeframe.M1
    
    def test_m1_role(self):
        """M1 should have execution_timing role."""
        assert TIMEFRAME_ROLES[Timeframe.M1] == "execution_timing"
    
    def test_m1_finer_than_m5(self):
        """M1 should be finer than M5."""
        assert Timeframe.M1.is_finer_than(Timeframe.M5)
        assert Timeframe.M5.is_coarser_than(Timeframe.M1)


# ============================================================================
# 2. MT5Ingestor Tests
# ============================================================================

class TestMT5IngestorM1:
    def test_timeframe_map_has_m1(self):
        """TIMEFRAME_MAP should include M1."""
        ingestor = MT5Ingestor()
        assert Timeframe.M1 in ingestor.TIMEFRAME_MAP
        assert ingestor.TIMEFRAME_MAP[Timeframe.M1] == "TIMEFRAME_M1"
    
    def test_ingest_ticks_method_exists(self):
        """MT5Ingestor should have ingest_ticks method."""
        ingestor = MT5Ingestor()
        assert hasattr(ingestor, "ingest_ticks")
        import inspect
        sig = inspect.signature(ingestor.ingest_ticks)
        params = list(sig.parameters.keys())
        assert "symbol" in params
        assert "start" in params
        assert "end" in params
        assert "tick_type" in params


# ============================================================================
# 3. Tick Normalization Tests
# ============================================================================

class TestTickNormalizer:
    def test_normalize_creates_canonical_schema(self, sample_ticks):
        """TickNormalizer should produce canonical schema."""
        normalizer = TickNormalizer()
        normalized = normalizer.normalize(sample_ticks.reset_index())
        
        # Check index
        assert isinstance(normalized.index, pd.DatetimeIndex)
        assert normalized.index.tz is not None
        assert normalized.index.name == "timestamp"
        
        # Check required columns
        for col in ("bid", "ask", "last", "volume"):
            assert col in normalized.columns
        
        # Check spread computed
        assert "spread" in normalized.columns
    
    def test_bid_ask_order_preserved(self, sample_ticks):
        """Bid should be <= Ask after normalization."""
        normalizer = TickNormalizer()
        normalized = normalizer.normalize(sample_ticks.reset_index())
        
        assert (normalized["bid"] <= normalized["ask"]).all()
    
    def test_positive_prices(self, sample_ticks):
        """Prices should be positive after normalization."""
        normalizer = TickNormalizer()
        normalized = normalizer.normalize(sample_ticks.reset_index())
        
        for col in ("bid", "ask", "last"):
            assert (normalized[col] > 0).all()
    
    def test_monotonic_timestamps(self, sample_ticks):
        """Timestamps should be monotonic after normalization."""
        normalizer = TickNormalizer()
        normalized = normalizer.normalize(sample_ticks.reset_index())
        
        assert normalized.index.is_monotonic_increasing
    
    def test_no_duplicate_timestamps(self, sample_ticks):
        """Duplicate timestamps should be removed."""
        # Create duplicates
        dup_ticks = pd.concat([sample_ticks, sample_ticks.iloc[:10]])
        
        normalizer = TickNormalizer()
        normalized = normalizer.normalize(dup_ticks.reset_index())
        
        assert not normalized.index.duplicated().any()
        assert len(normalized) == len(sample_ticks)
    
    def test_validate_tick_integrity_passes(self, sample_ticks):
        """validate_tick_integrity should pass for clean data."""
        normalizer = TickNormalizer()
        normalized = normalizer.normalize(sample_ticks.reset_index())
        
        issues = validate_tick_integrity(normalized)
        assert len(issues) == 0
    
    def test_validate_tick_integrity_catches_bid_gt_ask(self, sample_ticks):
        """Should catch bid > ask."""
        bad_ticks = sample_ticks.copy()
        bad_ticks.loc[bad_ticks.index[0], "bid"] = bad_ticks.loc[bad_ticks.index[0], "ask"] + 1.0
        
        issues = validate_tick_integrity(bad_ticks)
        assert any("bid > ask" in i.lower() for i in issues)
    
    def test_resample_ticks_to_m1(self, sample_ticks):
        """Should resample ticks to M1 OHLCV."""
        m1 = resample_ticks_to_m1(sample_ticks)
        
        assert len(m1) > 0
        for col in ("open", "high", "low", "close", "volume", "spread"):
            assert col in m1.columns
        
        # OHLC consistency
        assert (m1["high"] >= m1[["open", "close"]].max(axis=1)).all()
        assert (m1["low"] <= m1[["open", "close"]].min(axis=1)).all()


# ============================================================================
# 4. Validation Checks Tests
# ============================================================================

class TestTickValidationChecks:
    def test_check_tick_schema(self, sample_ticks):
        """check_tick_schema should validate required columns."""
        issues = check_tick_schema(sample_ticks)
        assert len(issues) == 0
    
    def test_check_tick_schema_missing_columns(self):
        """Should error on missing bid/ask."""
        df = pd.DataFrame({"last": [1.0], "volume": [100]})
        df.index = pd.DatetimeIndex(["2024-01-01"], tz="UTC")
        
        issues = check_tick_schema(df)
        assert any(i.code == "TICK_SCHEMA_MISSING_COLUMNS" for i in issues)
    
    def test_check_tick_integrity_bid_gt_ask(self, sample_ticks):
        """check_tick_integrity should catch bid > ask."""
        bad = sample_ticks.copy()
        bad.loc[bad.index[0], "bid"] = bad.loc[bad.index[0], "ask"] + 1.0
        
        issues = check_tick_integrity_checks(bad)
        assert any(i.code == "TICK_BID_GREATER_THAN_ASK" for i in issues)
    
    def test_check_tick_integrity_negative_spread(self, sample_ticks):
        """Should catch negative spread."""
        bad = sample_ticks.copy()
        bad["spread"] = -10
        
        issues = check_tick_integrity_checks(bad)
        assert any(i.code == "TICK_SPREAD_NEGATIVE" for i in issues)
    
    def test_check_m1_ohlc_consistency(self, sample_m1):
        """M1 OHLC consistency check should pass for valid data."""
        issues = check_m1_ohlc_consistency(sample_m1)
        assert len(issues) == 0
    
    def test_check_m1_ohlc_inconsistent(self, sample_m1):
        """Should catch OHLC violations."""
        df = sample_m1.copy()
        df.loc[df.index[0], "high"] = df.loc[df.index[0], "low"] - 1  # high < low
        
        issues = check_m1_ohlc_consistency(df)
        assert any(i.code == "M1_OHLC_INCONSISTENT" for i in issues)


# ============================================================================
# 5. MarketDataValidator Integration Tests
# ============================================================================

class TestMarketDataValidatorTick:
    def test_validator_detects_tick_data(self, sample_ticks):
        """Validator should detect tick data and run tick checks."""
        validator = MarketDataValidator()
        report = validator.validate(sample_ticks, Timeframe.M1)
        
        # Should run tick checks, not OHLCV checks
        codes = [i.code for i in report.issues]
        assert "TICK_SCHEMA_MISSING_COLUMNS" not in codes  # has bid/ask
        # Tick integrity checks should run
        assert any("TICK" in c for c in codes) or report.passed
    
    def test_validator_ohlcv_for_m1(self, sample_m1):
        """Validator should run OHLCV checks for M1 bars."""
        m1_with_ts = sample_m1.reset_index()
        validator = MarketDataValidator()
        report = validator.validate(m1_with_ts, Timeframe.M1)
        
        codes = [i.code for i in report.issues]
        # Should run M1 OHLC check
        assert "M1_OHLC_INCONSISTENT" not in codes or report.passed


# ============================================================================
# 6. M5→M1 Alignment Tests
# ============================================================================

class TestM5ToM1Alignment:
    def create_test_signals(self, m5: pd.DataFrame) -> pd.DataFrame:
        """Create synthetic M5 signals for testing."""
        signals = m5.reset_index().copy()
        signals["timestamp"] = signals["timestamp"]  # already timestamp
        signals["donchian_high"] = signals["high"].rolling(20).max().shift(1)
        signals["donchian_low"] = signals["low"].rolling(20).min().shift(1)
        signals["donchian_mid"] = (signals["donchian_high"] + signals["donchian_low"]) / 2
        signals["atr"] = 1.0
        signals["stop_distance"] = 2.0
        signals["h1_regime"] = 1
        signals["entry_long"] = (signals["close"] > signals["donchian_high"]) & (signals["h1_regime"] == 1)
        signals["entry_short"] = (signals["close"] < signals["donchian_low"]) & (signals["h1_regime"] == -1)
        signals["exit_long"] = signals["close"] < signals["donchian_mid"]
        signals["exit_short"] = signals["close"] > signals["donchian_mid"]
        signals["max_holding_bars"] = 6
        return signals
    
    def test_alignment_creates_signal_columns(self, sample_m5, sample_m1):
        """Alignment should propagate M5 signals to M1."""
        m5_signals = self.create_test_signals(sample_m5)
        m1_exec = sample_m1.reset_index()
        
        aligned = create_aligned_execution_frame(m5_signals, m1_exec, max_holding_bars_m1=6)
        
        # Check signal columns exist
        sig_cols = [c for c in aligned.columns if c.startswith("m5_signal_")]
        assert len(sig_cols) > 0
        assert "m5_signal_donchian_high" in aligned.columns
        assert "m5_signal_stop_distance" in aligned.columns
        assert "m5_signal_entry_long" in aligned.columns
    
    def test_no_lookahead_signal_completion(self, sample_m5, sample_m1):
        """M5 signal completion should be <= M1 completion."""
        m5_signals = self.create_test_signals(sample_m5)
        m1_exec = sample_m1.reset_index()
        
        aligner = M5ToM1Alignment()
        aligned = aligner.align_signals_to_execution(m5_signals, m1_exec)
        
        # Check no lookahead
        checks = aligner.check_no_lookahead(aligned)
        assert checks["passed"] is True
        # Check if the completion comparison was run (columns must exist)
        if "signal_completion_before_m1_completion" in checks["checks"]:
            assert checks["checks"]["signal_completion_before_m1_completion"]["passed"] is True
    
    def test_entry_after_signal(self, sample_m5, sample_m1):
        """Entry bar should be after signal bar."""
        m5_signals = self.create_test_signals(sample_m5)
        m1_exec = sample_m1.reset_index()
        
        aligner = M5ToM1Alignment()
        aligned = aligner.align_signals_to_execution(m5_signals, m1_exec)
        checks = aligner.check_no_lookahead(aligned)
        
        assert checks["checks"]["entry_after_signal"]["passed"] is True
    
    def test_entry_fill_price_computed(self, sample_m5, sample_m1):
        """Entry fill prices should be computed for signal bars."""
        m5_signals = self.create_test_signals(sample_m5)
        m1_exec = sample_m1.reset_index()
        
        aligned = create_aligned_execution_frame(m5_signals, m1_exec)
        
        # Should have entry fill price columns
        assert "entry_fill_price_long" in aligned.columns
        assert "entry_fill_price_short" in aligned.columns
    
    def test_stop_prices_computed(self, sample_m5, sample_m1):
        """Stop prices should be computed from stop_distance."""
        m5_signals = self.create_test_signals(sample_m5)
        m1_exec = sample_m1.reset_index()
        
        aligned = create_aligned_execution_frame(m5_signals, m1_exec)
        
        assert "stop_price_long" in aligned.columns
        assert "stop_price_short" in aligned.columns
        
        # Stop price should be entry - stop_distance for long
        valid = aligned["entry_fill_price_long"].notna() & aligned["stop_price_long"].notna()
        if valid.any():
            diff = aligned.loc[valid, "entry_fill_price_long"] - aligned.loc[valid, "stop_price_long"]
            assert (diff - 2.0).abs().max() < 1e-10  # stop_distance = 2.0
    
    def test_max_holding_bars_propagated(self, sample_m5, sample_m1):
        """Max holding bars should be propagated where M5 signal is available."""
        m5_signals = self.create_test_signals(sample_m5)
        m1_exec = sample_m1.reset_index()
        
        aligned = create_aligned_execution_frame(m5_signals, m1_exec, max_holding_bars_m1=6)
        
        assert "max_holding_bars_m1" in aligned.columns
        # Should be 6 where not NaN (after first M5 signal)
        valid = aligned["max_holding_bars_m1"].notna()
        assert valid.any(), "Should have some valid max_holding_bars values"
        assert (aligned.loc[valid, "max_holding_bars_m1"] == 6).all()


# ============================================================================
# 7. Cost Model Tests
# ============================================================================

class TestCostModel:
    def test_cost_model_creation(self, exness_spec):
        """Should create cost model with spec."""
        model = create_cost_model_from_spec(
            spec=exness_spec,
            avg_spread_points=200,
            median_spread_points=180,
            commission_per_lot=0.0,
            swap_long_points=-10.0,
            swap_short_points=-5.0,
        )
        
        assert model.spec.symbol == "XAUUSDm"
        assert model.avg_spread_points == 200
        assert model.median_spread_points == 180
        assert model.commission_per_lot_round_trip_usd == 0.0
    
    def test_round_trip_spread_not_doubled(self, exness_spec):
        """Round trip should count spread ONCE (entry + exit = 1 spread paid)."""
        model = create_cost_model_from_spec(
            spec=exness_spec,
            avg_spread_points=200,
            median_spread_points=180,
        )
        
        # 1 lot, 200 points entry spread, 180 points exit spread
        breakdown = model.calculate_round_trip_cost(
            lots=1.0,
            entry_spread_points=200,
            exit_spread_points=180,
            hold_nights=0,
            side="long",
        )
        
        # Spread cost = (200 + 180) * point_value * lots
        # point_value = 0.001 * 100 = $0.10 per point per lot
        expected_spread = (200 + 180) * 0.10 * 1.0
        assert breakdown.spread_cost_usd == pytest.approx(expected_spread)
        # Total spread points = 380 (NOT 200*2 or 180*2)
        assert breakdown.entry_spread_points == 200
        assert breakdown.exit_spread_points == 180
    
    def test_commission_zero_for_raw_spread(self, exness_spec):
        """Commission should be $0 for Exness raw spread account."""
        model = create_cost_model_from_spec(spec=exness_spec, commission_per_lot=0.0)
        
        breakdown = model.calculate_round_trip_cost(
            lots=1.0, entry_spread_points=200, exit_spread_points=180, hold_nights=0
        )
        
        assert breakdown.commission_usd == 0.0
        assert breakdown.commission_source == "verified"
    
    def test_swap_calculation(self, exness_spec):
        """Swap should be calculated correctly."""
        model = create_cost_model_from_spec(
            spec=exness_spec,
            swap_long_points=-10.0,
            swap_short_points=-5.0,
        )
        
        # Long, 1 night
        breakdown_long = model.calculate_round_trip_cost(
            lots=1.0, entry_spread_points=200, exit_spread_points=180,
            hold_nights=1, side="long"
        )
        # -10 points * $0.10 * 1 lot * 1 night = -$1.00
        assert breakdown_long.swap_usd == pytest.approx(-1.0)
        
        # Short, 1 night
        breakdown_short = model.calculate_round_trip_cost(
            lots=1.0, entry_spread_points=200, exit_spread_points=180,
            hold_nights=1, side="short"
        )
        # -5 points * $0.10 * 1 lot * 1 night = -$0.50
        assert breakdown_short.swap_usd == pytest.approx(-0.5)
    
    def test_slippage_per_fill(self, exness_spec):
        """Slippage should be applied per fill (entry + exit = 2 fills)."""
        model = create_cost_model_from_spec(
            spec=exness_spec,
            slippage_points=5.0,
        )
        
        breakdown = model.calculate_round_trip_cost(
            lots=1.0, entry_spread_points=200, exit_spread_points=180,
            hold_nights=0
        )
        
        # 2 fills * 5 points * $0.10 * 1 lot = $1.00
        assert breakdown.slippage_usd == pytest.approx(1.0)
    
    def test_cost_breakdown_itemized(self, exness_spec):
        """CostBreakdown should have all items separated."""
        model = create_cost_model_from_spec(spec=exness_spec)
        
        breakdown = model.calculate_round_trip_cost(
            lots=0.01, entry_spread_points=200, exit_spread_points=180,
            hold_nights=1, side="long"
        )
        
        # All fields present
        assert breakdown.spread_cost_usd >= 0
        assert breakdown.commission_usd >= 0
        assert breakdown.swap_usd <= 0  # negative for long
        assert breakdown.slippage_usd >= 0
        assert breakdown.total_usd == pytest.approx(
            breakdown.spread_cost_usd + breakdown.commission_usd +
            breakdown.swap_usd + breakdown.slippage_usd
        )
        
        # Source tracking
        assert breakdown.spread_source in ("observed", "fallback")
        assert breakdown.commission_source in ("verified", "assumed")
        assert breakdown.swap_source in ("verified", "assumed")
        assert breakdown.slippage_source == "assumed"


# ============================================================================
# 8. Feasibility Calculator Tests
# ============================================================================

class TestFeasibilityCalculator:
    def test_infeasible_at_30_usd(self, exness_spec):
        """Should be infeasible at $30 with typical stop distance."""
        # Typical stop: 2.0 price units * 100 oz = $200 per lot
        # Risk budget at $30, 1% = $0.30
        # Lots needed = 0.30 / 200 = 0.0015 -> floored to 0.00 -> rejected
        
        analyzer = AccountFeasibilityAnalyzer(
            spec=exness_spec,
            equity_usd=30.0,
            risk_fraction=0.01,
        )
        
        result = analyzer.analyze(
            avg_stop_distance_price=2.0,  # $200 risk per lot
            avg_spread_points=200,
            entry_price=2000.0,
        )
        
        assert result.feasible is False
        assert "min volume breach" in result.rejection_reason
        assert result.risk_at_min_lot_usd == pytest.approx(2.0)  # 0.01 * $200
        assert result.risk_budget_usd == 0.30
    
    def test_feasible_with_tight_stop(self, exness_spec):
        """Should be feasible with very tight stop."""
        # Stop: 0.01 price units * 100 oz = $1 per lot
        # Risk budget = $0.30
        # Lots needed = 0.30 / 1.0 = 0.3 -> floored to 0.3 -> OK
        
        analyzer = AccountFeasibilityAnalyzer(
            spec=exness_spec,
            equity_usd=30.0,
            risk_fraction=0.01,
        )
        
        result = analyzer.analyze(
            avg_stop_distance_price=0.01,  # $1 risk per lot
            avg_spread_points=200,
            entry_price=2000.0,
        )
        
        assert result.feasible is True
        assert result.lots_floored >= 0.01
    
    def test_minimum_equity_calculation(self, exness_spec):
        """Should calculate minimum equity correctly."""
        analyzer = AccountFeasibilityAnalyzer(
            spec=exness_spec,
            equity_usd=30.0,
            risk_fraction=0.01,
        )
        
        # Stop = 2.0 -> risk at min lot = $2.00
        # For 1% risk budget: equity = 2.00 / 0.01 = $200
        min_equity = analyzer.find_minimum_viable_equity(avg_stop_distance_price=2.0)
        
        assert min_equity == pytest.approx(200.0)
    
    def test_margin_calculation(self, exness_spec):
        """Margin should be calculated correctly."""
        analyzer = AccountFeasibilityAnalyzer(
            spec=exness_spec,
            equity_usd=30.0,
            risk_fraction=0.01,
            leverage=2000,
        )
        
        result = analyzer.analyze(
            avg_stop_distance_price=0.01,  # feasible
            avg_spread_points=200,
            entry_price=2000.0,
        )
        
        # Margin = (2000 * 100 * 0.01) / 2000 = $1.0
        assert result.margin_required_usd == pytest.approx(1.0)
        assert result.free_margin_after_entry_usd == pytest.approx(29.0)
        assert result.margin_level_pct == pytest.approx(3000.0)
    
    def test_cost_per_trade_at_min_lot(self, exness_spec):
        """Cost per trade at min lot should be calculated."""
        analyzer = AccountFeasibilityAnalyzer(
            spec=exness_spec,
            equity_usd=30.0,
            risk_fraction=0.01,
        )
        
        result = analyzer.analyze(
            avg_stop_distance_price=0.01,
            avg_spread_points=200,
            entry_price=2000.0,
        )
        
        # Spread: 200 points * $0.10 * 0.01 = $0.20
        assert result.spread_cost_per_trade_usd == pytest.approx(0.20)
        assert result.commission_per_trade_usd == 0.0
        assert result.total_cost_per_trade_usd >= result.spread_cost_per_trade_usd
    
    def test_result_serialization(self, exness_spec):
        """FeasibilityResult should serialize to dict."""
        analyzer = AccountFeasibilityAnalyzer(spec=exness_spec)
        result = analyzer.analyze(0.01, 200, 2000.0)
        
        d = result.to_dict()
        assert "feasible" in d
        assert "rejection_reason" in d
        assert "min_equity_required_usd" in d


# ============================================================================
# 9. Ingestion Pipeline Tests
# ============================================================================

class TestIngestionPipeline:
    def test_pipeline_accepts_custom_normalizer(self):
        """IngestionPipeline should accept custom normalizer in run()."""
        pipeline = IngestionPipeline(ingestor=None)  # ingestor not used in this test
        
        # Check run method signature accepts normalizer parameter
        import inspect
        sig = inspect.signature(pipeline.run)
        assert "normalizer" in sig.parameters
    
    def test_pipeline_has_run_ticks_method(self):
        """IngestionPipeline should have run_ticks method."""
        pipeline = IngestionPipeline(ingestor=None)
        assert hasattr(pipeline, "run_ticks")


# ============================================================================
# 10. Integration: Assignment 22 Result Reproduction
# ============================================================================

class TestAssignment22Reproduction:
    """Verify Assignment 22 feasibility finding is reproduced."""
    
    def test_assignment22_min_risk_calculation(self, exness_spec):
        """
        Assignment 22 found: minimum cash risk per executable trade = $2.09
        Risk budget (1% of $30) = $0.30
        Min lot (0.01) risks 7x budget -> INFEASIBLE
        """
        analyzer = AccountFeasibilityAnalyzer(
            spec=exness_spec,
            equity_usd=30.0,
            risk_fraction=0.01,
        )
        
        # From Assignment 22: avg stop distance ~2.09 price units for XAUUSDm
        # Risk per lot = 2.09 * 100 = $209
        # Risk at 0.01 lots = $2.09
        result = analyzer.analyze(
            avg_stop_distance_price=2.09,
            avg_spread_points=200,
            entry_price=2000.0,
        )
        
        assert result.feasible is False
        assert result.risk_at_min_lot_usd == pytest.approx(2.09, rel=0.01)
        assert result.risk_budget_usd == 0.30
        assert result.risk_at_min_lot_multiple_of_budget == pytest.approx(6.97, rel=0.05)  # ~7x
        assert result.min_equity_required_usd == pytest.approx(209.0, rel=0.05)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])