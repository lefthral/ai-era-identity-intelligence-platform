# ADR Index

This directory contains the Architecture Decision Records (ADRs) for
the Identity Intelligence Platform. Each ADR captures one significant
design decision, the context, the alternatives considered, and the
consequences.

| #   | Title                                                  | Status   |
| --- | ------------------------------------------------------ | -------- |
| 0001 | Multi-cloud via the adapter pattern                   | Accepted |
| 0002 | Hybrid XGBoost + deterministic rule scoring            | Accepted |
| 0003 | Audit log mapped to U.S. Treasury FS-AI RMF            | Accepted |
| 0004 | Kinesis + Lambda over KDA / MSK                       | Accepted |
| 0005 | DynamoDB for online, S3 for offline features           | Accepted |
| 0006 | Free-tier default, single-region AWS                   | Accepted |
| 0007 | XGBoost over GNN as the primary scorer                 | Accepted |

## How to read these

Start with 0001 (the architecture principle) and 0002 (the scoring
philosophy). They are the two decisions that shape everything else.

ADRs 0003-0005 are the production-readiness decisions: audit, stream
processing, and feature storage. These are the questions a senior
data engineering interviewer will ask about.

ADRs 0006 and 0007 are the cost/ML trade-offs: why we did not use
GNN, why we did not deploy multi-region, and how the defaults
get out of the way when production traffic arrives.

## How to write a new ADR

1. Copy the next number (`0008-slug.md`)
2. Use the template at the bottom of this file
3. Submit a PR - review by at least one other engineer before merge

```markdown
# ADR-NNNN: Title

- **Status:** Proposed | Accepted | Deprecated | Superseded by NNNN
- **Date:** YYYY-MM-DD
- **Deciders:** Names

## Context

What is the situation? What forces are at play?

## Decision

What did we choose?

## Consequences

### Positive
### Negative
### Neutral

## Alternatives considered

What else did we consider? Why was each rejected?

## References

Links to code, docs, or external material.
```
