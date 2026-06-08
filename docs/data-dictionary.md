# Data Dictionary

> Every field, every type, every meaning - for analysts, investigators,
> and compliance officers who need to understand the platform's data
> without reading the code.

This document is the canonical reference for:

- **Investigators** querying the case-management UI
- **Compliance officers** preparing regulatory reports
- **Data scientists** building training datasets
- **Engineers** extending the platform

## Conventions

- All IDs are UUID v4 unless otherwise noted
- All timestamps are UTC, microsecond precision
- All monetary values are `Decimal` (never `float`) to avoid
  rounding errors in financial calculations
- All enums are serialized as their string value (e.g.,
  `GroundTruthLabel.DEEPFAKE_ATTACK` → `"deepfake_attack"`)
- All PII fields are stored encrypted at rest (KMS in AWS,
  CMEK in GCP)

---

## 1. Event Stream (`PaymentEvent`)

The atomic unit that flows through the platform. One event per
payment attempt, regardless of outcome.

| Field | Type | Description |
|-------|------|-------------|
| `event_id` | UUID | Unique event identifier |
| `event_type` | enum | `PAYMENT_INITIATED`, `PAYMENT_AUTHORIZED`, `PAYMENT_SETTLED`, `PAYMENT_RETURNED`, `KYC_UPDATE`, `DEVICE_FINGERPRINT`, `LOGIN`, `PASSWORD_RESET` |
| `event_time` | datetime | When the originating system received the event (UTC) |
| `rail` | enum | `SWIFT_ISO20022`, `FEDNOW`, `RTP`, `CARD`, `ACH`, `SEPA`, `WIRE`, `INTERNAL` |
| `actor.person_id` | UUID | The natural person initiating the payment |
| `actor.account_id` | UUID | The account debited |
| `actor.device.fingerprint` | str | Hash of the device fingerprint |
| `actor.device.device_type` | str | `mobile`, `laptop`, `tablet`, `pos`, `atm` |
| `actor.device.os_family` | str? | `iOS`, `Android`, `Windows`, `macOS`, `Linux` |
| `actor.device.browser_family` | str? | `Safari`, `Chrome`, `Firefox`, `Edge` |
| `actor.device.first_seen` | datetime | When this device was first observed for this person |
| `actor.device.last_seen` | datetime | Most recent observation |
| `actor.device.is_known_trusted` | bool | Whether the device is on the user's allow-list |
| `actor.ip.address` | str | IPv4 dotted-quad |
| `actor.ip.asn` | int | Autonomous System Number |
| `actor.ip.country_code` | str | ISO 3166-1 alpha-2 |
| `actor.ip.is_proxy` | bool | VPN or residential proxy detected |
| `actor.ip.is_tor_exit` | bool | Tor exit node |
| `actor.ip.is_datacenter` | bool | Datacenter IP (hosting/VPS) |
| `actor.country_code` | str | ISO 3166-1 alpha-2 |
| `actor.session_id` | UUID? | The session in which the payment was initiated |
| `counterparty.account_id` | UUID | The account credited |
| `counterparty.country_code` | str | ISO 3166-1 alpha-2 |
| `counterparty.is_new_beneficiary` | bool | First-time wire to this counterparty |
| `counterparty.account_age_days` | int | Days since the counterparty account was opened |
| `counterparty.bank_identifier` | str | BIC/SWIFT or ABA routing number |
| `counterparty.name_on_account` | str | As entered by the actor (may be a synthetic name in attacks) |
| `amount.value` | Decimal | The amount in `amount.currency` |
| `amount.currency` | enum | `USD`, `EUR`, `GBP`, `HKD`, `SGD`, `JPY`, `CNY` |
| `memo` | str? | Free-text memo field as entered by the actor |
| `ground_truth_label` | enum | `legit`, `standard_fraud`, `deepfake_attack`, `money_mule`, `synthetic_identity`, `unknown` |
| `attack_pattern` | str? | For synthetic data: `arup`, `singapore`, etc. |
| `synthetic_seed` | int? | The RNG seed used to generate the event (synthetic only) |
| `extra` | dict | Free-form extension dict (e.g., `{"is_cross_border": true}`) |

### Event types in detail

- **`PAYMENT_INITIATED`** - the moment the actor submits the wire;
  the primary event used for scoring
- **`PAYMENT_AUTHORIZED`** - back-office approval, may be the
  second decision point
