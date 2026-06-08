# Security Model

> The platform handles payment events, PII, and money. This document
> describes the attack surface, the controls in place, and the gaps
> that a Tier 2 deployment would close.

This is not a full threat model - that belongs in a separate document
maintained by the bank's CISO. This is the **platform's** view of its
own security posture, written for engineers extending the system and
for compliance reviewers.

## 1. Assets

The platform processes:

| Asset | Sensitivity | Storage |
|-------|-------------|---------|
| Payment events (amount, rail, account IDs) | Confidential | Kinesis (24h), S3 (7y) |
| Person records (name, DOB, country, KYC status) | PII (GDPR-relevant) | RDS Postgres, Neo4j |
| Device fingerprints, IP addresses | Pseudonymous PII | RDS Postgres, Neo4j, DDB |
| Decisions (action, score, rule hits) | Internal | RDS Postgres |
| Audit log | Regulator-facing | RDS Postgres + S3 Parquet |
| Model artifacts | Confidential | S3 (KMS-encrypted) |
| Sanctions list | Public source | RDS Postgres |

## 2. Attack Surface

### 2.1 Inbound

- **Kinesis Data Streams** (`identity-intel-events`)
 - Authenticated via IAM role on the producer side
 - TLS in transit
 - Producers are upstream payment systems (trusted)
- **FastAPI HTTP** (`/api/*`)
 - Public by default; **must** be behind an API Gateway + WAF in
    production (Tier 2)
 - No auth in the MVP; **must** add OAuth2 / mTLS in Tier 2
- **Streamlit UI** (port 8501)
 - No auth in the MVP; **must** add SSO in Tier 2
- **MLflow tracking server** (port 5000)
 - No auth in the MVP; **must** add basic auth in Tier 2
 - Security group restricted to your IP (see `ec2.tf`)

### 2.2 Outbound

- **Kinesis** → downstream consumers (Lambda)
- **S3 PUT** for feature snapshots and model artifacts
- **DynamoDB** for online feature lookups
- **RDS Postgres** for decisions, cases, audit
- **Neo4j Aura** for the identity graph
- **Slack / PagerDuty** webhook for alerts (Tier 2; stub today)

### 2.3 Supply Chain

- **Python dependencies** pinned in `requirements.txt` and locked
  via `pyproject.toml`
- **Container images** built from `python:3.11-slim`; no third-party
  base images
- **Terraform modules** are local (no `git::https://` references)

## 3. Controls In Place

| Control | Where | Notes |
|---------|-------|-------|
| Encryption in transit (TLS 1.2+) | All services | Kinesis, RDS, DDB, S3, Neo4j Aura, FastAPI |
| Encryption at rest (KMS) | All services | S3, RDS, DDB, Lambda env vars |
| PII separation | Schema | Person PII in `Person` table; device/IP metadata in separate columns |
| Audit log (append-only) | RDS Postgres | Application role has INSERT-only grant; no UPDATE/DELETE |
| Feature snapshot version pinning | Decision | `online_store_version` in every `FeatureSnapshot` |
| Model version pinning | Decision | `ModelVersion.run_id` in every decision |
| Policy hash pinning | Decision | `PolicyVersion.policy_hash` in every decision |
| Decimal for money | `MoneyAmount.value` | No float arithmetic on currency |
| Signed events (Tier 2) | Event schema | Reserve a `signature` field for Tier 2 producer-side HMAC |
| Input validation | Pydantic | Every event validated at the boundary |
| Dependency audit | `requirements.txt` | Run `pip-audit` in CI (Tier 2) |
| Secret management | `.env` (local) / Secrets Manager (AWS) | No secrets in code |
| IRSA (IAM Roles for Service Accounts) | Lambda | Lambdas assume roles; no static AWS keys |
| Least-privilege IAM | `iam.tf` | Lambda role has Kinesis read + S3 read/write + DDB RW; no `*:*` |
| VPC isolation (RDS) | `rds.tf` | RDS in private subnet; not publicly accessible |
| S3 block public access | `s3.tf` | All buckets have `block_public_acls`, `block_public_policy` |
| `failure_mode` on rule engine | `rules.py` | A bad rule raises an exception that is logged, not propagated |

