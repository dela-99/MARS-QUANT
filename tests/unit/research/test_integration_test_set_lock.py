"""Integration test: test set lock enforced through the actual pipeline."""

from __future__ import annotations

from pathlib import Path
import tempfile

import pytest

from mars.research.hypothesis import HypothesisStore
from mars.research.experiment import ExperimentLog, ExperimentRecord
from mars.core.types import HypothesisStatus


def test_test_set_lock_enforced_in_pipeline(tmp_path: Path):
    """
    Integration test: when a hypothesis has test_set_locked=True,
    any attempt to evaluate on test data via the experiment log
    must raise BEFORE touching test data.

    This catches the real bug: someone bypassing the store and
    reading parquet directly, or forgetting to call the guard.
    """
    hypothesis_root = tmp_path / "hypotheses"
    experiment_root = tmp_path / "experiment_logs"
    store = HypothesisStore(root=hypothesis_root)
    exp_log = ExperimentLog(root=experiment_root, hypothesis_root=hypothesis_root)

    # Create a hypothesis and lock its test set
    rec = store.new_template(
        hypothesis_id="HYP-LOCK-TEST",
        title="Locked hypothesis",
        problem_statement="Test set should be locked",
        author="integration-test",
    )
    store.set_status("HYP-LOCK-TEST", HypothesisStatus.TESTING)
    store.lock_test_set("HYP-LOCK-TEST", "EXP-FIRST-001")

    # Now try to start an experiment and complete it with evaluated_on_test=True
    # This should raise because test set is locked
    exp_rec = ExperimentRecord(
        hypothesis_id="HYP-LOCK-TEST",
        name="EXP-SHOULD-FAIL",
        parameters={},
    )
    exp_log.write(exp_rec)

    with pytest.raises(RuntimeError, match="Test set.*locked.*HYP-LOCK-TEST"):
        exp_log.complete(
            exp_rec.experiment_id,
            metrics={"accuracy": 0.5},
            artifacts=[],
            evaluated_on_test=True,
        )


def test_test_set_unlocked_allows_evaluation(tmp_path: Path):
    """Sanity check: unlocked hypothesis allows test evaluation."""
    hypothesis_root = tmp_path / "hypotheses2"
    experiment_root = tmp_path / "experiment_logs2"
    store = HypothesisStore(root=hypothesis_root)
    exp_log = ExperimentLog(root=experiment_root, hypothesis_root=hypothesis_root)

    rec = store.new_template(
        hypothesis_id="HYP-UNLOCKED-TEST",
        title="Unlocked hypothesis",
        problem_statement="Test set is available",
        author="integration-test",
    )
    store.set_status("HYP-UNLOCKED-TEST", HypothesisStatus.TESTING)

    exp_rec = ExperimentRecord(
        hypothesis_id="HYP-UNLOCKED-TEST",
        name="EXP-SHOULD-WORK",
        parameters={},
    )
    exp_log.write(exp_rec)

    # This should succeed
    completed = exp_log.complete(
        exp_rec.experiment_id,
        metrics={"accuracy": 0.55},
        artifacts=[],
        evaluated_on_test=True,
    )
    assert completed.status == "completed"
    assert completed.metrics["accuracy"] == 0.55

    # Now test set should be locked
    with pytest.raises(RuntimeError, match="Test set locked for HYP-UNLOCKED-TEST"):
        exp_log.assert_can_evaluate_on_test("HYP-UNLOCKED-TEST")