# Architecture

## 1. System Overview

The AI-Era Identity Intelligence Platform is a **streaming-first** data platform organized around six capability pillars:

| Pillar | Purpose | Primary Tech |
|---|---|---|
| P1: Identity Graph | Resolve entities, detect mule rings | Neo4j |
| P2: Stream Ingestion | Ingest multi-rail events | Kinesis / Redpanda |
| P3: Feature Store | Online + offline features | DynamoDB / S3 / PG |
| P4: Real-Time Decisioning | XGBoost + rules, <500ms p99 | Lambda + XGBoost |
| P5: Model & Data Governance | Lineage, drift, audit | MLflow + GE |
| P6: Case Management | Investigator workflow, SAR | FastAPI + Streamlit |

## 2. Data Flow

```
   [Event Generator]
          │
          │  put_records (Avro)
          ▼
   [Kinesis / Redpanda]
          │
          │  (parallel fan-out via Lambda event source mappings)
          │
   ┌──────┼─────────────────────────────┐
   │      │                             │
   ▼      ▼                             ▼
[Feature   [Graph             [Real-Time
Computer]  Updater]           Scorer]
   │         │                     │
   │         │                     │
   ▼         ▼                     ▼
 [S3]    [Neo4j]              [DynamoDB]
 [DDB]                            │
                                   │
                                   ▼
                            [Postgres: cases,
                             decisions, audit_log]
                                   │
                                   ▼
                          [FastAPI + Streamlit]
```

## 3. Component Details

### 3.1 Event Generator (`src/generators/`)

Produces three pattern families for evaluation:

- **`arup_pattern.py`** - replays the Arup deepfake heist: 15 wires, $25.6M total, single day, mule chain through 5+ HK accounts, deepfake-instructed from CFO. Source: VerifyReal case study + Hong Kong police disclosures.
- **`singapore_pattern.py`** - replays the Singapore finance director scam: single $499K wire, deepfake CFO on Zoom, mule → HK offshore accounts. Funds recovered in 4 days via FRONTIER+.
- **`baseline.py`** - 10K synthetic users, ~500 txn/sec realistic bank mix (90% legit, 8% standard fraud, 2% deepfake-attack). Used to train the model with realistic noise.

All events are **deterministic given a seed** - reproducible for testing and re-training.

### 3.2 Schema (Avro-compatible JSON)

```json
{
  "event_id": "uuid",
  "event_type": "PAYMENT_INITIATED",
  "event_time": "2026-01-15T14:23:11.123Z",
  "rail": "SWIFT_ISO20022",
  "actor": {
    "person_id": "uuid",
    "account_id": "uuid",
    "device_fp": "string",
    "ip": "string",
    "country": "ISO-3166"
  },
  "counterparty": {
    "account_id": "uuid",
    "country": "ISO-3166",
    "new_beneficiary": "boolean"
  },
  "amount": {"value": "decimal", "currency": "ISO-4217"},
  "memo": "string",
  "ground_truth_label": "legit|standard_fraud|deepfake_attack",
  "attack_pattern": "arup|singapore|null"
}
```

### 3.3 Feature Catalog (~25 features)

**Velocity (windowed):**
- `txns_last_1h` (per account, device, IP)
- `txns_last_24h`
- `distinct_beneficiaries_24h`
- `amount_sum_24h`
- `cross_border_hops_24h`

**Jurisdictional:**
- `origin_country_risk_score`
- `destination_country_risk_score`
- `is_high_risk_jurisdiction` (FATF grey/black list match)
- `jurisdiction_velocity_km_per_hour` (impossible travel)

**Behavioral:**
- `amount_zscore_user` (vs. 90-day user history)
- `amount_zscore_peer` (vs. peer group)
- `time_of_day_zscore`
- `beneficiary_age_days`
- `first_time_beneficiary_high_amount`

**Network (from Neo4j):**
- `shared_device_count` (other accounts on this device)
- `shared_ip_count`
- `mule_ring_proximity_score`
- `mule_ring_member` (boolean)
- `counterparty_watchlist_match`
- `ego_network_degree`
- `ego_network_clustering_coefficient`
- `community_size_louvain`
- `community_fraud_rate`

### 3.4 Scoring

**Hybrid model:**
1. **XGBoost classifier** - trained on synthetic labels, predicts P(fraud | features). Returns score 0-1.
2. **Rule engine** - 10 hardcoded deterministic rules. Any rule hit sets `rule_score = 1.0`.
3. **Combination** - `decision_score = max(xgb_score, rule_score)`. Either source can flag.

