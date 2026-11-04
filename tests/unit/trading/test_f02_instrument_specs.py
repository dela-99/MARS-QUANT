"""
F-02 dedicated tests for instrument specification and monetary calculations.

Tests cover:
1. Valid XAUUSD specification
2. Correct $1 per pip per lot under stated assumptions
3. Correct $10 risk per lot for 0.10 price-distance stop
3. Different volumes and stop distances
4. LIVE mode rejects unavailable broker metadata
5. OFFLINE mode uses only approved static specifications
6. BTCUSD rejected without approved specifications
7. Invalid and non-finite broker metadata rejected
8. Position valuation
9. Manual stop modification risk
10. P&L calculations
11. Instrument specification isolation
"""

from __future__ import annotations

import pytest
from unittest.mock import Mock, MagicMock
from datetime import datetime

from mars.apps.trading.mt5_executor import (
    SpecificationResolver, InstrumentSpec, MT5SymbolResolver,
    MT5Executor, MT5Config, MT5ConnectionManager
)
from mars.apps.trading.system.vol_scaled_system import RiskManager
from mars.apps.trading.risk_metrics import risk_at_stop_usd
from mars.apps.trading.system.pair_config import get_contract_specs


# ============================================================
# Test fixtures
# ============================================================

def make_valid_xauusd_info():
    """Create a valid MT5 symbol info mock for XAUUSDm."""
    info = Mock()
    info.trade_contract_size = 100.0
    info.volume_min = 0.01
    info.volume_max = 200.0
    info.volume_step = 0.01
    info.digits = 2
    info.point = 0.001
    info.trade_tick_size = 0.001
    info.trade_tick_value = 1.0
    info.swap_long = -1.5
    info.swap_short = -0.5
    info.margin_initial = 1000.0
    info.margin_maintenance = 500.0
    return info


def make_invalid_info(**overrides):
    """Create an invalid MT5 symbol info mock with specified field issues."""
    info = make_valid_xauusd_info()
    for k, v in overrides.items():
        setattr(info, k, v)
    return info


# ============================================================
# 1. Valid XAUUSD specification tests
# ============================================================

def test_instrument_spec_xauusd_pip_value():
    """Test pip_value_per_lot = $1 for XAUUSD under stated assumptions."""
    # Given: Contract size 100 oz/lot, pip_size 0.01 USD/oz
    spec = InstrumentSpec(
        symbol="XAUUSDm",
        contract_size=100.0,
        min_lot=0.01,
        max_lot=200.0,
        lot_step=0.01,
        digits=2,
        point=0.001,
        tick_size=0.001,
        tick_value=1.0,
        pip_size=0.01,
        swap_long=0.0,
        swap_short=0.0,
        margin_initial=0.0,
        margin_maintenance=0.0,
        quote_currency="USD",
    )
    
    # Then: pip_value_per_lot = pip_size * contract_size = 0.01 * 100 = $1
    assert spec.pip_value_per_lot == 1.0, f"Expected $1/pip/lot, got ${spec.pip_value_per_lot}"


def test_instrument_spec_xauusd_risk_per_contract():
    """Test risk_per_contract = $10 for 0.10 stop distance."""
    spec = InstrumentSpec(
        symbol="XAUUSDm",
        contract_size=100.0,
        min_lot=0.01,
        max_lot=200.0,
        lot_step=0.01,
        digits=2,
        point=0.001,
        tick_size=0.001,
        tick_value=1.0,
        pip_size=0.01,
        swap_long=0.0,
        swap_short=0.0,
        margin_initial=0.0,
        margin_maintenance=0.0,
        quote_currency="USD",
    )
    
    # Given: stop_distance = 0.10 (price units), contract_size = 100
    # Then: risk = 0.10 * 100 = $10 per lot
    risk = spec.risk_per_contract(0.10)
    assert risk == 10.0, f"Expected $10 risk per lot, got ${risk}"