## 4. Known Gaps (Tier 2 work)

These are the items that a CISO would flag for a real bank:

- **No API authentication** - `make deploy-aws` exposes `/api/*`
  unauthenticated. Add Cognito or API Gateway + IAM auth in Tier 2.
- **No network-level segmentation** - Lambdas and the EC2 MLflow host
  are in the default VPC. Tier 2: dedicated subnets with NACLs.
- **No WAF** - public endpoints are not behind AWS WAF. Tier 2.
- **No rate limiting on the FastAPI service** - a misbehaving client
  could DoS. Tier 2: add `slowapi` or API Gateway throttling.
- **Sanctions list is simulated** - `data/sanctions_list.json` is
  fictional. Tier 2: live OFAC + UN + EU feeds, updated weekly.
- **No DLP on the audit log** - the audit log may contain indirect
  identifiers. Tier 2: add column-level encryption for PII columns.
- **No bias audit** - model fairness across protected classes is
  not measured. Tier 2: SHAP-by-demographic dashboards.
- **No penetration test** - the platform has not been red-teamed.
  Tier 2: annual pentest by an external firm.
- **No data retention enforcement** - S3 lifecycle policies are
  in place, but the RDS audit log grows indefinitely. Tier 2:
  archive to S3 Glacier after 7 years.
- **No SOC2 controls** - there is no formal SOC2 Type II report
  for the platform. Tier 2: SOC2 Type II readiness.

## 5. Incident Response

The MVP does not have a formal IR plan. For Tier 2, the following
runbook should be in place:

1. **Detection** - CloudWatch alarms on:
  - Decision volume > 2x baseline
  - Latency p99 > 500ms
  - Lambda error rate > 1%
  - RDS CPU > 80%
2. **Triage** - on-call engineer paged via PagerDuty
3. **Containment** - model rollback (MLflow stage transition),
   rule disable (set `enabled: false` in the policy YAML)
4. **Eradication** - rotate any leaked credentials, patch the
   vulnerability, deploy a new model version
5. **Recovery** - restore the previous model version, replay
   any in-flight decisions
6. **Post-mortem** - write-up within 5 business days, with
   timeline, customer impact, and corrective actions

## 6. Reporting a Vulnerability

If you find a security issue in this project, please email
`security@<your-domain>.com` with a description. We will respond
within 2 business days.

For Tier 2 deployment, the bank's vulnerability disclosure program
takes precedence over anything in this repo.

## 7. Compliance Mappings

| Control | FS-AI RMF | SOC2 CC | EU AI Act |
|---------|-----------|---------|-----------|
| Audit log | §3.1 Traceability | CC7.2 | Art. 12 |
| Explainability | §3.2 Explainability | CC2.3 | Art. 13 |
| Bias testing | §3.3 Fairness | - | Art. 10 |
| Version pinning | §3.4 Versioning | CC8.1 | Art. 11 |
| Human-in-the-loop | §4.1 HITL | CC1.4 | Art. 14 |

The platform's hybrid scoring (XGBoost + rules + audit log)
addresses Art. 13, 14, and the FS-AI RMF §3.1, §3.2, §3.4. Bias
testing (Art. 10, §3.3) and HITL (Art. 14, §4.1) are addressed
by the case-management UI: every `REVIEW`/`BLOCK` decision opens
a case that requires an investigator's action.

## 8. What This Document Does NOT Cover

- Customer-side security (e.g., their MFA, their devices)
- Upstream payment system security (e.g., SWIFT CSP)
- Cloud provider security (AWS, GCP shared responsibility)
- Physical security of data centers
- Third-party vendor risk (covered separately by the bank's
  procurement process)
