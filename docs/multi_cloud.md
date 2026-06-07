# Multi-Cloud Architecture: AWS Primary, GCP Portable

The Identity Intelligence Platform is designed for **cloud-agnostic
business logic** with **target-specific adapters**. This document
explains the boundary and the trade-offs.

## The Boundary

```
+----------------------------------------------------------+
|  domain/        entities, events, decisions (Pydantic)   |
|                 100% cloud-agnostic                       |
+----------------------------------------------------------+
                          |
                          v
+----------------------------------------------------------+
|  application/    features, rules, scoring, api, worker   |
|                 depends only on domain/                  |
|                 100% cloud-agnostic                       |
+----------------------------------------------------------+
                          |
                          v
+----------------------------------------------------------+
|  infrastructure/adapters/interfaces.py                    |
|    EventPublisher, EventConsumer, OfflineFeatureStore,    |
|    OnlineFeatureStore, OperationalStore, ModelRegistry    |
|  100% cloud-agnostic (Python ABCs)                        |
+----------------------------------------------------------+
                          |
       +------------------+------------------+
       v                                     v
+-----------------------+         +------------------------+
| infrastructure/       |         | infrastructure/        |
|   adapters/local/     |         |   adapters/aws/        |
|   adapters/gcp/       |         | (boto3)                |
| (google-cloud-sdk)    |         +------------------------+
+-----------------------+
```

**The contract**: code under `src/domain/` and `src/application/` MUST
NOT import boto3, google.cloud, or any cloud SDK. The factory in
`src/infrastructure/adapters/factory.py` is the only place where the
choice of cloud is made.

## AWS Mapping

| Component | AWS Service | Free-Tier Limit |
|-----------|-------------|-----------------|
| Event spine | Kinesis Data Streams | 1M PUTs/month |
| Stream consumer | Lambda | 1M invocations/month |
| Offline feature store | S3 + Parquet | 5 GB / 12 months |
| Online feature store | DynamoDB | 25 GB + 25M reads/writes |
| Operational store | RDS Postgres (db.t3.micro) | 750 hrs / 12 months |
| Graph DB | Neo4j Aura free tier | 1 instance, 200K nodes |
| Model registry + tracking | MLflow on EC2 t3.micro | 750 hrs / 12 months |
| Batch / ETL | Lambda + S3 | 1M invocations/month |
| Orchestration | Step Functions (optional) | 4K state transitions/month |
| Secrets | Secrets Manager | 30-day rotation; first secret free |

## GCP Equivalent

| Component | GCP Service | Free-Tier Limit |
|-----------|-------------|-----------------|
| Event spine | Pub/Sub | 10 GB/month |
| Stream consumer | Cloud Run | 2M invocations/month |
| Offline feature store | Cloud Storage | 5 GB / 12 months |
| Online feature store | Firestore | 1 GB + 50K reads/20K writes |
| Operational store | Cloud SQL Postgres (db-f1-micro) | 750 hrs / 12 months |
| Graph DB | Neo4j Aura (cloud-agnostic) | same as above |
| Model registry + tracking | Vertex AI Experiments | free tier |
| Batch / ETL | Cloud Functions | 2M invocations/month |
| Orchestration | Cloud Workflows | 5K steps/month |
| Secrets | Secret Manager | 6 active versions free |

## Why This Matters for Hiring

Banking clients often have **a primary cloud and a portability
requirement**. Showing that you:

1. Isolated cloud SDKs to an adapter layer
2. Wrote Terraform for two different clouds
3. Have a factory that selects the right adapter at runtime

…directly addresses what a senior data engineering or platform
architect interviewer is screening for.

## Deployment Trade-offs

| Concern | AWS Choice | GCP Choice | Rationale |
|---------|-----------|-----------|-----------|
| Cost ceiling | Kinesis + Lambda | Pub/Sub + Cloud Run | Both are ~$0 within free tier; managed >> self-hosted |
| Latency p99 | Kinesis ~70ms | Pub/Sub ~100ms | Kinesis is slightly faster |
| Min-heap ops | 1 (DDB) | 1 (Firestore) | Both eliminate Redis/EVCache cost |
| Lock-in | Moderate (Kinesis, DDB) | Moderate (Pub/Sub, Firestore) | The adapter pattern lets you swap |
| Local dev | Redpanda (Kinesis) | Redpanda (Pub/Sub) | Same image, both Kafka-compatible |

## When to Use This Pattern

- You expect to be asked "can this run on Azure?" in an interview
- Your client has an "AWS primary, GCP fallback" multi-cloud policy
- You want to show that you understand adapter/port patterns

## When NOT to Use This Pattern

- You have <2 weeks to ship and only one cloud is needed
- Your business logic is tightly coupled to a cloud-native feature
  (e.g., KCL, BigQuery ML)
- You don't actually intend to maintain both deployments
