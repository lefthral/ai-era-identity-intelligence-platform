"""SQLAlchemy database setup."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


def _default_dsn() -> str:
    env = os.getenv("ENVIRONMENT", "local").lower()
    if env == "aws":
        host = os.getenv("AWS_RDS_ENDPOINT")
        return f"postgresql://{os.getenv('AWS_RDS_USER')}:{os.getenv('AWS_RDS_PASSWORD')}@{host}:5432/{os.getenv('AWS_RDS_DB', 'identity_intel')}"
    if env == "gcp":
        # Cloud SQL uses a Unix socket; the application would inject the DSN
        return os.getenv(
            "GCP_CLOUD_SQL_DSN", "postgresql://identity:local@localhost/identity_intel"
        )
    return os.getenv(
        "LOCAL_POSTGRES_DSN",
        "postgresql://identity:localdevpassword@localhost:5432/identity_intel",
    )


_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(_default_dsn(), pool_pre_ping=True, future=True)
    return _engine


def get_session() -> Session:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionLocal()


@contextmanager
def session_scope() -> Iterator[Session]:
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    from src.infrastructure.persistence import models  # noqa: F401

    Base.metadata.create_all(bind=get_engine())
    logger.info("Database initialized")
