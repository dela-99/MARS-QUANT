"""Simple fixed-fractional risk policy (V1 skeleton)."""

from __future__ import annotations

from typing import Any, Optional, Set

from mars.libs.risk.base import BaseRiskPolicy, RiskDecision
from mars.libs.strategies.base import TradeSetup


class FixedFractionalRisk(BaseRiskPolicy):
    """
    Size positions as a fixed fraction of equity risk.

    V1 is intentionally simple:
    - rejects if max risk exceeded conceptually via size cap
    - optional block on configured weekday numbers (0=Mon)
    - optional news flag filter via setup.metadata['news_flag']
    """

    def __init__(
        self,
        risk_fraction: float = 0.01,
        stop_distance: float = 10.0,
        max_lot: float = 1.0,
        blocked_weekdays: Optional[Set[int]] = None,
        block_news: bool = False,
    ) -> None:
        super().__init__(name="fixed_fractional")
        self.risk_fraction = risk_fraction
        self.stop_distance = stop_distance
        self.max_lot = max_lot
        self.blocked_weekdays = blocked_weekdays or set()
        self.block_news = block_news

    def evaluate(
        self,
        setup: TradeSetup,
        *,
        equity: float,
        **kwargs: Any,
    ) -> RiskDecision:
        if setup.side == "flat":
            return RiskDecision(approved=False, reason="flat setup")

        wd = setup.timestamp.weekday()
        if wd in self.blocked_weekdays:
            return RiskDecision(approved=False, reason=f"blocked weekday {wd}")

        if self.block_news and setup.metadata.get("news_flag"):
            return RiskDecision(approved=False, reason="news filter")

        if self.stop_distance <= 0:
            return RiskDecision(approved=False, reason="invalid stop distance")

        # Dollar risk / stop → naive unit size (instrument point value = 1 for research units)
        risk_dollars = equity * self.risk_fraction
        size = min(risk_dollars / self.stop_distance, self.max_lot)
        if size <= 0:
            return RiskDecision(approved=False, reason="computed size <= 0")

        return RiskDecision(
            approved=True,
            size=float(size),
            stop_distance=self.stop_distance,
            reason="approved",
            metadata={"risk_fraction": self.risk_fraction, "risk_dollars": risk_dollars},
        )
