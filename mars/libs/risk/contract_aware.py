"""
Contract-aware fixed-fractional risk policy (Assignment 14).

Reuses the existing risk-engine interface (:class:`mars.libs.risk.base.BaseRiskPolicy`
and :class:`mars.libs.risk.base.RiskDecision`) and the weekday / news filters of
:class:`mars.libs.risk.fixed_fractional.FixedFractionalRisk`, but replaces the
"instrument point value = 1" placeholder sizing with a contract-size aware
calculation:

    risk_per_lot_usd = stop_distance_price * contract_size * quote_to_usd
    lots_exact       = (equity * risk_fraction) / risk_per_lot_usd
    lots             = floor(lots_exact / volume_step) * volume_step

Broker volume constraints (min / max / step) are applied **only** when they are
supplied by the caller together with their provenance.  A trade is never forced:
if the broker minimum volume would breach the configured risk limit the setup is
rejected with an explicit reason.

Nothing in this module invents broker data.  ``InstrumentSpec.volume_spec_source``
records where the volume constraints came from:

    "mt5.live"           verified from a connected MT5 terminal
    "pair_config.offline" taken from the repository's offline symbol configuration
    "unverified_default" placeholder values - flagged in every run record
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from mars.libs.risk.base import RiskDecision
from mars.libs.risk.fixed_fractional import FixedFractionalRisk
from mars.libs.strategies.base import TradeSetup


@dataclass(frozen=True)
class InstrumentSpec:
    """Instrument contract specification used for sizing and cost conversion."""

    symbol: str = "XAUUSDm"
    contract_size: float = 100.0       # units per lot (troy ounces for XAUUSDm)
    pip_size: float = 0.01             # price move of one "pip" (USD per oz)
    point_size: float = 0.001          # broker tick; the spread column is quoted in points
    quote_currency: str = "USD"
    volume_min: float = 0.01
    volume_max: float = 200.0
    volume_step: float = 0.01
    volume_spec_source: str = "unverified_default"
    spec_source: str = "pair_config.offline"

    @property
    def pip_value_per_lot_usd(self) -> float:
        """USD value of one pip for one lot (USD-quoted instrument)."""
        return self.pip_size * self.contract_size

    @property
    def point_value_per_lot_usd(self) -> float:
        """USD value of one broker point (tick) for one lot."""
        return self.point_size * self.contract_size

    def spread_points_to_price(self, spread_points: float) -> float:
        """Convert an observed spread (broker points) into a price distance."""
        return float(spread_points) * self.point_size

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "contract_size": self.contract_size,
            "pip_size": self.pip_size,
            "point_size": self.point_size,
            "quote_currency": self.quote_currency,
            "volume_min": self.volume_min,
            "volume_max": self.volume_max,
            "volume_step": self.volume_step,
            "volume_spec_source": self.volume_spec_source,
            "spec_source": self.spec_source,
            "pip_value_per_lot_usd": self.pip_value_per_lot_usd,
            "point_value_per_lot_usd": self.point_value_per_lot_usd,
        }


def floor_to_step(value: float, step: float) -> float:
    """Round ``value`` down onto the broker volume grid."""
    if step <= 0:
        return float(value)
    return math.floor((value + 1e-12) / step) * step


class ContractAwareFixedFractionalRisk(FixedFractionalRisk):
    """
    Fixed-fractional risk with contract-size aware sizing and broker volume rules.

    Parameters
    ----------
    spec:
        Instrument specification (contract size, pip/point size, volume rules).
    risk_fraction:
        Fraction of equity risked per trade.  Configurable per research run.
    max_lot:
        Optional hard cap on lot size, applied on top of ``spec.volume_max``.
    enforce_volume_rules:
        When False the broker volume constraints are ignored (used only for
        sensitivity studies).  The default is True.
    """

    def __init__(
        self,
        spec: Optional[InstrumentSpec] = None,
        risk_fraction: float = 0.01,
        max_lot: Optional[float] = None,
        enforce_volume_rules: bool = True,
        blocked_weekdays: Optional[set] = None,
        block_news: bool = False,
    ) -> None:
        effective_max_lot = max_lot if max_lot is not None else (spec.volume_max if spec else 1.0)
        super().__init__(
            risk_fraction=risk_fraction,
            stop_distance=1.0,          # overridden per setup via metadata
            max_lot=effective_max_lot,
            blocked_weekdays=blocked_weekdays,
            block_news=block_news,
        )
        self.spec = spec or InstrumentSpec()
        self.risk_fraction = risk_fraction
        self.enforce_volume_rules = enforce_volume_rules
        #: Optional hard cap applied on top of the broker volume maximum.
        self._max_lot_override = max_lot

    # ------------------------------------------------------------------
    def evaluate(self, setup: TradeSetup, *, equity: float, **kwargs: Any) -> RiskDecision:
        """Size a setup against the configured risk budget.

        Rejection reasons are explicit so a run ledger can record *why* a signal
        did not become a trade.
        """
        # Reuse the inherited weekday / news / flat filters before sizing.
        base = super().evaluate(setup, equity=equity)
        if not base.approved:
            return base

        stop_distance = float(setup.metadata.get("stop_distance", 0.0) or 0.0)
        if stop_distance <= 0:
            return RiskDecision(
                approved=False,
                reason="invalid stop distance",
                metadata={"stop_distance": stop_distance},
            )

        spec = self.spec
        quote_to_usd = float(kwargs.get("quote_to_usd", 1.0))
        risk_dollars = equity * self.risk_fraction
        risk_per_lot = stop_distance * spec.contract_size * quote_to_usd
        if risk_per_lot <= 0:
            return RiskDecision(approved=False, reason="non-positive risk per lot")

        lots_exact = risk_dollars / risk_per_lot
        lots = floor_to_step(lots_exact, spec.volume_step)

        metadata: Dict[str, Any] = {
            "risk_fraction": self.risk_fraction,
            "risk_dollars": risk_dollars,
            "risk_per_lot_usd": risk_per_lot,
            "lots_exact": lots_exact,
            "stop_distance": stop_distance,
            "contract_size": spec.contract_size,
            "volume_spec_source": spec.volume_spec_source,
            "quote_to_usd": quote_to_usd,
        }

        if self.enforce_volume_rules:
            if lots < spec.volume_min - 1e-12:
                # The broker minimum volume would risk more than the budget:
                # reject rather than force an oversized trade.
                risk_at_min = spec.volume_min * risk_per_lot
                metadata.update(
                    {
                        "risk_at_min_volume_usd": risk_at_min,
                        "risk_limit_usd": risk_dollars,
                        "required_lots": lots_exact,
                    }
                )
                return RiskDecision(
                    approved=False,
                    reason=(
                        f"min volume breach: {spec.volume_min} lots risks "
                        f"${risk_at_min:.2f} > budget ${risk_dollars:.2f}"
                    ),
                    metadata=metadata,
                )
            if lots > spec.volume_max + 1e-12:
                metadata["required_lots"] = lots_exact
                return RiskDecision(
                    approved=False,
                    reason=(
                        f"max volume exceeded: required {lots_exact:.4f} lots > "
                        f"broker max {spec.volume_max}"
                    ),
                    metadata=metadata,
                )

        if self._max_lot_override is not None and lots > self._max_lot_override:
            lots = floor_to_step(self._max_lot_override, spec.volume_step)

        if lots <= 0:
            return RiskDecision(approved=False, reason="computed size <= 0", metadata=metadata)

        metadata["approved_lots"] = lots
        return RiskDecision(
            approved=True,
            size=float(lots),
            stop_distance=stop_distance,
            reason="approved",
            metadata=metadata,
        )


__all__ = ["ContractAwareFixedFractionalRisk", "InstrumentSpec", "floor_to_step"]
