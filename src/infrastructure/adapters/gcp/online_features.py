"""Firestore-backed online feature store (free tier: 1GB)."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta

from src.infrastructure.adapters.interfaces import OnlineFeatureStore

logger = logging.getLogger(__name__)


class FirestoreOnlineFeatureStore(OnlineFeatureStore):
    def __init__(self, collection: str | None = None):
        self.collection = collection or os.getenv("GCP_FIRESTORE_COLLECTION", "online_features")
        self._db = None

    def _ensure_db(self):
        if self._db is None:
            from google.cloud import firestore

            self._db = firestore.Client()
        return self._db

    def put(self, entity_id: str, features: dict[str, float], ttl_seconds: int = 86400) -> None:
        db = self._ensure_db()
        expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        db.collection(self.collection).document(entity_id).set(
            {
                "features": features,
                "expires_at": expires_at,
            }
        )

    def get(self, entity_id: str) -> dict[str, float] | None:
        db = self._ensure_db()
        doc = db.collection(self.collection).document(entity_id).get()
        if not doc.exists:
            return None
        data = doc.to_dict()
        expires_at = data.get("expires_at")
        if expires_at and expires_at < datetime.utcnow():
            return None
        return data.get("features")