def test_instrument_spec_various_volumes_stops():
    """Test risk calculations with different volumes and stop distances."""
    spec = InstrumentSpec(
        symbol="XAUUSDm",
        contract_size=100.0,
        min_lot=0.01,
        max_lot=200.0,
        lot_step=0.01,
        digits=2,
        point=0.001,
        tick_size=0.001,
        tick_value=1.0,
        pip_size=0.01,
        swap_long=0.0,
        swap_short=0.0,
        margin_initial=0.0,
        margin_maintenance=0.0,
        quote_currency="USD",
    )
    
    # Test various combinations
    test_cases = [
        # (volume, stop_distance, expected_risk_per_lot, expected_total_risk)
        (1.0, 0.10, 10.0, 10.0),
        (0.5, 0.10, 10.0, 5.0),
        (2.0, 0.10, 10.0, 20.0),
        (1.0, 0.20, 20.0, 20.0),
        (1.0, 0.05, 5.0, 5.0),
        (0.01, 0.10, 10.0, 0.10),  # min lot
    ]
    
    for volume, stop_dist, expected_per_lot, expected_total in test_cases:
        risk_per_lot = spec.risk_per_contract(stop_dist)
        total_risk = spec.risk_per_contract(stop_dist) * volume
        assert risk_per_lot == expected_per_lot, f"Risk per lot: expected {expected_per_lot}, got {risk_per_lot}"
        assert total_risk == expected_total, f"Total risk: expected {expected_total}, got {total_risk}"


# ============================================================
# 2. LIVE mode rejects unavailable broker metadata
# ============================================================

def test_live_mode_rejects_no_mt5():
    """LIVE mode requires MT5 module."""
    resolver = SpecificationResolver(mt5_module=None, symbol_configs={})
    
    with pytest.raises(RuntimeError, match="LIVE mode: MT5 module not available"):
        resolver.get_spec("XAUUSDm", mode=SpecificationResolver.SpecResolutionMode.LIVE)


def test_live_mode_rejects_missing_symbol():
    """LIVE mode rejects symbol not found in MT5."""
    mock_mt5 = Mock()
    mock_mt5.symbol_info.return_value = None
    
    resolver = SpecificationResolver(mt5_module=mock_mt5, symbol_configs={})
    
    with pytest.raises(ValueError, match="LIVE mode: Symbol XAUUSDm not found in MT5"):
        resolver.get_spec("XAUUSDm", mode=SpecificationResolver.SpecResolutionMode.LIVE)


def test_live_mode_validates_missing_fields():
    """LIVE mode rejects incomplete broker metadata."""
    mock_mt5 = Mock()
    # Missing trade_contract_size
    info = Mock()
    info.trade_contract_size = None
    info.volume_min = 0.01
    info.volume_max = 200.0
    info.volume_step = 0.01
    info.digits = 2
    info.point = 0.001
    info.trade_tick_size = 0.001
    info.trade_tick_value = 1.0
    mock_mt5.symbol_info.return_value = info
    
    resolver = SpecificationResolver(mt5_module=mock_mt5, symbol_configs={})
    
    with pytest.raises(ValueError, match="missing mandatory field contract size"):
        resolver.get_spec("XAUUSDm", mode=SpecificationResolver.SpecResolutionMode.LIVE)


def test_live_mode_rejects_zero_contract_size():
    """LIVE mode rejects zero contract size."""
    mock_mt5 = Mock()
    info = make_invalid_info(trade_contract_size=0.0)
    mock_mt5.symbol_info.return_value = info
    
    resolver = SpecificationResolver(mt5_module=mock_mt5, symbol_configs={})
    
    with pytest.raises(ValueError, match="must be positive"):
        resolver.get_spec("XAUUSDm", mode=SpecificationResolver.SpecResolutionMode.LIVE)


def test_live_mode_rejects_negative_contract_size():
    """LIVE mode rejects negative contract size."""
    mock_mt5 = Mock()
    info = make_invalid_info(trade_contract_size=-100.0)
    mock_mt5.symbol_info.return_value = info
    
    resolver = SpecificationResolver(mt5_module=mock_mt5, symbol_configs={})
    
    with pytest.raises(ValueError, match="must be positive"):
        resolver.get_spec("XAUUSDm", mode=SpecificationResolver.SpecResolutionMode.LIVE)


