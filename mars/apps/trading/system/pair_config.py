"""
Per-Pair Strategy Configuration.

Human-defined, explicit configuration table — never auto-generated.
Each entry defines strategy class and parameters per symbol.
Disabled pairs (enabled=False) generate zero signals/orders.
"""

from typing import Literal

# Valid strategy identifiers
StrategyName = Literal["donchian_mtf", "donchian", "ma_crossover", "combined"]

# Per-pair strategy configuration
# enabled=False pairs are skipped entirely in signal generation and order placement
PAIR_CONFIG = {
    "XAUUSDm": {
        "strategy": "donchian_mtf",
        "enabled": True,
        "donchian_window": 20,
        "exit_window": 10,
        "stop_mode": "atr",
        "stop_multiplier": 2.0,
        "rr_ratio": 3.0,
        "session_filter": "all",
    },
    "EURUSDm": {
        "strategy": "donchian_mtf",
        "enabled": True,
        "donchian_window": 20,
        "exit_window": 10,
        "stop_mode": "fixed_pips",
        "risk_pips": 5.0,
        "pip_size": 0.0001,
        "rr_ratio": 3.0,
        "session_filter": "all",
    },
    "USDJPYm": {
        "strategy": "donchian_mtf",
        "enabled": True,
        "donchian_window": 20,
        "exit_window": 10,
        "stop_mode": "fixed_pips",
        "risk_pips": 31.6,
        "pip_size": 0.01,
        "rr_ratio": 3.0,
        "session_filter": "all",
    },
    "EURGBPm": {
        "strategy": "donchian_mtf",
        "enabled": False,
        "disabled_reason": (
            "PF=0.95, negative Sharpe on 2020-2024 backtest — "
            "underperforms with current Donchian+MTF params. "
            "Pending: one bounded parameter-tuning pass, or a different "
            "strategy class, before re-enabling."
        ),
        "donchian_window": 20,
        "exit_window": 10,
        "stop_multiplier": 2.0,
        "rr_ratio": 2.5,
        "session_filter": "all",
    },
}


def get_enabled_symbols() -> list[str]:
    """Return list of enabled trading symbols (MT5 format, e.g., 'XAUUSDm')."""
    return [symbol for symbol, cfg in PAIR_CONFIG.items() if cfg["enabled"]]


def get_pair_config(symbol: str) -> dict:
    """Get configuration for a specific symbol. Raises KeyError if not found."""
    if symbol not in PAIR_CONFIG:
        raise KeyError(f"Symbol {symbol} not found in PAIR_CONFIG")
    return PAIR_CONFIG[symbol]


def is_enabled(symbol: str) -> bool:
    """Check if a symbol is enabled for trading."""
    return PAIR_CONFIG.get(symbol, {}).get("enabled", False)


def get_disabled_reason(symbol: str) -> str | None:
    """Get disabled reason if symbol is disabled, else None."""
    cfg = PAIR_CONFIG.get(symbol, {})
    if not cfg.get("enabled", True):
        return cfg.get("disabled_reason")
    return None


def create_signal_generator(symbol: str):
    """Factory to create signal generator from PAIR_CONFIG for a symbol."""
    from mars.apps.trading.signals.trend_breakout import (
        DonchianBreakoutSignal,
        MACrossoverSignal,
        CombinedTrendSignal,
        TrendSignalFactory,
    )

    cfg = get_pair_config(symbol)
    strategy = cfg["strategy"]

    if strategy == "donchian_mtf":
        # Multi-timeframe Donchian: use session filter from config
        return DonchianBreakoutSignal(
            window=cfg["donchian_window"],
            exit_window=cfg["exit_window"],
            session_filter=cfg.get("session_filter", "all"),
            stop_mode=cfg.get("stop_mode", "atr"),
            risk_pips=cfg.get("risk_pips"),
            pip_size=cfg.get("pip_size"),
            stop_multiplier=cfg.get("stop_multiplier", 2.0),
        )
    elif strategy == "donchian":
        return DonchianBreakoutSignal(
            window=cfg["donchian_window"],
            exit_window=cfg["exit_window"],
            session_filter=cfg.get("session_filter", "all"),
        )
    elif strategy == "ma_crossover":
        return MACrossoverSignal(
            fast_window=cfg.get("ma_fast", 50),
            slow_window=cfg.get("ma_slow", 200),
            ma_type=cfg.get("ma_type", "EMA"),
            session_filter=cfg.get("session_filter", "all"),
        )
    elif strategy == "combined":
        return TrendSignalFactory.combined_trend(
            donchian_window=cfg["donchian_window"],
            ma_fast=cfg.get("ma_fast", 50),
            ma_slow=cfg.get("ma_slow", 200),
            session=cfg.get("session_filter", "all"),
        )
    else:
        raise ValueError(f"Unknown strategy '{strategy}' for symbol {symbol}")


def get_data_path(symbol: str) -> str:
    """Get the parquet data path for a symbol from SYMBOL_CONFIGS (imported lazily)."""
    # Import here to avoid circular dependency
    from run_multi_pair_backtest import SYMBOL_CONFIGS
    config_key = get_config_key(symbol)
    return SYMBOL_CONFIGS[config_key]["data_path"]


def get_contract_specs(symbol: str) -> dict:
    """Get contract specs for a symbol from SYMBOL_CONFIGS."""
    from run_multi_pair_backtest import SYMBOL_CONFIGS
    config_key = get_config_key(symbol)
    return SYMBOL_CONFIGS[config_key]


# MT5 symbol to internal config key mapping
MT5_SYMBOL_TO_CONFIG_KEY = {
    "XAUUSDm": "XAUUSD",
    "EURUSDm": "EURUSD",
    "USDJPYm": "USDJPY",
    "EURGBPm": "EURGBP",
}


def get_config_key(mt5_symbol: str) -> str:
    """Convert MT5 symbol to SYMBOL_CONFIGS key."""
    return MT5_SYMBOL_TO_CONFIG_KEY.get(mt5_symbol, mt5_symbol)