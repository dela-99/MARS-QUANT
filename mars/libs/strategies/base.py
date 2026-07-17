"""Strategy abstraction for candidate trade setup generation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

import pandas as pd

Side = Literal["long", "short", "flat"]


@dataclass
class TradeSetup:
    """A candidate trade idea — not an execution order."""

    timestamp: datetime
    symbol: str
    side: Side
    confidence: Optional[float] = None
    rationale: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseStrategy(ABC):
    """
    Generate candidate long/short setups from market (and optional model) inputs.

    This is intentionally not a full execution strategy. Execution adapters and
    risk policies sit outside this interface.
    """

    def __init__(self, name: str = "base", symbol: str = "XAUUSD") -> None:
        self.name = name
        self.symbol = symbol

    @abstractmethod
    def generate_setups(self, market_data: pd.DataFrame, **kwargs: Any) -> List[TradeSetup]:
        """Return candidate setups for the provided market window."""
