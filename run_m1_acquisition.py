#!/usr/bin/env python
"""
End-to-end M1/Tick Acquisition and Validation Demonstration (Assignment 23).

Acquires M1 OHLCV and tick data from MT5, validates, stores versioned,
runs alignment checks, and performs $30 feasibility analysis.

Usage:
    python run_m1_acquisition.py --start 2024-01-01 --end 2024-12-31 --timeframes M1 TICKS
    python run_m1_acquisition.py --validate-only              # validate existing M1 if present
    python run_m1_acquisition.py --feasibility-only           # run feasibility with existing data
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from mars.core.config import DEFAULT_CONFIG
from mars.core.timeframes import Timeframe
from mars.core.types import DatasetLayer
from mars.data.catalog.catalog import LocalDatasetCatalog
from mars.data.ingestion.mt5 import MT5Ingestor
from mars.data.ingestion.pipeline import IngestionPipeline
from mars.data.normalization.ticks import resample_ticks_to_m1, validate_tick_integrity
from mars.data.storage.parquet_store import ParquetDatasetStore
from mars.data.validation.pipeline import MarketDataValidator
from mars.libs.execution.alignment import M5ToM1Alignment, create_aligned_execution_frame
from mars.libs.execution.cost_model import create_cost_model_from_spec
from mars.libs.risk.contract_aware import InstrumentSpec
from mars.libs.risk.feasibility import AccountFeasibilityAnalyzer
from mars.libs.strategies.xau_scalping_donchian import ScalpingDonchianParams, compute_scalping_signals
from mars.apps.research_lab.xau_scalping_donchian_research import load_dataset, slice_window


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="M1/Tick Acquisition & Validation")
    parser.add_argument(
        "--start", type=str, default=None,
        help="Start date (YYYY-MM-DD). Default: 1 year ago."
    )
    parser.add_argument(
        "--end", type=str, default=None,
        help="End date (YYYY-MM-DD). Default: now."
    )
    parser.add_argument(
        "--timeframes", nargs="+", default=["M1", "TICKS"],
        choices=["M1", "TICKS", "M5", "H1"],
        help="Data to acquire. Default: M1 TICKS"
    )
    parser.add_argument(
        "--symbol", type=str, default="XAUUSDm",
        help="Trading symbol. Default: XAUUSDm"
    )
    parser.add_argument(
        "--version", type=str, default="1.0.0",
        help="Dataset version. Default: 1.0.0"
    )
    parser.add_argument(
        "--validate-only", action="store_true",
        help="Only validate existing M1 data (no MT5 acquisition)"
    )
    parser.add_argument(
        "--feasibility-only", action="store_true",
        help="Only run feasibility analysis with existing data"
    )
    parser.add_argument(
        "--skip-mt5", action="store_true",
        help="Skip MT5 acquisition, use existing data only"
    )
    parser.add_argument(
        "--output-dir", type=str, default="reports/assignment23",
        help="Output directory for reports"
    )
    return parser.parse_args()


def get_default_dates() -> tuple[datetime, datetime]:
    """Get default date range (last 12 months)."""
    end = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=365)
    return start, end


def acquire_m1_data(
    ingestor: MT5Ingestor,
    pipeline: IngestionPipeline,
    symbol: str,
    start: datetime,
    end: datetime,
    version: str,
) -> tuple[Path, dict, dict]:
    """Acquire and store M1 OHLCV data."""
    print(f"\n{'='*60}")
    print(f"ACQUIRING M1 OHLCV: {symbol} [{start.date()} → {end.date()}]")
    print(f"{'='*60}")
    
    try:
        path, metadata, report = pipeline.run(
            symbol=symbol,
            timeframe=Timeframe.M1,
            start=start,
            end=end,
            version=version,
            source_name="exness_mt5",
            layer=DatasetLayer.PROCESSED,
        )
        
        print(f"✅ M1 acquisition successful")
        print(f"   Path: {path}")
        print(f"   Rows: {metadata.row_count:,}")
        print(f"   Date range: {metadata.start_ts} → {metadata.end_ts}")
        print(f"   Columns: {', '.join(metadata.columns)}")
        print(f"   Validation: {'PASSED' if report.passed else 'FAILED'}")
        if not report.passed:
            for issue in report.errors:
                print(f"   ❌ ERROR: {issue.message}")
            for issue in report.warnings:
                print(f"   ⚠️  WARNING: {issue.message}")
        
        return path, metadata.model_dump(), report.summary()
    
    except Exception as e:
        print(f"❌ M1 acquisition failed: {e}")
        return None, {"error": str(e)}, {"error": str(e)}


def acquire_tick_data(
    ingestor: MT5Ingestor,
    pipeline: IngestionPipeline,
    symbol: str,
    start: datetime,
    end: datetime,
    version: str,
) -> tuple[Path, dict, dict]:
    """Acquire and store tick data."""
    print(f"\n{'='*60}")
    print(f"ACQUIRING TICK DATA: {symbol} [{start.date()} → {end.date()}]")
    print(f"{'='*60}")
    
    try:
        path, metadata, report = pipeline.run_ticks(
            symbol=symbol,
            start=start,
            end=end,
            version=version,
            source_name="exness_mt5",
            layer=DatasetLayer.RAW,
        )
        
        print(f"✅ Tick acquisition successful")
        print(f"   Path: {path}")
        print(f"   Rows: {metadata.row_count:,}")
        print(f"   Date range: {metadata.start_ts} → {metadata.end_ts}")
        print(f"   Columns: {', '.join(metadata.columns)}")
        print(f"   Validation: {'PASSED' if report.passed else 'FAILED'}")
        if not report.passed:
            for issue in report.errors:
                print(f"   ❌ ERROR: {issue.message}")
            for issue in report.warnings:
                print(f"   ⚠️  WARNING: {issue.message}")
        
        return path, metadata.model_dump(), report.summary()
    
    except Exception as e:
        print(f"❌ Tick acquisition failed: {e}")
        return None, {"error": str(e)}, {"error": str(e)}


def validate_existing_m1(output_dir: Path) -> dict:
    """Validate existing M1 data from processed storage."""
    print(f"\n{'='*60}")
    print(f"VALIDATING EXISTING M1 DATA")
    print(f"{'='*60}")
    
    m1_path = DEFAULT_CONFIG.paths.processed / "xauusdm" / "m1" / "v1.0.0" / "data.parquet"
    if not m1_path.exists():
        print(f"❌ No M1 data found at {m1_path}")
        return {"error": "M1 data not found", "path": str(m1_path)}
    
    print(f"Loading: {m1_path}")
    m1 = pd.read_parquet(m1_path)
    
    # Ensure UTC index - handle both cases: timestamp as column or index
    if "timestamp" in m1.columns:
        m1 = m1.set_index("timestamp")
    if m1.index.tz is None:
        m1.index = m1.index.tz_localize("UTC")
    else:
        m1.index = m1.index.tz_convert("UTC")
    m1.index.name = "timestamp"
    
    # Add timestamp column for validator
    m1_with_ts = m1.reset_index()
    
    validator = MarketDataValidator()
    report = validator.validate(m1_with_ts, Timeframe.M1)
    
    print(f"Rows: {len(m1):,}")
    print(f"Date range: {m1.index.min()} → {m1.index.max()}")
    print(f"Columns: {', '.join(m1.columns)}")
    print(f"Validation: {'PASSED' if report.passed else 'FAILED'}")
    
    for issue in report.issues:
        level = "❌" if issue.severity == "error" else ("⚠️" if issue.severity == "warning" else "ℹ️")
        print(f"   {level} {issue.code}: {issue.message} (count: {issue.count})")
    
    # Basic stats
    stats = {
        "rows": len(m1),
        "start": str(m1.index.min()),
        "end": str(m1.index.max()),
        "columns": list(m1.columns),
        "validation_passed": report.passed,
        "validation_summary": report.summary(),
    }
    
    # Spread stats
    if "spread" in m1.columns:
        spread = m1["spread"].dropna()
        stats["spread_stats"] = {
            "mean": float(spread.mean()),
            "median": float(spread.median()),
            "min": float(spread.min()),
            "max": float(spread.max()),
            "zero_count": int((spread == 0).sum()),
            "nan_count": int(spread.isna().sum()),
        }
    
    return stats


def validate_existing_ticks(output_dir: Path) -> dict:
    """Validate existing tick data from raw storage."""
    print(f"\n{'='*60}")
    print(f"VALIDATING EXISTING TICK DATA")
    print(f"{'='*60}")
    
    # Check for tick data in raw
    raw_dir = DEFAULT_CONFIG.paths.raw / "xauusdm" / "ticks" / "exness"
    tick_files = list(raw_dir.glob("*.parquet")) if raw_dir.exists() else []
    
    if not tick_files:
        print(f"ℹ️  No tick data found in {raw_dir}")
        return {"error": "No tick data found", "path": str(raw_dir)}
    
    results = {}
    for f in tick_files:
        print(f"Loading: {f}")
        ticks = pd.read_parquet(f)
        
        if ticks.index.tz is None:
            ticks.index = ticks.index.tz_localize("UTC")
        else:
            ticks.index = ticks.index.tz_convert("UTC")
        ticks.index.name = "timestamp"
        
        # Validate
        issues = validate_tick_integrity(ticks)
        print(f"  Rows: {len(ticks):,}")
        print(f"  Date range: {ticks.index.min()} → {ticks.index.max()}")
        print(f"  Columns: {', '.join(ticks.columns)}")
        
        if issues:
            for issue in issues:
                print(f"  ❌ {issue}")
        else:
            print(f"  ✅ Tick integrity checks passed")
        
        # Spread stats
        if "spread" in ticks.columns:
            spread = ticks["spread"].dropna()
            print(f"  Spread: mean={spread.mean():.1f}, median={spread.median():.1f}, max={spread.max():.1f}")
        
        results[f.name] = {
            "rows": len(ticks),
            "start": str(ticks.index.min()),
            "end": str(ticks.index.max()),
            "columns": list(ticks.columns),
            "issues": issues,
        }
    
    return results


def run_alignment_check(m1_data: pd.DataFrame, m5_data: pd.DataFrame, h1_data: pd.DataFrame) -> dict:
    """Run M5→M1 alignment validation with synthetic signals."""
    print(f"\n{'='*60}")
    print(f"M5→M1 ALIGNMENT VALIDATION")
    print(f"{'='*60}")
    
    # Generate M5 signals using Assignment 22 strategy
    params = ScalpingDonchianParams(
        donchian_lookback=20,
        ema_period=50,
        ema_slope_bars=5,
        atr_period=14,
        atr_stop_multiplier=2.0,
        execution_timeframe="M5",
        max_holding_bars=6,
    )
    
    # Use overlapping date range between M1, M5, and H1
    # For M1 data that's only recent, use the intersection
    overlap_start = max(m1_data.index.min(), m5_data.index.min(), h1_data.index.min())
    overlap_end = min(m1_data.index.max(), m5_data.index.max(), h1_data.index.max())
    
    if overlap_start >= overlap_end:
        print(f"⚠️  No overlapping date range between M1, M5, H1")
        return {"error": "No overlapping date range"}
    
    # Use the most recent 90 days of overlapping data for testing
    test_end = overlap_end
    test_start = test_end - timedelta(days=90)
    # But ensure we have at least 30 days of M5 warmup
    if test_start < m5_data.index.min() + timedelta(days=30):
        test_start = m5_data.index.min() + timedelta(days=30)
    
    print(f"Test window: {test_start.date()} → {test_end.date()}")
    
    m5_slice = m5_data[(m5_data.index >= test_start) & (m5_data.index < test_end)].copy()
    h1_slice = h1_data[(h1_data.index >= test_start) & (h1_data.index < test_end)].copy()
    
    if len(m5_slice) < 100 or len(h1_slice) < 20:
        print(f"⚠️  Insufficient data for alignment test")
        return {"error": "Insufficient data"}
    
    # Add timestamp column for signal computation
    m5_with_ts = m5_slice.reset_index()
    h1_with_ts = h1_slice.reset_index()
    
    print(f"Generating M5 signals on {len(m5_slice)} bars...")
    signals = compute_scalping_signals(
        execution_tf=m5_with_ts,
        context_tf=m5_with_ts,
        h1=h1_with_ts,
        params=params,
    ).frame
    
    print(f"Signals generated: {len(signals)} bars")
    print(f"  Entry long: {int(signals['entry_long'].sum())}")
    print(f"  Entry short: {int(signals['entry_short'].sum())}")
    
    # Slice M1 to same window
    m1_slice = m1_data[(m1_data.index >= test_start) & (m1_data.index < test_end)].copy()
    
    # Ensure timestamp is a column (not index)
    if m1_slice.index.name == "timestamp" or m1_slice.index.name is None:
        if "timestamp" in m1_slice.columns:
            # Already has timestamp column, just ensure index is RangeIndex
            m1_with_ts = m1_slice.reset_index(drop=True)
        else:
            m1_with_ts = m1_slice.reset_index()
    else:
        m1_with_ts = m1_slice.reset_index()
    
    print(f"Aligning to {len(m1_slice)} M1 bars...")
    
    # Create aligned execution frame
    aligned = create_aligned_execution_frame(
        m5_signals=signals,
        m1_execution=m1_with_ts,
        max_holding_bars_m1=6,
    )
    
    print(f"Aligned frame: {len(aligned)} bars")
    print(f"  Signal columns: {[c for c in aligned.columns if c.startswith('m5_signal_')]}")
    
    # Run no-lookahead checks
    aligner = M5ToM1Alignment()
    checks = aligner.check_no_lookahead(aligned)
    
    print(f"\nNo-Lookahead Checks:")
    for check_name, result in checks["checks"].items():
        if "passed" in result:
            status = "✅" if result["passed"] else "❌"
            print(f"  {status} {check_name}: {result}")
        else:
            print(f"  ℹ️  {check_name}: {result}")
    
    # Entry timing verification
    if "entry_bar_index" in aligned.columns:
        valid_entries = aligned["entry_bar_index"] >= 0
        if valid_entries.any():
            print(f"\nEntry Timing:")
            print(f"  Signal bars: {aligned.loc[valid_entries, 'signal_bar_index'].values[:5]}")
            print(f"  Entry bars:  {aligned.loc[valid_entries, 'entry_bar_index'].values[:5]}")
            print(f"  Difference:  {(aligned.loc[valid_entries, 'entry_bar_index'] - aligned.loc[valid_entries, 'signal_bar_index']).values[:5]}")
    
    return {
        "aligned_rows": len(aligned),
        "m5_signal_rows": len(signals),
        "m1_execution_rows": len(m1_slice),
        "lookahead_checks": checks,
        "test_window": f"{test_start.date()} → {test_end.date()}",
    }


def run_feasibility_analysis(m1_data: pd.DataFrame, m5_data: pd.DataFrame) -> dict:
    """Run independent $30 feasibility analysis."""
    print(f"\n{'='*60}")
    print(f"$30 ACCOUNT FEASIBILITY ANALYSIS")
    print(f"{'='*60}")
    
    # Exness XAUUSDm spec
    spec = InstrumentSpec(
        symbol="XAUUSDm",
        contract_size=100.0,
        pip_size=0.01,
        point_size=0.001,
        quote_currency="USD",
        volume_min=0.01,
        volume_max=200.0,
        volume_step=0.01,
        volume_spec_source="mt5.live",
        spec_source="mt5.live",
    )
    
    # Calculate average stop distance from M5 signals (Assignment 22 params)
    params = ScalpingDonchianParams(
        donchian_lookback=20,
        ema_period=50,
        ema_slope_bars=5,
        atr_period=14,
        atr_stop_multiplier=2.0,
        execution_timeframe="M5",
        max_holding_bars=6,
    )
    
    # Use recent data for stats
    recent_start = m5_data.index.max() - timedelta(days=180)
    m5_recent = m5_data[m5_data.index >= recent_start].copy()
    h1_recent = m5_recent.resample("1h").agg({
        "open": "first", "high": "max", "low": "min", "close": "last",
        "tick_volume": "sum", "spread": "mean"
    }).dropna()
    
    m5_with_ts = m5_recent.reset_index()
    h1_with_ts = h1_recent.reset_index()
    
    signals = compute_scalping_signals(
        execution_tf=m5_with_ts,
        context_tf=m5_with_ts,
        h1=h1_with_ts,
        params=params,
    ).frame
    
    # Average stop distance (where valid)
    valid_stops = signals["stop_distance"].dropna()
    avg_stop_distance = float(valid_stops.mean()) if len(valid_stops) > 0 else 0.0
    
    # Average spread from M1 data
    m1_recent = m1_data[m1_data.index >= recent_start] if len(m1_data) > 0 else pd.DataFrame()
    if len(m1_recent) > 0 and "spread" in m1_recent.columns:
        avg_spread = float(m1_recent["spread"].dropna().mean())
    elif "spread" in m5_recent.columns:
        avg_spread = float(m5_recent["spread"].dropna().mean())
    else:
        avg_spread = 200.0  # fallback
    
    # Average entry price
    avg_price = float(m5_recent["close"].mean()) if len(m5_recent) > 0 else 2000.0
    
    print(f"Input Parameters:")
    print(f"  Avg Stop Distance: {avg_stop_distance:.5f} price units")
    print(f"  Avg Spread: {avg_spread:.1f} points")
    print(f"  Avg Price: {avg_price:.2f}")
    
    # Run feasibility analysis
    analyzer = AccountFeasibilityAnalyzer(
        spec=spec,
        equity_usd=30.0,
        risk_fraction=0.01,
        leverage=2000,
        commission_per_lot=0.0,
        swap_long_points=-10.0,
        swap_short_points=-5.0,
        avg_holding_bars=6.0,
        timeframe_minutes=5,
    )
    
    result = analyzer.analyze(
        avg_stop_distance_price=avg_stop_distance,
        avg_spread_points=avg_spread,
        entry_price=avg_price,
        side="long",
    )
    
    print(result)
    
    # Also test with M1 execution timeframe (3-6 min holds)
    print(f"\n--- M1 Execution Mode (3-6 min holds) ---")
    analyzer_m1 = AccountFeasibilityAnalyzer(
        spec=spec,
        equity_usd=30.0,
        risk_fraction=0.01,
        leverage=2000,
        commission_per_lot=0.0,
        swap_long_points=-10.0,
        swap_short_points=-5.0,
        avg_holding_bars=6.0,
        timeframe_minutes=1,  # M1 bars
    )
    
    # For M1, stop distance might be different (using M1 ATR)
    # Use same stop distance for comparison
    result_m1 = analyzer_m1.analyze(
        avg_stop_distance_price=avg_stop_distance,
        avg_spread_points=avg_spread,
        entry_price=avg_price,
        side="long",
    )
    
    print(result_m1)
    
    # Minimum equity required
    min_equity = analyzer.find_minimum_viable_equity(avg_stop_distance)
    print(f"\nMinimum equity for 1% risk at min lot: ${min_equity:.2f}")
    
    return {
        "m5_execution": result.to_dict(),
        "m1_execution": result_m1.to_dict(),
        "min_equity_required_usd": min_equity,
        "input_params": {
            "avg_stop_distance": avg_stop_distance,
            "avg_spread_points": avg_spread,
            "avg_price": avg_price,
        },
    }


def load_existing_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load existing M1, M5, H1 data from processed storage."""
    m1, m5, h1 = load_dataset(DEFAULT_CONFIG.paths.root)
    return m1, m5, h1


