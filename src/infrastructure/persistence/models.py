"""SQLAlchemy ORM models."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.persistence.database import Base


class DecisionRow(Base):
    __tablename__ = "decisions"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    event_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), index=True, nullable=False)
    decision_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, default=datetime.utcnow
    )
    action: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    xgb_score: Mapped[float] = mapped_column(Float, nullable=False)
    rule_score: Mapped[float] = mapped_column(Float, nullable=False)
    final_score: Mapped[float] = mapped_column(Float, nullable=False)
    model_run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    model_stage: Mapped[str] = mapped_column(String(16), nullable=False)
    policy_hash: Mapped[str] = mapped_column(String(32), nullable=False)
    feature_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_names: Mapped[list] = mapped_column(JSON, nullable=False)
    feature_values: Mapped[list] = mapped_column(JSON, nullable=False)
    rule_hits: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    attack_pattern: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    ground_truth_label: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    amount_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    actor_country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    counterparty_country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    actor_account_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    counterparty_account_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )

    case: Mapped[CaseRow | None] = relationship(back_populates="decision", uselist=False)


class CaseRow(Base):
    __tablename__ = "cases"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    decision_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("decisions.id"), index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), index=True, default="open", nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    investigator: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    decision: Mapped[DecisionRow] = relationship(back_populates="case")


class AuditLogRow(Base):
    __tablename__ = "audit_log"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, index=True
    )
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    subject_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), index=True, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    previous_entry_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
