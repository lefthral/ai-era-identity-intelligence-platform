"""Persistence layer: SQLAlchemy-based operational store.

Uses the same schema across all targets (local Postgres, RDS, Cloud SQL).
The repositories expose domain-friendly methods; raw SQL stays inside.
"""

from src.infrastructure.persistence.database import (
    Base,
    get_engine,
    get_session,
    init_db,
)
from src.infrastructure.persistence.repos import (
    AuditLogRepository,
    CaseRepository,
    DecisionRepository,
    StatsRepository,
)

__all__ = [
    "AuditLogRepository",
    "Base",
    "CaseRepository",
    "DecisionRepository",
    "StatsRepository",
    "get_engine",
    "get_session",
    "init_db",
]
