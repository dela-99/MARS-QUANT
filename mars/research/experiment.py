"""Experiment logging for reproducible research runs."""
 
from __future__ import annotations
 
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4
 
from pydantic import BaseModel, Field
 
from mars.core.config import DEFAULT_CONFIG
 
 
class ExperimentRecord(BaseModel):
    """Single experiment run metadata."""
 
    experiment_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    hypothesis_id: str
    name: str
    description: str = ""
    dataset_ids: list[str] = Field(default_factory=list)
    feature_versions: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[str] = Field(default_factory=list)
    status: str = "created"  # created | running | completed | failed
    seed: Optional[int] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    notes: str = ""
 
 
class ExperimentLog:
    """Append-only experiment log under research/experiment_logs/."""
 
    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = root or DEFAULT_CONFIG.paths.experiment_logs
        self.root.mkdir(parents=True, exist_ok=True)
 
    def _path(self, experiment_id: str) -> Path:
        return self.root / f"{experiment_id}.json"
 
    def write(self, record: ExperimentRecord) -> Path:
        path = self._path(record.experiment_id)
        path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
        return path
 
    def read(self, experiment_id: str) -> ExperimentRecord:
        path = self._path(experiment_id)
        if not path.exists():
            raise FileNotFoundError(path)
        return ExperimentRecord.model_validate_json(path.read_text(encoding="utf-8"))
 
    def complete(
        self,
        experiment_id: str,
        metrics: dict[str, Any],
        artifacts: Optional[list[str]] = None,
    ) -> ExperimentRecord:
        rec = self.read(experiment_id)
        rec = rec.model_copy(
            update={
                "metrics": metrics,
                "artifacts": artifacts or rec.artifacts,
                "status": "completed",
                "completed_at": datetime.now(timezone.utc),
            }
        )
        self.write(rec)
        return rec
 
    def list_for_hypothesis(self, hypothesis_id: str) -> list[ExperimentRecord]:
        results = []
        for path in sorted(self.root.glob("*.json")):
            try:
                rec = ExperimentRecord.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
            except Exception:
                continue
            if rec.hypothesis_id == hypothesis_id:
                results.append(rec)
        return results