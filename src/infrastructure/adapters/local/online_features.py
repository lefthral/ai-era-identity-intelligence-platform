"""PostgreSQL-backed online feature store.

In production this would be DynamoDB (AWS) or Firestore (GCP). For local
dev we use a PostgreSQL table with a TTL column.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta

from src.infrastructure.adapters.interfaces import OnlineFeatureStore

logger = logging.getLogger(__name__)


class PostgresOnlineFeatureStore(OnlineFeatureStore):
    def __init__(self, dsn: str | None = None):
        self.dsn = dsn or os.getenv(
            "LOCAL_POSTGRES_DSN",
            "postgresql://identity:localdevpassword@localhost:5432/identity_intel",
        )
        self._ensure_table()

    def _conn(self):
        import psycopg2

        return psycopg2.connect(self.dsn)

    def _ensure_table(self) -> None:
        try:
            with self._conn() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS online_features (
                        entity_id TEXT PRIMARY KEY,
                        features JSONB NOT NULL,
                        expires_at TIMESTAMPTZ NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_online_features_expires ON online_features(expires_at)"
                )
                conn.commit()
        except Exception as e:
            logger.warning("Could not ensure online_features table: %s", e)

    def put(self, entity_id: str, features: dict[str, float], ttl_seconds: int = 86400) -> None:
        expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO online_features (entity_id, features, expires_at, updated_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (entity_id) DO UPDATE
                SET features = EXCLUDED.features,
                    expires_at = EXCLUDED.expires_at,
                    updated_at = NOW()
            """,
                (entity_id, json.dumps(features), expires_at),
            )
            conn.commit()

    def get(self, entity_id: str) -> dict[str, float] | None:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT features FROM online_features
                WHERE entity_id = %s AND expires_at > NOW()
            """,
                (entity_id,),
            )
            row = cur.fetchone()
            return json.loads(row[0]) if row else None
