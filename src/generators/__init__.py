"""Synthetic event generators.

Each generator replays a documented real-world AI-fraud pattern with
deterministic seeding so the demo is reproducible. The patterns are:

- arup_pattern.py: the $25.6M Arup deepfake wire-fraud heist (Jan 2024)
- singapore_pattern.py: the $499K Singapore finance-director deepfake scam (Mar 2025)
- baseline.py: 10K users, realistic bank-mix traffic, ~500 txn/sec

All generators emit PaymentEvent instances that flow through the same
event backbone as production traffic.

Note: imports are deferred to function-call time so that other parts
of the platform (e.g., the API) can run without faker installed.
"""

__all__ = [
    "generate_arup_events",
    "generate_baseline_events",
    "generate_events",
    "generate_singapore_events",
]


def __getattr__(name: str):
    """PEP 562 lazy module attribute access."""
    if name == "generate_arup_events":
        from src.generators.arup_pattern import generate_arup_events

        return generate_arup_events
    if name == "generate_singapore_events":
        from src.generators.singapore_pattern import generate_singapore_events

        return generate_singapore_events
    if name == "generate_baseline_events":
        from src.generators.baseline import generate_baseline_events

        return generate_baseline_events
    if name == "generate_events":
        from src.generators.runner import generate_events

        return generate_events
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