- **`PAYMENT_SETTLED`** - funds have left the originating account
- **`PAYMENT_RETURNED`** - funds have been returned (either by
  beneficiary bank recall or originator recall)
- **`KYC_UPDATE`** - a person or account's KYC status changed
- **`DEVICE_FINGERPRINT`** - a new device was observed
- **`LOGIN`** - successful authentication
- **`PASSWORD_RESET`** - a password reset was performed

## 2. Decision Stream (`Decision`)

The output of the real-time scorer. One decision per event that
reaches the scorer.

| Field | Type | Description |
|-------|------|-------------|
| `decision_id` | UUID | Unique decision identifier |
| `event_id` | UUID | The event that was scored |
| `decision_time` | datetime | When the decision was made (UTC) |
| `action` | enum | `ALLOW`, `REVIEW`, `BLOCK` |
| `xgb_score` | float [0,1] | The XGBoost model's fraud probability |
| `rule_score` | float [0,1] | The maximum severity across hit rules |
| `final_score` | float [0,1] | `max(xgb_score, rule_score)` |
| `model_version.run_id` | str | MLflow run ID |
| `model_version.model_name` | str | e.g., `identity_intel_xgb` |
| `model_version.stage` | str | `Staging`, `Production`, `Archived` |
| `model_version.algorithm` | str | `xgboost`, `heuristic` |
| `model_version.trained_at` | datetime | When the model was trained |
| `model_version.metrics` | dict | Last-known metrics: `{auc, precision, recall, f1}` |
| `policy_version.policy_name` | str | e.g., `default_policy_v1` |
| `policy_version.policy_hash` | str | SHA-256 of the policy YAML at decision time |
| `policy_version.rules_count` | int | Number of rules in the policy at decision time |
| `feature_snapshot.feature_names` | list[str] | The 19 feature names |
| `feature_snapshot.feature_values` | list[float] | The 19 feature values |
| `feature_snapshot.computed_at` | datetime | When the features were computed |
| `feature_snapshot.online_store_version` | str | Version of the online store schema |
| `rule_hits[]` | list | One entry per rule that fired |
| `explanation` | str? | Plain-text explanation (LLM-generated in Tier 3) |
| `data_lineage_event_id` | str? | OpenLineage event ID |

### `RuleHit`

| Field | Type | Description |
|-------|------|-------------|
| `rule_id` | str | e.g., `R001` |
| `rule_name` | str | e.g., `High velocity wires` |
| `severity` | enum | `low`, `medium`, `high`, `critical` |
| `reason` | str | Why the rule fired (human-readable) |
| `evidence` | dict | The specific values that triggered the rule |

### Action thresholds

| Score | Action |
|-------|--------|
| ≥ 0.80 | `BLOCK` - hold the payment, open a case |
| 0.50 ≤ score < 0.80 | `REVIEW` - queue for investigator review |
| < 0.50 | `ALLOW` - release the payment |

## 3. Case Stream (`Case`)

A case is opened automatically for every `REVIEW` or `BLOCK`
decision. Investigators work cases; cases have outcomes.

| Field | Type | Description |
|-------|------|-------------|
| `case_id` | UUID | Unique case identifier |
| `decision_id` | UUID | The triggering decision |
| `event_id` | UUID | The triggering event |
| `status` | enum | `OPEN`, `IN_REVIEW`, `CONFIRMED_FRAUD`, `FALSE_POSITIVE`, `ESCALATED` |
| `opened_at` | datetime | When the case was opened |
| `closed_at` | datetime? | When the case was closed |
| `investigator` | str? | Username of the assigned investigator |
| `notes` | str? | Investigator notes |
| `outcome_amount_recovered_usd` | Decimal? | Amount recovered (CONFIRMED_FRAUD only) |
| `outcome_recovery_days` | int? | Days from opening to recovery |

## 4. Audit Log Stream (`AuditLog`)

Append-only. One row per decision. Mirrors the `Decision` plus
regulator-facing metadata.

| Field | Type | Description |
|-------|------|-------------|
| `audit_id` | UUID | Unique audit identifier |
| `decision_id` | UUID | The decision being audited |
| `event_id` | UUID | The event that was scored |
| `actor` | str | The principal that made the decision (e.g., `system@identity-intel`) |
| `action_taken` | enum | The action the system took (`ALLOW`, `REVIEW`, `BLOCK`) |
| `final_score` | float | The decision score |
| `model_version_id` | str | `model_name:run_id` |
| `policy_version_id` | str | `policy_name:policy_hash` |
| `rule_codes_hit` | str | Comma-separated rule codes |
| `fs_ai_rmf_principle` | str | The FS-AI RMF principle this audit row evidences |
| `fs_ai_rmf_evidence` | str | URI to the evidence artifact (S3 key) |
| `created_at` | datetime | When the audit row was written |

