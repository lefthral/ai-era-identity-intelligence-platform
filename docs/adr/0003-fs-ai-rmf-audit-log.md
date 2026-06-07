# ADR-0003: Audit Log Mapped to U.S. Treasury FS-AI Risk Management Framework

- **Status:** Accepted
- **Date:** 2026-01-15
- **Deciders:** Identity Intel team

## Context

The U.S. Treasury's **FS-AI Risk Management Framework** (Feb 2026)
mandates that any AI-driven decision at a U.S. financial institution
must be:

1. **Traceable** — decision can be replayed against historical state
2. **Explainable** — a human can understand the inputs and reasoning
3. **Versioned** — the exact model + policy in force at decision time
   is recoverable
4. **Bias-auditable** — decisions can be sliced by protected
   demographic attributes

The platform produces ~hundreds of decisions per second at production
scale. A regulator investigating one decision six months later must
be able to reconstruct it exactly.

## Decision

The `Decision` Pydantic model (`src/domain/decisions.py`) carries:

- `decision_id` (UUID v4)
- `event_id` (the input)
- `model_version` — full `ModelVersion` object with run_id, algorithm,
  trained_at, metrics
- `policy_version` — full `PolicyVersion` object with policy_name,
  policy_hash, rules_count
- `feature_snapshot` — the exact 19-feature vector that was scored
- `rule_hits` — every rule that fired, with reason + evidence
- `data_lineage_event_id` — OpenLineage event ID for cross-system trace

The decision row in Postgres mirrors this 1:1, plus:

- `created_at` (UTC, microsecond precision)
- `latency_ms` (the wall-clock time from event receive to decision)
- `fs_ai_rmf_principle` — string from {Explainability, Fairness,
  Accountability, Privacy, Robustness, Transparency}
- `fs_ai_rmf_evidence` — URI to the evidence artifact
  (S3 key for the Parquet feature snapshot)

## Consequences

### Positive

- Regulator-friendly: any decision can be defended in an audit by
  pulling one row and one S3 object.
- The audit log itself is append-only (Postgres grants no UPDATE
  or DELETE on `decisions` to the application role).
- The hash of the policy YAML in `policy_version.policy_hash` means
  "which rules were active" is recoverable by hash, even if the
  rules file is edited later.

### Negative

- ~30% larger decision row than a minimal decision_id + scores
  schema. At 100 decisions/sec this is 50 GB/year — cheap.
- The `feature_snapshot` Parquet file must be retained for the same
  period as the decision (7 years for U.S. AML). Use S3 Glacier
  after 90 days.
- OpenLineage integration adds an outbound dependency on the
  lineage service; if it goes down, the decision should still be
  made (and the lineage emitted on retry).

### Neutral

- The audit log is a write-only table; we never read it in the
  hot path. Reads happen only for regulator requests or
  case-management investigation.

## Alternatives considered

- **Black-box ML, no audit**: rejected — non-compliant with
  FS-AI RMF, blocks adoption by U.S. banks.
- **External WORM storage (e.g., S3 Object Lock) for decisions**:
  deferred to Tier 2 — adds cost without addressing the core
  explainability requirement.

## References

- `src/domain/decisions.py` — the `Decision` model
- `src/infrastructure/persistence/models.py` — the `DecisionRow`
- `src/infrastructure/persistence/repos.py` — the writer
- `docs/research_brief.md` §3 — the FS-AI RMF context
- `docs/tier2_roadmap.md` §2.5 — Tier 2 compliance work
