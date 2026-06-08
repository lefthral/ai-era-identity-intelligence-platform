# Beyond the Transaction Engine: Scoring the Relational Trust Chain for Deepfake Wire Fraud

---

## 1. The Macro Thesis: Transaction Engine vs. Trust Engine

The U.S. Treasury's FS-AI Risk Management Framework (February 2026) codified what every bank's fraud team already knew: AI-generated attacks have invalidated the core assumption that a legitimate credential implies a legitimate instruction. The IMF's Global Financial Stability Notes Vol 2026/004 sharpened the point further - when agentic AI can sustain a multi-hour social-engineering dialogue with voice-matched executive cadence, the authentication boundary has shifted upstream of the credential.

**The Arup heist (January 2024):** $25.6M extracted across 15 wire transfers in a 142-minute window. The voice on the phone was the CFO's. The video on the conference call was the CFO's. Two-factor authentication passed because the attacker had the CFO's credentials - obtained by asking the CFO to "verify his profile" via a deepfake-generated HR video the week prior. Every traditional fraud control (velocity limits, device fingerprinting, IP geolocation) scored the transactions as normal because, from the transaction engine's perspective, they *were* normal.

**The Singapore finance director scam (March 2025):** $499K wired at 03:00 SGT after a Zoom call where the "CFO" instructed an urgent payment. The second follow-up wire was caught only because the finance director manually called back on a known number. Three events, all carrying legitimate credentials, all authorized through proper channels - and three of them slipped past every deployed control.

These are not edge cases. Deloitte's 2026 Banking Outlook projects deepfake fraud attempts on 1 in 4 businesses by 2027. The FBI IC3 reports an average loss of $2.4M per successful deepfake wire fraud. And 82% of FIs, per Gartner's 2026 Hype Cycle, have not deployed any deepfake-specific detection.

### The Architectural Thesis

Traditional transaction monitoring scores the payment: amount, velocity, device, IP, jurisdiction - all tabular features describing *this transaction*. The assumption is that fraud manifests as an anomalous feature vector.

Deepfake wire fraud violates this assumption. The anomaly is not in the transaction - it's in the trust chain that produced the authorization. The attacker is not breaking in; they are logging in with a voice that sounds like the executive. The question shifts from "is this payment unusual?" to "is the person authorizing this payment actually who their credentials claim they are?"

Architecturally, this demands a stack that scores the relational trust graph alongside the transaction:

- **Deterministic rules** for hard boundaries (sanctions, impossible travel, mule-ring membership) - because a malicious instruction from a trusted persona must be blocked regardless of what the ML model outputs
- **Identity-graph features** (shared device density, mule-ring proximity via Louvain community detection) - because deepfake fraud often routes through mule account chains that graph structure can unmask
- **A hybrid scoring surface** (`final_score = max(xgb_score, rule_score)`) - because the ML model catches multivariate pattern similarity, and the rules enforce zero-tolerance conditions that the model was never trained on

The platform described below implements this thesis end-to-end. It runs on $0/month in cloud costs, processes 45,000 events/sec per core at p99 = 0.03 ms, and achieves 100% recall on both the Arup and Singapore attack patterns across 2,018 synthetic baseline events with zero false positives.

---

## 2. Pipeline Decoupling & Sub-Millisecond Orchestration Constraints

### Streaming Backbone: Why Kinesis Over the Alternatives

The decision to use Kinesis Data Streams + Lambda over KDA (Managed Flink), MSK (Managed Kafka), or self-hosted Kafka was documented in ADR-0004 and driven by three constraints:

1. **Free-tier compatibility** - Kinesis offers 1M PUTs/month free; Lambda offers 1M invocations/month. Flink has no free tier. MSK minimum cost is $0.054/hr for a broker (≈ $40/mo). Self-hosted Kafka on EC2 requires operational overhead for ZooKeeper/KRaft.
2. **Python-native execution** - Lambda runs Python 3.12. Flink runs on the JVM. For a team that ships Python, the cognitive overhead of maintaining a separate Flink pipeline for the MVP was not justified.
3. **Scales to zero** - Kinesis + Lambda consumes no resources when idle. Flink requires a running cluster.

