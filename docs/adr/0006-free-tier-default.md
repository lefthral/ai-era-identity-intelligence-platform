# ADR-0006: Free-Tier Default, Single-Region AWS

- **Status:** Accepted
- **Date:** 2026-01-15
- **Deciders:** Identity Intel team

## Context

The platform's stated requirement is "free-tier runnable end-to-end."
This imposes hard constraints on the architecture:

- Kinesis: 1M PUTs/month free forever (after first 12 months)
- Lambda: 1M invocations/month free forever
- DynamoDB: 25 GB + 25M WCU/RCU free forever
- S3: 5 GB / 12 months free, then standard S3 pricing
- RDS: db.t3.micro, 20 GB, 750 hrs/month free for 12 months
- EC2: t3.micro, 750 hrs/month free for 12 months
- Neo4j Aura: 1 free instance, 200K nodes, forever

Multi-region and multi-AZ is out of scope for the MVP.

## Decision

The default `terraform/aws/main.tf` deploys to `us-east-1` in a
single VPC, single AZ, with a single Kinesis shard. After 12 months,
the bill is still under $30-80/month at the documented traffic
level. The architecture is "single-region by default, multi-region
by configuration change" - the same Terraform root supports it
with `multi_az = true` and a second-region provider block.

## Consequences

### Positive

- **Demoable in 60 seconds**: no AWS account required for the
  walkthrough; free tier makes the cloud deployment accessible
  to any reviewer.
- **No surprise bills**: 12-month cost ceiling is well-documented.
- **Simple Terraform**: a single `terraform apply` and you're done.

### Negative

- **Single-AZ is a SPOF**: if the AZ goes down, the platform
  goes down. For the MVP that's acceptable; for production
  it's not.
- **RDS clock starts ticking**: 12-month free RDS benefit means
  the cost goes from $0 to ~$15/month at the one-year mark.
- **EC2 MLflow host has same 12-month limit**: post-year-1,
  MLflow moves to either a paid t3.micro ($8/month) or
  a serverless alternative (Fargate Spot, Cloud Run, etc.).

### Neutral

- The Terraform variables that govern these defaults are
  `kinesis_shard_count`, `rds_instance_class`, `ec2_instance_type`,
  and `multi_az`. Changing any of them is a one-line edit.

## When to revisit

- Real production traffic
- 12-month free-tier window expires
- Compliance requires multi-region

## References

- `docs/multi_cloud.md` - the cost table
- `terraform/aws/variables.tf` - all the knobs
- `terraform/aws/main.tf` - the single-region default
- `docs/tier2_roadmap.md` §2.5 - multi-region as a Tier 2 item