def main():
    args = parse_args()
    
    # Setup output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Parse dates
    if args.start:
        start = datetime.strptime(args.start, "%Y-%m-%d")
    else:
        start, _ = get_default_dates()
    
    if args.end:
        end = datetime.strptime(args.end, "%Y-%m-%d")
    else:
        _, end = get_default_dates()
    
    print(f"\n{'#'*60}")
    print(f"# M.A.R.S. QUANT — ASSIGNMENT 23")
    print(f"# M1/Tick Data Acquisition & Short-Horizon Research Foundation")
    print(f"# {'#'*52}")
    print(f"# Symbol: {args.symbol}")
    print(f"# Date Range: {start.date()} → {end.date()}")
    print(f"# Timeframes: {', '.join(args.timeframes)}")
    print(f"# Version: {args.version}")
    print(f"# Output: {output_dir}")
    print(f"{'#'*60}\n")
    
    # Load existing data for validation/alignment/feasibility
    print(f"Loading existing datasets...")
    m1_existing, m5_existing, h1_existing = load_existing_data()
    print(f"  M1: {len(m1_existing):,} bars" if len(m1_existing) > 0 else "  M1: NOT AVAILABLE")
    print(f"  M5: {len(m5_existing):,} bars")
    print(f"  H1: {len(h1_existing):,} bars")
    
    results = {
        "symbol": args.symbol,
        "date_range": {"start": str(start), "end": str(end)},
        "version": args.version,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
    
    # ============================================================
    # FEASIBILITY ONLY MODE
    # ============================================================
    if args.feasibility_only:
        print(f"\nRunning feasibility analysis only...")
        feasibility = run_feasibility_analysis(m1_existing, m5_existing)
        results["feasibility"] = feasibility
        
        # Save report
        import json
        with open(output_dir / "feasibility_report.json", "w") as f:
            json.dump(feasibility, f, indent=2, default=str)
        
        print(f"\n✅ Feasibility report saved to {output_dir}/feasibility_report.json")
        return 0
    
    # ============================================================
    # VALIDATE ONLY MODE
    # ============================================================
    if args.validate_only:
        print(f"\nRunning validation only...")
        m1_stats = validate_existing_m1(output_dir)
        results["m1_validation"] = m1_stats
        
        tick_stats = validate_existing_ticks(output_dir)
        results["tick_validation"] = tick_stats
        
        if len(m1_existing) > 0 and len(m5_existing) > 0:
            alignment = run_alignment_check(m1_existing, m5_existing, h1_existing)
            results["alignment"] = alignment
        
        feasibility = run_feasibility_analysis(m1_existing, m5_existing)
        results["feasibility"] = feasibility
        
        # Save report
        import json
        with open(output_dir / "validation_report.json", "w") as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"\n✅ Validation report saved to {output_dir}/validation_report.json")
        return 0
    
    # ============================================================
    # MT5 ACQUISITION MODE
    # ============================================================
    if not args.skip_mt5:
        # Initialize MT5 ingestor and pipeline
        ingestor = MT5Ingestor()
        pipeline = IngestionPipeline(ingestor=ingestor)
        
        # Acquire M1
        if "M1" in args.timeframes:
            m1_path, m1_meta, m1_report = acquire_m1_data(
                ingestor, pipeline, args.symbol, start, end, args.version
            )
            results["m1_acquisition"] = {
                "path": str(m1_path) if m1_path else None,
                "metadata": m1_meta,
                "validation": m1_report,
            }
        
        # Acquire Ticks
        if "TICKS" in args.timeframes:
            tick_path, tick_meta, tick_report = acquire_tick_data(
                ingestor, pipeline, args.symbol, start, end, args.version
            )
            results["tick_acquisition"] = {
                "path": str(tick_path) if tick_path else None,
                "metadata": tick_meta,
                "validation": tick_report,
            }
    
    # ============================================================
    # POST-ACQUISITION VALIDATION & ANALYSIS
    # ============================================================
    # Reload data (may have new M1)
    m1_data, m5_data, h1_data = load_existing_data()
    
    if len(m1_data) > 0:
        m1_stats = validate_existing_m1(output_dir)
        results["m1_validation"] = m1_stats
    
    if "TICKS" in args.timeframes and not args.skip_mt5:
        tick_stats = validate_existing_ticks(output_dir)
        results["tick_validation"] = tick_stats
    
    # Alignment check
    if len(m1_data) > 0 and len(m5_data) > 0:
        alignment = run_alignment_check(m1_data, m5_data, h1_data)
        results["alignment"] = alignment
    
    # Feasibility
    feasibility = run_feasibility_analysis(m1_data, m5_data)
    results["feasibility"] = feasibility
    
    # ============================================================
    # SAVE FINAL REPORT
    # ============================================================
    import json
    report_path = output_dir / "acquisition_report.json"
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n{'='*60}")
    print(f"COMPLETION SUMMARY")
    print(f"{'='*60}")
    print(f"Report saved: {report_path}")
    
    if "m1_acquisition" in results:
        m1 = results["m1_acquisition"]
        status = "✅" if m1.get("path") else "❌"
        print(f"  M1 Acquisition: {status} {m1.get('path', 'FAILED')}")
    
    if "tick_acquisition" in results:
        tick = results["tick_acquisition"]
        status = "✅" if tick.get("path") else "❌"
        print(f"  Tick Acquisition: {status} {tick.get('path', 'FAILED')}")
    
    if "alignment" in results:
        align = results["alignment"]
        status = "✅" if align.get("lookahead_checks", {}).get("passed") else "❌"
        print(f"  M5→M1 Alignment: {status} (lookahead: {align.get('lookahead_checks', {}).get('passed', 'N/A')})")
    
    if "feasibility" in results:
        feas = results["feasibility"]
        m5_feas = feas.get("m5_execution", {}).get("feasible", False)
        m1_feas = feas.get("m1_execution", {}).get("feasible", False)
        print(f"  $30 Feasibility (M5 exec): {'✅' if m5_feas else '❌'}")
        print(f"  $30 Feasibility (M1 exec): {'✅' if m1_feas else '❌'}")
        print(f"  Min Equity Required: ${feas.get('min_equity_required_usd', 0):.2f}")
    
    # Exit code
    if args.skip_mt5 or not args.timeframes:
        return 0
    
    # Fail if acquisition was requested but failed
    if "M1" in args.timeframes and not results.get("m1_acquisition", {}).get("path"):
        return 1
    if "TICKS" in args.timeframes and not results.get("tick_acquisition", {}).get("path"):
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())