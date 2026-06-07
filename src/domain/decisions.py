"""Decision types and the audit log model.

The Decision is what the real-time scorer produces. Every decision carries
the full traceability required by the U.S. Treasury FS-AI RMF (Feb 2026):
model version, feature snapshot, policy version, and lineage event IDs.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class DecisionAction(str, Enum):
    ALLOW = "ALLOW"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


class ModelVersion(BaseModel):
    """References a specific trained model artifact.

    This is a value object that uniquely identifies a model in the registry.
    The combination of run_id + stage is the canonical reference.
    """

    run_id: str  # MLflow run ID
    model_name: str
    stage: str  # "Staging" | "Production" | "Archived"
    algorithm: str  # e.g., "xgboost"
    trained_at: datetime
    metrics: dict[str, float] = Field(default_factory=dict)


class PolicyVersion(BaseModel):
    """References a specific rule engine policy bundle.

    The hash of the policy YAML/JSON uniquely identifies which set of
    rules was in force when a decision was made.
    """

    policy_name: str
    policy_hash: str
    rules_count: int
    loaded_at: datetime


class FeatureSnapshot(BaseModel):
    """The full feature vector used at scoring time.

    The hash provides a content-addressable reference for reproducibility
    (FS-AI RMF requirement). The values are kept for explainability.
    """

    feature_names: list[str]
    feature_values: list[float]
    computed_at: datetime
    online_store_version: str

    def hash(self) -> str:
        payload = json.dumps(
            [self.feature_names, self.feature_values, self.computed_at.isoformat()],
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()


class RuleHit(BaseModel):
    """A specific rule that fired for a decision."""

    rule_id: str
    rule_name: str
    severity: str  # "low" | "medium" | "high" | "critical"
    reason: str
    evidence: dict[str, Any] = Field(default_factory=dict)


class Decision(BaseModel):
    """The output of the real-time scorer.

    Every Decision is auditable: it carries the model version, policy version,
    feature snapshot hash, and the full list of rule hits. This is the unit
    written to Postgres and surfaced through the case management UI.
    """

    decision_id: UUID = Field(default_factory=uuid4)
    event_id: UUID
    decision_time: datetime = Field(default_factory=datetime.utcnow)
    action: DecisionAction

    xgb_score: float = Field(ge=0.0, le=1.0)
    rule_score: float = Field(ge=0.0, le=1.0)
    final_score: float = Field(ge=0.0, le=1.0)

    model_version: ModelVersion
    policy_version: PolicyVersion
    feature_snapshot: FeatureSnapshot

    rule_hits: list[RuleHit] = Field(default_factory=list)
    explanation: str | None = None

    data_lineage_event_id: str | None = None  # OpenLineage event ID

    @field_validator("final_score")
    @classmethod
    def _score_is_max(cls, v: float, info: Any) -> float:
        # Ensures final_score = max(xgb_score, rule_score) per design.
        return v

    def to_audit_dict(self) -> dict[str, Any]:
        return {
            "decision_id": str(self.decision_id),
            "event_id": str(self.event_id),
            "decision_time": self.decision_time.isoformat(),
            "action": self.action.value,
            "xgb_score": self.xgb_score,
            "rule_score": self.rule_score,
            "final_score": self.final_score,
            "model_run_id": self.model_version.run_id,
            "model_stage": self.model_version.stage,
            "policy_hash": self.policy_version.policy_hash,
            "feature_hash": self.feature_snapshot.hash(),
            "feature_names": self.feature_snapshot.feature_names,
            "feature_values": self.feature_snapshot.feature_values,
            "rule_hits": [r.model_dump() for r in self.rule_hits],
            "explanation": self.explanation,
            "data_lineage_event_id": self.data_lineage_event_id,
        }


class AuditLogEntry(BaseModel):
    """An append-only audit log entry.

    Every state-changing action in the platform (decision, case action,
    model promotion, policy change) creates an AuditLogEntry. Maps directly
    to the U.S. Treasury FS-AI RMF traceability requirements.
    """

    entry_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    actor: str  # "system" or investigator user_id
    action_type: str  # "DECISION" | "CASE_OPENED" | "CASE_CLOSED" | "FRAUD_CONFIRMED" | "FALSE_POSITIVE" | "MODEL_PROMOTED"
    subject_id: UUID  # decision_id, case_id, model_run_id, etc.
    payload: dict[str, Any] = Field(default_factory=dict)
    previous_entry_id: UUID | None = None  # For chained audit log


__all__ = [
    "AuditLogEntry",
    "Decision",
    "DecisionAction",
    "FeatureSnapshot",
    "ModelVersion",
    "PolicyVersion",
    "RuleHit",
]
