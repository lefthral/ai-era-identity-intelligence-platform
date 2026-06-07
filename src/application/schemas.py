"""API response/request schemas.

These are Pydantic models that flow over the wire via FastAPI. They are
defined in their own module (not in api.py) to avoid circular imports
between the API and the graph client.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from src.domain.decisions import DecisionAction


class RuleHitResponse(BaseModel):
    rule_id: str
    rule_name: str
    severity: str
    reason: str
    evidence: dict[str, Any] = Field(default_factory=dict)


class DecisionResponse(BaseModel):
    decision_id: UUID
    event_id: UUID
    action: DecisionAction
    final_score: float
    xgb_score: float
    rule_score: float
    rule_hits: list[RuleHitResponse]
    model_version_id: str
    policy_version_id: str
    created_at: datetime
    latency_ms: int
    fs_ai_rmf_principle: str
    fs_ai_rmf_evidence: str


class CaseResponse(BaseModel):
    case_id: UUID
    decision: DecisionResponse | None = None
    status: str
    opened_at: datetime
    notes: str | None = None
    related_decision: DecisionResponse | None = None
    decision_id: UUID | None = None
    closed_at: datetime | None = None
    investigator: str | None = None


class CaseActionRequest(BaseModel):
    action: str
    investigator: str
    notes: str | None = None


class GraphNode(BaseModel):
    id: str
    label: str
    type: str
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    source: str
    target: str
    type: str
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class StatsResponse(BaseModel):
    total_events: int
    total_decisions: int
    total_cases: int
    open_cases: int
    blocked_count: int
    review_count: int
    allow_count: int
    block_rate: float
    deepfake_attack_caught: int
    arup_pattern_caught: int
    singapore_pattern_caught: int


class HealthResponse(BaseModel):
    status: str
    components: dict[str, str]
    model_version: str | None = None
    environment: str
    timestamp: datetime


__all__ = [
    "CaseResponse",
    "DecisionResponse",
    "GraphEdge",
    "GraphNode",
    "GraphResponse",
    "HealthResponse",
    "RuleHitResponse",
    "StatsResponse",
]
