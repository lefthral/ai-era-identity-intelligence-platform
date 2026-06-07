"""MinIO-backed offline feature store (S3 API)."""

from __future__ import annotations

import io
import logging
import os
from datetime import datetime
from typing import Any

import pandas as pd

from src.infrastructure.adapters.interfaces import OfflineFeatureStore

logger = logging.getLogger(__name__)


class MinIOOfflineFeatureStore(OfflineFeatureStore):
    def __init__(
        self,
        bucket: str = "identity-intel-features",
        endpoint: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
    ):
        self.bucket = bucket
        self.endpoint = endpoint or os.getenv("LOCAL_MINIO_ENDPOINT", "localhost:9000")
        self.access_key = access_key or os.getenv("LOCAL_MINIO_ACCESS_KEY", "localdev")
        self.secret_key = secret_key or os.getenv("LOCAL_MINIO_SECRET_KEY", "localdevpassword")
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            from minio import Minio

            self._client = Minio(
                self.endpoint,
                access_key=self.access_key,
                secret_key=self.secret_key,
                secure=False,
            )
            if not self._client.bucket_exists(self.bucket):
                self._client.make_bucket(self.bucket)
        return self._client

    def write_batch(self, features: list[dict[str, Any]], partition_key: datetime) -> None:
        if not features:
            return
        client = self._ensure_client()
        df = pd.DataFrame(features)
        buf = io.BytesIO()
        df.to_parquet(buf, index=False)
        buf.seek(0)
        key = f"dt={partition_key.strftime('%Y-%m-%d')}/hr={partition_key.strftime('%H')}/features-{int(partition_key.timestamp())}.parquet"
        client.put_object(
            self.bucket,
            key,
            buf,
            length=len(buf.getvalue()),
            content_type="application/octet-stream",
        )

    def read(self, entity_id: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
        client = self._ensure_client()
        prefix = "dt="
        results: list[dict[str, Any]] = []
        for obj in client.list_objects(self.bucket, prefix=prefix, recursive=True):
            try:
                resp = client.get_object(self.bucket, obj.object_name)
                df = pd.read_parquet(io.BytesIO(resp.read()))
                df = df[
                    (df.get("entity_id") == entity_id)
                    & (df.get("event_time") >= start)
                    & (df.get("event_time") <= end)
                ]
                results.extend(df.to_dict("records"))
            except Exception as e:
                logger.warning("Failed to read %s: %s", obj.object_name, e)
        return results
