"""
Spread-aware backtest engine for M.A.R.S.

Converts mid-price OHLC fills to bid/ask-aware fills using spread data.
Both entry and exit fills are adjusted directionally.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

import numpy as np
import pandas as pd


@dataclass
class SpreadConfig:
    """Configuration for spread modeling."""
    # Spread column is in "points" (10 points = 1 pip)
    # 1 pip = $0.10 per oz for XAUUSD
    points_per_pip: float = 10.0
    dollars_per_pip: float = 0.10
    
    # Session-aware multipliers (empirically derived, 1.0 = base)
    session_multipliers: dict[str, float] = None
    
    def __post_init__(self):
        if self.session_multipliers is None:
            # Based on empirical analysis - spread doesn't widen much at transitions in this dataset
            # These are modest adjustments
            self.session_multipliers = {
                "Asia": 1.0,
                "London": 1.0,
                "Overlap": 1.0,
                "NY": 1.0,
                "Transition": 1.2,  # modest widening at session boundaries
            }


def get_session(hour: int) -> str:
    """Map UTC hour to session."""
    if 0 <= hour < 8:
        return "Asia"
    elif 8 <= hour < 13:
        return "London"
    elif 13 <= hour < 17:
        return "Overlap"
    else:
        return "NY"


def is_transition_hour(hour: int) -> bool:
    """Check if hour is a session transition."""
    # London open (8), Overlap start (13), Overlap end (17), NY close (22/0)
    return hour in [7, 8, 12, 13, 16, 17, 21, 22]


def get_spread_at_timestamp(
    spread_series: pd.Series,
    timestamp: pd.Timestamp,
    config: SpreadConfig,
) -> float:
    """
    Get spread in dollars at a specific timestamp.
    
    Uses session-aware multiplier and transition-hour awareness.
    """
    # Ensure timestamp is tz-naive to match spread_series index
    if timestamp.tz is not None:
        timestamp = timestamp.tz_convert(None)
    
    # Get base spread in points
    if timestamp in spread_series.index:
        base_spread_points = spread_series.loc[timestamp]
    else:
        # Fallback to nearest
        base_spread_points = spread_series.asof(timestamp)
        if pd.isna(base_spread_points):
            base_spread_points = spread_series.median()
    
    hour = timestamp.hour
    session = get_session(hour)
    
    # Apply session multiplier
    multiplier = config.session_multipliers.get(session, 1.0)
    
    # Additional transition multiplier
    if is_transition_hour(hour):
        multiplier *= config.session_multipliers.get("Transition", 1.2)
    
    spread_points = base_spread_points * multiplier
    
    # Convert to dollars: points -> pips -> dollars
    spread_pips = spread_points / config.points_per_pip
    spread_dollars = spread_pips * config.dollars_per_pip
    
    return spread_dollars


def get_fill_price(
    mid_price: float,
    side: Literal["buy", "sell"],
    spread_dollars: float,
) -> float:
    """
    Calculate fill price given mid price, side, and spread in dollars.
    
    Buy -> pay ask (mid + spread/2)
    Sell -> receive bid (mid - spread/2)
    """
    half_spread = spread_dollars / 2
    if side == "buy":
        return mid_price + half_spread
    else:
        return mid_price - half_spread


def apply_spread_to_trades(
    trades: pd.DataFrame,
    price_data: pd.DataFrame,
    spread_series: pd.Series,
    config: Optional[SpreadConfig] = None,
) -> pd.DataFrame:
    """
    Apply spread-aware fill prices to backtest trades.
    
    Parameters
    ----------
    trades : DataFrame with columns EntryTime, ExitTime, EntryPrice, ExitPrice, Size
    price_data : OHLCV DataFrame with DatetimeIndex
    spread_series : Spread series indexed by timestamp (same index as price_data)
    config : SpreadConfig
    
    Returns
    -------
    trades with adjusted EntryPrice, ExitPrice, PnL
    """
    config = config or SpreadConfig()
    trades = trades.copy()
    
    # Ensure timestamps
    trades['EntryTime'] = pd.to_datetime(trades['EntryTime'])
    trades['ExitTime'] = pd.to_datetime(trades['ExitTime'])
    
    # Determine side from EntryPrice vs ExitPrice or Size
    # For long: EntryPrice < ExitPrice typically (but not guaranteed)
    # We need to know direction. Check if there's a direction column.
    # In backtesting.py, long positions have positive Size, short have negative
    # Or we infer from EntryPrice vs ExitPrice for the first trade
    
    adjusted_trades = []
    
    for _, trade in trades.iterrows():
        entry_time = trade['EntryTime']
        exit_time = trade['ExitTime']
        entry_mid = trade['EntryPrice']
        exit_mid = trade['ExitPrice']
        size = trade['Size']
        
        # Get spread at entry and exit
        entry_spread = get_spread_at_timestamp(spread_series, entry_time, config)
        exit_spread = get_spread_at_timestamp(spread_series, exit_time, config)
        
        # Determine side: if PnL > 0 when ExitPrice > EntryPrice, it's long
        # But we don't know PnL yet. Use Size sign convention from backtesting.py
        # In backtesting.py, buy() creates positive size, sell() creates negative
        is_long = size > 0
        
        if is_long:
            # Long: buy at ask, sell at bid
            entry_fill = get_fill_price(entry_mid, "buy", entry_spread)
            exit_fill = get_fill_price(exit_mid, "sell", exit_spread)
        else:
            # Short: sell at bid, buy at ask
            entry_fill = get_fill_price(entry_mid, "sell", entry_spread)
            exit_fill = get_fill_price(exit_mid, "buy", exit_spread)
        
        # Calculate PnL with spread-adjusted fills
        # PnL = size * (exit_fill - entry_fill) for long
        # PnL = size * (entry_fill - exit_fill) for short (size is negative)
        # Unified: PnL = size * (exit_fill - entry_fill)
        gross_pnl = size * (exit_fill - entry_fill)
        
        # Commission (already in original, but we recalculate for consistency)
        # Commission charged on both entry and exit notional
        commission = abs(size * entry_fill) * 0.0002 + abs(size * exit_fill) * 0.0002
        net_pnl = gross_pnl - commission
        
        adjusted_trades.append({
            **trade.to_dict(),
            'entry_fill': entry_fill,
            'exit_fill': exit_fill,
            'entry_spread': entry_spread,
            'exit_spread': exit_spread,
            'gross_pnl_spread': gross_pnl,
            'net_pnl_spread': net_pnl,
            'commission_spread': commission,
        })
    
    return pd.DataFrame(adjusted_trades)


def compute_spread_aware_metrics(
    trades: pd.DataFrame,
    initial_cash: float = 10000,
) -> dict:
    """Compute backtest metrics from spread-adjusted trades."""
    net_returns = trades['net_pnl_spread'] / initial_cash
    equity_curve = (1 + net_returns).cumprod()
    
    total_return = equity_curve.iloc[-1] - 1
    n_trades = len(trades)
    win_rate = (trades['net_pnl_spread'] > 0).mean()
    
    # Sharpe
    if len(net_returns) > 1 and net_returns.std() > 0:
        sharpe = float(net_returns.mean() / net_returns.std() * np.sqrt(252))
    else:
        sharpe = float('nan')
    
    # Max drawdown
    rolling_max = equity_curve.expanding().max()
    drawdown = equity_curve / rolling_max - 1
    max_dd = float(drawdown.min())
    
    # Profit factor
    gross_profits = trades.loc[trades['net_pnl_spread'] > 0, 'net_pnl_spread'].sum()
    gross_losses = abs(trades.loc[trades['net_pnl_spread'] < 0, 'net_pnl_spread'].sum())
    profit_factor = gross_profits / gross_losses if gross_losses > 0 else float('inf')
    
    return {
        'n_trades': int(n_trades),
        'win_rate': float(win_rate),
        'total_return': float(total_return),
        'total_return_pct': float(total_return * 100),
        'sharpe': sharpe,
        'max_drawdown': float(max_dd),
        'max_drawdown_pct': float(max_dd * 100),
        'profit_factor': float(profit_factor),
        'total_net_pnl': float(trades['net_pnl_spread'].sum()),
        'total_commission': float(trades['commission_spread'].sum()),
        'avg_net_return': float(net_returns.mean()),
    }


# Convenience function for the Hyp-A vectorized backtest
def spread_aware_session_backtest(
    features: pd.DataFrame,
    y_direction: pd.Series,
    y_return: pd.Series,
    predictions: np.ndarray,
    spread_series: pd.Series,
    config: Optional[SpreadConfig] = None,
    commission: float = 0.0002,
) -> dict:
    """
    Vectorized session backtest with spread-aware fills.
    
    This replaces simple_session_backtest in run_hyp_a_backtest.py
    """
    config = config or SpreadConfig()
    
    pred = np.asarray(predictions)
    realized = y_return.loc[features.index].to_numpy()
    direction = y_direction.loc[features.index].to_numpy()
    
    # Long when pred=1, short when pred=0
    side = np.where(pred == 1, 1.0, -1.0)
    
    # For each trade, we need the spread at entry (London open) and exit (London close)
    # The features index is daily (date), we need to map to session timestamps
    # London open ~08:00 UTC, London close ~17:00 UTC
    
    # Get spread at London open and close for each date
    dates = features.index
    
    entry_spreads = []
    exit_spreads = []
    
    for date in dates:
        # London open ~08:00 UTC
        entry_ts = pd.Timestamp(date).tz_localize(None).replace(hour=8, minute=0)
        # London close ~17:00 UTC
        exit_ts = pd.Timestamp(date).tz_localize(None).replace(hour=17, minute=0)
        
        entry_spread = get_spread_at_timestamp(spread_series, entry_ts, config)
        exit_spread = get_spread_at_timestamp(spread_series, exit_ts, config)
        
        entry_spreads.append(entry_spread)
        exit_spreads.append(exit_spread)
    
    entry_spreads = np.array(entry_spreads)
    exit_spreads = np.array(exit_spreads)
    
    # The returns (realized) are in percentage terms (e.g., 0.001 = 0.1%)
    # The spread is in dollars per ounce (e.g., $0.06)
    # We need to convert spread to percentage terms.
    # For XAUUSD, 1% return = $20 per ounce (at $2000/oz)
    # So spread_pct = spread_dollars / price * 100
    # But we don't have the price at each date in the feature frame.
    # Approximation: use a typical price (e.g., $2000) or compute from the data.
    
    # Better: the realized return is (Close - Open) / Open
    # The spread cost in return terms = spread_dollars / Open_price
    # We can approximate Open_price from the London open price in the data
    
    # For now, use a simpler approach: the realized return already includes the bid-ask
    # spread in real trading. The "mid" return we have is (mid_close - mid_open) / mid_open
    # The actual net return with spread = (bid_close - ask_open) / ask_open for long
    # = (mid_close - spread/2 - mid_open - spread/2) / (mid_open + spread/2)
    # ≈ (mid_close - mid_open - spread) / mid_open  (for small spread)
    # = mid_return - spread / mid_open
    
    # So spread cost in return terms = spread_dollars / mid_open_price
    
    # We don't have mid_open_price in the features. Let's approximate it.
    # Since we're working with daily London session data, we can estimate
    # from the realized return and the actual prices.
    
    # Actually, let's use a different approach: the features were built from price data
    # that has the London open/close. We need to get the London open price for each date.
    # For now, use a constant approximation: XAUUSD ~ $2000
    typical_price = 2000.0
    
    # Spread cost per trade (round trip) in return terms
    # Long: pay ask at entry (spread/2), receive bid at exit (-spread/2) = total spread
    # Short: receive bid at entry (-spread/2), pay ask at exit (spread/2) = total spread
    # So round-trip spread cost in dollars = entry_spread + exit_spread
    spread_cost_dollars = entry_spreads + exit_spreads
    spread_cost_pct = spread_cost_dollars / typical_price  # as decimal (not percentage)
    
    # Commission (2x notional)
    commission_cost = 2 * commission
    
    # Net return per trade
    # Gross = side * realized
    # Net = gross - spread_cost_pct - commission_cost
    gross = side * realized
    net = gross - spread_cost_pct - commission_cost
    
    equity = np.cumprod(1.0 + net)
    total_return = float(equity[-1] - 1.0) if len(equity) else 0.0
    hit = float((pred == direction).mean()) if len(pred) else float('nan')
    sharpe = (
        float(np.mean(net) / (np.std(net) + 1e-12) * np.sqrt(252))
        if len(net) > 1
        else float('nan')
    )
    max_dd = float(np.min(equity / np.maximum.accumulate(equity) - 1.0)) if len(equity) else 0.0
    
    # Profit factor
    gross_profits = net[net > 0].sum()
    gross_losses = abs(net[net < 0].sum())
    profit_factor = gross_profits / gross_losses if gross_losses > 0 else float('inf')
    
    return {
        "n_trades": int(len(pred)),
        "hit_rate": hit,
        "total_return": total_return,
        "total_return_pct": total_return * 100,
        "sharpe_approx": sharpe,
        "max_drawdown": max_dd,
        "max_drawdown_pct": max_dd * 100,
        "profit_factor": profit_factor,
        "mean_net_return": float(np.mean(net)) if len(net) else 0.0,
        "total_spread_cost": float(spread_cost_pct.sum()),
        "avg_spread_cost": float(spread_cost_pct.mean()),
        "commission": commission,
    }


if __name__ == "__main__":
    # Quick test
    config = SpreadConfig()
    print("SpreadConfig:", config)
    print("Session multipliers:", config.session_multipliers)
    
    # Test fill price
    mid = 2000.0
    spread = 0.06  # $0.06
    print(f"Mid: {mid}, Spread: ${spread}")
    print(f"Buy fill: {get_fill_price(mid, 'buy', spread)}")
    print(f"Sell fill: {get_fill_price(mid, 'sell', spread)}")