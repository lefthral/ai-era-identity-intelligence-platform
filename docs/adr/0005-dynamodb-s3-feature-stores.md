# ADR-0005: DynamoDB for Online Features, S3 for Offline Features

- **Status:** Accepted
- **Date:** 2026-01-15
- **Deciders:** Identity Intel team

## Context

The platform needs both a **low-latency online feature store** (read
during scoring, ~5ms p99) and a **high-throughput offline feature
store** (read during training, batch analytics).

Options for the online store:

1. **DynamoDB** (AWS) / **Firestore** (GCP)
2. **ElastiCache for Redis** / **Memorystore**
3. **RDS Postgres** with a hot table
4. **RocksDB / DuckDB on Lambda local disk**

For the offline store:

1. **S3** (AWS) / **GCS** (GCP) + Parquet
2. **Redshift** / **BigQuery** (columnar)
3. **Glue / Athena** as the query layer

## Decision

- **Online**: DynamoDB single-table, primary key = `entity_id`,
  TTL on a 24h window. AWS equivalent for GCP is Firestore.
- **Offline**: S3 with Parquet, partitioned by `event_time` (yyyy/mm/dd).
  Query layer is Athena.

## Consequences

### Positive

- **Cost**: Both are within AWS free tier for the MVP.
  DynamoDB: 25 GB storage + 25M WCU/RCU per month, forever.
  S3: 5 GB / 12 months; the rest is ~$0.023/GB-month.
- **No ElastiCache cost**: Redis would have been $15-30/month
  even at minimum, and it would have been a separate billing line.
- **Serverless**: no cluster to operate, no patching.
- **Strong consistency for the active row**: DynamoDB's
  strongly-consistent reads give us exactly-once-write semantics
  for the latest features.

### Negative

- **Eventual consistency for the history**: DynamoDB Streams
  ordering is per-shard, not global. For the online store
  (which only needs the latest) this is fine. For history,
  we use S3 + Parquet.
- **Item-size limit**: DynamoDB items are capped at 400 KB.
  Our feature vector is ~2 KB; the counter is fine.
- **No rich query**: DynamoDB only does key-value + secondary
  index. For complex ad-hoc queries ("all events from account
  X in the last 24h where score > 0.8") we go to Athena on S3.
- **No transactions across the two stores**: a failure between
  the online and offline writes leaves them temporarily
  inconsistent. The `feature_snapshot_id` in the audit log
  is the canonical reference; the offline write can be replayed.

### Neutral

- The single-table DynamoDB pattern means a single provisioned
  instance; we don't shard by feature category.

## Alternatives considered

- **Redis**: rejected for cost + operational burden. Also, Redis
  Cluster at the multi-AZ tier is 3x the cost of DynamoDB at our
  scale, and gives no free tier.
- **RDS Postgres with a hot table**: rejected because the read
  latency (5-10ms even with a hot buffer pool) is on the edge
  of our 200ms budget when we add 3-4 sub-50ms hot reads.
- **RocksDB on Lambda**: rejected because state is lost when
  the Lambda container freezes, and we need multi-AZ consistency.

## References

- `terraform/aws/dynamodb.tf` - the two tables
- `terraform/aws/s3.tf` - the feature + model buckets
- `src/infrastructure/adapters/aws/online_features.py` - DDB client
- `src/infrastructure/adapters/aws/offline_features.py` - S3 client
- `src/infrastructure/adapters/interfaces.py` - the contracts
