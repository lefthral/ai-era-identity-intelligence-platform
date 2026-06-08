# ADR-0007: XGBoost Over a GNN as the Primary Scorer

- **Status:** Accepted
- **Date:** 2026-01-15
- **Deciders:** Identity Intel team

## Context

Two ML approaches were considered for the primary scorer:

1. **XGBoost** on the 19 tabular features per event
2. **Graph Neural Network (GNN)** using Neo4j GDS embeddings as input

The GNN approach is intuitively appealing: deepfake wire-fraud is a
network-level pattern (mule rings, shared devices), and a GNN can
natively learn from graph structure. But the platform requirement
is to ship a Tier 1 MVP in 4-6 weeks, demonstrate **recruiter-
recognizable** depth, and stay within the AWS free tier.

## Decision

Use **XGBoost** for the primary scorer in Tier 1, with the option
to add a GNN as a **third score** in the hybrid ensemble at Tier 3.

The graph still plays a critical role: **Neo4j** stores the
identity graph and provides the network features (shared device
count, shared IP count, mule ring proximity score) that XGBoost
consumes as tabular inputs. The "graph-ness" is captured as
features, not as a different model architecture.

## Consequences

### Positive

- **Recruiter-recognizable**: "Built an XGBoost fraud model" is
  a phrase that lands in interviews; "Built a GraphSAGE model
  in PyTorch Geometric" is sometimes met with "what's that?"
- **Fast iteration**: training takes seconds; we can run 100
  experiments in a week.
- **Tooling**: SHAP, MLflow, sklearn ecosystem all work natively.
- **Cold-start friendly**: a tabular model trains with 10K rows;
  a GNN needs careful negative sampling and graph construction.
- **Inference cost**: XGBoost inference is ~0.03ms per event on
  Lambda; GNN inference is 5-50ms depending on embedding size.
- **Free tier**: training fits on the EC2 t3.micro; GNN training
  needs a GPU instance.

### Negative

- **Network patterns are second-class**: the XGBoost feature
  `shared_device_count` is a scalar, not a learned embedding.
  Two mules with the same device get a high score; a chain of
  5 mules each with a different device but a shared IP does not
  get the same "graph distance" signal.
- **No transitive learning**: the model can't infer that an
  account is suspicious because of who its counterparty's
  counterparty is.

### Neutral

- The graph features are computed once per event and cached
  in the online feature store, so adding them to the XGBoost
  input is free at inference time.

## Alternatives considered

- **GNN-only**: rejected for cold-start, inference cost, and
  free-tier compatibility. Considered again at Tier 3.
- **Random Forest**: rejected for less expressive feature
  interactions than XGBoost.
- **Logistic regression baseline**: used as the scoring fallback
  when the XGBoost model file is missing (heuristic).

## When to revisit

- Sustained fraud loss from patterns the XGBoost can't catch
- A real training set of >1M labeled events is available
- A GPU inference path is acceptable (Tier 3)

## References

- `src/ml/train.py` - the XGBoost trainer
- `src/ml/dataset.py` - feature assembly
- `src/infrastructure/graph/client.py` - graph feature source
- `docs/tier2_roadmap.md` §3.1 - the GNN addition
- `docs/research_brief.md` - why AI-fraud matters now
