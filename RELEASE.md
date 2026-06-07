# Release notes

## v0.1.0 (2026-06-06) — Initial public release

First end-to-end release of the AI-Era Identity Intelligence Platform.
Built around the documented **Arup ($25.6M, Jan 2024)** and
**Singapore ($499K, Mar 2025)** deepfake wire-fraud incidents.

### Highlights

- **Streaming pipeline** (generator → features → rules → scorer →
  decision → audit) on a single laptop or AWS free tier.
- **Hybrid scoring**: `final_score = max(xgb_score, rule_score)`.
  Default scorer is a deterministic heuristic; XGBoost training is
  optional.
- **Cloud-portable**: one `Environment` env var switches between
  `local`, `aws`, and `gcp` adapters.
- **Audit log shape maps to U.S. Treasury FS-AI RMF** (Feb 2026)
  traceability requirements.
- **100% deepfake recall, 100% precision, 0% FPR** on the synthetic
  Arup + Singapore + baseline dataset (2018 events, see
  `models/analysis.json`).
- **54 tests, all passing**. `make ci` mirrors GitHub Actions.
- **No credit card needed**: every component runs within the free
  tier of AWS, GCP, Neo4j Aura, or local Docker.

### Known limitations

See `docs/SECURITY.md` and `docs/tier2_roadmap.md`:

- Synthetic data only — no real bank data
- Single region (no multi-region failover)
- No real MLflow (uses local SQLite)
- Heuristic scorer (not a trained XGBoost model)
- No SSO / RBAC (single-user Streamlit)
- No model drift monitoring

### Upgrade

This is the first release. No upgrade path.
