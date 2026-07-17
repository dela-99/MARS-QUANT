"""
Train baseline XGBoost classifier/regressor for Hypothesis A (Asia → London).

Usage (from repo root)::

    python -m mars.apps.trainer.train_xgb_baseline --year 2018
"""

from __future__ import annotations

import argparse
from pathlib import Path

from mars.apps.research_lab.xauusd_baseline_pipeline import run_baseline_pipeline
from mars.libs.utils.paths import ProjectPaths


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="M.A.R.S. XGBoost baseline trainer (Hyp-A).")
    p.add_argument("--year", type=int, default=2018, help="Start year of raw dataset suffix.")
    p.add_argument("--symbol", type=str, default="xauusd")
    p.add_argument("--timeframe", type=str, default="h1")
    p.add_argument("--train-ratio", type=float, default=0.70)
    p.add_argument("--val-ratio", type=float, default=0.15)
    p.add_argument("--test-ratio", type=float, default=0.15)
    p.add_argument(
        "--data-path",
        type=str,
        default=None,
        help="Optional explicit path to raw parquet (overrides year/symbol/tf).",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    paths = ProjectPaths.from_root()
    if args.data_path:
        data_path = Path(args.data_path)
    else:
        data_path = (
            paths.raw_data
            / f"{args.symbol.lower()}_{args.timeframe.lower()}_{args.year}_present.parquet"
        )

    result = run_baseline_pipeline(
        data_path=data_path,
        symbol=args.symbol.upper(),
        timeframe=args.timeframe.lower(),
        train_ratio=args.train_ratio,
        val_ratio=args.val_ratio,
        test_ratio=args.test_ratio,
        save_artifacts=True,
    )
    print(result["summary"])
    print(f"\nReport: {result['report_path']}")
    print(f"Classifier: {result['classifier_path']}")


if __name__ == "__main__":
    main()
