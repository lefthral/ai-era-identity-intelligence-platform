"""S3-backed offline feature store (free tier: 5GB, 12 months)."""

from __future__ import annotations

import io
import logging
import os
from datetime import datetime
from typing import Any

import pandas as pd

from src.infrastructure.adapters.interfaces import OfflineFeatureStore

logger = logging.getLogger(__name__)


class S3OfflineFeatureStore(OfflineFeatureStore):
    def __init__(self, bucket: str | None = None, region: str | None = None):
        self.bucket = bucket or os.getenv("AWS_S3_BUCKET", "identity-intel-features")
        self.region = region or os.getenv("AWS_REGION", "us-east-1")
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            import boto3

            self._client = boto3.client("s3", region_name=self.region)
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
        client.put_object(Bucket=self.bucket, Key=key, Body=buf.getvalue())

    def read(self, entity_id: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
        client = self._ensure_client()
        paginator = client.get_paginator("list_objects_v2")
        results: list[dict[str, Any]] = []
        for page in paginator.paginate(Bucket=self.bucket, Prefix="dt="):
            for obj in page.get("Contents", []):
                try:
                    resp = client.get_object(Bucket=self.bucket, Key=obj["Key"])
                    df = pd.read_parquet(io.BytesIO(resp["Body"].read()))
                    df = df[(df.get("entity_id") == entity_id)]
                    results.extend(df.to_dict("records"))
                except Exception as e:
                    logger.warning("Failed to read %s: %s", obj["Key"], e)
        return results
