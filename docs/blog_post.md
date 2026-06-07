# Blog Post: Building a Real-Time AI-Fraud Pipeline on the Free Tier

*A data engineering case study in 2026 — when AI-generated fraud
stopped being a hypothetical and became a line item.*

## The Trigger

In January 2024, an Arup finance employee received a video call from
someone who looked and sounded exactly like their CFO. Over the next
142 minutes, 15 wires totaling **$25.6M** were sent to five
Hong Kong bank accounts. Every video frame, every vocal inflection, was
synthesized. It was not until a follow-up call to a known phone number
that anyone realized the CFO had been on a call all day.

In March 2025, a Singapore-based firm lost **$499K** in the same way.

By 2026, **one in four** attempted business wire fraud events involved
synthetic media. The U.S. Treasury's FS-AI Risk Management Framework
made AI-fraud controls a regulatory expectation, not a roadmap item.

This is the context in which the **Identity Intelligence Platform**
ships. It is a real-time data engineering pipeline designed to detect
exactly this attack pattern — and it runs entirely on free-tier cloud
infrastructure.

## What the Platform Does

Given a stream of payment events (real or synthetic), the platform
answers four questions in under 200 milliseconds:

1. **Is this transaction structurally similar to a deepfake
   attack pattern?** (XGBoost + 19 engineered features)
2. **Does it violate any deterministic risk rules?** (R001-R010:
   velocity, jurisdiction, beneficiary, network, sanctions)
3. **Is the recipient connected to a known mule ring?** (Neo4j
   Louvain community detection)
4. **Can we explain the decision six months from now to a regulator?**
   (FS-AI RMF-mapped audit log)

The decision is one of: `ALLOW`, `REVIEW`, or `BLOCK`.

## How It's Built

```
Payment event
    |
    v
Kinesis (or Pub/Sub) -------------------------------+
    |                                               |
    v                                               v
Lambda: feature computer              Lambda: graph updater
    |                                               |
    +-----------> DynamoDB (online features) <------+
    |
    v
Lambda: scorer
    |  XGBoost + rules
    v
Postgres (decisions + cases + audit log)
    |
    v
Streamlit investigator UI
```

Every arrow is an interface in `src/infrastructure/adapters/interfaces.py`.
The business logic — features, rules, scoring — does not know it runs on
AWS. The same code runs against Redpanda (local), Kinesis (AWS), or
Pub/Sub (GCP) by swapping the adapter at the factory.

## The Three Design Decisions That Mattered

### 1. Hybrid scoring, not pure ML

A pure XGBoost model would have been faster to build. But XGBoost
cannot explain to a regulator *why* a wire was blocked, and it cannot
encode a hard business rule like "no wires to sanctioned jurisdictions
regardless of model score." The platform uses:

```
final_score = max(xgb_score, rule_score)
```

The model catches what rules miss; rules enforce what the model can't
be trusted to enforce.

### 2. Adapter pattern, not parallel codebases

Most multi-cloud demos write the same business logic twice. This
project writes it once and confines the cloud SDK to a single
directory. The factory reads `ENVIRONMENT=aws` (or `local`, or `gcp`)
and wires the right adapter. To support a fourth cloud (Azure), you
add a directory, not a rewrite.

### 3. Audit log mapped to a real federal framework

Every decision row includes a `fs_ai_rmf_principle` and
`fs_ai_rmf_evidence` column. The platform does not just log
decisions — it logs them in the shape the U.S. Treasury's FS-AI
RMF expects. This is the difference between a project and a
*portfolio-ready* project: the latter is auditable.

## The Free-Tier Math

| Service | Free-Tier Quota | Our Use | Headroom |
|---------|-----------------|---------|----------|
| Kinesis | 1M PUTs/month | ~50K/month | 20x |
| Lambda | 1M invocations/month | ~50K/month | 20x |
| DynamoDB | 25 GB + 25M ops | <1 GB + <1M ops | 25x |
| S3 | 5 GB / 12mo | ~1 GB | 5x |
| RDS t3.micro | 750 hrs / 12mo | 730 hrs (always on) | ~3% |
| EC2 t3.micro | 750 hrs / 12mo | 730 hrs (MLflow) | ~3% |
| Neo4j Aura | 1 instance, 200K nodes | ~5K nodes | 40x |

Total monthly cost inside the free tier: **$0**. Post-free-tier (year 2):
$30-80 depending on traffic.

## What the Demo Looks Like

1. `make start` — spins up Redpanda, Postgres, MinIO, Neo4j, MLflow
2. `make generate-arup` — publishes 15 wires over 142 simulated minutes
3. Open the Streamlit UI at `localhost:8501`
4. The Live Decision Feed shows each wire as it's scored; the Graph
   Explorer shows the resulting Hong Kong mule ring; the Audit Log
   shows each decision with its FS-AI RMF mapping
5. `make train` — retrains the XGBoost model against the labeled
   synthetic dataset, logs to MLflow

## What I'd Add With More Time

- **Streaming feature aggregations** in DynamoDB Streams (today they're
  recomputed from scratch per event in the Lambda)
- **Real OFAC sanctions list** (today it's a simulated subset)
- **Cross-account entity resolution** in Neo4j (fuzzy match on
  device + IP + behavioral signal)
- **GCP deployment as a one-command `make deploy-gcp`** (today the
  Terraform is reference-only)
- **A frontend for the audit log** with regulatory export

## Why This Project, For Hiring

A data engineering candidate in 2026 is competing for roles that did
not exist in 2023. Banks need people who can:

- Build streaming pipelines against managed services
- Embed ML models into transaction-decision flows
- Explain model decisions to non-technical regulators
- Architect for multi-cloud portability
- Ship on a budget

This project demonstrates all five. The code is at
`github.com/<your-handle>/identity-intel`. Try it on a Saturday
afternoon with `make start && make generate-mix`.