**Decision thresholds (configurable):**
- `score >= 0.8` → BLOCK
- `0.5 <= score < 0.8` → REVIEW (case created)
- `score < 0.5` → ALLOW

**Latency budget:** <500ms p99 from Kinesis PutRecord to decision written to Postgres.

### 3.5 Audit Log (Treasury FS-AI RMF Alignment)

Every decision carries:

| Field | Maps to FS-AI RMF Control |
|---|---|
| `decision_id` | Auditability |
| `event_id` | Traceability |
| `model_version` (MLflow run ID) | Model governance |
| `feature_snapshot_hash` (SHA-256) | Data lineage |
| `policy_version` (rule engine config hash) | Decision governance |
| `feature_values` (full snapshot) | Explainability |
| `rule_hits` (which rules fired) | Explainability |
| `xgb_score`, `rule_score` | Score transparency |
| `decision_timestamp` | Auditability |
| `data_lineage_event_id` (OpenLineage) | Data lineage |

This directly satisfies the Treasury's Feb 2026 guidance: "Pure outputs from models such as GPT or Claude, without human review, full traceability, and technical reproducibility, are no longer acceptable."

### 3.6 Identity Graph Schema (Neo4j)

```cypher
(:Person {id, name, kyc_status, country, risk_score})
(:Account {id, bank, opened_at, balance_band, is_mule})
(:Device {fp, type, first_seen, last_seen})
(:IP {addr, asn, country, is_proxy})
(:MuleRing {id, pattern, confidence, first_detected})

(:Person)-[:OWNS]->(:Account)
(:Account)-[:TRANSFERRED_TO {count, total_amount, last_at}]->(:Account)
(:Device)-[:USED_BY]->(:Person)
(:IP)-[:USED_BY]->(:Person)
(:Person)-[:MEMBER_OF]->(:MuleRing)
(:Account)-[:MEMBER_OF]->(:MuleRing)
```

**Graph algorithms run periodically (every 5 min):**
- Louvain community detection → identify suspected mule rings
- PageRank → identify high-influence entities
- Shortest path → distance to known fraud entities

## 4. Failure Modes & Mitigations

| Failure | Detection | Mitigation |
|---|---|---|
| Lambda cold start adds latency | CloudWatch latency metric | Provisioned concurrency (Tier 2) |
| Neo4j Aura free tier limits hit | Aura dashboard alerts | Cache reads; fallback to PG JOIN |
| XGBoost model overfits to synthetic data | Holdout AUC vs train AUC gap | Document; use realistic label noise |
| Feature drift in production | Evidently AI monitor (Tier 2) | Retraining pipeline (Tier 2) |
| Kinesis throttling | CloudWatch `PutRecords.ThrottledRecords` | Increase shard count (cost-incurring) |
| RDS free tier expires | Billing alert at $20 | Migrate to local PG or self-hosted |
| Event generator seed drift | Deterministic seeding in tests | CI checks for seed reproducibility |

## 5. Local vs AWS Mapping

| Concern | Local (Docker) | AWS |
|---|---|---|
| Streaming | Redpanda (single Kafka API) | Kinesis Data Streams |
| Processing | Python workers | Lambda (Python 3.12) |
| Offline features | MinIO (S3 API) | S3 |
| Online features | PostgreSQL `online_features` table | DynamoDB |
| Graph | Neo4j Community | Neo4j Aura Free |
| API | FastAPI on host | FastAPI on EC2 t3.micro |
| UI | Streamlit on host | Streamlit on EC2 t3.micro |
| MLflow | Docker container | EC2 t3.micro |

The application code uses **adapter interfaces** defined in `src/infrastructure/adapters/interfaces.py`. AWS and local implementations satisfy the same interface, so business logic is identical.

## 6. Why This Maps to Real Banking Pain Points

| Research Finding | This Platform's Response |
|---|---|
| Wolters Kluwer: 48% cite data quality as #1 AI barrier | Great Expectations checkpoints on every feature batch |
| Treasury FS-AI RMF (Feb 2026) requires traceability | Audit log with model/feature/policy versions |
| Capgemini: 71% execs cite data fragmentation | Unified identity graph (Neo4j) as source of truth |
| Deloitte: AI stuck in PoC, can't scale | Production-shaped pipeline with IaC, monitoring, audit |
| IMF 2026/004: deterministic execution layer | Rule engine as deterministic guardrail over ML |
| Industry: 76% of orgs had AI security incident | Tokenized agent credentials ready for Tier 3 |
| Arup/Singapore pattern: legitimate auth + fake trust | Score the trust chain, not just the transaction |

See [docs/research_brief.md](docs/research_brief.md) for the full research synthesis.
