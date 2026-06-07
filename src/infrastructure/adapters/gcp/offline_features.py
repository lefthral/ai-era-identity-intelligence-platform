"""GCS-backed offline feature store (free tier: 5GB, 12 months)."""

from __future__ import annotations

import io
import logging
import os
from datetime import datetime
from typing import Any

import pandas as pd

from src.infrastructure.adapters.interfaces import OfflineFeatureStore

logger = logging.getLogger(__name__)


class GCSOfflineFeatureStore(OfflineFeatureStore):
    def __init__(self, bucket: str | None = None):
        self.bucket = bucket or os.getenv("GCP_GCS_BUCKET", "identity-intel-features")
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            from google.cloud import storage

            self._client = storage.Client()
        return self._client

    def write_batch(self, features: list[dict[str, Any]], partition_key: datetime) -> None:
        if not features:
            return
        client = self._ensure_client()
        bucket = client.bucket(self.bucket)
        df = pd.DataFrame(features)
        buf = io.BytesIO()
        df.to_parquet(buf, index=False)
        buf.seek(0)
        key = f"dt={partition_key.strftime('%Y-%m-%d')}/hr={partition_key.strftime('%H')}/features-{int(partition_key.timestamp())}.parquet"
        blob = bucket.blob(key)
        blob.upload_from_file(buf, content_type="application/octet-stream")

    def read(self, entity_id: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
        client = self._ensure_client()
        bucket = client.bucket(self.bucket)
        blobs = list(bucket.list_blobs(prefix="dt="))
        results: list[dict[str, Any]] = []
        for blob in blobs:
            try:
                df = pd.read_parquet(io.BytesIO(blob.download_as_bytes()))
                df = df[df.get("entity_id") == entity_id]
                results.extend(df.to_dict("records"))
            except Exception as e:
                logger.warning("Failed to read %s: %s", blob.name, e)
        return results