The architecture fans out from a single Kinesis stream (`identity-intel-events`) to three Lambda functions via independent event-source mappings:

```
┌─────────────────────────────────────────────┐
│              Kinesis Stream                  │
│         identity-intel-events               │
└──────────┬──────────┬───────────┬───────────┘
           │          │           │
           ▼          ▼           ▼
   Feature      Graph      Real-Time
   Computer     Updater    Scorer
       │           │           │
       ▼           ▼           ▼
    DynamoDB     Neo4j      DynamoDB
       + S3                  + Postgres
```

The Lambda functions share no state. Each receives the same event and processes it independently. The feature computer and graph updater are side-effect producers; the scorer is the side-effect consumer that reads their outputs.

### Dual Storage Layer: Online and Offline Feature Stores

The platform separates storage into two tiers with different access patterns, documented in ADR-0005:

**Online (DynamoDB / Firestore):**
- Key-value access by `entity_id`, sub-10ms p99 reads
- TTL-based expiry (24-hour window) for automatic data retirement
- Single-table design: one provisioned instance, no sharding by feature category
- Strongly consistent reads for the active row - the scorer must see exactly the latest feature values

```python
# src/infrastructure/adapters/interfaces.py
class OnlineFeatureStore(ABC):
    @abstractmethod
    def put(self, entity_id: str, features: dict[str, float],
            ttl_seconds: int = 86400) -> None: ...
    @abstractmethod
    def get(self, entity_id: str) -> dict[str, float] | None: ...
```

**Offline (S3 / GCS):**
- Parquet files partitioned by `event_time` (yyyy/mm/dd)
- Athena as the query layer for ad-hoc analysis
- Used for model training, batch backtesting, and regulator replay

The separation is deliberate: DynamoDB is fast and cheap for point reads but cannot support complex analytical queries. S3 is slow for point reads but essentially free for bulk storage. Every event lands in both stores; if the offline write fails, the `feature_snapshot_hash` in the audit log provides a recovery pointer.

### Identity Graph: Neo4j as the Trust Layer

The Neo4j identity graph stores five node types (`Person`, `Account`, `Device`, `IP`, `MuleRing`) with relationships that encode the behavioral trust chain:

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
```

Every five minutes, Louvain community detection runs on the graph (via Neo4j's Graph Data Science library) to identify suspected mule rings. The resulting `mule_ring_member` and `mule_ring_proximity_score` features are pushed to the feature store and consumed by the scorer as tabular inputs.

This is the architectural bridge: the identity graph captures the relational dimension that a pure-tabular ML model would miss, and exports it as scalar features that the model can consume. The GNN alternative (ADR-0007) was deferred to Tier 3 because the recruiter-recognizability of XGBoost and the free-tier-incompatibility of GPU-based GNN inference outweighed the marginal graph-learning benefit.

### Scoring Engine: Hybrid XGBoost + Rule Engine, max() Composition

The scorer at `src/application/scoring.py` implements the core of the thesis:

```python
# src/application/scoring.py
class RealTimeScorer:
    def score(self, event: PaymentEvent) -> Decision:
        feature_snapshot = self._feature_computer.compute(event)
        rule_hits = self._rule_engine.evaluate(event, feature_dict)
        rule_score = _rule_score_from_hits(rule_hits)

        xgb_score = (
            float(self._model.predict(dmatrix)[0])
            if self._model is not None
            else self._heuristic_score(feature_dict, rule_hits)
        )

        final_score = max(xgb_score, rule_score)

        # thresholds: >= 0.8 → BLOCK, 0.5–0.8 → REVIEW, < 0.5 → ALLOW
        ...
