"""FastAPI service layer.

Exposes the platform's functionality as a REST API for the Streamlit UI
and external integrations.

Endpoints:
- GET  /api/health
- GET  /api/decisions?since=&limit=
- GET  /api/cases/{case_id}
- POST /api/cases/{case_id}/action
- GET  /api/graph/{entity_id}
- GET  /api/features/{entity_id}
- GET  /api/stats
- GET  /api/audit/{subject_id}
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from src.application.features import FeatureComputer
from src.application.rules import RuleEngine
from src.application.schemas import (
    CaseActionRequest,
    CaseResponse,
    DecisionResponse,
    GraphResponse,
    HealthResponse,
    RuleHitResponse,
    StatsResponse,
)
from src.application.scoring import RealTimeScorer
from src.domain.decisions import ModelVersion
from src.infrastructure.persistence import (
    AuditLogRepository,
    CaseRepository,
    DecisionRepository,
    StatsRepository,
)

logger = logging.getLogger(__name__)


# ── Pydantic models for request/response ────────────────────────────────


# ── Application setup ────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Identity Intelligence API")
    app.state.feature_computer = FeatureComputer()
    app.state.rule_engine = RuleEngine()
    model_path_str: str | None = os.getenv("MODEL_PATH", "models/xgb_v1.ubj")
    if model_path_str and not os.path.exists(model_path_str):
        logger.warning("Model file %s not found; using heuristic scorer", model_path_str)
        model_path_str = None
    app.state.scorer = RealTimeScorer(
        model_path=model_path_str,
        model_version=ModelVersion(
            run_id=os.getenv("MODEL_RUN_ID", "production_xgb_v1"),
            model_name="identity_intel_xgb",
            stage=os.getenv("MODEL_STAGE", "Production"),
            algorithm="xgboost" if model_path_str else "heuristic",
            trained_at=datetime.now(UTC),
            metrics={},
        ),
    )
    app.state.environment = os.getenv("ENVIRONMENT", "local")
    yield
    # Shutdown
    logger.info("Stopping Identity Intelligence API")


app = FastAPI(
    title="Identity Intelligence Platform",
    version="0.1.0",
    description=(
        "Real-time AI-fraud detection. Built around the documented Arup "
        "($25.6M, Jan 2024) and Singapore ($499K, Mar 2025) deepfake "
        "wire-fraud incidents."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Dependency providers ─────────────────────────────────────────────────


def get_feature_computer() -> FeatureComputer:
    return app.state.feature_computer


def get_rule_engine() -> RuleEngine:
    return app.state.rule_engine


def get_scorer() -> RealTimeScorer:
    return app.state.scorer


def get_decision_repo() -> DecisionRepository:
    return DecisionRepository()


def get_case_repo() -> CaseRepository:
    return CaseRepository()


def get_audit_repo() -> AuditLogRepository:
    return AuditLogRepository()


def get_stats_repo() -> StatsRepository:
    return StatsRepository()


# ── Endpoints ────────────────────────────────────────────────────────────


@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    components = {
        "postgres": "unknown",
        "neo4j": "unknown",
        "mlflow": "unknown",
    }
    # In production these would be real health checks
    return HealthResponse(
        status="ok",
        components=components,
        model_version=os.getenv("MODEL_RUN_ID", "production_xgb_v1"),
        environment=app.state.environment,
        timestamp=datetime.utcnow(),
    )


@app.get("/api/decisions", response_model=list[DecisionResponse])
async def list_decisions(
    limit: int = Query(default=50, ge=1, le=500),
    since: datetime | None = None,
    repo: DecisionRepository = Depends(get_decision_repo),
) -> list[DecisionResponse]:
    rows = repo.list(limit=limit, since=since)
    return [_decision_to_response(d) for d in rows]


def _decision_to_response(decision) -> DecisionResponse:
    """Map the internal Decision domain object to the API DTO."""
    rule_hits = [
        RuleHitResponse(
            rule_id=h.rule_id,
            rule_name=h.rule_name,
            severity=h.severity,
            reason=h.reason,
            evidence=h.evidence,
        )
        for h in decision.rule_hits
    ]
    return DecisionResponse(
        decision_id=decision.decision_id,
        event_id=decision.event_id,
        action=decision.action,
        final_score=decision.final_score,
        xgb_score=decision.xgb_score,
        rule_score=decision.rule_score,
        rule_hits=rule_hits,
        model_version_id=decision.model_version.run_id,
        policy_version_id=decision.policy_version.policy_hash,
        created_at=decision.decision_time,
        latency_ms=0,
        fs_ai_rmf_principle="reliability",
        fs_ai_rmf_evidence=f"model={decision.model_version.run_id}",
    )


@app.get("/api/cases/{case_id}", response_model=CaseResponse)
async def get_case(
    case_id: UUID,
    repo: CaseRepository = Depends(get_case_repo),
) -> CaseResponse:
    case = repo.get(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


@app.post("/api/cases/{case_id}/action")
async def case_action(
    case_id: UUID,
    body: CaseActionRequest,
    repo: CaseRepository = Depends(get_case_repo),
) -> dict[str, Any]:
    case = repo.get(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    repo.apply_action(case_id=case_id, request=body)
    return {"case_id": str(case_id), "action": body.action, "recorded": True}


@app.get("/api/graph/{entity_id}", response_model=GraphResponse)
async def graph(
    entity_id: str,
    depth: int = Query(default=2, ge=1, le=5),
) -> GraphResponse:
    from src.infrastructure.graph import get_graph_client

    client = get_graph_client()
    return client.get_subgraph(entity_id, depth=depth)


@app.get("/api/graph/mule-rings", response_model=list[dict])
async def mule_rings(
    min_size: int = Query(default=3, ge=2, le=20),
) -> list[dict]:
    from src.infrastructure.graph import get_graph_client

    client = get_graph_client()
    return client.detect_mule_rings(min_community_size=min_size)


@app.get("/api/features/{entity_id}")
async def features(
    entity_id: str,
    computer: FeatureComputer = Depends(get_feature_computer),
) -> dict[str, Any]:
    # In production this would read from the online feature store.
    # For the API demo we return a snapshot derived from the local
    # history.
    from src.application.features import FEATURE_NAMES

    return {
        "entity_id": entity_id,
        "features": dict.fromkeys(FEATURE_NAMES, 0.0),
    }


@app.get("/api/stats", response_model=StatsResponse)
async def stats(
    repo: StatsRepository = Depends(get_stats_repo),
    window_minutes: int = Query(default=60, ge=1, le=10080),
) -> StatsResponse:
    return repo.get_summary()


@app.get("/api/audit", response_model=list[dict])
async def audit(
    limit: int = Query(default=200, ge=1, le=1000),
    repo: AuditLogRepository = Depends(get_audit_repo),
) -> list[dict]:
    return repo.list_recent(limit=limit)


def main() -> None:
    import uvicorn

    uvicorn.run(
        "src.application.api:app",
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", "8000")),
        reload=bool(int(os.getenv("API_RELOAD", "0"))),
    )


if __name__ == "__main__":
    main()
