"""
Dataset fingerprinting for reproducibility.
 
A fingerprint is a content-addressable hash of the canonical dataset.
Two datasets with the same fingerprint are considered identical for research.
"""
 
from __future__ import annotations
 
import hashlib
import json
from datetime import datetime, timezone
from typing import Optional
 
import numpy as np
import pandas as pd
 
from mars.core.schemas import DatasetFingerprint
 
 
def _canonical_bytes(df: pd.DataFrame) -> bytes:
    """
    Serialize a DataFrame into a deterministic byte stream.
 
    Rules:
        - sort by index if DatetimeIndex
        - columns sorted lexicographically for hash stability of column order
        - float values rounded to 10 decimal places before hashing
        - use parquet in-memory via pyarrow when available, else CSV fallback
    """
    frame = df.copy()
    if isinstance(frame.index, pd.DatetimeIndex):
        frame = frame.sort_index()
    # Reset index so it participates in the hash
    frame = frame.reset_index()
    frame = frame.reindex(sorted(frame.columns), axis=1)
 
    for col in frame.select_dtypes(include=[np.floating]).columns:
        frame[col] = frame[col].round(10)
 
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
        import io
 
        table = pa.Table.from_pandas(frame, preserve_index=False)
        buf = io.BytesIO()
        pq.write_table(table, buf, compression="none")
        return buf.getvalue()
    except Exception:
        return frame.to_csv(index=False).encode("utf-8")
 
 
def compute_fingerprint(
    df: pd.DataFrame,
    algorithm: str = "sha256",
) -> DatasetFingerprint:
    """Compute a content fingerprint for ``df``."""
    raw = _canonical_bytes(df)
    h = hashlib.new(algorithm)
    h.update(raw)
    digest = h.hexdigest()
 
    columns = list(df.columns) if not isinstance(df.index, pd.RangeIndex) else list(df.columns)
    if isinstance(df.index, pd.DatetimeIndex) or df.index.name is not None:
        # include index name in column list for transparency
        idx_name = df.index.name or "index"
        column_names = [str(idx_name)] + [str(c) for c in df.columns]
    else:
        column_names = [str(c) for c in df.columns]
 
    return DatasetFingerprint(
        algorithm=algorithm,
        digest=digest,
        row_count=len(df),
        column_names=column_names,
        created_at=datetime.now(timezone.utc),
    )
 
 
def fingerprint_to_metadata(
    fingerprint: DatasetFingerprint,
    extra: Optional[dict] = None,
) -> dict:
    """Serialize fingerprint for sidecar JSON."""
    payload = fingerprint.model_dump(mode="json")
    if extra:
        payload["extra"] = extra
    return payload
 
 
def write_fingerprint_sidecar(path: str | bytes, fingerprint: DatasetFingerprint) -> None:
    """Write ``{path}.fingerprint.json`` next to a parquet file."""
    from pathlib import Path
 
    p = Path(str(path))
    sidecar = p.with_suffix(p.suffix + ".fingerprint.json")
    sidecar.write_text(
        json.dumps(fingerprint.model_dump(mode="json"), indent=2, default=str),
        encoding="utf-8",
    )