## 5. Feature Catalog

The 19 features scored by the model. All are computed at
event-time from the actor's history + the current event.

### Velocity (5)

| Feature | Description |
|---------|-------------|
| `txns_last_1h` | Count of transactions in the last hour for this actor |
| `txns_last_24h` | Count in the last 24 hours |
| `distinct_beneficiaries_24h` | Unique beneficiaries in the last 24h |
| `amount_sum_24h` | Total amount sent in the last 24h (USD-equivalent) |
| `cross_border_hops_24h` | Count of cross-border wires in the last 24h |

### Jurisdictional (4)

| Feature | Description |
|---------|-------------|
| `origin_country_risk_score` | `COUNTRY_RISK[actor.country_code]` (0.0-1.0) |
| `destination_country_risk_score` | `COUNTRY_RISK[counterparty.country_code]` |
| `is_high_risk_jurisdiction` | 1.0 if either side is in a high-risk country |
| `jurisdiction_velocity_km_per_hour` | Speed of the actor in km/h (impossible-travel detection) |

### Behavioral (5)

| Feature | Description |
|---------|-------------|
| `amount_zscore_user` | Z-score of this amount vs. the actor's 90-day history |
| `amount_log` | `log10(amount.value)` |
| `time_of_day_zscore` | Z-score of the event hour vs. the actor's history |
| `beneficiary_age_days` | Age of the counterparty account |
| `first_time_beneficiary_high_amount` | 1.0 if the beneficiary is new AND amount > actor's median |

### Network (5)

| Feature | Description |
|---------|-------------|
| `shared_device_count` | Number of other accounts seen on this device |
| `shared_ip_count` | Number of other accounts seen on this IP |
| `mule_ring_proximity_score` | Graph distance to the nearest known mule ring (0.0 = far, 1.0 = in ring) |
| `mule_ring_member` | 1.0 if the actor is in a flagged mule ring |
| `ego_network_degree` | The actor's degree in the identity graph |

## 6. Sanctions List (`SanctionEntry`)

A subset of the OFAC SDN + UN 1267 + EU CFSP lists, used by
rule R010 (Sanctions list fuzzy match).

| Field | Type | Description |
|-------|------|-------------|
| `id` | str | e.g., `SIM-IND-001` (simulated IDs) |
| `name` | str | The name as listed |
| `country` | str | ISO 3166-1 alpha-2 |
| `list` | enum | `OFAC-SDN`, `UN-1267`, `EU-CFSP`, `UK-HMT` |
| `aliases` | list[str] | Known aliases |

In production, this is replaced with the live OFAC + UN + EU feed
updated weekly (Tier 2).

## 7. Identity Graph (Neo4j)

Node labels: `Person`, `Account`, `Device`, `IPAddress`, `Phone`,
`Email`, `Beneficiary`

Edge types: `OWNS`, `USES`, `CONNECTED_FROM`, `CALLED`,
`EMAILED`, `TRANSFERRED_TO`

The graph is the source for:

- `shared_device_count` (count of `Person` nodes connected to the
  same `Device`)
- `shared_ip_count` (count of `Person` nodes connected to the
  same `IPAddress`)
- `mule_ring_proximity_score` (Louvain community detection)

## 8. Operational Metrics (not stored, computed on demand)

| Metric | Definition |
|--------|------------|
| `event_count_60m` | Events received in the last 60 minutes |
| `decision_count_60m` | Decisions made in the last 60 minutes |
| `case_count_60m` | Cases opened in the last 60 minutes |
| `block_rate_60m` | `BLOCK` decisions / total decisions, last 60 min |
| `p99_latency_ms` | 99th-percentile scorer latency over the last 60 min |
| `deepfake_attack_recall_24h` | Fraction of synthetic deepfake events blocked/REVIEWed |
| `arup_pattern_caught` | Was the Arup attack pattern fully caught? (1/0) |
| `singapore_pattern_caught` | Was the Singapore attack pattern fully caught? (1/0) |