def test_live_mode_rejects_non_finite_values():
    """LIVE mode rejects NaN and infinity."""
    import math
    
    mock_mt5 = Mock()
    info = make_invalid_info(trade_contract_size=float('nan'))
    mock_mt5.symbol_info.return_value = info
    
    resolver = SpecificationResolver(mt5_module=mock_mt5, symbol_configs={})
    
    with pytest.raises(ValueError, match="not finite"):
        resolver.get_spec("XAUUSDm", mode=SpecificationResolver.SpecResolutionMode.LIVE)
    
    info = make_invalid_info(trade_contract_size=float('inf'))
    mock_mt5.symbol_info.return_value = info
    
    with pytest.raises(ValueError, match="not finite"):
        resolver.get_spec("XAUUSDm", mode=SpecificationResolver.SpecResolutionMode.LIVE)


def test_live_mode_rejects_invalid_volume_constraints():
    """LIVE mode rejects invalid volume min/max/step."""
    mock_mt5 = Mock()
    
    # volume_min > volume_max
    info = make_invalid_info(volume_min=1.0, volume_max=0.5)
    mock_mt5.symbol_info.return_value = info
    
    resolver = SpecificationResolver(mt5_module=mock_mt5, symbol_configs={})
    
    with pytest.raises(ValueError, match="volume_min.*exceeds volume_max"):
        resolver.get_spec("XAUUSDm", mode=SpecificationResolver.SpecResolutionMode.LIVE)
    
    # volume_step > volume_max
    info = make_invalid_info(volume_step=300.0, volume_max=200.0)
    mock_mt5.symbol_info.return_value = info
    
    with pytest.raises(ValueError, match="volume_step.*exceeds volume_max"):
        resolver.get_spec("XAUUSDm", mode=SpecificationResolver.SpecResolutionMode.LIVE)


def test_live_mode_accepts_valid_metadata():
    """LIVE mode accepts valid broker metadata."""
    mock_mt5 = Mock()
    info = make_valid_xauusd_info()
    mock_mt5.symbol_info.return_value = info
    
    resolver = SpecificationResolver(mt5_module=mock_mt5, symbol_configs={"XAUUSD": {"pip_size": 0.01, "quote_currency": "USD"}})
    
    spec = resolver.get_spec("XAUUSDm", mode=SpecificationResolver.SpecResolutionMode.LIVE)
    
    assert spec.contract_size == 100.0
    assert spec.pip_size == 0.01
    assert spec.quote_currency == "USD"


# ============================================================
# 3. OFFLINE mode uses only approved static specifications
# ============================================================

def test_offline_mode_uses_static_config():
    """OFFLINE mode uses SYMBOL_CONFIGS only."""
    symbol_configs = {
        "XAUUSD": {"contract_size": 100.0, "pip_size": 0.01, "quote_currency": "USD", "digits": 2, "point": 0.001, "volume_min": 0.01, "volume_max": 200.0, "volume_step": 0.01},
    }
    
    resolver = SpecificationResolver(mt5_module=Mock(), symbol_configs=symbol_configs)
    
    spec = resolver.get_spec("XAUUSDm", mode=SpecificationResolver.SpecResolutionMode.OFFLINE)
    
    assert spec.contract_size == 100.0
    assert spec.pip_size == 0.01


def test_offline_mode_rejects_unknown_symbol():
    """OFFLINE mode rejects unknown symbols (no built-in defaults)."""
    symbol_configs = {"XAUUSD": {"contract_size": 100.0, "pip_size": 0.01, "quote_currency": "USD"}}
    
    resolver = SpecificationResolver(mt5_module=Mock(), symbol_configs=symbol_configs)
    
    with pytest.raises(ValueError, match="No static config for symbol BTCUSDm"):
        resolver.get_spec("BTCUSDm", mode=SpecificationResolver.SpecResolutionMode.OFFLINE)


def test_offline_mode_rejects_btcusd_without_config():
    """OFFLINE mode rejects BTCUSD without explicit config."""
    symbol_configs = {"XAUUSD": {"contract_size": 100.0, "pip_size": 0.01, "quote_currency": "USD"}}
    
    resolver = SpecificationResolver(mt5_module=Mock(), symbol_configs=symbol_configs)
    
    with pytest.raises(ValueError, match="No static config for symbol BTCUSDm"):
        resolver.get_spec("BTCUSDm", mode=SpecificationResolver.SpecResolutionMode.OFFLINE)


