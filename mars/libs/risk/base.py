"""Risk policy abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from mars.libs.strategies.base import TradeSetup


@dataclass
class RiskDecision:
    """Output of a risk policy evaluation for a single setup."""

    approved: bool
    size: float = 0.0
    stop_distance: Optional[float] = None
    take_profit_distance: Optional[float] = None
    reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseRiskPolicy(ABC):
    """
    Risk controls for candidate setups.

    Responsibilities (extensible):
    - position sizing
    - stop-loss distance
    - max risk per trade
    - session / news filters
    """

    def __init__(self, name: str = "base") -> None:
        self.name = name

    @abstractmethod
    def evaluate(
        self,
        setup: TradeSetup,
        *,
        equity: float,
        **kwargs: Any,
    ) -> RiskDecision:
        ...
