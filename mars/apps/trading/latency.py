"""UTC timestamp and derived-latency helpers for the live trading pipeline.

Raw timestamps remain the audit source of truth.  Durations are intentionally
computed at read time so corrected broker/audit timestamps are reflected
without a second stored representation.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

import pandas as pd


LATENCY_FIELDS = (
    "movement_detected_at",
    "signal_generated_at",
    "risk_approved_at",
    "order_submitted_at",
    "order_filled_at",
)


def utc_now_iso() -> str:
    """Return an offset-aware UTC ISO-8601 timestamp for audit writes."""
    return datetime.now(timezone.utc).isoformat()


def utc_iso(value: Any) -> str | None:
    """Normalise a datetime-like value to the audit database's UTC format."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp):
        return None
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    return timestamp.isoformat()


def derive_latency_metrics(raw_timestamps: Mapping[str, Any]) -> dict[str, float | None]:
    """Compute pipeline durations in milliseconds from raw timestamp fields.

    A metric is ``None`` when either required event did not occur (for example,
    a risk-rejected signal has no broker submission or fill).
    """
    parsed: dict[str, pd.Timestamp | None] = {}
    for field in LATENCY_FIELDS:
        value = raw_timestamps.get(field)
        timestamp = pd.to_datetime(value, utc=True, errors="coerce")
        parsed[field] = None if pd.isna(timestamp) else timestamp

    def elapsed_ms(start: str, end: str) -> float | None:
        start_at = parsed[start]
        end_at = parsed[end]
        if start_at is None or end_at is None:
            return None
        return (end_at - start_at).total_seconds() * 1000.0

    return {
        "detection_latency_ms": elapsed_ms("movement_detected_at", "signal_generated_at"),
        "signal_latency_ms": elapsed_ms("signal_generated_at", "risk_approved_at"),
        "execution_latency_ms": elapsed_ms("order_submitted_at", "order_filled_at"),
        "total_latency_ms": elapsed_ms("movement_detected_at", "order_filled_at"),
    }


def format_latency_ms(value: float | None) -> str:
    """Render a nullable millisecond duration compactly for the dashboard."""
    if value is None or pd.isna(value):
        return "—"
    if abs(value) < 1_000:
        return f"{value:.0f} ms"
    return f"{value / 1_000:.3f} s"