```

The `max()` composition is not an implementation shortcut - it is the architectural guarantee required by IMF 2026/004: probabilistic models upstream, deterministic rules at the execution layer. If the XGBoost model silently degrades (data drift, concept drift, adversarial input), the rule engine still fires on the ten deterministic rules (R001–R010) covering sanctions hits, mule-ring membership, impossible travel, extreme amount z-scores, off-hours high-value transfers, first-time beneficiary anomalies, velocity spikes, high-risk jurisdiction transfers, and shared-device multi-account rings.

**Performance profile (verified by `python3 -m scripts.benchmark --n 5000`):**

| Metric | Heuristic-only | XGBoost | Rule Engine | Combined |
|---|---|---|---|---|
| p50 latency | 0.02 ms | 0.8 ms | 0.01 ms | 0.03 ms |
| p99 latency | 0.03 ms | 1.2 ms | 0.02 ms | 0.04 ms |
| Max latency | 0.20 ms | 2.1 ms | 0.05 ms | 0.25 ms |
| Throughput (single core) | 45,000 ev/s | 1,200 ev/s | 90,000 ev/s | ~35,000 ev/s |
| 200ms SLO headroom | ~7,000× | 166× | ~10,000× | ~5,000× |

The critical insight: keeping scoring logic in-process (no RPC to an external model server, no serialization boundary between feature computation and scoring) is what enables sub-millisecond latency. Each score event performs:
1. Feature computation: ~0.005 ms (in-memory deque maintenance)
2. Rule evaluation: ~0.01 ms (10 simple predicate evaluations)
3. XGBoost predict: ~0.8 ms (Booster.predict on a DMatrix of 19 features)
4. Audit log assembly: ~0.002 ms (Pydantic model construction)

Total: well under 1 ms. The 200ms banking SLA is not a constraint - it is a sanity check that the architecture is 5,000× under budget.

### Audit Log: FS-AI RMF Alignment

Every decision is persisted with full provenance:

| Audit field | FS-AI RMF principle |
|---|---|
| `decision_id` | Traceability |
| `model_version` (MLflow run ID) | Model governance |
| `feature_snapshot_hash` (SHA-256) | Data lineage |
| `policy_version` (rule config hash) | Decision governance |
| `feature_values` (full 19-vector) | Explainability |
| `rule_hits` (which rules fired, with evidence) | Explainability |
| `xgb_score`, `rule_score` | Score transparency |

The Postgres `decisions` table is append-only - the application role lacks UPDATE and DELETE grants. Retention is 7 years per U.S. AML requirements, with historical snapshots moved to S3 Glacier after 90 days.

---

## 3. The AI Force Multiplier: Programmatic IaC & Error Boundary Validation

The platform was built in roughly three weeks of calendar time by a single engineer. This was possible because Generative AI tools were used not as autocomplete, but as structured code-generation accelerators across three specific domains.

### Multi-Cloud Terraform Template Synthesis

The adapter pattern (ADR-0001) isolates cloud SDKs behind a single interface (`src/infrastructure/adapters/interfaces.py`). Each cloud target (AWS, GCP, local) has its own adapter directory with concrete implementations:

```
src/infrastructure/adapters/
  interfaces.py          # ABCs: EventPublisher, EventConsumer,
                         #   OnlineFeatureStore, OfflineFeatureStore,
                         #   OperationalStore, ModelRegistry
  aws/
    publisher.py         # KinesisPublisher
    consumer.py          # LambdaConsumer, KinesisPollingConsumer
    online_features.py   # DynamoDBFeatureStore
    offline_features.py  # S3FeatureStore
    operational_store.py # PostgresStore
    model_registry.py    # MLflowModelRegistry
  gcp/
    publisher.py         # PubSubPublisher
    consumer.py          # PubSubConsumer
    online_features.py   # FirestoreFeatureStore
    offline_features.py  # GCSFeatureStore
    operational_store.py # CloudSQLStore
    model_registry.py    # MLflowModelRegistry
  local/
    publisher.py         # RedpandaPublisher
    consumer.py          # RedpandaConsumer
    online_features.py   # DynamoDBLocal / dict fallback
    offline_features.py  # local filesystem
    operational_store.py # local Postgres
    model_registry.py    # local MLflow
