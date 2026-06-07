# Pull request

Thanks for contributing! Please fill out the sections below.

## What does this PR do?

A 1-3 sentence description. Link any related issues.

## Affected area

- [ ] Streaming ingest
- [ ] Feature computer
- [ ] Rule engine
- [ ] ML scorer
- [ ] Graph
- [ ] Persistence
- [ ] API / worker
- [ ] UI
- [ ] Terraform
- [ ] Docker
- [ ] CI / tooling
- [ ] Docs
- [ ] Tests
- [ ] Other: ___________

## Type of change

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds capability)
- [ ] Breaking change (fix or feature that changes existing behavior)
- [ ] Documentation update

## Checklist

- [ ] Tests pass locally: `make ci`
- [ ] New code has type hints and docstrings
- [ ] Domain / application / infrastructure boundaries respected
  (see `CONTRIBUTING.md`)
- [ ] No cloud SDKs leaked into the application layer
- [ ] If user-facing: README / docs updated
- [ ] If model behavior changed: `notebooks/training_analysis.py`
  re-run and results pasted below

## Test output

```
$ make ci
... paste tail of output here
```

## Screenshots

If UI / Streamlit change, attach before / after.
