"""
Formal research methodology workflow.
 
Idea → Hypothesis → Formal mathematics → Feature engineering →
Historical testing → Walk-forward → Statistical tests →
Risk review → Approval → Production candidate
"""
 
from __future__ import annotations
 
from dataclasses import dataclass, field
from typing import Optional
 
from mars.core.types import HypothesisStatus, ValidationStage
from mars.research.experiment import ExperimentLog, ExperimentRecord
from mars.research.hypothesis import HypothesisStore
 
 
METHODOLOGY_STAGES: tuple[ValidationStage, ...] = (
    ValidationStage.IDEA,
    ValidationStage.HYPOTHESIS,
    ValidationStage.FORMAL_MATHEMATICS,
    ValidationStage.FEATURE_ENGINEERING,
    ValidationStage.HISTORICAL_TESTING,
    ValidationStage.WALK_FORWARD,
    ValidationStage.STATISTICAL_TESTS,
    ValidationStage.RISK_REVIEW,
    ValidationStage.APPROVAL,
    ValidationStage.PRODUCTION_CANDIDATE,
)
 
 
@dataclass
class WorkflowState:
    hypothesis_id: str
    current_stage: ValidationStage = ValidationStage.IDEA
    completed_stages: list[ValidationStage] = field(default_factory=list)
    blocked_reason: Optional[str] = None
 
    def can_advance(self) -> bool:
        return self.blocked_reason is None
 
    def advance(self) -> ValidationStage:
        if not self.can_advance():
            raise RuntimeError(f"Workflow blocked: {self.blocked_reason}")
        idx = METHODOLOGY_STAGES.index(self.current_stage)
        if idx >= len(METHODOLOGY_STAGES) - 1:
            return self.current_stage
        self.completed_stages.append(self.current_stage)
        self.current_stage = METHODOLOGY_STAGES[idx + 1]
        return self.current_stage
 
 
class ResearchWorkflow:
    """
    Enforce stage gates for a hypothesis.
 
    This does not run models — it tracks research process integrity.
    """
 
    def __init__(
        self,
        hypothesis_store: Optional[HypothesisStore] = None,
        experiment_log: Optional[ExperimentLog] = None,
    ) -> None:
        self.hypotheses = hypothesis_store or HypothesisStore()
        self.experiments = experiment_log or ExperimentLog()
        self._states: dict[str, WorkflowState] = {}
 
    def start(self, hypothesis_id: str) -> WorkflowState:
        # ensure hypothesis exists
        self.hypotheses.get(hypothesis_id)
        state = WorkflowState(hypothesis_id=hypothesis_id)
        self._states[hypothesis_id] = state
        self.hypotheses.set_status(hypothesis_id, HypothesisStatus.TESTING)
        return state
 
    def get_state(self, hypothesis_id: str) -> WorkflowState:
        if hypothesis_id not in self._states:
            self._states[hypothesis_id] = WorkflowState(hypothesis_id=hypothesis_id)
        return self._states[hypothesis_id]
 
    def advance(self, hypothesis_id: str) -> WorkflowState:
        state = self.get_state(hypothesis_id)
        state.advance()
        if state.current_stage == ValidationStage.PRODUCTION_CANDIDATE:
            self.hypotheses.set_status(hypothesis_id, HypothesisStatus.ACCEPTED)
        return state
 
    def reject(self, hypothesis_id: str, reason: str) -> None:
        state = self.get_state(hypothesis_id)
        state.blocked_reason = reason
        self.hypotheses.set_status(
            hypothesis_id, HypothesisStatus.REJECTED, notes=reason
        )
 
    def archive(self, hypothesis_id: str) -> None:
        self.hypotheses.set_status(hypothesis_id, HypothesisStatus.ARCHIVED)
 
    def log_experiment(
        self,
        hypothesis_id: str,
        name: str,
        parameters: Optional[dict] = None,
        seed: Optional[int] = None,
    ) -> ExperimentRecord:
        rec = ExperimentRecord(
            hypothesis_id=hypothesis_id,
            name=name,
            parameters=parameters or {},
            seed=seed,
            status="running",
        )
        self.experiments.write(rec)
        return rec