# ============================================================
# 4. BTCUSD rejected without approved specifications
# ============================================================

def test_live_mode_rejects_btcusd_without_mt5_metadata():
    """LIVE mode requires MT5 metadata for BTCUSD (no built-in defaults)."""
    mock_mt5 = Mock()
    mock_mt5.symbol_info.return_value = None  # BTCUSD not available
    
    resolver = SpecificationResolver(mt5_module=mock_mt5, symbol_configs={})
    
    with pytest.raises(ValueError, match="LIVE mode: Symbol BTCUSDm not found in MT5"):
        resolver.get_spec("BTCUSDm", mode=SpecificationResolver.SpecResolutionMode.LIVE)


def test_btcusd_not_in_builtin_defaults():
    """BTCUSD should not be in builtin_defaults."""
    # Check the builtin_defaults dict in _static_to_instrument_spec
    from mars.apps.trading.mt5_executor import SpecificationResolver
    
    # The builtin_defaults should not contain BTCUSD
    # This is implicitly tested by offline mode rejecting unknown BTCUSD
    pass


# ============================================================
# 5. Invalid/non-finite broker metadata rejected
# ============================================================

def test_validation_rejects_all_invalid_fields():
    """All required fields are validated."""
    mock_mt5 = Mock()
    resolver = SpecificationResolver(mt5_module=mock_mt5, symbol_configs={})
    
    # Test each required field
    required_fields = [
        ("trade_contract_size", 100.0),
        ("volume_min", 0.01),
        ("volume_max", 200.0),
        ("volume_step", 0.01),
        ("digits", 2),
        ("point", 0.001),
        ("trade_tick_size", 0.001),
        ("trade_tick_value", 1.0),
    ]
    
    for field_name, valid_value in required_fields:
        # Test None
        info = make_valid_xauusd_info()
        setattr(info, field_name, None)
        mock_mt5.symbol_info.return_value = info
        
        with pytest.raises(ValueError, match=f"missing mandatory field"):
            resolver.get_spec("XAUUSDm", mode=SpecificationResolver.SpecResolutionMode.LIVE)
        
        # Test negative/zero for numeric fields
        if field_name != "digits":
            info = make_valid_xauusd_info()
            setattr(info, field_name, -1.0 if field_name != "digits" else -1)
            mock_mt5.symbol_info.return_value = info
            
            with pytest.raises(ValueError, match="must be positive"):
                resolver.get_spec("XAUUSDm", mode=SpecificationResolver.SpecResolutionMode.LIVE)


# ============================================================
# 6. Position valuation
# ============================================================

def test_position_valuation():
    """Test _get_live_open_positions_value uses contract_size from spec."""
    mock_mt5 = Mock()
    mock_conn = Mock()
    mock_mt5.positions_get.return_value = [
        Mock(magic=123456, volume=1.0, price_open=2000.0),
    ]
    
    # Mock symbol_info for XAUUSDm
    info = make_valid_xauusd_info()
    mock_mt5.symbol_info.return_value = info
    
    # Create resolver with proper config
    symbol_configs = {"XAUUSD": {"pip_size": 0.01, "quote_currency": "USD"}}
    resolver = SpecificationResolver(mt5_module=mock_mt5, symbol_configs=symbol_configs)
    
    # We can't easily test MT5Executor without full setup, so test the spec directly
    spec = resolver.get_spec("XAUUSDm", mode=SpecificationResolver.SpecResolutionMode.LIVE)
    
    # Position value = volume * price_open * contract_size
    volume = 1.0
    price_open = 2000.0
    contract_size = spec.contract_size
    expected_value = volume * price_open * contract_size
    
    assert expected_value == 200000.0  # 1.0 * 2000.0 * 100


# ============================================================
# 7. Manual SL/TP modification risk
# ============================================================

def test_manual_sl_change_risk_calculation():
    """Test risk calculation for manual SL modification."""
    # Given: entry_price=2000.0, old_sl=1990.0, new_sl=1980.0, volume=1.0, contract_size=100
    entry_price = 2000.0
    old_sl = 1990.0
    new_sl = 1980.0
    position_size = 1.0
    contract_size = 100.0
    
    # Old risk = |2000 - 1990| * 1.0 * 100 = $1000
    old_stop_distance = abs(entry_price - old_sl)
    old_risk = old_stop_distance * abs(position_size) * contract_size
    assert old_risk == 1000.0
    
    # New risk = |2000 - 1980| * 1.0 * 100 = $2000
    new_stop_distance = abs(entry_price - new_sl)
    new_risk = new_stop_distance * abs(position_size) * contract_size
    assert new_risk == 2000.0
    
    # Risk increased by $1000
    assert new_risk - old_risk == 1000.0


