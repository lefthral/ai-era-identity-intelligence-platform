# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned
- Tier 2: GNN-based mule ring detection
- Tier 2: Real XGBoost training pipeline (replacing heuristic)
- Tier 2: OpenLineage integration for full data lineage

## [0.1.0] - 2026-06-06

Initial public release.

### Added
- Domain models (`src/domain/`): Pydantic `PaymentEvent`, `Decision`,
  `RuleHit`, `ModelVersion`, `PolicyVersion`, `FeatureSnapshot`.
  Cloud-agnostic, no infrastructure dependencies.
- Synthetic event generators (`src/generators/`):
  - `arup_pattern.py` — the documented $25.6M / 15-wire Arup deepfake
    fraud (Jan 2024).
  - `singapore_pattern.py` — the $499K Singapore deepfake CFO scam
    (Mar 2025).
  - `baseline.py` — realistic normal activity.
- Feature computer (`src/application/features.py`): 19 streaming features
  (velocity, network, jurisdictional risk, behavior).
- Rule engine (`src/application/rules.py`): 10 deterministic rules
  (R001–R010) including impossible travel, sanctions hit, mule ring
  proximity, off-hours high value, and extreme amount z-score.
- Hybrid scorer (`src/application/scoring.py`):
  `final_score = max(xgb_score, rule_score)` per ADR-0002.
  Falls back to a deterministic heuristic when no trained model exists.
- ML pipeline (`src/ml/`): XGBoost training with MLflow tracking, plus
  per-class evaluation utilities.
- Infrastructure adapters (`src/infrastructure/adapters/`):
  factory pattern, `EventPublisher`, `EventConsumer`,
  `OfflineFeatureStore`, `OnlineFeatureStore`, `GraphClient`,
  `Notifier` — with concrete implementations for `local`, `aws`, and
  `gcp` targets.
- Persistence (`src/infrastructure/persistence/`): SQLAlchemy models
  + repositories for `Decision`, `Case`, `AuditLog`, `Stats`.
- Audit log shape mapped to U.S. Treasury FS-AI RMF (Feb 2026)
  traceability requirements.
- Notifications (`src/infrastructure/notifications/`): Noop, Slack,
  PagerDuty — selected by `ALERT_CHANNEL` env var.
- Lambda handlers (`lambdas/`): `feature_computer`, `graph_updater`,
  `scorer` — three Lambda entry points.
- FastAPI service (`src/application/api.py`): 9 endpoints
  (health, decisions, cases, graph, mule-rings, features, stats, audit).
- Streamlit UI (`app/streamlit_app.py`): 4 pages (Live Feed, Case
  Detail, Graph Explorer, Audit Log), with offline sample-data
  fallback for demo without Docker.
- Terraform (`terraform/`): AWS (Kinesis + Lambda + S3 + DynamoDB +
  RDS t3.micro + EC2 t3.micro + IAM) and GCP reference (Pub/Sub +
  GCS + Firestore + Cloud SQL db-f1-micro + Cloud Run).
- Docker (`docker/`, `docker-compose.yml`): 3 Dockerfiles (api,
  consumer, ui) and a local stack.
- Scripts (`scripts/`): `generate_events`, `build_lambdas.sh`,
  `deploy_aws.sh`, `local_run.sh`, `benchmark.py`,
  `seed_demo_data.py`.
- Tests (`tests/`): 54 tests across domain, generators, application,
  adapters, and integration. 100% pass. `make ci` mirrors GitHub
  Actions.
- Examples (`examples/`): `walkthrough.py` (end-to-end demo),
  `investigator_cli.py` (case investigation).
- Configs (`configs/`): `xgb_v1.yaml`, `rules.yaml`.
- Data (`data/sanctions_list.json`): simulated OFAC/UN/EU list.
- Docs (`docs/`):
  - `research_brief.md` — institutional context (5 vectors).
  - `multi_cloud.md` — AWS ↔ GCP mapping.
  - `blog_post.md` — "Building on the free tier".
  - `tier2_roadmap.md` — production-hardening + research roadmap.
  - `data-dictionary.md` — every field documented.
  - `glossary.md` — banking terms.
  - `SECURITY.md` — attack surface + 13 controls + 10 known gaps.
  - `adr/` — 7 architecture decision records.
- Notebooks-as-scripts (`notebooks/`): `training_analysis.py` for
  reproducible per-class metrics.
- CI (`.github/workflows/ci.yml`): 4 jobs (lint, test 3.11+3.12,
  terraform validate, docker build).
- GitHub community health: CODEOWNERS, 5 issue templates, PR template,
  SECURITY, SUPPORT, FUNDING.

[Unreleased]: https://github.com/lefthral/ai-era-identity-intelligence-platform/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/lefthral/ai-era-identity-intelligence-platform/releases/tag/v0.1.0