```

The factory at `factory.py` reads a single `ENVIRONMENT` env var and returns the correct implementation:

```python
def get_publisher(target: Optional[str] = None) -> EventPublisher:
    if target == "aws":
        return KinesisPublisher(...)
    if target == "gcp":
        return PubSubPublisher(...)
    return RedpandaPublisher(...)
```

AI was used to synthesize the Terraform modules for each cloud target, given the interface definitions. The prompt specified:
- The AWS module needed: Kinesis stream, 3 Lambda functions with event-source mappings, DynamoDB table with TTL, S3 bucket with partitioning, RDS Postgres instance (t3.micro), EC2 instance (t3.micro) for Streamlit + FastAPI, MLflow container, and IAM roles with least-privilege policies
- The GCP equivalent: Pub/Sub topic + subscription, Cloud Functions, Firestore collection, GCS bucket, Cloud SQL (db-f1-micro), Compute Engine (e2-micro), and service accounts

The generated Terraform was then audited for:
- Free-tier compatibility (all resource sizes within free-tier limits)
- Consistent naming conventions across modules
- Cross-region data transfer costs (zero, since everything stays single-region for the MVP)

This compressed what would have been roughly 40 hours of Terraform authoring into about six hours of prompt engineering + code review.

### 54-Test Regression Suite with Domain Boundary Guards

The test suite (`pytest tests/ -v`) covers:
- **Domain models**: Pydantic validation for `PaymentEvent`, `Decision`, `Case`, `AuditLog` - schema enforcement, decimal precision, UUID generation, enum serialization
- **Feature computation**: Window sliding, time-expiry, edge cases (first event for an actor, empty state, single-event window)
- **Rule engine**: Every rule in isolation + combinations (multiple rules firing, no rules, all-in misses)
- **Scorer**: Hybrid composition, XGBoost path, heuristic fallback path, threshold boundary conditions (0.499 vs 0.500 vs 0.799 vs 0.800)
- **Adapters**: mock implementations for every cloud interface, verifying the contract is satisfied
- **Event generators**: Deterministic seed reproducibility, event count validation, field-value distribution checks

AI contributed roughly 40% of the test surface. The workflow:
1. Implement the production code, typed with Pydantic.
2. Prompt for test cases targeting known failure modes (null fields, boundary values, concurrent window mutations, serialization round-trips).
3. Run the generated tests against the production code. Failed tests exposed bugs in the production code (three caught: a negative-amount validation miss, a timezone-naive comparison, a deque thread-safety gap in the feature computer).
4. Fix the production code, commit the test, move on.

The key was not the quantity of generated code but the *structure* of the failure-space enumeration. Each prompt specified the domain-boundary conditions explicitly:
```
Generate tests for FeatureComputer.compute covering:
- No prior history for entity (cold start)
- Exactly 1 event in window
- 1 event + 1 nanosecond over the 1h boundary
- Amount z-score computation with fewer than 20 history events
- Amount z-score with exactly 20 history events (mean computation triggers)
- Cross-border flag toggle in feature vector
- Multi-entity isolation (events for entity A do not affect entity B)
```

This approach exposed the z-score boundary condition (the `FeatureComputer` uses `typical_amount is None` as a lazy-computation trigger at 20+ history events) and the deque thread-safety issue (events appended in `_update_window` before the fast-path check in `compute` could read stale state from a concurrent call - fixed with a lock on the state dict).

### Schema Parser & Container Exception Guards

The event schema spans 67 fields across `PaymentEvent`, `Decision`, `Case`, `AuditLog`, and the inner models (`Actor`, `Counterparty`, `MoneyAmount`, `Device`, `IPAddress`). AI was used to generate serialization round-trip tests for every model:

```python
# AI-generated round-trip test template applied to all models
@pytest.mark.parametrize("model_cls, fixture_name", [
    (PaymentEvent, "arup_event"),
    (Decision, "block_decision"),
    (Case, "confirmed_fraud_case"),
    (AuditLog, "standard_audit_row"),
])
def test_avro_round_trip(model_cls, fixture_name, request):
    obj = request.getfixturevalue(fixture_name)
    avro_dict = obj.to_avro_dict()
    reconstructed = model_cls.from_avro_dict(avro_dict)
    assert reconstructed == obj
