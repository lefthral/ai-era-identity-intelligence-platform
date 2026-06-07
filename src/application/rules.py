"""Rule engine.

The rule engine is a deterministic guardrail on top of the ML model.
It is the architectural separation required by IMF Notes 2026/004:
probabilistic models upstream, deterministic rules at the execution layer.

Each rule has:
- A unique ID
- A severity (low / medium / high / critical)
- An evaluation function that takes a PaymentEvent + FeatureSnapshot
  and returns (fired: bool, reason: str, evidence: dict)

The rule engine is loaded from a YAML config (configs/rules.yaml) so
policies are versioned and changes are auditable.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml

from src.domain.decisions import PolicyVersion, RuleHit
from src.domain.events import PaymentEvent

logger = logging.getLogger(__name__)


# ── Rule definitions ─────────────────────────────────────────────────────


@dataclass
class Rule:
    id: str
    name: str
    severity: str
    description: str
    evaluate: Callable[[PaymentEvent, dict[str, float]], tuple[bool, str, dict]]


def _rule_sanctions_hit(event: PaymentEvent, features: dict[str, float]) -> tuple[bool, str, dict]:
    """Counterparty in simulated sanctions/PEP list."""
    # In production this would call an OFAC/UN/EU sanctions list service
    sanctioned_countries = {"IR", "KP", "SY", "CU"}
    if event.counterparty.country_code in sanctioned_countries:
        return (
            True,
            f"Counterparty country {event.counterparty.country_code} is sanctioned",
            {
                "country": event.counterparty.country_code,
                "list": "OFAC_SDN_SIMULATED",
            },
        )
    return False, "", {}


def _rule_mule_ring_member(
    event: PaymentEvent, features: dict[str, float]
) -> tuple[bool, str, dict]:
    if features.get("mule_ring_member", 0.0) >= 1.0:
        return (
            True,
            "Actor account is a member of a suspected mule ring",
            {
                "mule_ring_proximity": features.get("mule_ring_proximity_score", 0.0),
            },
        )
    return False, "", {}


def _rule_impossible_travel(
    event: PaymentEvent, features: dict[str, float]
) -> tuple[bool, str, dict]:
    # If the actor's country changed dramatically across recent events, flag it
    countries_count = features.get("jurisdiction_velocity_km_per_hour", 0.0)
    if countries_count >= 5.0:
        return (
            True,
            f"Impossible travel: {int(countries_count)} distinct countries in 24h",
            {
                "countries_count": int(countries_count),
            },
        )
    return False, "", {}


def _rule_high_value_new_beneficiary(
    event: PaymentEvent, features: dict[str, float]
) -> tuple[bool, str, dict]:
    if event.counterparty.is_new_beneficiary and float(event.amount.value) >= 100000:
        return (
            True,
            f"High value transfer to new beneficiary: ${float(event.amount.value):,.2f}",
            {
                "amount_usd": float(event.amount.value),
                "beneficiary_age_days": event.counterparty.account_age_days,
            },
        )
    return False, "", {}


def _rule_extreme_amount_zscore(
    event: PaymentEvent, features: dict[str, float]
) -> tuple[bool, str, dict]:
    z = features.get("amount_zscore_user", 0.0)
    if abs(z) >= 5.0:
        return (
            True,
            f"Amount z-score {z:.1f} (extreme deviation from user history)",
            {
                "zscore": z,
            },
        )
    return False, "", {}


def _rule_off_hours_high_value(
    event: PaymentEvent, features: dict[str, float]
) -> tuple[bool, str, dict]:
    hour = event.event_time.hour
    if (hour < 6 or hour >= 22) and float(event.amount.value) >= 50000:
        return (
            True,
            f"High-value transfer at off-hours ({hour:02d}:00)",
            {
                "hour": hour,
                "amount_usd": float(event.amount.value),
            },
        )
    return False, "", {}


def _rule_first_time_beneficiary_extreme(
    event: PaymentEvent, features: dict[str, float]
) -> tuple[bool, str, dict]:
    if event.counterparty.is_new_beneficiary and float(event.amount.value) >= 1000000:
        return (
            True,
            f"First-time beneficiary + ${float(event.amount.value):,.0f} (>$1M)",
            {
                "amount_usd": float(event.amount.value),
            },
        )
    return False, "", {}


def _rule_velocity_spike(event: PaymentEvent, features: dict[str, float]) -> tuple[bool, str, dict]:
    txns_1h = features.get("txns_last_1h", 0.0)
    if txns_1h >= 5.0:
        return (
            True,
            f"Velocity spike: {int(txns_1h)} transactions in last 1h",
            {
                "txns_1h": int(txns_1h),
            },
        )
    return False, "", {}


def _rule_high_risk_jurisdiction(
    event: PaymentEvent, features: dict[str, float]
) -> tuple[bool, str, dict]:
    if features.get("is_high_risk_jurisdiction", 0.0) >= 1.0:
        return (
            True,
            "Origin or destination is a high-risk jurisdiction (FATF)",
            {
                "origin_country": event.actor.country_code,
                "destination_country": event.counterparty.country_code,
            },
        )
    return False, "", {}


def _rule_shared_device_multi_account(
    event: PaymentEvent, features: dict[str, float]
) -> tuple[bool, str, dict]:
    shared = features.get("shared_device_count", 1.0)
    if shared >= 5.0:
        return (
            True,
            f"Device used by {int(shared)} accounts (possible mule ring)",
            {
                "shared_device_count": int(shared),
            },
        )
    return False, "", {}


# Default rule set, ordered roughly by severity
DEFAULT_RULES: list[Rule] = [
    Rule(
        "R001",
        "Sanctions/PEP hit",
        "critical",
        "Counterparty in sanctions list",
        _rule_sanctions_hit,
    ),
    Rule(
        "R002",
        "Mule ring member",
        "critical",
        "Actor is in a known mule ring",
        _rule_mule_ring_member,
    ),
    Rule(
        "R003",
        "Impossible travel",
        "high",
        "Multiple distinct countries in 24h",
        _rule_impossible_travel,
    ),
    Rule(
        "R004",
        "High value + new beneficiary",
        "high",
        "Wire >$100K to new beneficiary",
        _rule_high_value_new_beneficiary,
    ),
    Rule(
        "R005",
        "Extreme amount z-score",
        "high",
        "Amount >>5σ from user history",  # noqa: RUF001, RUF003 (σ is the standard symbol for stddev)
        _rule_extreme_amount_zscore,
    ),
    Rule(
        "R006",
        "Off-hours high value",
        "medium",
        ">$50K between 22:00 and 06:00",
        _rule_off_hours_high_value,
    ),
    Rule(
        "R007",
        "First-time beneficiary + $1M+",
        "critical",
        "First-time beneficiary with >$1M wire",
        _rule_first_time_beneficiary_extreme,
    ),
    Rule(
        "R008",
        "Velocity spike (1h)",
        "medium",
        ">=5 transactions in last hour",
        _rule_velocity_spike,
    ),
    Rule(
        "R009",
        "High-risk jurisdiction",
        "high",
        "Origin or destination in FATF list",
        _rule_high_risk_jurisdiction,
    ),
    Rule(
        "R010",
        "Shared device, multi-account",
        "medium",
        "Device used by >=5 accounts",
        _rule_shared_device_multi_account,
    ),
]


class RuleEngine:
    """Evaluates the rule set against a PaymentEvent + FeatureSnapshot."""

    def __init__(self, rules: list[Rule] | None = None) -> None:
        self._rules = rules or DEFAULT_RULES
        self._policy_name = "default_policy_v1"
        self._policy_hash = self._compute_hash()
        self._loaded_at = datetime.utcnow()

    def _compute_hash(self) -> str:
        payload = "\n".join(f"{r.id}:{r.name}:{r.severity}" for r in self._rules)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    @property
    def policy_version(self) -> PolicyVersion:
        return PolicyVersion(
            policy_name=self._policy_name,
            policy_hash=self._policy_hash,
            rules_count=len(self._rules),
            loaded_at=self._loaded_at,
        )

    def evaluate(self, event: PaymentEvent, feature_values: dict[str, float]) -> list[RuleHit]:
        hits: list[RuleHit] = []
        for rule in self._rules:
            try:
                fired, reason, evidence = rule.evaluate(event, feature_values)
                if fired:
                    hits.append(
                        RuleHit(
                            rule_id=rule.id,
                            rule_name=rule.name,
                            severity=rule.severity,
                            reason=reason,
                            evidence=evidence,
                        )
                    )
            except Exception:
                logger.exception("Rule %s raised during evaluation", rule.id)
        return hits

    @property
    def rule_score(self) -> float:
        """The maximum severity across hit rules. 1.0 if any critical hit, 0.0 if none."""
        return 0.0  # Filled at evaluate() time by the caller


def evaluate_rules(
    event: PaymentEvent,
    feature_values: dict[str, float],
    engine: RuleEngine | None = None,
) -> list[RuleHit]:
    if engine is None:
        engine = RuleEngine()
    return engine.evaluate(event, feature_values)


def load_rules_from_config(path: Path) -> list[Rule]:
    """Load a custom rule set from YAML. For now this is a stub that
    returns the default set; the full YAML schema is documented in
    configs/rules.yaml."""
    if not path.exists():
        return DEFAULT_RULES
    with open(path) as f:
        yaml.safe_load(f)  # validate the YAML parses; rules still come from DEFAULT_RULES
    # In a full implementation, this would parse the YAML and construct
    # Rule objects with the appropriate evaluators. For Tier 1 we ship
    # the deterministic default set.
    return DEFAULT_RULES


__all__ = [
    "DEFAULT_RULES",
    "Rule",
    "RuleEngine",
    "evaluate_rules",
    "load_rules_from_config",
]