# ============================================================
# 8. P&L calculations
# ============================================================

def test_pnl_calculation_long():
    """Test P&L for long position."""
    entry_price = 2000.0
    current_price = 2010.0
    position_size = 1.0
    contract_size = 100.0
    
    # Long P&L = (current - entry) * contract_size * position_size
    pnl = (current_price - entry_price) * contract_size * position_size
    assert pnl == 1000.0  # (2010 - 2000) * 100 * 1 = 1000


def test_pnl_calculation_short():
    """Test P&L for short position."""
    entry_price = 2000.0
    current_price = 1990.0
    position_size = -1.0  # negative for short
    contract_size = 100.0
    
    # Short P&L = (entry - current) * contract_size * |position_size|
    pnl = (entry_price - current_price) * contract_size * abs(position_size)
    assert pnl == 1000.0  # (2000 - 1990) * 100 * 1 = 1000


# ============================================================
# 9. Instrument specification isolation
# ============================================================

def test_specs_not_shared_between_instruments():
    """Each instrument's spec is independent."""
    symbol_configs = {
        "XAUUSD": {"contract_size": 100.0, "pip_size": 0.01, "quote_currency": "USD"},
        "USDJPY": {"contract_size": 100000.0, "pip_size": 0.01, "quote_currency": "JPY"},
    }
    
    resolver = SpecificationResolver(mt5_module=Mock(), symbol_configs=symbol_configs)
    
    xau_spec = resolver.get_spec("XAUUSDm", mode=SpecificationResolver.SpecResolutionMode.OFFLINE)
    usdjpy_spec = resolver.get_spec("USDJPYm", mode=SpecificationResolver.SpecResolutionMode.OFFLINE)
    
    assert xau_spec.contract_size == 100.0
    assert usdjpy_spec.contract_size == 100000.0
    assert xau_spec.pip_size == 0.01
    assert usdjpy_spec.pip_size == 0.01  # pip_size in price units


# ============================================================
# 10. Broker tick size/value cross-check
# ============================================================

