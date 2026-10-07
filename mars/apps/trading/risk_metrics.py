"""Shared, audit-safe USD risk and realized-R calculations.

These helpers are for reporting and analytics only. They deliberately use the
same contract specifications as the trading configuration, while avoiding any
dependency from live sizing or risk-approval logic.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from mars.apps.trading.system.pair_config import get_contract_specs


@lru_cache(maxsize=16)
def _contract_specs(symbol: str) -> dict[str, Any]:
    """Cache immutable config lookup; imported configuration can be expensive."""
    return get_contract_specs(symbol)


def quote_to_usd_at_entry(symbol: str, entry_price: float) -> float:
    """Return the USD value of one quote-currency unit at entry.

    USD-quoted instruments already settle in USD. For USDJPY, one JPY is
    worth ``1 / USDJPY`` USD at the entry price. Other non-USD quotes require
    a separately audited cross-rate and are intentionally not approximated.
    """
    specs = _contract_specs(symbol)
    quote_currency = specs.get("quote_currency", "USD")
    if quote_currency == "USD":
        return 1.0
    if quote_currency == "JPY":
        if entry_price <= 0:
            raise ValueError("JPY quote conversion requires a positive entry price")
        return 1.0 / entry_price
    raise ValueError(
        f"No audited {quote_currency}/USD conversion is available for {symbol}; "
        "do not approximate realized R."
    )


def risk_at_stop_usd(
    symbol: str,
    entry_price: float,
    stop_price: float,
    filled_lots: float,
) -> float | None:
    """Return the USD amount at risk between entry and stop, or ``None``."""
    if entry_price <= 0 or filled_lots == 0:
        return None
    specs = _contract_specs(symbol)
    contract_size = float(specs["contract_size"])
    stop_distance = abs(float(entry_price) - float(stop_price))
    if stop_distance <= 0:
        return None
    risk_in_quote = stop_distance * abs(float(filled_lots)) * contract_size
    return risk_in_quote * quote_to_usd_at_entry(symbol, float(entry_price))


def realized_r(
    symbol: str,
    entry_price: float,
    stop_price: float,
    filled_lots: float,
    realized_pnl_usd: float,
) -> float | None:
    """Compute broker-realized P&L divided by entry-time USD stop risk."""
    risk_usd = risk_at_stop_usd(symbol, entry_price, stop_price, filled_lots)
    if risk_usd is None or risk_usd <= 0:
        return None
    return float(realized_pnl_usd) / risk_usd
