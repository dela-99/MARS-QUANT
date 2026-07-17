"""Strategy / candidate setup generation."""

from mars.libs.strategies.base import BaseStrategy, TradeSetup
from mars.libs.strategies.hyp_a_ml_signal import HypAMLDirectionStrategy

__all__ = ["BaseStrategy", "TradeSetup", "HypAMLDirectionStrategy"]
