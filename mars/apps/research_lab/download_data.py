"""
MT5 data download entry point (optional; requires MetaTrader5 + credentials).

Usage::

    python -m mars.apps.research_lab.download_data --symbol XAUUSD --year 2018 --timeframe H1
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from mars.libs.utils.paths import ProjectPaths


def main() -> None:
    parser = argparse.ArgumentParser(description="Download OHLCV via MetaTrader 5.")
    parser.add_argument("--symbol", type=str, default="XAUUSD")
    parser.add_argument("--year", type=int, default=2018)
    parser.add_argument("--timeframe", type=str, default="H1")
    args = parser.parse_args()

    try:
        import MetaTrader5 as mt5
        import pandas as pd
        from dotenv import load_dotenv
        import os
    except ImportError as e:
        raise SystemExit(
            f"Missing dependency: {e}. Install requirements and ensure MetaTrader5 is available."
        )

    load_dotenv()
    account = os.getenv("DEMO_ACCOUNT_NUMBER")
    password = os.getenv("PASSWORD")
    server = os.getenv("SERVER")
    if not all([account, password, server]):
        raise SystemExit("Set DEMO_ACCOUNT_NUMBER, PASSWORD, SERVER in .env")

    timeframes = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
    }
    tf = timeframes.get(args.timeframe.upper(), mt5.TIMEFRAME_H1)

    if not mt5.initialize(login=int(account), password=password, server=server):
        raise SystemExit(f"MT5 initialize failed: {mt5.last_error()}")

    rates = mt5.copy_rates_range(
        args.symbol, tf, datetime(args.year, 1, 1), datetime.now()
    )
    mt5.shutdown()

    if rates is None:
        raise SystemExit("No data received from MT5.")

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")

    paths = ProjectPaths.from_root()
    paths.raw_data.mkdir(parents=True, exist_ok=True)
    out = (
        paths.raw_data
        / f"{args.symbol.lower()}_{args.timeframe.lower()}_{args.year}_present.parquet"
    )
    df.to_parquet(out)
    print(f"Saved {len(df)} rows → {out}")


if __name__ == "__main__":
    main()
