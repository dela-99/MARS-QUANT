"""
Hypothesis records and persistence.

Every hypothesis has:
    Unique ID, problem statement, mathematical formulation,
    required datasets, features, experiments, statistical validation,
    and status (Draft / Testing / Accepted / Rejected / Archived).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from mars.core.config import DEFAULT_CONFIG
from mars.core.schemas import HypothesisRecord
from mars.core.types import HypothesisStatus


def _hypothesis_path(hypothesis_id: str, root: Optional[Path] = None) -> Path:
    base = root or DEFAULT_CONFIG.paths.hypotheses
    return base / f"{hypothesis_id}.json"


def save_hypothesis(
    record: HypothesisRecord,
    root: Optional[Path] = None,
) -> Path:
    """Persist a hypothesis record as JSON under research/hypotheses/."""
    path = _hypothesis_path(record.hypothesis_id, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    updated = record.model_copy(
        update={"updated_at": datetime.now(timezone.utc)}
    )
    path.write_text(updated.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_hypothesis(
    hypothesis_id: str,
    root: Optional[Path] = None,
) -> HypothesisRecord:
    path = _hypothesis_path(hypothesis_id, root)
    if not path.exists():
        raise FileNotFoundError(f"Hypothesis not found: {path}")
    return HypothesisRecord.model_validate_json(path.read_text(encoding="utf-8"))


class HypothesisStore:
    """CRUD + status transitions for research hypotheses."""

    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = root or DEFAULT_CONFIG.paths.hypotheses
        self.root.mkdir(parents=True, exist_ok=True)

    def create(self, record: HypothesisRecord) -> Path:
        path = _hypothesis_path(record.hypothesis_id, self.root)
        if path.exists():
            raise FileExistsError(f"Hypothesis already exists: {record.hypothesis_id}")
        return save_hypothesis(record, self.root)

    def get(self, hypothesis_id: str) -> HypothesisRecord:
        return load_hypothesis(hypothesis_id, self.root)

    def update(self, record: HypothesisRecord) -> Path:
        return save_hypothesis(record, self.root)

    def set_status(
        self,
        hypothesis_id: str,
        status: HypothesisStatus,
        notes: Optional[str] = None,
    ) -> HypothesisRecord:
        rec = self.get(hypothesis_id)
        updates: dict = {"status": status}
        if notes:
            updates["notes"] = (rec.notes + "\n" + notes).strip() if rec.notes else notes
        rec = rec.model_copy(update=updates)
        self.update(rec)
        return rec

    def lock_test_set(
        self,
        hypothesis_id: str,
        experiment_id: str,
    ) -> HypothesisRecord:
        """Lock the test set for a hypothesis — called when an experiment first evaluates on test data."""
        rec = self.get(hypothesis_id)
        if rec.test_set_locked:
            raise RuntimeError(
                f"Test set already locked for {hypothesis_id} "
                f"by experiment {rec.test_set_locked_by_experiment} at {rec.test_set_locked_at}. "
                f"Further test-set evaluation is forbidden."
            )
        rec = rec.model_copy(
            update={
                "test_set_locked": True,
                "test_set_locked_at": datetime.now(timezone.utc),
                "test_set_locked_by_experiment": experiment_id,
            }
        )
        self.update(rec)
        return rec

    def assert_test_set_unlocked(self, hypothesis_id: str) -> None:
        """Raise if the test set is already locked for this hypothesis."""
        rec = self.get(hypothesis_id)
        if rec.test_set_locked:
            raise RuntimeError(
                f"Test set locked for {hypothesis_id} "
                f"by experiment {rec.test_set_locked_by_experiment} at {rec.test_set_locked_at}. "
                f"Use validation splits only (purged CV, walk-forward)."
            )

    def list(
        self,
        status: Optional[HypothesisStatus] = None,
    ) -> list[HypothesisRecord]:
        records: list[HypothesisRecord] = []
        for path in sorted(self.root.glob("*.json")):
            try:
                rec = HypothesisRecord.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
            except Exception:
                continue
            if status is None or rec.status == status:
                records.append(rec)
        return records

    def new_template(
        self,
        hypothesis_id: str,
        title: str,
        problem_statement: str,
        author: str = "",
    ) -> HypothesisRecord:
        """Create a draft hypothesis with methodology placeholders."""
        rec = HypothesisRecord(
            hypothesis_id=hypothesis_id,
            title=title,
            problem_statement=problem_statement,
            mathematical_formulation="TODO: formal math",
            required_datasets=[],
            required_features=[],
            experiments=[],
            statistical_validation=[
                "sharpe",
                "sortino",
                "calmar",
                "max_drawdown",
                "bootstrap_ci",
                "information_coefficient",
                "purged_cv",
                "walk_forward",
                "out_of_sample",
            ],
            status=HypothesisStatus.DRAFT,
            author=author,
        )
        self.create(rec)
        return rec