"""Shared realized-R currency-normalization coverage."""
from __future__ import annotations

import pytest

from mars.apps.trading.risk_metrics import realized_r, risk_at_stop_usd


def test_usdjpy_stop_risk_uses_entry_time_quote_conversion():
    risk = risk_at_stop_usd(
        symbol="USDJPYm",
        entry_price=158.233,
        stop_price=157.906,
        filled_lots=0.01,
    )
    assert risk == pytest.approx(2.066573, rel=1e-6)
    assert realized_r("USDJPYm", 158.233, 157.906, 0.01, -2.07) == pytest.approx(-1.000, abs=0.002)


def test_usd_quoted_contracts_need_no_price_conversion():
    assert realized_r("XAUUSDm", 2000.0, 1990.0, 0.01, -10.0) == pytest.approx(-1.0)