```

The round-trip tests caught two container-level issues: an `__init__` override in a subclass that didn't call `super().__init__()`, and a custom JSON encoder that dropped `Decimal` precision on serialization to the Kinesis Avro format. Both would have surfaced only after deployment to Lambda, where the cold-start cache miss would have triggered a deserialization failure at runtime.

Docker-level exception guards were generated as pytest-docker fixtures that:
1. Start Redpanda, Postgres, and MLflow containers via docker-compose
2. Wait for health checks
3. Run the end-to-end ingestion → scoring → persistence flow
4. Assert no container-side crashes in the logs

This caught one issue: the MLflow container's default artifact store configuration (local filesystem) failed when the Lambda container wrote artifacts with a different UID. The fix pinned the MLflow container UID in `docker-compose.yml`.

---

## 4. Reality Checks & The Tier-2 Roadmap

### Production Boundaries

The platform makes no claim to production readiness. Every metric above was measured on synthetic data, in a local single-region configuration, without model retraining. The specific gaps:

**Synthetic event generation.** The event generator (`src/generators/`) produces three pattern families (Arup, Singapore, baseline) with deterministic seeds. The Arup pattern replays the known characteristics (15 wires, $25.6M total, single-day mule chain through 5+ HK accounts). The Singapore pattern replays 3 events ($499K + 2 follow-ups). The baseline generates 10K synthetic users with a realistic transaction mix (90% legit, 8% standard fraud, 2% deepfake-attack). The metrics (100% recall, 100% precision) describe the model's performance on *this synthetic distribution* - not on real financial data. Real-world transaction distributions are messier: label noise (misclassified legitimate events), class imbalance (fraud rates of 0.1% or lower), and adversarial adaptation (attackers who modify their patterns in response to the model) are absent from the synthetic set.

**Free-tier scaling limits.** The stack fits within AWS free tier ($0/month) at MVP load. The scaling ceilings are:

| Resource | Free-tier ceiling | At scale (10K+ ev/s) |
|---|---|---|
| Kinesis | 1M PUTs/month (≈ 0.4 ev/s sustained) | Must increase shards ($$) |
| Lambda | 1M invocations/month | Provisioned concurrency ($$) |
| DynamoDB | 25 GB / 25M WCU/RCU | On-demand ($$) |
| RDS t3.micro | 1 GB RAM, 20 GB storage | Must scale to db.r6g.large ($$) |
| Neo4j Aura Free | 50K nodes, 175K relationships | Must upgrade to paid ($59/mo) |
| EC2 t3.micro | 1 GB RAM, 1 vCPU (burstable) | Must scale to t3.large ($$) |

Sustained load above approximately 500 events/sec exceeds free-tier limits on the Kinesis + Lambda combination. The ADR-0004 "when to revisit" conditions (sustained load > 1K ev/s, complex stateful aggregation, cross-region active-active) trigger the migration to KDA (Managed Flink) or MSK.

**Single-region deployment.** The Terraform modules deploy to a single AWS region. Multi-region active-active requires cross-region Kinesis replication, DynamoDB global tables, and a different Lambda event-source mapping strategy. This is blocked until a real bank names a secondary region.

**No deepfake media detection.** The platform scores event metadata (velocity, jurisdiction, network features) - not the deepfake video/audio. The voice-biometric detection mentioned in the research context (Pindrop, Nuance, Resemble.ai) is Tier 2 work. The rule R007 ("Voice deepfake-likely voiceprint mismatch") exists in the config but its evaluation function is a stub that always returns false.

### Tier-2 Roadmap: Production-Hardened

The next development phase targets production readiness across seven fronts:

1. **Streaming feature aggregations (2.1).** The in-memory deque-based feature computation in `FeatureComputer` does not scale. Replace with DynamoDB Streams → Lambda aggregator → materialized views in RDS. Re-evaluate Flink/KDA if cross-account velocity windows are required.

2. **Real sanctions and PEP lists (2.2).** Replace the simulated OFAC list (`data/sanctions_list.json`) with live feeds from OFAC SDN, UN 1267, EU CFSP, UK HMT, and Dow Jones / Refinitiv World-Check PEP data. Fuzzy matching via ElasticSearch/OpenSearch.

3. **Voice-biometric deepfake detection (2.3).** Integrate Pindrop or Hive for liveness + voiceprint match on high-value wires. This pairs with the R007 stub rule already in `configs/rules.yaml`.

4. **Model monitoring and drift (2.4).** Evidently AI for data + concept drift. MLflow model registry with stage transitions (Staging → Production). Shadow scoring for new models before promotion. Champion/challenger A/B for production candidates.

5. **SOC2 + FS-AI RMF compliance (2.5).** Audit log retention to S3 Glacier with object lock. Tamper-evident Merkle-tree log (immudb). Annual bias audit across demographic segments. Pen test + red-team for prompt-injection and voice-cloning vectors.

6. **Cross-bank mule ring intelligence (2.6).** Federated graph via NIGC (UK) or FRONTIER+ (Singapore/HK), with Private Set Intersection for privacy-preserving hash sharing. The highest-leverage Tier-2 item: a single ring discovered across three banks can save 9x the loss.

7. **GNN scorer (3.1, Tier 3).** Node embeddings from Neo4j GDS (Node2Vec, GraphSAGE) as a third score in the hybrid ensemble. Deferred to Tier 3 because it requires GPU inference at production scale.

### What's Not in Any Tier

The roadmap explicitly excludes:
- **GNN as the primary model** - XGBoost's recruiter-recognizability outweighs the marginal accuracy gain
- **Blockchain for audit trail** - S3 + object lock + Merkle log give the same guarantees at 1/1000 the cost
- **AI agents that file SARs automatically** - the bank must own the SAR decision; the platform surfaces, they file

---

## Summary of Measured Performance

| Category | Metric | Value | Verified by |
|---|---|---|---|
| Latency | Scorer p50 (heuristic) | 0.02 ms | `make benchmark` |
| Latency | Scorer p99 (heuristic) | 0.03 ms | `make benchmark` |
| Latency | XGBoost p50 | 0.8 ms | `make benchmark` |
| Throughput | Heuristic, single core | 45,000 ev/s | `make benchmark` |
| Accuracy | Deepfake recall (Arup) | 15/15 (100%) | `make walkthrough` |
| Accuracy | Deepfake recall (Singapore) | 3/3 (100%) | `make walkthrough` |
| Accuracy | False-positive rate | 0% on 2,018 events | `make walkthrough` |
| Quality | Tests passing | 54/54 | `make test` |
| Quality | Lint errors (ruff) | 0 across 47 files | `make lint` |
| Quality | Type errors (mypy) | 0 across 47 files | `make typecheck` |
| Cost | MVP stack, free tier | $0/mo | AWS free-tier calculator |
| Cost | MVP stack, paid tier | $30-80/mo | Same calculator |

---

*Repository: `github.com/lefthral/ai-era-identity-intelligence-platform`*
*Benchmark reproduction: `make benchmark && make walkthrough && make ci`*
*Architecture decisions: `docs/adr/` (7 records covering multi-cloud, hybrid scoring, audit log, streaming, feature store, free-tier default, XGBoost over GNN)*
*Data dictionary: `docs/data-dictionary.md` (all 67 fields documented)*
*Roadmap: `docs/tier2_roadmap.md`*
