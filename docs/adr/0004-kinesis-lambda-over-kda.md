# ADR-0004: Kinesis + Lambda Over Kinesis + KDA (Managed Flink)

- **Status:** Accepted
- **Date:** 2026-01-15
- **Deciders:** Identity Intel team

## Context

The real-time event spine needs to feed three Lambda-equivalent
consumers (feature computer, graph updater, scorer) plus optional
archive. Options considered:

1. **Kinesis Data Streams + Lambda** (event source mappings)
2. **Kinesis Data Streams + KDA (Managed Flink / Apache Flink)**
3. **MSK (Managed Kafka) + Kafka Streams**
4. **Self-hosted Kafka + custom consumer**

## Decision

Use **Kinesis + Lambda** for the MVP.

- One Kinesis stream (`identity-intel-events`)
- Three Lambda functions, each with an event source mapping
- One KCL-style polling consumer (`KinesisPollingConsumer`) for the
  long-lived worker entry point (used in environments where Lambda
  is not preferred, e.g., on EC2 t3.micro in the free-tier deploy)

## Consequences

### Positive

- **Cost**: Kinesis free tier = 1M PUTs/month; Lambda free tier =
  1M invocations/month. Within budget for any reasonable MVP load.
- **No JVM**: Python-native; faster iteration; smaller Lambda zip.
- **Auto-scaling**: Lambda concurrency scales with shard count.
- **No Zookeeper**: no MSK control-plane burden.
- **15-minute Lambda timeout**: adequate for the worst-case
  per-event compute (~50ms p99, leaving 99.97% of the budget free).

### Negative

- **15-minute hard cap**: any single Lambda invocation can run at
  most 15 minutes. Per-event processing fits; per-batch does not.
- **At-least-once delivery**: a Lambda crash after work but before
  the implicit commit causes a redelivery. The application must
  be idempotent (the `decision_id` UUID v4 + UPSERT on the
  `decisions` table ensures this).
- **Single-region**: Kinesis is regional; multi-region requires
  cross-region replication or a different design.

### Neutral

- Kinesis has a hard ceiling of 1,000 shards per stream. At
  1 MB/s per shard, that's 86 GB/day — well above the MVP load.

## Alternatives considered

- **KDA (Managed Flink)**: rejected for the MVP because Flink's
  stateful operators and exactly-once semantics are overkill for
  the load. Revaluate at >5K events/sec sustained.
- **MSK (Managed Kafka)**: rejected because it adds Zookeeper
  cost (now KRaft, but still), requires a separate consumer
  framework, and gives no free-tier benefit.
- **Self-hosted Kafka on EC2**: rejected because of operational
  burden and the time investment required.

## When to revisit

- Sustained load exceeds 1K events/sec
- Per-event processing exceeds 5 minutes (e.g., GNN inference)
- Cross-region active-active is required

## References

- `terraform/aws/kinesis.tf` — the stream definition
- `terraform/aws/lambda.tf` — the three functions
- `src/infrastructure/adapters/aws/consumer.py` — the two consumer
  classes (Lambda + polling)
- `lambdas/feature_computer/handler.py` — the Lambda entry point
