"""Repository pattern over the operational store."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from src.application.schemas import (
    CaseActionRequest,
    CaseResponse,
    StatsResponse,
)
from src.domain.decisions import (
    Decision,
    DecisionAction,
    FeatureSnapshot,
    ModelVersion,
    PolicyVersion,
    RuleHit,
)
from src.infrastructure.persistence.database import session_scope
from src.infrastructure.persistence.models import (
    AuditLogRow,
    CaseRow,
    DecisionRow,
)

logger = logging.getLogger(__name__)


def _ground_truth_value(event: Any) -> str | None:
    label = getattr(event, "ground_truth_label", None)
    return label.value if label is not None else None


def _decision_row_to_response(row: DecisionRow) -> Decision:
    rule_hits = [
        RuleHit(
            rule_id=r.get("rule_id", ""),
            rule_name=r.get("rule_name", ""),
            severity=r.get("severity", "low"),
            reason=r.get("reason", ""),
            evidence=r.get("evidence", {}),
        )
        for r in (row.rule_hits or [])
    ]
    return Decision(
        decision_id=row.id,
        event_id=row.event_id,
        decision_time=row.decision_time,
        action=DecisionAction(row.action),
        xgb_score=row.xgb_score,
        rule_score=row.rule_score,
        final_score=row.final_score,
        model_version=ModelVersion(
            run_id=row.model_run_id or "unknown",
            model_name="identity_intel_xgb",
            stage=row.model_stage or "Unknown",
            algorithm="xgboost",
            trained_at=row.decision_time,
            metrics={},
        ),
        policy_version=PolicyVersion(
            policy_name="default",
            policy_hash=row.policy_hash or "unknown",
            rules_count=10,
            loaded_at=row.decision_time,
        ),
        feature_snapshot=FeatureSnapshot(
            feature_names=row.feature_names or [],
            feature_values=row.feature_values or [],
            computed_at=row.decision_time,
            online_store_version="v1",
        ),
        rule_hits=rule_hits,
        explanation=row.explanation,
    )


class DecisionRepository:
    def insert(self, decision, event: Any) -> UUID:
        with session_scope() as session:
            row = DecisionRow(
                id=decision.decision_id,
                event_id=decision.event_id,
                decision_time=decision.decision_time,
                action=decision.action.value,
                xgb_score=decision.xgb_score,
                rule_score=decision.rule_score,
                final_score=decision.final_score,
                model_run_id=decision.model_version.run_id,
                model_stage=decision.model_version.stage,
                policy_hash=decision.policy_version.policy_hash,
                feature_hash=decision.feature_snapshot.hash(),
                feature_names=decision.feature_snapshot.feature_names,
                feature_values=decision.feature_snapshot.feature_values,
                rule_hits=[r.model_dump() for r in decision.rule_hits],
                explanation=decision.explanation,
                attack_pattern=getattr(event, "attack_pattern", None),
                ground_truth_label=_ground_truth_value(event),
                amount_usd=(
                    float(getattr(event.amount, "value", 0))
                    if getattr(event, "amount", None)
                    else None
                ),
                actor_country=getattr(getattr(event, "actor", None), "country_code", None),
                counterparty_country=getattr(
                    getattr(event, "counterparty", None), "country_code", None
                ),
                actor_account_id=str(getattr(getattr(event, "actor", None), "account_id", ""))
                or None,
                counterparty_account_id=str(
                    getattr(getattr(event, "counterparty", None), "account_id", "")
                )
                or None,
            )
            session.add(row)

            # Auto-open a case for REVIEW or BLOCK actions
            if decision.action.value in ("REVIEW", "BLOCK"):
                case = CaseRow(
                    id=uuid4(),
                    decision_id=row.id,
                    status="open",
                )
                session.add(case)
        return row.id

    def get(self, decision_id: UUID) -> Decision | None:
        with session_scope() as session:
            row = session.get(DecisionRow, decision_id)
            if not row:
                return None
            return _decision_row_to_response(row)

    def list(
        self,
        since: datetime | None = None,
        limit: int = 100,
        action: str | None = None,
    ) -> list[Decision]:
        with session_scope() as session:
            q = session.query(DecisionRow).order_by(DecisionRow.decision_time.desc())
            if since:
                q = q.filter(DecisionRow.decision_time >= since)
            if action:
                q = q.filter(DecisionRow.action == action)
            rows = q.limit(limit).all()
            return [_decision_row_to_response(r) for r in rows]


class CaseRepository:
    def get(self, case_id: UUID) -> CaseResponse | None:
        with session_scope() as session:
            row = session.get(CaseRow, case_id)
            if not row:
                return None
            return CaseResponse(
                case_id=row.id,
                decision_id=row.decision_id,
                status=row.status,
                opened_at=row.opened_at,
                closed_at=row.closed_at,
                investigator=row.investigator,
                notes=row.notes,
            )

    def list(self, status: str | None = None, limit: int = 100) -> list[CaseResponse]:
        with session_scope() as session:
            q = session.query(CaseRow).order_by(CaseRow.opened_at.desc())
            if status:
                q = q.filter(CaseRow.status == status)
            rows = q.limit(limit).all()
            return [
                CaseResponse(
                    case_id=r.id,
                    decision_id=r.decision_id,
                    status=r.status,
                    opened_at=r.opened_at,
                    closed_at=r.closed_at,
                    investigator=r.investigator,
                    notes=r.notes,
                )
                for r in rows
            ]

    def apply_action(self, case_id: UUID, request: CaseActionRequest) -> CaseResponse:
        with session_scope() as session:
            row = session.get(CaseRow, case_id)
            if not row:
                raise ValueError(f"Case {case_id} not found")
            new_status_map = {
                "confirm_fraud": "closed_confirmed_fraud",
                "false_positive": "closed_false_positive",
                "escalate": "closed_escalated",
            }
            row.status = new_status_map[request.action]
            row.investigator = request.investigator
            row.notes = (row.notes or "") + (
                f"\n[{datetime.now(UTC).isoformat()}] {request.investigator}: {request.action} - {request.notes or ''}"
            )
            row.closed_at = datetime.now(UTC)
        return CaseResponse(
            case_id=row.id,
            decision_id=row.decision_id,
            status=row.status,
            opened_at=row.opened_at,
            closed_at=row.closed_at,
            investigator=row.investigator,
            notes=row.notes,
        )


class AuditLogRepository:
    def append(
        self,
        actor: str,
        action_type: str,
        subject_id: UUID,
        payload: dict[str, Any] | None = None,
    ) -> UUID:
        with session_scope() as session:
            row = AuditLogRow(
                actor=actor,
                action_type=action_type,
                subject_id=subject_id,
                payload=payload or {},
            )
            session.add(row)
            return row.id

    def list_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        with session_scope() as session:
            rows = (
                session.query(AuditLogRow).order_by(AuditLogRow.timestamp.desc()).limit(limit).all()
            )
            return [
                {
                    "id": str(r.id),
                    "timestamp": r.timestamp.isoformat(),
                    "actor": r.actor,
                    "action_type": r.action_type,
                    "subject_id": str(r.subject_id),
                    "payload": r.payload,
                }
                for r in rows
            ]

    def list_for_subject(self, subject_id: str) -> list[dict[str, Any]]:
        with session_scope() as session:
            try:
                subj_uuid = UUID(subject_id)
            except ValueError:
                return []
            rows = (
                session.query(AuditLogRow)
                .filter(AuditLogRow.subject_id == subj_uuid)
                .order_by(AuditLogRow.timestamp.asc())
                .all()
            )
            return [
                {
                    "id": str(r.id),
                    "timestamp": r.timestamp.isoformat(),
                    "actor": r.actor,
                    "action_type": r.action_type,
                    "subject_id": str(r.subject_id),
                    "payload": r.payload,
                }
                for r in rows
            ]


class StatsRepository:
    def get_summary(self) -> StatsResponse:
        with session_scope() as session:
            from sqlalchemy import func

            total_decisions = session.query(func.count(DecisionRow.id)).scalar() or 0
            blocked = (
                session.query(func.count(DecisionRow.id))
                .filter(DecisionRow.action == "BLOCK")
                .scalar()
                or 0
            )
            review = (
                session.query(func.count(DecisionRow.id))
                .filter(DecisionRow.action == "REVIEW")
                .scalar()
                or 0
            )
            allow = (
                session.query(func.count(DecisionRow.id))
                .filter(DecisionRow.action == "ALLOW")
                .scalar()
                or 0
            )
            total_cases = session.query(func.count(CaseRow.id)).scalar() or 0
            open_cases = (
                session.query(func.count(CaseRow.id)).filter(CaseRow.status == "open").scalar() or 0
            )
            arup_caught = (
                session.query(func.count(DecisionRow.id))
                .filter(
                    DecisionRow.attack_pattern == "arup",
                    DecisionRow.action.in_(["REVIEW", "BLOCK"]),
                )
                .scalar()
                or 0
            )
            singapore_caught = (
                session.query(func.count(DecisionRow.id))
                .filter(
                    DecisionRow.attack_pattern == "singapore",
                    DecisionRow.action.in_(["REVIEW", "BLOCK"]),
                )
                .scalar()
                or 0
            )
            deepfake_caught = (
                session.query(func.count(DecisionRow.id))
                .filter(
                    DecisionRow.ground_truth_label == "deepfake_attack",
                    DecisionRow.action.in_(["REVIEW", "BLOCK"]),
                )
                .scalar()
                or 0
            )
        return StatsResponse(
            total_events=total_decisions,
            total_decisions=total_decisions,
            total_cases=total_cases,
            open_cases=open_cases,
            blocked_count=blocked,
            review_count=review,
            allow_count=allow,
            block_rate=blocked / total_decisions if total_decisions else 0.0,
            deepfake_attack_caught=deepfake_caught,
            arup_pattern_caught=arup_caught,
            singapore_pattern_caught=singapore_caught,
        )