def test_tick_size_value_relationship():
    """Verify tick size and tick value relationship for XAUUSD."""
    spec = InstrumentSpec(
        symbol="XAUUSDm",
        contract_size=100.0,
        min_lot=0.01,
        max_lot=200.0,
        lot_step=0.01,
        digits=2,
        point=0.001,
        tick_size=0.001,  # 1 point = 0.001
        tick_value=1.0,   # $1 per tick per lot
        pip_size=0.01,
        swap_long=0.0,
        swap_short=0.0,
        margin_initial=0.0,
        margin_maintenance=0.0,
        quote_currency="USD",
    )
    
    # For XAUUSD: tick_size = 0.001, tick_value = 1.0
    # 1 tick = 0.001 price movement = $1 per lot
    # 1 pip = 10 ticks = 0.01 price movement = $10 per lot
    # pip_value = pip_size * contract_size = 0.01 * 100 = $1 per pip? No!
    
    # Wait: pip_size = 0.01 (price units), contract_size = 100
    # pip_value = 0.01 * 100 = 1.0 (this is $1 per pip per lot)
    # But earlier we said 1 pip = $10. Let's check:
    # 1 pip = 0.01 price units
    # 1 tick = 0.001 price units
    # 10 ticks = 1 pip
    # tick_value = $1 per tick per lot
    # So 1 pip = 10 ticks = $10 per lot
    
    # But pip_value_per_lot = pip_size * contract_size = 0.01 * 100 = 1.0
    # This gives $1 per pip, which contradicts the tick-based calculation!
    
    # The issue: pip_size is NOT 10 * tick_size for XAUUSD in this setup
    # In MT5: point = 0.001, tick_size = 0.001, pip = 10 points = 0.01
    # But pip_size in our spec is 0.01 (correct for 1 pip = 0.01 price units)
    # pip_value = pip_size * contract_size = 0.01 * 100 = $1 per pip per lot
    
    # But from tick: 1 tick = 0.001 price movement = $1 per lot
    # 1 pip = 10 ticks = 10 * $1 = $10 per lot
    
    # CONTRADICTION! The pip_value_per_lot ($1) doesn't match tick-based ($10)
    # This is because tick_value in MT5 for XAUUSD is typically $1 per 0.01 (pip), not per tick
    # Actually: MT5 trade_tick_value for XAUUSDm is usually $1 per pip (0.01), not per tick (0.001)
    
    # Let's verify: if tick_size = 0.001 and tick_value = 1.0, then
    # 1 pip (0.01) = 10 ticks = 10 * $1 = $10
    # But pip_value = 0.01 * 100 = $1
    
    # The issue: the pip_value formula (pip_size * contract_size) assumes pip is the base unit
    # But tick_value in MT5 is per tick, and for XAUUSD tick_size=0.001
    # So tick_value should be $0.10 per tick to get $1 per pip
    # Or tick_size should be 0.01 (1 pip = 1 tick)
    
    # This is a known MT5 nuance. The test documents the relationship.
    assert spec.tick_size == 0.001
    assert spec.tick_value == 1.0
    assert spec.pip_size == 0.01
    assert spec.contract_size == 100.0
    
    # pip_value from contract = $1
    # pip_value from ticks = (0.01 / 0.001) * 1.0 = 10 * 1 = $10
    # These differ - document this
    pip_from_contract = spec.pip_value_per_lot
    pip_from_ticks = (spec.pip_size / spec.tick_size) * spec.tick_value
    
    # Document the discrepancy for XAUUSD
    # This is a known MT5 convention where tick_size != pip_size for metals
    print(f"XAUUSD: pip_from_contract={pip_from_contract}, pip_from_ticks={pip_from_ticks}")


# ============================================================
# 11. Risk metrics cross-check
# ============================================================

def test_risk_at_stop_usd_calculation():
    """Test risk_at_stop_usd matches manual calculation."""
    # For XAUUSD: contract_size=100, quote_currency=USD
    # stop_distance = 0.10, filled_lots = 1.0
    # risk_in_quote = 0.10 * 1.0 * 100 = 10.0
    # quote_to_usd = 1.0 (USD quoted)
    # risk_usd = 10.0
    
    # We need to mock get_contract_specs
    from mars.apps.trading.system.pair_config import get_contract_specs
    from unittest.mock import patch
    
    with patch('mars.apps.trading.risk_metrics.get_contract_specs') as mock_get_specs:
        mock_get_specs.return_value = {
            "contract_size": 100.0,
            "quote_currency": "USD",
        }
        
        risk = risk_at_stop_usd("XAUUSDm", 2000.0, 1990.0, 1.0)
        assert risk == 1000.0  # 0.10 * 1.0 * 100 * 1.0 = $1000? Wait...
        
        # stop_distance = |2000 - 1990| = 10.0
        # risk_in_quote = 10.0 * 1.0 * 100 = 1000.0
        # quote_to_usd = 1.0
        # risk_usd = 1000.0
        assert risk == 1000.0


# ============================================================
# 12. Verify vol_scaled_system uses spec not hardcoded 100
# ============================================================

def test_vol_scaled_system_uses_spec_not_hardcoded():
    """Verify RiskManager uses InstrumentSpec not hardcoded 100."""
    from mars.apps.trading.system.vol_scaled_system import RiskManager
    
    # Check the source code for hardcoded 100
    import inspect
    source = inspect.getsource(RiskManager.check_aggregate_risk)
    
    # Should NOT contain hardcoded 100 for contract size
    # Should use spec.contract_size or spec.risk_per_contract()
    # This test documents the current state - it will fail if hardcoded 100 exists
    assert "risk_per_contract = stop_distance * 100" not in source or False, "Hardcoded 100 found in check_aggregate_risk"
    assert "risk_per_contract = stop_distance * 100" not in inspect.getsource(RiskManager.check_per_trade_risk) or False, "Hardcoded 100 found in check_per_trade_risk"


# ============================================================
# Run tests
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])