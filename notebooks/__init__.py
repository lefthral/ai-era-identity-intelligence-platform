"""Notebooks-as-scripts.

Each file in this directory is a self-contained script version of
what would otherwise be a Jupyter notebook. They run without
Jupyter installed (so they can be in CI) and produce deterministic
JSON / CSV artifacts for the UI to consume.

Currently:
- training_analysis.py: per-class metrics, feature availability,
  high-risk country coverage. Writes models/analysis.json.
"""
