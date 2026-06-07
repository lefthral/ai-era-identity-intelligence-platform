# Contributing

Thanks for your interest in improving the Identity Intelligence
Platform. This document explains how to set up a dev environment,
run the tests, and submit a change.

## Code of Conduct

Be kind. Assume good intent. Don't be the person who makes
open-source miserable for everyone else.

## Development Setup

### Prerequisites

- Python 3.11 or 3.12
- Docker + Docker Compose (for the local stack)
- Terraform 1.7+ (for AWS / GCP deploys)
- AWS CLI (for the AWS deploy)
- gcloud CLI (for the GCP deploy, optional)

### First-time setup

```bash
git clone <repo-url> identity-intel
cd identity-intel
make install-dev      # installs prod + dev deps
make start            # starts the local stack (Redpanda, Neo4j, Postgres, MinIO, MLflow)
make init-db          # creates the Postgres schema
make init-neo4j       # creates the Neo4j constraints
```

### Verify your setup

```bash
make walkthrough      # runs the end-to-end demo (no Docker needed)
make test             # 54 tests
make benchmark        # latency check, target p99 < 200ms
make lint             # ruff + black + mypy
```

## Project Layout

```
src/
  domain/             # Pydantic models — no cloud SDKs, no I/O
  application/        # Use cases — features, rules, scoring, worker
  generators/         # Synthetic event generators (Arup, Singapore, baseline)
  infrastructure/
    adapters/         # Cloud-specific I/O (boto3, google-cloud, kafka-python)
      local/          # Redpanda + MinIO + Postgres for dev
      aws/            # Kinesis + S3 + DynamoDB
      gcp/            # Pub/Sub + GCS + Firestore
    persistence/      # SQLAlchemy repos
    graph/            # Neo4j client
  ml/                 # XGBoost training + evaluation

lambdas/              # AWS Lambda handlers (3 functions)
terraform/            # AWS + GCP infrastructure
app/                  # Streamlit UI
docs/                 # Architecture, ADRs, data dictionary, security
tests/                # Pytest suite
examples/             # Runnable end-to-end demos
scripts/              # One-off scripts (generate, build, deploy, benchmark)
```

## Coding Style

- **Type hints everywhere** — Pydantic models, function signatures
- **No comments** unless the code is genuinely surprising. Let
  the names carry the meaning.
- **Docstrings on public APIs** — short, with type information
  already in the signature
- **Imports**: `from src.X import Y` (no relative imports). The
  project root must be in `PYTHONPATH` (the Makefile handles this).
- **Formatting**: `black` (line length 100) + `ruff` (line length
  100, the rules in `pyproject.toml`)
- **Type checking**: `mypy src/ --ignore-missing-imports`

Run `make format` to auto-fix what `black` and `ruff` can fix.

## Boundaries (Do NOT cross)

- **`src/domain/` must NOT import from `src/infrastructure/`.**
  The domain is the core; everything else is replaceable.
- **`src/application/` must NOT import cloud SDKs.** Adapters
  are the only place boto3 / google-cloud / kafka-python is
  imported.
- **Cloud SDK imports must be lazy** in the factory and adapters,
  so the platform can run in an environment without the cloud
  SDK installed.
- **Do NOT add a `requirements.txt` change without updating
  `pyproject.toml`.** They must stay in sync.

## Adding a New Cloud Adapter

1. Create `src/infrastructure/adapters/<cloud>/`
2. Implement each interface from `interfaces.py`:
   - `EventPublisher`
   - `EventConsumer`
   - `OfflineFeatureStore`
   - `OnlineFeatureStore`
3. Add a `get_<cloud>_factory()` function in `factory.py`
4. Add a test in `tests/test_adapters.py` that exercises the
   factory path
5. Document the new cloud in `docs/multi_cloud.md`

## Adding a New Rule

1. Open `src/application/rules.py` and add a `Rule` instance to
   `DEFAULT_RULES`
2. Choose a `code` (next free number: `R011` if R001-R010 are
   taken)
3. Pick a `severity`: `low` (0.3), `medium` (0.6), `high` (0.85),
   or `critical` (1.0)
4. Write the `evaluate` predicate. It must be **pure** — no
   I/O, no global state, no datetime.now() (the `now` is passed
   in via `feature_values` or as an argument)
5. Add a test in `tests/test_application.py` that constructs a
   synthetic event that should trigger the rule and asserts the
   rule fired

## Adding a New Feature

1. Add the feature name to `FEATURE_NAMES` in
   `src/application/features.py`
2. Add the computation in `_extract_features`
3. Add the model retraining:
   - Delete `models/xgb_v1.ubj` (or version it)
   - `make train` — the new feature will be picked up
4. Document the feature in `docs/data-dictionary.md` §5
5. Update the ADR if this is a non-trivial addition

## Submitting a Change

1. Fork the repo
2. Create a feature branch (`git checkout -b feat/new-rule`)
3. Make the change
4. Run `make ci` locally — must pass
5. Open a PR against `main` with:
   - A clear title (`feat: add R011 voice biometric mismatch rule`)
   - A description of the what + why
   - Screenshots for any UI changes
   - A note on backwards-compatibility

A maintainer will review within 2 business days.

## Release Process

(For Tier 2 — the MVP is at v0.1.0.)

1. Bump `version` in `pyproject.toml`
2. Update `CHANGELOG.md` (not present in MVP; add at v0.2.0)
3. Tag the commit: `git tag -a v0.2.0 -m "Release 0.2.0"`
4. Push the tag: `git push origin v0.2.0`
5. CI builds and publishes the Lambda zip + Docker images

## Questions?

- Open an issue
- Or email `engineering@<your-domain>.com`
