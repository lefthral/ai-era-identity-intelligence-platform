"""Domain layer: pure business logic with zero cloud SDK imports.

The domain layer is the heart of the platform. It contains the entities,
value objects, and core invariants. It must be possible to import this
module in a unit test with no AWS, GCP, or Kafka credentials configured.
"""

from src.domain.decisions import (
    AuditLogEntry,
    Decision,
    DecisionAction,
    FeatureSnapshot,
    ModelVersion,
    PolicyVersion,
    RuleHit,
)
from src.domain.entities import (
    Account,
    Counterparty,
    Currency,
    Device,
    GeoLocation,
    IPAddress,
    Person,
)
from src.domain.events import (
    EventType,
    GroundTruthLabel,
    PaymentEvent,
    RailType,
)

__all__ = [
    "Account",
    "AuditLogEntry",
    "Counterparty",
    "Currency",
    "Decision",
    "DecisionAction",
    "Device",
    "EventType",
    "FeatureSnapshot",
    "GeoLocation",
    "GroundTruthLabel",
    "IPAddress",
    "ModelVersion",
    "PaymentEvent",
    "Person",
    "PolicyVersion",
    "RailType",
    "RuleHit",
]
