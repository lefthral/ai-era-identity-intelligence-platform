# ADR-0001: Use a Cloud-Agnostic Adapter Pattern for Multi-Cloud Portability

- **Status:** Accepted
- **Date:** 2026-01-15
- **Deciders:** Identity Intel team

## Context

The platform was scoped to be deployable on AWS (primary) and GCP
(portability reference). The original implementation choices were:

1. **Parallel codebases** — write the AWS pipeline twice, once for each cloud
2. **Adapter pattern** — write business logic once, swap cloud-specific implementations
3. **Cloud-native** — pick one and write directly against its SDK

## Decision

Use the **adapter pattern** (`src/infrastructure/adapters/`).

The application layer (`src/application/`) depends only on interfaces in
`src/infrastructure/adapters/interfaces.py`. Concrete implementations
live in `aws/`, `gcp/`, and `local/`. The factory reads an
`ENVIRONMENT` env var and returns the right class.

```python
# src/infrastructure/adapters/factory.py
def get_publisher(target: Optional[str] = None) -> EventPublisher:
    if target == "aws":
        return KinesisPublisher(...)
    if target == "gcp":
        return PubSubPublisher(...)
    return RedpandaPublisher(...)
```

## Consequences

### Positive

- Business logic (`src/application/`, `src/domain/`) is portable.
- Adding a fourth cloud (Azure) is `src/infrastructure/adapters/azure/`,
  not a rewrite.
- Local development uses the same business code path as production —
  just with different adapter classes.
- The pattern is well-understood by senior platform engineers.

### Negative

- The lowest-common-denominator interface is forced on every cloud
  (e.g., Kinesis and Pub/Sub have different ordering guarantees, but
  the `EventPublisher` interface only exposes the intersection).
- One extra layer of indirection when reading the code.
- Cannot use cloud-native features that don't have a portable
  equivalent (e.g., BigQuery ML).

### Neutral

- The factory pattern adds 30 lines of code but saves 1000+ lines
  of duplication.

## Alternatives considered

- **Parallel codebases**: rejected — twice the code, twice the bugs,
  no real portability because the two would diverge.
- **Cloud-native (AWS only)**: rejected — the requirements called
  out GCP portability. Also, the adapter pattern is recruiter-recognizable
  in the platform-engineer interview.

## References

- `docs/multi_cloud.md` — the user-facing explanation
- `src/infrastructure/adapters/factory.py` — the implementation
- `src/infrastructure/adapters/interfaces.py` — the contracts
