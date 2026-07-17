"""Text report writers for experiment results."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional


def write_text_report(
    path: str | Path,
    sections: Iterable[str],
    *,
    title: str = "M.A.R.S. Experiment Report",
) -> Path:
    """Write a plain-text multi-section report."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: List[str] = [
        f"=== {title} ===",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]
    for section in sections:
        lines.append(section.rstrip())
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
