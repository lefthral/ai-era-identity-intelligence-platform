# ADR-0002: Hybrid XGBoost + Deterministic Rule Scoring

- **Status:** Accepted
- **Date:** 2026-01-15
- **Deciders:** Identity Intel team

## Context

Two scoring strategies were considered:

1. **Pure ML** (XGBoost only)
2. **Pure rules** (deterministic only)
3. **Hybrid** - both, with `final_score = max(xgb_score, rule_score)`

## Decision

Use the **hybrid** approach. The ML model catches what rules miss
(pattern-level similarity to historical attacks). Rules enforce what
the model can't be trusted to enforce (sanctions lists, hard
jurisdictional blocks, deterministic velocity ceilings).

```python
# src/application/scoring.py
@property
def final_score(self) -> float:
    return max(self.xgb_score, self.rule_score)
```

## Consequences

### Positive

- **Explainability**: Every BLOCK decision can point to either the
  XGBoost SHAP values OR the specific rule(s) that fired. The
  FS-AI RMF (Feb 2026) requires this.
- **Robustness to model drift**: If the model silently degrades,
  the rules still fire on the documented attack patterns.
- **Regulator trust**: Hard rules for sanctioned jurisdictions are
  non-negotiable; a model saying "0.49, allow" should never override
  a sanctions hit.
- **Cold start**: A new model can be deployed alongside battle-tested
  rules without losing coverage during ramp-up.

### Negative

- Two scoring systems to maintain, version, and monitor.
- A rule that fires with 100% severity forces `final_score = 1.0`,
  which can mask ML calibration issues.
- Slightly higher compute cost per event (rules are ~0.01ms, ML is
  ~0.03ms, so combined is ~0.04ms - still well under our 200ms budget).

### Neutral

- SHAP is computed on every ML-scored event so the explanation
  layer can use it. This adds ~5ms per event in production, but
  is computed in parallel with the rule engine.

## Alternatives considered

- **Pure ML**: rejected - black box, hard to defend in regulator
  meetings, no hard guarantees on sanctions.
- **Pure rules**: rejected - can't catch novel attack patterns,
  brittle to attacker adaptation.

## References

- `src/application/scoring.py:RealTimeScorer` - implementation
- `src/application/rules.py:RuleEngine` - the rule side
- `configs/rules.yaml` - the 10 default rules
- `docs/tier2_roadmap.md` §3.1 - future: GNN as a third score
