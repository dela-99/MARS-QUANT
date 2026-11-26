"""
Tests for M5 Strategy Research Runner.
"""

from pathlib import Path
import pytest


def test_research_runner_end_to_end_smoke():
    from mars.apps.research_lab.m5_strategy_research import M5StrategyResearch
    
    research = M5StrategyResearch(Path("C:/Users/RIDGE/MARS-QUANT"))
    # Run on tiny window for smoke test
    result = research.run_single_strategy("momentum", period="dev", max_bars=1000)
    
    assert result is not None
    assert "trades" in result
    assert "metrics" in result
    assert "feasibility" in result


def test_research_runner_all_strategies():
    from mars.apps.research_lab.m5_strategy_research import M5StrategyResearch, STRATEGY_REGISTRY
    
    research = M5StrategyResearch(Path("C:/Users/RIDGE/MARS-QUANT"))
    
    for strategy_name in STRATEGY_REGISTRY.keys():
        result = research.run_single_strategy(strategy_name, period="dev", max_bars=500)
        assert result is not None
        assert "metrics" in result
        assert "feasibility" in result