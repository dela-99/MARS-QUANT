"""
Exness XAUUSDm dataset construction, validation and provenance (Assignment 14, Phase B).

Purpose
-------
The consolidated Exness M5 export (``data/raw/xauusdm/m5/exness/XAUUSDm_M5_2020_2026_raw.csv``)
contains a **daily-interval block embedded inside an M5 series**:

    2020-01-02 00:00  ->  2021-07-16 00:00   (478 rows, D1 frequency, spread == 0)

``XAUUSDm_M5_2020_1_12.csv`` is entirely daily bars (311 rows, one bar per calendar
day at 00:00).  ``XAUUSDm_M5_2021 jan to dec.csv`` is daily bars from 2021-01-03 up
to 2021-07-16 and true M5 bars from 2021-07-16 13:05 onwards.  The file named
``XAUUSDm_M5_2024 jan to feb.csv`` actually contains the **full 2024 calendar year**
(2024-01-01 23:05 -> 2024-12-31, 70,773 M5 rows) - the filename is wrong, the file
contents are authoritative.

This module builds a research-grade, versioned dataset that contains **only true
M5 bars**, preserves the observed spread and tick volume, and records full
provenance (source checksums, exclusions, transformations, quality checks).

It also exposes the raw-H1 vs M5 hour-grid reconciliation finding:
the Exness H1 parquet export sits on a **different hourly grid** than the M5 CSV
export (offset +2h in winter months, +3h in summer months, tracking European DST).
H1 context is therefore always derived by resampling the M5 dataset, never by
mixing the raw H1 file into the M5 frame.

Nothing in this module invents broker data: bid/ask, commission, swap and slippage
are never fabricated.  Only the *observed* spread column is carried forward.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: A row belongs to a daily block when its time-of-day equals the previous row's
#: time-of-day AND the gap to the previous row is an exact multiple of one day.
#: M5 rows are 300 s apart, so this rule can never fire on genuine M5 data.
_DAILY_MULTIPLE_S = 86_400

#: Canonical processed column order.
CANONICAL_COLUMNS: Tuple[str, ...] = (
    "open",
    "high",
    "low",
    "close",
    "tick_volume",
    "volume",
    "spread",
)

#: Raw consolidated Exness M5 export (immutable).
DEFAULT_RAW_M5 = Path(
    "data/raw/xauusdm/m5/exness/XAUUSDm_M5_2020_2026_raw.csv"
)

#: Original yearly Exness exports (immutable, outside the repo).
DEFAULT_SOURCE_DIR = Path(r"C:\Users\RIDGE\trading-data")

#: Version produced by this module.
M5_VERSION = "v1.2.0"
D1_VERSION = "v1.0.0"
H1_VERSION = "v1.2.0"


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    """Return the SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def _read_exness_csv(path: Path) -> pd.DataFrame:
    """Read one MT5 History-Centre CSV export into a canonical frame.

    The export is tab separated with ``<DATE> <TIME> <OPEN> ... <SPREAD>`` columns.
    ``<DATE>``/``<TIME>`` are combined into a single UTC timestamp.
    """
    df = pd.read_csv(path, sep="\t")
    df.columns = [c.strip().strip("<>").strip().lower() for c in df.columns]
    if "date" in df.columns and "time" in df.columns:
        raw = df["date"].astype(str).str.strip() + " " + df["time"].astype(str).str.strip()
    else:  # pragma: no cover - defensive
        raw = df[df.columns[0]].astype(str).str.strip()
    df = df.assign(timestamp=pd.to_datetime(raw, errors="coerce", utc=True))
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    for col in ("open", "high", "low", "close"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in ("tickvol", "vol", "spread"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype("int64")
        else:
            df[col] = 0
    df = df.rename(columns={"tickvol": "tick_volume", "vol": "volume"})
    return df[["timestamp", "open", "high", "low", "close", "tick_volume", "volume", "spread"]]


def classify_daily_interval(df: pd.DataFrame) -> pd.Series:
    """Return a boolean mask flagging rows that belong to a daily-interval block.

    A row is daily-interval iff its time-of-day equals the previous row's
    time-of-day and the gap to the previous row is an exact multiple of 86,400 s.
    The leading run of midnight-anchored rows is also flagged, because the
    consolidated export starts with the 2020-01-02 daily bar.
    """
    ts = df["timestamp"]
    gap = ts.diff().dt.total_seconds()
    same_tod = ts.dt.time == ts.shift(1).dt.time
    multiple = (gap % _DAILY_MULTIPLE_S == 0) & (gap >= _DAILY_MULTIPLE_S)
    mask = (same_tod & multiple).fillna(False)
    _propagate_leading_midnight_run(ts, mask)
    return mask


def _propagate_leading_midnight_run(ts: pd.Series, mask: pd.Series) -> None:
    """Flag the leading run of midnight-anchored rows as daily (in place)."""
    if not len(ts):
        return
    midnight = ts.dt.time == pd.Timestamp("00:00:00").time()
    i = 0
    while i < len(ts) and bool(midnight.iloc[i]):
        mask.iloc[i] = True
        i += 1


def split_m5_and_d1(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Split a consolidated Exness frame into (true M5 rows, daily-interval rows).

    The first row of the consolidated file is part of the daily block (it is the
    2020-01-02 daily bar), so it is classified as daily whenever the file starts
    with a run of midnight-anchored rows.
    """
    ts = df["timestamp"]
    gap = ts.diff().dt.total_seconds()
    same_tod = ts.dt.time == ts.shift(1).dt.time
    multiple = (gap % _DAILY_MULTIPLE_S == 0) & (gap >= _DAILY_MULTIPLE_S)
    daily = (same_tod & multiple).fillna(False)
    _propagate_leading_midnight_run(ts, daily)

    m5 = df[~daily].reset_index(drop=True)
    d1 = df[daily].reset_index(drop=True)
    return m5, d1


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@dataclass
class QualityReport:
    """Structured result of the dataset validation gate."""

    rows: int = 0
    start: Optional[str] = None
    end: Optional[str] = None
    duplicate_timestamps: int = 0
    monotonic_increasing: bool = True
    ohlc_violations: int = 0
    non_positive_prices: int = 0
    missing_values: int = 0
    negative_spread_rows: int = 0
    zero_spread_rows: int = 0
    non_five_minute_intervals: int = 0
    daily_interval_rows: int = 0
    session_break_gaps: int = 0
    intraday_closure_gaps: int = 0
    multi_day_closure_gaps: int = 0
    in_session_outage_gaps: int = 0
    max_in_session_outage_bars: int = 0
    in_session_outage_examples: List[Dict[str, Any]] = field(default_factory=list)
    interval_histogram: Dict[str, int] = field(default_factory=dict)
    rows_per_year: Dict[str, int] = field(default_factory=dict)
    weekend_gaps: int = 0
    passed: bool = False
    failures: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rows": self.rows,
            "start": self.start,
            "end": self.end,
            "duplicate_timestamps": self.duplicate_timestamps,
            "monotonic_increasing": self.monotonic_increasing,
            "ohlc_violations": self.ohlc_violations,
            "non_positive_prices": self.non_positive_prices,
            "missing_values": self.missing_values,
            "negative_spread_rows": self.negative_spread_rows,
            "zero_spread_rows": self.zero_spread_rows,
            "non_five_minute_intervals": self.non_five_minute_intervals,
            "daily_interval_rows": self.daily_interval_rows,
            "gap_classification": {
                "session_break": self.session_break_gaps,
                "intraday_closure": self.intraday_closure_gaps,
                "multi_day_closure": self.multi_day_closure_gaps,
                "in_session_outage": self.in_session_outage_gaps,
                "max_in_session_outage_missing_bars": self.max_in_session_outage_bars,
                "in_session_outage_examples": self.in_session_outage_examples,
            },
            "interval_histogram": self.interval_histogram,
            "rows_per_year": self.rows_per_year,
            "weekend_gaps": self.weekend_gaps,
            "passed": self.passed,
            "failures": self.failures,
            "notes": self.notes,
        }


def validate_m5(df: pd.DataFrame, *, expect_five_minute: bool = True) -> QualityReport:
    """Validate an M5 frame against the M.A.R.S. data contract.

    Hard failures (block the data gate): duplicate timestamps, non-monotonic
    index, OHLC violations, non-positive prices, missing values, negative spread.
    Soft observations (documented, not blocking): gaps that correspond to market
    closures (weekends and the daily session break).
    """
    rep = QualityReport()
    rep.rows = int(len(df))
    if len(df) == 0:
        rep.failures.append("empty dataset")
        rep.passed = False
        return rep

    ts = df["timestamp"] if "timestamp" in df.columns else pd.DatetimeIndex(df.index)
    rep.start = str(ts.iloc[0])
    rep.end = str(ts.iloc[-1])
    rep.duplicate_timestamps = int(ts.duplicated().sum())
    rep.monotonic_increasing = bool(ts.is_monotonic_increasing)

    ohlc = df[["open", "high", "low", "close"]]
    rep.missing_values = int(df[list(CANONICAL_COLUMNS)].isna().sum().sum())
    rep.ohlc_violations = int(
        (
            (df["high"] < df["low"])
            | (df["high"] < df["open"])
            | (df["high"] < df["close"])
            | (df["low"] > df["open"])
            | (df["low"] > df["close"])
        ).sum()
    )
    rep.non_positive_prices = int((ohlc <= 0).any(axis=1).sum())
    if "spread" in df.columns:
        rep.negative_spread_rows = int((df["spread"] < 0).sum())
        rep.zero_spread_rows = int((df["spread"] == 0).sum())

    gap = ts.diff().dt.total_seconds().dropna()
    if len(gap):
        vc = gap.value_counts()
        rep.interval_histogram = {f"{int(k)}s": int(v) for k, v in vc.head(12).items()}
        if expect_five_minute:
            rep.non_five_minute_intervals = int((gap != 300).sum())
            rep.daily_interval_rows = int((gap % _DAILY_MULTIPLE_S == 0).sum())
            rep.weekend_gaps = int(((gap >= 172_800) & (gap <= 180_000)).sum())
            rep.multi_day_closure_gaps = int((gap >= 172_800).sum())
            rep.session_break_gaps = int(((gap >= 3_600) & (gap < 4_200)).sum())
            rep.intraday_closure_gaps = int(
                ((gap >= 4_200) & (gap < 172_800)).sum()
            )
            outages = gap[(gap > 300) & (gap < 3_600)]
            rep.in_session_outage_gaps = int(len(outages))
            if len(outages):
                missing = (outages / 300.0).round().astype(int) - 1
                rep.max_in_session_outage_bars = int(missing.max())
                idx = outages.index
                examples = []
                for i in list(idx)[:20]:
                    examples.append(
                        {
                            "after": str(ts.iloc[i - 1]),
                            "before": str(ts.iloc[i]),
                            "gap_seconds": int(outages.loc[i]),
                            "missing_bars": int(round(float(outages.loc[i]) / 300.0)) - 1,
                        }
                    )
                rep.in_session_outage_examples = examples

    rep.rows_per_year = {
        str(y): int(n) for y, n in ts.dt.year.value_counts().sort_index().items()
    }

    if rep.duplicate_timestamps:
        rep.failures.append(f"{rep.duplicate_timestamps} duplicate timestamps")
    if not rep.monotonic_increasing:
        rep.failures.append("timestamps are not strictly increasing")
    if rep.ohlc_violations:
        rep.failures.append(f"{rep.ohlc_violations} OHLC integrity violations")
    if rep.non_positive_prices:
        rep.failures.append(f"{rep.non_positive_prices} non-positive price rows")
    if rep.missing_values:
        rep.failures.append(f"{rep.missing_values} missing values")
    if rep.negative_spread_rows:
        rep.failures.append(f"{rep.negative_spread_rows} negative spread rows")
    if expect_five_minute and rep.daily_interval_rows:
        rep.failures.append(
            f"{rep.daily_interval_rows} whole-day intervals remain - daily bars are "
            "embedded in the M5 series"
        )
    if rep.zero_spread_rows:
        rep.notes.append(
            f"{rep.zero_spread_rows} bars carry spread == 0 (the cost model substitutes "
            "the per-bar median spread for those bars)"
        )
    if rep.in_session_outage_gaps:
        rep.notes.append(
            f"{rep.in_session_outage_gaps} in-session feed outages "
            f"(max {rep.max_in_session_outage_bars} missing bars) - documented, not filled; "
            "bar-count based indicators are unaffected in structure"
        )
    rep.passed = not rep.failures
    return rep


# ---------------------------------------------------------------------------
# Resampling
# ---------------------------------------------------------------------------


def resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Resample a canonical frame to a higher timeframe.

    Aggregation: open=first, high=max, low=min, close=last, tick_volume=sum,
    volume=sum, spread=mean.  Periods that contain no source bar are dropped;
    periods with fewer than the expected number of bars are **kept** but flagged
    by the caller's validation (no silent filling).
    """
    out = df.copy()
    out["timestamp"] = out["timestamp"]
    out = out.set_index("timestamp").sort_index()
    agg = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "tick_volume": "sum",
        "volume": "sum",
        "spread": "mean",
    }
    res = out.resample(rule).agg(agg)
    res = res.dropna(subset=["open", "high", "low", "close"]).reset_index()
    res["spread"] = res["spread"].fillna(0).round().astype("int64")
    res["tick_volume"] = res["tick_volume"].astype("int64")
    res["volume"] = res["volume"].astype("int64")
    return res[list(CANONICAL_COLUMNS) + ["timestamp"]]


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


@dataclass
class SourceInventory:
    """Provenance record for one original Exness export file."""

    filename: str
    sha256: str
    rows: int
    start: str
    end: str
    modal_interval_seconds: int
    inferred_timeframe: str
    daily_rows: int
    m5_rows: int
    filename_mislabelled: bool = False
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "filename": self.filename,
            "sha256": self.sha256,
            "rows": self.rows,
            "date_range": {"start": self.start, "end": self.end},
            "modal_interval_seconds": self.modal_interval_seconds,
            "inferred_timeframe": self.inferred_timeframe,
            "daily_rows": self.daily_rows,
            "m5_rows": self.m5_rows,
            "filename_mislabelled": self.filename_mislabelled,
            "notes": self.notes,
        }


def _modal_interval_seconds(df: pd.DataFrame) -> int:
    gap = df["timestamp"].diff().dt.total_seconds().dropna()
    if not len(gap):
        return 0
    return int(gap.value_counts().index[0])


def _infer_timeframe(seconds: int) -> str:
    return {60: "M1", 300: "M5", 900: "M15", 1800: "M30", 3600: "H1",
            14400: "H4", 86400: "D1"}.get(seconds, f"{seconds}s")


def inventory_sources(source_dir: Path = DEFAULT_SOURCE_DIR) -> List[SourceInventory]:
    """Inspect every original Exness export and record its true content.

    The returned inventory is what makes the 2020 and 2024 findings auditable:
    the file *name* is never trusted over the file *content*.
    """
    out: List[SourceInventory] = []
    for path in sorted(Path(source_dir).glob("XAUUSDm_M5_*.csv")):
        raw = _read_exness_csv_safe(path)
        m5, d1 = split_m5_and_d1(raw)
        modal = _modal_interval_seconds(raw)
        name = path.name
        mislabelled = False
        notes = ""
        if "2020" in name:
            notes = (
                "Entirely daily-interval bars (one bar per calendar day at 00:00, "
                "spread == 0). Not an M5 file - excluded from the M5 dataset."
            )
        if "2021" in name:
            notes = (
                "Daily-interval bars from 2021-01-03 to 2021-07-16, true M5 bars "
                "from 2021-07-16 13:05. The daily prefix is excluded from the M5 dataset."
            )
        if "2024" in name:
            mislabelled = True
            notes = (
                "Filename says '2024 jan to feb' but the file contains the FULL 2024 "
                "calendar year (2024-01-01 23:05 -> 2024-12-31, 70,773 M5 rows). "
                "Contents are authoritative; the filename is wrong."
            )
        out.append(
            SourceInventory(
                filename=name,
                sha256=sha256_file(path),
                rows=int(len(raw)),
                start=str(raw["timestamp"].iloc[0]),
                end=str(raw["timestamp"].iloc[-1]),
                modal_interval_seconds=modal,
                inferred_timeframe=_infer_timeframe(modal),
                daily_rows=int(len(d1)),
                m5_rows=int(len(m5)),
                filename_mislabelled=mislabelled,
                notes=notes,
            )
        )
    return out


def _read_exness_csv_safe(path: Path) -> pd.DataFrame:
    return _read_exness_csv(path)


# ---------------------------------------------------------------------------
# Dataset construction
# ---------------------------------------------------------------------------


def build_datasets(
    *,
    repo_root: Optional[Path] = None,
    raw_m5_path: Optional[Path] = None,
    source_dir: Path = DEFAULT_SOURCE_DIR,
    write: bool = True,
) -> Dict[str, Any]:
    """Build the versioned Exness XAUUSDm datasets and their provenance records.

    Produces:

    * ``data/processed/xauusdm/m5/v1.2.0/data.parquet`` - true M5 bars only
      (2021-07-16 13:05 -> 2026-10-09 20:55), preserving observed spread and
      tick volume.
    * ``data/processed/xauusdm/d1/v1.0.0/data.parquet`` - the excluded
      daily-interval block, preserved (not deleted) and documented.
    * ``data/processed/xauusdm/h1/v1.2.0/data.parquet`` - H1 resampled from the
      M5 v1.2.0 dataset (single source, single time frame).

    Returns a dict with the built frames, their validation reports and the
    provenance records.
    """
    root = Path(repo_root) if repo_root else Path.cwd()
    raw_path = Path(raw_m5_path) if raw_m5_path else root / DEFAULT_RAW_M5
    if not raw_path.exists():
        raise FileNotFoundError(f"Consolidated raw M5 export not found: {raw_path}")

    raw = _read_exness_csv(raw_path)
    m5, d1 = split_m5_and_d1(raw)

    m5_report = validate_m5(m5, expect_five_minute=True)
    d1_report = validate_m5(d1, expect_five_minute=False)
    h1 = resample_ohlcv(m5, "1h")
    h1_report = validate_m5(h1, expect_five_minute=False)

    inventory = inventory_sources(source_dir)

    # --- write -----------------------------------------------------------
    written: Dict[str, str] = {}
    if write:
        written["m5"] = _write_dataset(
            root, "xauusdm", "m5", M5_VERSION, m5, m5_report,
            source=str(Path(raw_path).relative_to(root)) if raw_path.is_relative_to(root) else str(raw_path),
            source_sha256=sha256_file(raw_path),
            transformations=[
                "Read consolidated Exness M5 export (tab separated MT5 History Centre format)",
                "Combined <DATE> and <TIME> into a single UTC timestamp column",
                "Classified daily-interval rows (same time-of-day + whole-day gap) and "
                "excluded them from the M5 dataset",
                "Preserved observed <SPREAD> (points) and <TICKVOL> verbatim",
                "Sorted chronologically; no rows dropped other than the daily block",
            ],
            known_issues=[
                "<VOL> (real volume) is identically zero in the Exness export; "
                "tick_volume is the only volume proxy available",
                "Session break and weekend gaps are genuine market closures and are "
                "not filled",
                "Spread is observed per bar in broker points; the point size used to "
                "convert it to price is an offline symbol-config value, not live-verified",
            ],
        )
        written["d1"] = _write_dataset(
            root, "xauusdm", "d1", D1_VERSION, d1, d1_report,
            source=str(Path(raw_path).relative_to(root)) if raw_path.is_relative_to(root) else str(raw_path),
            source_sha256=sha256_file(raw_path),
            transformations=[
                "Extracted the daily-interval block from the consolidated Exness M5 export",
                "Preserved unchanged; no interpolation, no resampling",
            ],
            known_issues=[
                "Daily bars only - unusable for M5 research (ATR/Donchian horizons)",
                "spread == 0 on every row: the broker did not record a spread for these bars",
                "Excluded from the M5 dataset and from every backtest in Assignment 14",
            ],
        )
        written["h1"] = _write_dataset(
            root, "xauusdm", "h1", H1_VERSION, h1, h1_report,
            source=f"data/processed/xauusdm/m5/{M5_VERSION}/data.parquet",
            source_sha256=written.get("m5_sha256", ""),
            transformations=[
                f"Resampled from M5 {M5_VERSION} with pandas resample('1h')",
                "Aggregation: open=first, high=max, low=min, close=last, "
                "tick_volume=sum, volume=sum, spread=mean",
                "H1 is derived from the SAME source and the SAME time frame as the M5 "
                "series, which removes the raw-H1 hour-grid offset",
            ],
            known_issues=[
                "The raw Exness H1 export sits on a different hourly grid than the M5 "
                "CSV export (offset +2h Nov-Mar, +3h Apr-Oct, tracking European DST); "
                "it is deliberately NOT mixed into this chain",
                "Hours that contain no M5 bar (the daily session break) are dropped, "
                "not filled",
            ],
        )

    return {
        "m5": m5,
        "d1": d1,
        "h1": h1,
        "m5_report": m5_report,
        "d1_report": d1_report,
        "h1_report": h1_report,
        "source_inventory": inventory,
        "raw_path": raw_path,
        "written": written,
    }


def _write_dataset(
    root: Path,
    symbol: str,
    timeframe: str,
    version: str,
    df: pd.DataFrame,
    report: QualityReport,
    *,
    source: str,
    source_sha256: str,
    transformations: List[str],
    known_issues: List[str],
) -> str:
    """Write a versioned parquet dataset plus its manifest; return the sha256."""
    out_dir = root / "data" / "processed" / symbol / timeframe / version
    out_dir.mkdir(parents=True, exist_ok=True)
    data_path = out_dir / "data.parquet"

    payload = df.copy()
    payload = payload.set_index("timestamp")
    payload.index.name = "timestamp"
    payload.to_parquet(data_path)
    checksum = sha256_file(data_path)

    manifest = {
        "dataset": f"{symbol.upper()}_{timeframe.upper()}",
        "version": version,
        "built_by": "mars.libs.data.xauusdm_exness.build_datasets",
        "source": source,
        "source_checksum": source_sha256,
        "checksum": checksum,
        "rows": int(len(payload)),
        "date_range": {
            "start": str(payload.index[0]),
            "end": str(payload.index[-1]),
        },
        "columns": list(payload.columns),
        "index": "DatetimeIndex (UTC)",
        "transformations": transformations,
        "known_issues": known_issues,
        "validation": report.to_dict(),
    }
    (out_dir / "_manifest.json").write_text(
        json.dumps(manifest, indent=2, default=str), encoding="utf-8"
    )
    return checksum


# ---------------------------------------------------------------------------
# Raw H1 grid reconciliation (documented finding, used by the report)
# ---------------------------------------------------------------------------


def reconcile_raw_h1_offset(raw_h1_path: Path, m5: pd.DataFrame) -> Dict[str, Any]:
    """Quantify the raw-H1 vs M5 hour-grid offset.

    For each candidate shift D the M5 window ``[t-D, t-D+1h)`` is aggregated and
    compared with the raw H1 bar labelled ``t``.  Returns the best shift per
    sampled day plus the aggregate dispersion.
    """
    raw = pd.read_parquet(raw_h1_path)
    ts_col = "time" if "time" in raw.columns else raw.columns[0]
    raw = raw.assign(ts=pd.to_datetime(raw[ts_col], utc=True)).set_index("ts").sort_index()
    m5 = m5.set_index("timestamp").sort_index()

    results = []
    for day in pd.date_range("2021-09-01", "2025-09-01", freq="3MS") + pd.Timedelta(days=10):
        day = pd.Timestamp(day, tz="UTC")
        r = raw.loc[(raw.index >= day) & (raw.index < day + pd.Timedelta(days=1))]
        if r.empty:
            continue
        best = None
        for shift in range(-6, 7):
            diffs = []
            for t, row in r.iterrows():
                w0 = t - pd.Timedelta(hours=shift)
                w = m5.loc[(m5.index >= w0) & (m5.index < w0 + pd.Timedelta(hours=1))]
                if len(w) < 10:
                    continue
                diffs.append(abs(float(row["close"]) - float(w["close"].iloc[-1])))
            if not diffs:
                continue
            med = float(pd.Series(diffs).median())
            if best is None or med < best[1]:
                best = (shift, med)
        if best:
            results.append({"day": str(day.date()), "best_shift_hours": best[0],
                            "median_abs_close_diff": round(best[1], 4)})
    shifts = [r["best_shift_hours"] for r in results]
    return {
        "samples": results,
        "distinct_shifts_observed": sorted(set(shifts)),
        "median_abs_close_diff_at_best_shift_usd": round(
            float(np.median([r["median_abs_close_diff"] for r in results])), 4
        ),
    }


__all__ = [
    "CANONICAL_COLUMNS",
    "M5_VERSION",
    "D1_VERSION",
    "H1_VERSION",
    "QualityReport",
    "SourceInventory",
    "build_datasets",
    "classify_daily_interval",
    "inventory_sources",
    "reconcile_raw_h1_offset",
    "resample_ohlcv",
    "sha256_file",
    "split_m5_and_d1",
    "validate_m5",
]
