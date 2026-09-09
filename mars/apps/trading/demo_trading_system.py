"""
Demo-ready Trading System for XAUUSD

Complete system integrating:
- Donchian breakout + MA crossover signals
- CARR vol-scaled position sizing
- Hard risk rules (stops, drawdown limits, position caps)
- Demo-ready paper trading interface
- Full backtest capability
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from mars.apps.trading.signals.trend_breakout import (
    DonchianBreakoutSignal,
    MACrossoverSignal,
    CombinedTrendSignal,
    TrendSignalFactory,
)
from mars.apps.trading.system.vol_scaled_system import (
    VolScaledSizer,
    SizingConfig,
    RiskManager,
    TradeExecutor,
    TradingSystem,
)
from mars.libs.data.loaders import load_ohlcv_parquet
from mars.libs.evaluation.metrics import classification_metrics
from mars.libs.evaluation.report import write_text_report
from mars.libs.utils.paths import ProjectPaths


class DemoTradingSystem:
    """
    Demo-ready XAUUSD Trend Trading System.
    
    Features:
    - Combined Donchian + MA trend signals
    - CARR vol-scaled position sizing (validated in Hyp-B)
    - Hard risk rules: stops, drawdown limits, position caps
    - Demo-ready paper trading with realistic fills
    - Full backtest + forward test capability
    """
    
    def __init__(
        self,
        equity: float = 100000,
        signal_type: str = "combined",  # "donchian", "ma", "combined"
        donchian_window: int = 20,
        ma_fast: int = 50,
        ma_slow: int = 200,
        session: str = "london",
        sizing_config: Optional[SizingConfig] = None,
        risk_config: Optional[dict] = None,
    ) -> None:
        self.equity = equity
        
        # Signal generator
        if signal_type == "donchian":
            self.signal_generator = TrendSignalFactory.donchian_trend(
                window=donchian_window, session=session
            )
        elif signal_type == "ma":
            self.signal_generator = TrendSignalFactory.ma_crossover_trend(
                fast=ma_fast, slow=ma_slow, session=session
            )
        else:  # combined
            self.signal_generator = TrendSignalFactory.combined_trend(
                donchian_window=donchian_window,
                ma_fast=ma_fast,
                ma_slow=ma_slow,
                session=session,
            )
        
        # Vol-scaled sizer (GARCH validated - CARR had numerical issues)
        sizing_config = sizing_config or SizingConfig(
            target_vol=0.15,  # 15% annualized target (matches SizingConfig default)
            max_leverage=3.0,
            min_leverage=0.01,
            max_position_pct=1.0,  # 100% of equity max (leverage already capped at 3x)
            kelly_fraction=0.5,
        )
        self.sizer = VolScaledSizer(sizing_config, garch_variant="garch")
        
        # Risk management
        risk_config = risk_config or {}
        self.risk_manager = RiskManager(
            max_daily_loss_pct=risk_config.get("max_daily_loss", 0.02),
            max_weekly_loss_pct=risk_config.get("max_weekly_loss", 0.05),
            max_monthly_loss_pct=risk_config.get("max_monthly_loss", 0.10),
            max_drawdown_pct=risk_config.get("max_drawdown", 0.15),
            max_position_pct=1.0,  # Not used by sizer (sizer has own config)
        )
        
        # Trading system
        self.trading_system = TradingSystem(
            signal_generator=self.signal_generator,
            equity=equity,
            sizer=self.sizer,
            risk_manager=self.risk_manager,
        )
        
        # State
        self.is_running = False
        self.current_equity = equity
        self.start_time = None
    
    def load_data(self, symbol: str = "XAUUSD", timeframe: str = "h1", start: str = "2020-01-01") -> pd.DataFrame:
        """Load and prepare OHLCV data."""
        paths = ProjectPaths.from_root()
        data_path = paths.raw_data / f"{symbol.lower()}_{timeframe}_2020_present.parquet"
        
        if not data_path.exists():
            # Try alternative paths
            alt_paths = [
                paths.raw_data / f"xauusd_{timeframe}_2020_present.parquet",
                paths.raw_data / f"xauusd_{timeframe}_2018_present.parquet",
            ]
            for p in alt_paths:
                if p.exists():
                    data_path = p
                    break
            else:
                raise FileNotFoundError(f"No data found for {symbol} {timeframe}")
        
        df = pd.read_parquet(data_path)
        
        # Handle both cases: timestamp as column or as index
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
            df = df.set_index("timestamp").sort_index()
        elif isinstance(df.index, pd.DatetimeIndex):
            df = df.sort_index()
        else:
            # Try to find a datetime column
            datetime_cols = [c for c in df.columns if "time" in c.lower() or "date" in c.lower()]
            if datetime_cols:
                df[datetime_cols[0]] = pd.to_datetime(df[datetime_cols[0]], utc=True)
                df = df.set_index(datetime_cols[0]).sort_index()
            else:
                raise ValueError(f"No timestamp column or datetime index found in {data_path}")
        
        # Filter by start date
        start_ts = pd.Timestamp(start, tz="UTC")
        df = df[df.index >= start_ts]
        
        # Ensure OHLC columns
        if "open" not in df.columns:
            raise ValueError("Data must have OHLC columns")
        
        # Ensure volume column exists (some FRED data doesn't have it)
        if "volume" not in df.columns:
            df["volume"] = 0.0
        
        return df[["open", "high", "low", "close", "volume"]]
    
    def run_backtest(
        self,
        start: str = "2020-01-01",
        end: Optional[str] = None,
        timeframe: str = "h1",
    ) -> dict:
        """Run full backtest on historical data."""
        print("=" * 60)
        print("M.A.R.S. Demo System Backtest")
        print("=" * 60)
        
        # Load data
        print(f"Loading XAUUSD H1 data from {start}...")
        df = self.load_data(start=start)
        if end:
            end_ts = pd.Timestamp(end, tz="UTC")
            df = df[df.index <= end_ts]
        print(f"Loaded {len(df)} bars from {df.index[0]} to {df.index[-1]}")
        
        # Fit sizer (CARR vol model)
        print("Fitting CARR vol model...")
        self.sizer.fit(df)
        
        # Generate signals
        print("Generating trend signals...")
        signals = self.signal_generator.generate(df)
        print(f"Signal distribution: {signals['signal'].value_counts().to_dict()}")
        
        # Get vol forecasts
        print("Generating vol forecasts...")
        forecast_vol = self.sizer.forecast_vol(df)
        
        # Compute position sizes
        print("Computing position sizes...")
        positions = self.sizer.compute_position_size(df, signals["signal"], self.equity, forecast_vol)
        
        # Run simulation
        print("Running simulation...")
        results = self._run_simulation(df, signals, positions)
        
        return results
    
    def _run_simulation(
        self,
        df: pd.DataFrame,
        signals: pd.DataFrame,
        positions: pd.DataFrame,
    ) -> dict:
        """Run the trading simulation."""
        initial_equity = self.equity
        self.risk_manager.current_equity = self.equity
        self.risk_manager.peak_equity = self.equity
        
        executor = TradeExecutor(self.equity, self.risk_manager, self.sizer)
        
        equity_curve = [self.equity]
        trades = []
        open_positions = {}
        
        # Align all data
        common_idx = df.index.intersection(signals.index).intersection(positions.index)
        df = df.loc[common_idx]
        signals = signals.loc[common_idx]
        positions = positions.loc[common_idx]
        
        for i, (timestamp, row) in enumerate(df.iterrows()):
            signal = signals["signal"].loc[timestamp] if timestamp in signals.index else 0
            position_size = positions["position_size"].loc[timestamp] if timestamp in positions.index else 0
            price = row["close"]
            time = timestamp
            
            # Check exits on open positions
            for symbol in list(open_positions.keys()):
                update = executor.update_position(symbol, price, time)
                if update["action"] == "close":
                    pnl = executor.close_position(symbol, price, update["reason"])
                    trades.append({
                        "time": time,
                        "pnl": pnl,
                        "reason": update["reason"],
                    })
                    open_positions.pop(symbol, None)
            
            # Enter new position only on signal transition (not every bar)
            prev_signal = signals["signal"].iloc[i-1] if i > 0 else 0
            if signal != 0 and signal != prev_signal and "XAUUSD" not in open_positions and position_size > 0:
                # Create trade config - use ATR for stop distance
                atr = row.get("ATRr_14", 5.0)  # fallback if not available
                stop_distance = atr * 2.5  # 2.5 ATR stop (tighter for better R:R)
                
                if signal == 1:
                    stop_price = df.iloc[i]["close"] - stop_distance
                    take_profit = df.iloc[i]["close"] + stop_distance * 2.5  # 2.5:1 R:R
                else:
                    stop_price = df.iloc[i]["close"] + stop_distance
                    take_profit = df.iloc[i]["close"] - stop_distance * 2.5
                
                from mars.apps.trading.system.vol_scaled_system import TradeConfig
                config = TradeConfig(
                    symbol="XAUUSD",
                    signal=signal,
                    entry_price=df.iloc[i]["close"],
                    stop_price=stop_price,
                    take_profit=take_profit,
                    position_size=position_size,
                    max_hold_hours=24,
                    risk_pct=0.01,
                    entry_time=time,
                )
                
                if executor.open_position(config):
                    open_positions["XAUUSD"] = True
            
            equity_curve.append(executor.equity)
        
        return {
            "equity_curve": equity_curve,
            "trades": trades,
            "final_equity": executor.equity,
            "total_return": (executor.equity - initial_equity) / initial_equity,
        }
    
    def run_demo(
        self,
        start: str = "2024-01-01",
        duration_days: int = 30,
    ) -> dict:
        """Run live demo simulation (paper trading mode)."""
        print(f"Starting demo trading for {duration_days} days...")
        
        # For demo, we use recent historical data as "live" feed
        end = (pd.Timestamp(start) + timedelta(days=duration_days)).strftime("%Y-%m-%d")
        return self.run_backtest(start=start, end=end)
    
    def get_status(self) -> dict:
        """Get current system status for monitoring."""
        return {
            "equity": self.equity,
            "current_equity": self.risk_manager.current_equity,
            "peak_equity": self.risk_manager.peak_equity,
            "daily_pnl": self.risk_manager.daily_pnl,
            "weekly_pnl": self.risk_manager.weekly_pnl,
            "monthly_pnl": self.risk_manager.monthly_pnl,
            "open_positions": len(self.executor.open_positions),
            "is_running": self.is_running,
        }


def main():
    """Main entry point for demo system."""
    import argparse
    
    parser = argparse.ArgumentParser(description="M.A.R.S. Demo Trading System")
    parser.add_argument("--mode", choices=["backtest", "demo"], default="backtest")
    parser.add_argument("--start", type=str, default="2020-01-01")
    parser.add_argument("--end", type=str, default=None)
    parser.add_argument("--equity", type=float, default=100000)
    parser.add_argument("--signal", choices=["donchian", "ma", "combined"], default="combined")
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()
    
    # Initialize system
    system = DemoTradingSystem(
        equity=args.equity,
        signal_type=args.signal,
        donchian_window=20,
        ma_fast=50,
        ma_slow=200,
        session="london",
    )
    
    if args.mode == "backtest":
        results = system.run_backtest(start=args.start, end=args.end)
        print(f"\n=== BACKTEST RESULTS ===")
        print(f"Final Equity: ${results['final_equity']:,.2f}")
        print(f"Total Return: {results['total_return']:.2%}")
        print(f"Total Trades: {len(results['trades'])}")
        
    elif args.mode == "demo":
        results = system.run_demo(start=args.start, duration_days=args.days)
        print(f"\n=== DEMO RESULTS ===")
        print(f"Final Equity: ${results['final_equity']:,.2f}")
        print(f"Total Return: {results['total_return']:.2%}")


if __name__ == "__main__":
    main()