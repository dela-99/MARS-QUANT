"""Project path resolution — independent of caller's working directory."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


def get_project_root() -> Path:
    """Return the repository root (parent of the top-level ``mars`` package)."""
    return Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class ProjectPaths:
    """Canonical paths for data, models, reports, and legacy code."""

    root: Path

    @classmethod
    def from_root(cls, root: Path | None = None) -> "ProjectPaths":
        return cls(root=root or get_project_root())

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def raw_data(self) -> Path:
        return self.data / "raw"

    @property
    def processed_data(self) -> Path:
        return self.data / "processed"

    @property
    def models(self) -> Path:
        return self.root / "models"

    @property
    def reports(self) -> Path:
        return self.root / "reports"

    @property
    def artifacts(self) -> Path:
        return self.root / "artifacts"

    @property
    def legacy(self) -> Path:
        return self.root / "legacy"

    @property
    def notebooks(self) -> Path:
        return self.root / "notebooks"

    @property
    def docs(self) -> Path:
        return self.root / "docs"
