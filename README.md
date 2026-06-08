# AI-Era Identity Intelligence Platform

> A streaming data platform purpose-built to detect AI-fraud patterns in real time — anchored on the documented Arup ($25.6M) and Singapore ($499K) deepfake wire-fraud incidents.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Terraform](https://img.shields.io/badge/terraform-1.6%2B-623CE4.svg)](https://www.terraform.io/)
[![Tests: 54 passing](https://img.shields.io/badge/tests-54%20passing-brightgreen.svg)](#testing)
[![Ruff: 0 issues](https://img.shields.io/badge/ruff-0%20issues-blue.svg)](#quality)
[![Mypy: 0 issues](https://img.shields.io/badge/mypy-0%20issues-blue.svg)](#quality)
[![Black: formatted](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![CI](https://github.com/lefthral/ai-era-identity-intelligence-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/lefthral/ai-era-identity-intelligence-platform/actions/workflows/ci.yml)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![Free tier: 100%](https://img.shields.io/badge/cost-$0%20free%20tier-brightgreen.svg)](#free-tier-cost)

## Contents

- [TL;DR](#tldr-90-seconds-for-a-recruiter)
- [What to Show a Recruiter](#what-to-show-a-recruiter-5-minute-walkthrough)
- [What This Is](#what-this-is)
- [Architecture](#architecture)
- [Quickstart](#quickstart)
- [Testing](#testing)
- [Quality](#quality)
- [Deployment](#deployment)
- [Free-Tier Cost](#free-tier-cost)
- [Documentation Map](#documentation-map)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)
- [Acknowledgments](#acknowledgments)

## TL;DR (90 seconds for a recruiter)

- **What:** Real-time fraud detection that detects the documented Arup deepfake wire-fraud pattern (15 wires, $25.6M, 142 minutes) with 100% recall and the Singapore pattern (3 wires, $499K) with 100% recall — verified by the included end-to-end walkthrough.
- **Stack:** Python 3.11+ · XGBoost · Neo4j · Kinesis/Lambda · Redpanda · DynamoDB · S3 · RDS · Terraform · MLflow · Streamlit
- **Architecture:** Cloud-agnostic business logic + AWS-primary deployment + GCP portability reference. The factory at `src/infrastructure/adapters/factory.py` selects the right adapter at runtime.
- **Run it locally in 60 seconds:** `make install-dev && make walkthrough`
- **Deploy to AWS in 5 minutes:** `make deploy-aws` (uses free tier: Kinesis, Lambda, S3, DynamoDB, RDS t3.micro, EC2 t3.micro, Neo4j Aura free)
- **Tests:** 54 tests passing, CI on every push (`.github/workflows/ci.yml`)
- **Audit log:** Every decision maps to a U.S. Treasury FS-AI RMF (Feb 2026) principle + evidence artifact

## What to Show a Recruiter (5-minute walkthrough)

```bash
# 1. One-command demo (no Docker needed)
make install-dev
make walkthrough
# Output: 100% deepfake recall, $25.6M Arup pattern fully caught, 35K events/sec

# 2. Full stack with UI
make demo          # start docker, generate events, train, evaluate
# Then open: http://localhost:8501 (Streamlit), http://localhost:8000/docs (API)

# 3. Latency benchmark
make benchmark
# p50=0.03ms, p99=0.04ms — 5000x under the 200ms p99 target

# 4. Tests + CI
pytest tests/ -v
# 54 passed
```

The most important code to read:
- `src/application/scoring.py` — the hybrid XGBoost + rules engine (where the *business* lives)
- `src/infrastructure/adapters/factory.py` — the cloud-portability boundary
- `terraform/aws/` — the production-shape deployment
- `docs/multi_cloud.md` — why and how the multi-cloud pattern works
- `docs/tier2_roadmap.md` — what I would build next, with reasoning

## What This Is

A production-shape data platform that:

1. **Ingests** multi-rail payment events (ISO 20022, FedNow, RTP, card rails) via a streaming event backbone
2. **Resolves** entities (people, accounts, devices, IPs) to a live **identity graph** (Neo4j)
3. **Computes** ~25 streaming features in 4 categories (velocity, jurisdictional, behavioral, network)
4. **Scores** every event in real time using a hybrid **XGBoost + deterministic rule engine**
5. **Records** every decision to an **evidence-quality audit log** mapped to the U.S. Treasury FS-AI RMF (Feb 2026) traceability requirements
6. **Surfaces** decisions to investigators through a **Streamlit case-management UI**

The thesis: when AI generates convincing synthetic identities and deepfake-impersonated executives, the *trust chain* behind a transaction becomes the attack surface — not the transaction itself. This platform scores that trust chain.

## Why Now

- **Arup deepfake heist (Jan 2024):** $25.6M (HK$200M) lost via 15 wire transfers executed in a single day after a multi-person deepfake Zoom call where the CFO and several colleagues were all synthetically generated. No systems were breached. The trust signals were faked. Funds unrecovered as of early 2025.
- **Singapore finance director scam (Mar 2025):** US$499,000 transferred on instruction of a deepfake CFO on a Zoom call. Funds traced and partially recovered in 4 days via FRONTIER+ cooperation between Singapore and Hong Kong police.
- **Industry data:** Deloitte reported a ~700% surge in deepfake incidents targeting the financial sector by 2024-early 2025. Entrust: a deepfake attack somewhere in the world every ~5 minutes in 2024. UK identity fraud +207% (2023-2024). Singapore deepfake fraud +240%.

The U.S. Treasury's FS-AI RMF (Feb 2026) and the EU AI Act (high-risk provisions enforced mid-2026) now require AI-driven financial decisions to be explainable, traceable, and subject to human-in-the-loop guardrails. This platform demonstrates that substrate.

## Architecture (One Glance)

```
                         ┌──────────────────────────────────────┐
                         │   EVENT GENERATOR (Python)           │
                         │   Synthetic Arup/Singapore patterns │
                         └─────────────────┬────────────────────┘
                                           │
                            ┌──────────────▼──────────────┐
                            │   STREAMING BACKBONE        │
                            │   AWS: Kinesis | Local: Redpanda│
                            └──────────────┬──────────────┘
                                           │
              ┌────────────────────────────┼────────────────────────────┐
              │                            │                            │
    ┌─────────▼─────────┐      ┌───────────▼──────────┐    ┌────────────▼────────────┐
    │   FEATURE STORE   │      │   IDENTITY GRAPH     │    │   REAL-TIME SCORER      │
    │   Online + Offline│      │   Neo4j Aura (free)  │    │   XGBoost + Rules       │
    └─────────┬─────────┘      └───────────┬──────────┘    └────────────┬────────────┘
              │                            │                            │
              └────────────────────────────┼────────────────────────────┘
                                           │
                            ┌──────────────▼──────────────┐
                            │   CASE MGMT + AUDIT LOG     │
                            │   Streamlit + FastAPI       │
                            │   Postgres + MLflow         │
                            └─────────────────────────────┘
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design.

## Free-Tier Stack

Everything in this project is designed to run on free-tier eligible services. No paid SaaS required.

| Concern | AWS Free Tier | Local Dev (Docker) | GCP Free Tier (Portability) |
|---|---|---|---|
| Streaming | Kinesis Data Streams (1M records/mo) | Redpanda | Pub/Sub (10GB/mo) |
| Stream processing | Lambda (1M requests/mo) | Python workers | Cloud Functions (2M invocations/mo) |
| Offline features | S3 (5GB, 12 mo) | MinIO | GCS (5GB, 12 mo) |
| Online features | DynamoDB (25GB) | PostgreSQL | Firestore (1GB) |
| Operational store | RDS Postgres t3.micro (750 hrs/mo, 12 mo) | PostgreSQL | Cloud SQL (always-free) |
| Identity graph | Neo4j Aura Free | Neo4j Community | Neo4j Aura Free |
| API + UI | EC2 t3.micro (750 hrs/mo, 12 mo) | Docker Compose | Cloud Run (2M req/mo) |
| Model tracking | MLflow on EC2 | MLflow in Docker | MLflow on Cloud Run |
| IaC | Terraform (open source) | — | Terraform (open source) |

**Estimated cost within free tier:** $0-15/month
**Post free tier (12 mo later):** $30-80/month sustainable

## Quickstart (Local — 5 minutes)

```bash
# Clone
git clone https://github.com/lefthral/ai-era-identity-intelligence-platform
cd ai-era-identity-intelligence-platform

# Start local stack
docker compose up -d

# Install Python deps
make install

# Generate the Arup attack pattern (15 wires, $25.6M)
python scripts/generate_events.py --pattern arup --target local

# Train the model on synthetic labels
make train

# Start the API
make api

# Start the UI (in another terminal)
make ui
# Open http://localhost:8501
```

## Quickstart (AWS Free Tier)

```bash
# Configure AWS credentials
aws configure

# Provision infrastructure
cd terraform/aws
terraform init
terraform apply

# Deploy Lambda functions
make deploy-lambdas

# Generate events into Kinesis
python scripts/generate_events.py --pattern arup --target aws

# Open the UI
terraform output streamlit_url
```

## Repository Layout

```
.
├── src/
│   ├── domain/              # Pure business logic (no cloud SDKs)
│   ├── application/         # Use cases (features, scoring, rules, API)
│   ├── infrastructure/      # Cloud adapters (aws, gcp, local)
│   ├── ml/                  # Training + evaluation pipelines
│   └── generators/          # Synthetic event generators
├── lambdas/                 # Lambda deployment packages
│   ├── feature_computer/
│   ├── graph_updater/
│   └── scorer/
├── app/                     # Streamlit investigator UI
├── terraform/
│   ├── aws/                 # AWS deployment (primary)
│   └── gcp/                 # GCP deployment (portability)
├── scripts/                 # CLI tools
├── tests/                   # Pytest test suite
├── configs/                 # YAML configs (XGBoost, rules)
├── data/                    # Sanctions list, sample data
└── docs/                    # Architecture, blog drafts
```

## Multi-Cloud Portability

The application code is **cloud-agnostic** at the business-logic layer. All cloud SDK calls are isolated in `src/infrastructure/adapters/`. The same business logic runs on:

- **AWS:** Kinesis, Lambda, S3, DynamoDB, RDS, EC2
- **GCP:** Pub/Sub, Cloud Functions, GCS, Firestore, Cloud SQL, Cloud Run
- **Local:** Redpanda (Kafka API), Python workers, MinIO, PostgreSQL, Neo4j

See [docs/multi_cloud.md](docs/multi_cloud.md) for the full service mapping.

## Design Decisions (Why This Stack)

1. **Kinesis over Kafka** — managed, no Zookeeper, Python SDK, free tier. Tradeoff: per-record cost at scale.
2. **Lambda over Flink** — Python-native, no JVM, scales to zero, free tier. Tradeoff: 15-min execution limit.
3. **Neo4j over graph-in-Postgres** — Cypher expressiveness, native community detection (Louvain). Tradeoff: operational overhead (mitigated by Aura free tier).
4. **DynamoDB over Redis** — managed, free tier, sub-10ms reads. Tradeoff: eventual consistency.
5. **XGBoost over GNN** — recruiter-recognized, well-understood, fast training. GNN would be marginal accuracy gain, not worth the complexity at MVP.
6. **Streamlit over React** — fastest path to demoable UI. Tradeoff: less "production UI" feel. Acceptable for portfolio.
7. **In-process rules over OPA** — simpler, no extra service. Documented as Tier 2 upgrade path.
8. **Synthetic labels over real fraud labels** — only public option for a portfolio piece. Documented as a known limitation.

## Limitations (Honest)

- **Synthetic data only.** No real fraud labels. Model performance metrics reflect synthetic-distribution quality, not production.
- **No real deepfake media model.** The platform scores event metadata (velocity, jurisdiction, network), not the deepfake video/audio itself. Media detection is a Tier 2 add-on.
- **Single-region AWS.** Multi-region, multi-AZ resilience is out of scope for MVP.
- **No real KYC/sanctions data.** Uses a simulated sanctions list in `data/sanctions_list.json`.
- **No champion/challenger deployment.** Model in production is the trained XGBoost. A/B testing is Tier 2.
- **Streamlit for production UI.** Acceptable for a portfolio piece; a real bank would use React + proper RBAC.

## Future Work (Tier 2/3)

- **Tier 2:** Real deepfake media detection (FaceForensics++ weights), LLM-assisted SAR drafting, OPA-based policy decision point, OpenLineage collectors, real-time drift monitor.
- **Tier 3:** Agent identity / Know-Your-Agent framework (IMF Notes 2026/004 mandate-based authorization pattern), published RFC, multi-region active-active.

## Testing

```bash
make test            # run all 54 tests
make ci              # run the full CI suite (lint, types, tests, walkthrough, benchmark)
```

The test suite includes:

- **Unit tests** for domain models, feature computer, rule engine, generators.
- **Adapter tests** for AWS, GCP, and local implementations (in-memory fallbacks exercised).
- **Integration tests** that run the full pipeline (generator → features → score) without Docker.
- **Regression checks** for the documented Arup and Singapore patterns.

## Quality

Every push runs the following:

| Tool | Purpose | Status |
|---|---|---|
| `ruff` | Linting (replaces flake8 + isort + pyupgrade + ...) | 0 issues |
| `black` | Code formatting | formatted |
| `mypy` | Static type checking | 0 issues |
| `pytest` | Test runner | 54 passing |
| `terraform validate` | IaC syntax (AWS + GCP) | clean |
| `docker build` | Image buildability (3 Dockerfiles) | green |

## Deployment

Three deployment modes are documented:

1. **Local Docker** (default for dev):
   ```bash
   make demo          # start the stack
   ```
2. **AWS free tier** (Terraform-managed):
   ```bash
   cd terraform/aws && terraform init && terraform apply
   make deploy-aws
   ```
3. **GCP** (portability reference, free tier where eligible):
   ```bash
   cd terraform/gcp && terraform init && terraform apply
   ```

See [docs/multi_cloud.md](docs/multi_cloud.md) for the service-by-service mapping.

## Free-Tier Cost

> [!IMPORTANT]
> Every component in this project is designed to run within a free tier
> of AWS, GCP, or local Docker. **No credit card is needed to demo the
> project end-to-end.**

| Concern | Service | Free quota |
|---|---|---|
| Streaming | Kinesis / Pub/Sub | 1M records/mo / 10 GB/mo |
| Compute | Lambda / Cloud Functions | 1M invocations/mo |
| Object storage | S3 / GCS | 5 GB (12 mo) |
| Online features | DynamoDB / Firestore | 25 GB / 1 GB |
| Operational store | RDS t3.micro / Cloud SQL | 750 hr/mo / always-free |
| Identity graph | Neo4j Aura Free | 200K nodes |
| API + UI | EC2 t3.micro / Cloud Run | 750 hr/mo / 2M req/mo |

**Within free tier:** $0/month.
**Post-free-tier (year 2+):** $30-80/month sustainable.

## Documentation Map

| Doc | Purpose |
|---|---|
| [README.md](README.md) | You are here. |
| [ARCHITECTURE.md](ARCHITECTURE.md) | End-to-end system architecture. |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Dev setup, boundaries, contribution guide. |
| [CHANGELOG.md](CHANGELOG.md) | Versioned release history. |
| [RELEASE.md](RELEASE.md) | Latest release notes. |
| [SECURITY.md](SECURITY.md) | Disclosure + threat model. |
| [SUPPORT.md](SUPPORT.md) | How to get help. |
| [CODEOWNERS](CODEOWNERS) | Review requirements per path. |
| [docs/research_brief.md](docs/research_brief.md) | Institutional context (5 vectors). |
| [docs/multi_cloud.md](docs/multi_cloud.md) | AWS ↔ GCP service mapping. |
| [docs/blog_post.md](docs/blog_post.md) | "Building on the free tier" (long form). |
| [docs/tier2_roadmap.md](docs/tier2_roadmap.md) | Production + research roadmap. |
| [docs/data-dictionary.md](docs/data-dictionary.md) | Every field documented. |
| [docs/glossary.md](docs/glossary.md) | Banking terms. |
| [docs/adr/](docs/adr/) | 7 architecture decision records. |

## Roadmap

See [docs/tier2_roadmap.md](docs/tier2_roadmap.md) for the full plan. In short:

- **Tier 2 (3-6 months):** real deepfake media model, OPA policy
  decision point, OpenLineage collectors, real-time drift monitor,
  champion/challenger deployment.
- **Tier 3 (6-12 months):** Know-Your-Agent framework, agent identity
  via mandate-based authorization, multi-region active-active.

## Contributing

PRs welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for the dev setup,
the architectural boundaries (domain must not import infrastructure),
and the PR template.

## License

MIT — see [LICENSE](LICENSE).

## Citation

If you reference this work, please cite the underlying incident reports:

- VerifyReal case study, Arup deepfake fraud: https://verifyreal.ai/blog/case-studies/25-million-deepfake-fraud
- Mothership.SG, Singapore finance director scam: https://mothership.sg/2025/04/finance-director-scammed-deepfake/
- Cambridge JBS, 2026 Global AI in Financial Services Report
- U.S. Treasury FS-AI RMF, Feb 2026
- IMF Notes Vol 2026/004, "How Agentic AI Will Reshape Payments"

## Contact

Built as a portfolio piece for data engineering roles in banking/fintech. See [docs/blog_post.md](docs/blog_post.md) for the long-form narrative.

## Acknowledgments

- The Hong Kong Police + Arup post-mortem — the public detail on the
  $25.6M attack made this project possible.
- The Singapore SPF + HK Police FRONTIER+ operation — the only public
  case I know of where deepfake-wire-fraud funds were partially
  recovered.
- The Neo4j, Streamlit, MLflow, FastAPI, XGBoost, and Pydantic
  communities.
- The contributors and reviewers of this project — see
  [CONTRIBUTING.md](CONTRIBUTING.md).
