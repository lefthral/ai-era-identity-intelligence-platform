# AI-Era Identity Intelligence Platform

A streaming platform that scores payment events in real time for AI-generated
fraud patterns. Built around two documented deepfake wire-fraud incidents:
the Arup heist ($25.6M, Jan 2024) and the Singapore CFO scam ($499K, Mar 2025).

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Tests: 54 passing](https://img.shields.io/badge/tests-54%20passing-brightgreen.svg)](#testing)
[![Ruff: 0 issues](https://img.shields.io/badge/ruff-0%20issues-blue.svg)](#quality)
[![Mypy: 0 issues](https://img.shields.io/badge/mypy-0%20issues-blue.svg)](#quality)
[![Black: formatted](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![CI](https://github.com/lefthral/ai-era-identity-intelligence-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/lefthral/ai-era-identity-intelligence-platform/actions/workflows/ci.yml)

## Contents

- [Run it (60 seconds)](#run-it-60-seconds)
- [What it does](#what-it-does)
- [Numbers](#numbers)
- [Architecture](#architecture)
- [Repo layout](#repo-layout)
- [Quality gates](#quality-gates)
- [Deployment](#deployment)
- [Design choices](#design-choices)
- [Limitations](#limitations)
- [Docs](#docs)

## Run it (60 seconds)

No Docker. No cloud account. No data files.

```bash
git clone https://github.com/lefthral/ai-era-identity-intelligence-platform
cd ai-era-identity-intelligence-platform
make install-dev        # pip install -e ".[dev]"
make walkthrough        # end-to-end demo, ~5s
```

Expected output (abbreviated):

```
$ make walkthrough
Stage 1: Generate events
  arup:       15 ($25.6M, 15 wires)
  singapore:   3 ($499K + 2 follow-ups)
  baseline:  500
Stage 3: Summary
  {
    "actions": {"ALLOW": 483, "REVIEW": 12, "BLOCK": 23},
    "labels": {"legit": 441, "money_mule": 13, "standard_fraud": 46, "deepfake_attack": 18}
  }
  Deepfake attack recall: 18/18 (100%)
  Arup pattern ($25.6M, 15 wires): 15/15 flagged (caught $25.6M)
```

Then try the rest:

```bash
make benchmark         # scorer latency, 5K events
make test              # pytest, 54 tests
make demo              # full Docker stack + UI on :8501 + API on :8000
```

## What it does

Ingest → features → rules → score → audit, end-to-end:

1. Ingest payment events from a streaming bus (Kinesis / Pub/Sub / Redpanda).
2. Maintain rolling 1h/24h windows for 19 streaming features (velocity, jurisdiction, network, behavior).
3. Update a live identity graph (Neo4j) — person, account, device, IP, mule rings.
4. Score every event: `final_score = max(xgb_score, rule_score)` (ADR-0002).
5. Emit a decision: `ALLOW` (< 0.5), `REVIEW` (0.5–0.8), `BLOCK` (≥ 0.8).
6. Persist the decision with model version, policy hash, feature snapshot hash, and rule hits — for replay 6 months later.

The hybrid score is deliberate: the XGBoost model picks up subtle multivariate
patterns, and the 10 deterministic rules (R001–R010) catch known signals
(sanctions hit, impossible travel, mule-ring proximity) the model may have
never seen in training.

## Numbers

Measured locally, no cloud, no model retraining.

| Metric | Value | Note |
|---|---|---|
| Scorer latency (heuristic) | p50 = 0.02 ms, p99 = 0.03 ms | ~7,000× under the 200 ms p99 SLO |
| Scorer latency (XGBoost) | p50 ≈ 0.8 ms, p99 ≈ 1.2 ms | 166× under SLO |
| Throughput (heuristic) | ~45,000 events/sec/core | single-threaded, in-memory |
| Deepfake recall (Arup) | 15/15 (100%) | $25.6M, 142-min window |
| Deepfake recall (Singapore) | 3/3 (100%) | $499K, 03:00 SGT |
| Precision (synthetic dataset) | 100% | no false positives across 2,018 events |
| False-positive rate | 0% | heuristic on synthetic baseline |
| Cold-start time | < 1 s | no model load needed (heuristic) |
| Memory (heuristic) | ~120 MB | per worker process |
| Cost within free tier | $0/mo | Kinesis + Lambda + DynamoDB + S3 + RDS t3.micro + EC2 t3.micro + Neo4j Aura |
| Cost after free tier | $30–80/mo | same stack, paid tier |

Reproduce the benchmark:

```bash
make benchmark
# Throughput: ~45000 events/sec
# p50: 0.02ms  p95: 0.03ms  p99: 0.03ms  max: 0.20ms
```

Reproduce the recall numbers:

```bash
make walkthrough
# See Stage 3 summary above.
```

## Architecture

```
                          ┌──────────────────────────────────────┐
                          │   EVENT GENERATOR (synthetic)        │
                          │   Arup / Singapore / baseline        │
                          └─────────────────┬────────────────────┘
                                            │
                             ┌──────────────▼──────────────┐
                             │   STREAMING BACKBONE        │
                             │   AWS: Kinesis              │
                             │   GCP: Pub/Sub              │
                             │   Local: Redpanda           │
                             └──────────────┬──────────────┘
                                            │
              ┌─────────────────────────────┼─────────────────────────────┐
              │                             │                             │
    ┌─────────▼─────────┐       ┌───────────▼──────────┐     ┌────────────▼────────────┐
    │  FEATURE COMPUTER │       │   IDENTITY GRAPH     │     │   REAL-TIME SCORER      │
    │  19 features,     │       │   Neo4j Aura (free)  │     │   XGBoost + 10 rules    │
    │  1h/24h windows   │       │   Louvain mule-ring  │     │   max(xgb, rule)        │
    └─────────┬─────────┘       └───────────┬──────────┘     └────────────┬────────────┘
              │                             │                             │
              └─────────────────────────────┼─────────────────────────────┘
                                            │
                             ┌──────────────▼──────────────┐
                             │   POSTGRES + MLflow         │
                             │   decisions, cases, audit   │
                             │   Streamlit UI, FastAPI     │
                             └─────────────────────────────┘
```

Same business logic on every target. The factory at
`src/infrastructure/adapters/factory.py` is the only file that knows which
cloud SDK belongs to which target — see ADR-0001.

## Repo layout

```
src/
  domain/           # Pydantic entities. No cloud SDKs.
  generators/       # Synthetic Arup + Singapore + baseline
  application/      # features, rules, scoring, API, worker
  infrastructure/   # adapters (aws/gcp/local), persistence, graph
  ml/               # XGBoost training + per-class evaluation
lambdas/            # feature_computer, graph_updater, scorer
app/                # Streamlit UI (4 pages)
terraform/          # aws/ (primary), gcp/ (portability)
docs/adr/           # 7 architecture decision records
```

Start with these three files if you only have 10 minutes:

- `src/application/scoring.py` — where the business lives.
- `src/infrastructure/adapters/factory.py` — the cloud-portability boundary.
- `docs/adr/0002-hybrid-xgb-rules.md` — the scoring design.

## Quality gates

Every push runs:

| Check | Status |
|---|---|
| `ruff check` | 0 issues |
| `black --check` | formatted |
| `mypy --ignore-missing-imports` | 0 issues in 47 files |
| `pytest tests/ -v` | 54 passed |
| `terraform validate` (AWS + GCP) | clean |
| `docker build` × 3 | green |

Locally:

```bash
make ci
# == Lint ==     ruff: 0 issues
# == Format ==   black: 64 files clean
# == Types ==    mypy: 0 issues in 47 files
# == Tests ==    54 passed in ~8s
# == Walkthrough == Arup 15/15 ($25.6M), Singapore 3/3
# == Benchmark == p50=0.02ms, p99=0.03ms, ~45K/sec
```

## Deployment

Three modes. All hit on free tier.

**Local Docker** (default for dev):

```bash
make demo
# Streamlit: http://localhost:8501
# API:       http://localhost:8000/docs
```

**AWS free tier** (Terraform-managed):

```bash
aws configure
cd terraform/aws && terraform init && terraform apply
make deploy-aws
```

**GCP** (portability reference):

```bash
cd terraform/gcp && terraform init && terraform apply
```

Service mapping lives in [`docs/multi_cloud.md`](docs/multi_cloud.md).

## Design choices

| Decision | Why | What it costs |
|---|---|---|
| Kinesis over Kafka | Managed, no ZooKeeper, Python SDK, free tier. | Per-record cost at scale. |
| Lambda over Flink | Python-native, no JVM, scales to zero, free tier. | 15-min execution cap. |
| Neo4j over graph-in-Postgres | Cypher expressiveness, native Louvain community detection. | One more service. |
| DynamoDB over Redis | Managed, free tier, sub-10ms reads. | Eventual consistency. |
| XGBoost over GNN | Recruiter-recognized, well-understood, fast training. | Doesn't use graph structure. |
| Streamlit over React | Fastest path to a demoable UI. | Looks like a notebook, not a bank portal. |
| Heuristic fallback over XGBoost-only | Demo works with zero training. | Heuristic is hand-tuned, not learned. |

Full reasoning lives in [`docs/adr/`](docs/adr/).

## Limitations

Things this isn't:

- **Not production-ready.** Single-region AWS. No SSO. No RBAC. No model
  drift monitoring. No champion/challenger. See [`docs/tier2_roadmap.md`](docs/tier2_roadmap.md).
- **Not a deepfake media detector.** It scores event metadata (velocity,
  jurisdiction, network), not the deepfake video/audio. Media detection
  is a Tier 2 add-on.
- **Not trained on real fraud.** Synthetic labels only. Metrics reflect
  synthetic-distribution quality, not production.
- **Not certified.** No PCI-DSS, SOC 2, or FS-AI RMF attestation.

## Docs

| | |
|---|---|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | End-to-end system design |
| [`docs/multi_cloud.md`](docs/multi_cloud.md) | AWS ↔ GCP service mapping |
| [`docs/data-dictionary.md`](docs/data-dictionary.md) | Every field in every event |
| [`docs/glossary.md`](docs/glossary.md) | SWIFT, ISO 20022, mule ring, etc. |
| [`docs/SECURITY.md`](docs/SECURITY.md) | Threat model + known gaps |
| [`docs/tier2_roadmap.md`](docs/tier2_roadmap.md) | Production + research roadmap |
| [`docs/adr/`](docs/adr/) | 7 architecture decision records |
| [`docs/research_brief.md`](docs/research_brief.md) | Institutional context |
| [`docs/blog_post.md`](docs/blog_post.md) | "Building on the free tier" (long form) |
| [`CHANGELOG.md`](CHANGELOG.md) | Versioned release history |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Dev setup, boundaries |
| [`SECURITY.md`](SECURITY.md) | Coordinated disclosure |

## License

MIT — see [`LICENSE`](LICENSE).
