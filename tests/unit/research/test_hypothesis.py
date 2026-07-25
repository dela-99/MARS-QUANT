"""Tests for hypothesis store and workflow."""
 
from __future__ import annotations
 
from pathlib import Path
 
from mars.core.types import HypothesisStatus, ValidationStage
from mars.research.hypothesis import HypothesisStore
from mars.research.workflow import ResearchWorkflow
 
 
def test_hypothesis_lifecycle(tmp_path: Path):
    store = HypothesisStore(root=tmp_path)
    rec = store.new_template(
        hypothesis_id="HYP-TEST-001",
        title="Test hypothesis",
        problem_statement="Does X predict Y?",
        author="tester",
    )
    assert rec.status == HypothesisStatus.DRAFT
    loaded = store.get("HYP-TEST-001")
    assert loaded.title == "Test hypothesis"
 
    store.set_status("HYP-TEST-001", HypothesisStatus.TESTING)
    assert store.get("HYP-TEST-001").status == HypothesisStatus.TESTING
 
 
def test_workflow_advance(tmp_path: Path):
    store = HypothesisStore(root=tmp_path)
    store.new_template(
        hypothesis_id="HYP-WF-001",
        title="WF",
        problem_statement="p",
    )
    wf = ResearchWorkflow(hypothesis_store=store)
    state = wf.start("HYP-WF-001")
    assert state.current_stage == ValidationStage.IDEA
    state = wf.advance("HYP-WF-001")
    assert state.current_stage == ValidationStage.HYPOTHESIS
    assert store.get("HYP-WF-001").status == HypothesisStatus.TESTING