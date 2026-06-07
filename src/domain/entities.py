"""Core entity types for the identity graph.

These are the nodes in the Neo4j identity graph and the value objects that
flow through the platform. They use Pydantic for validation and serialization.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class KYCStatus(str, Enum):
    VERIFIED = "verified"
    PENDING = "pending"
    REJECTED = "rejected"
    ENHANCED_DD = "enhanced_due_diligence"


class AccountType(str, Enum):
    CHECKING = "checking"
    SAVINGS = "savings"
    CORPORATE = "corporate"
    TRUST = "trust"
    MULE_SUSPECTED = "mule_suspected"


class Currency(str, Enum):
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
    HKD = "HKD"
    SGD = "SGD"
    JPY = "JPY"
    CNY = "CNY"


class GeoLocation(BaseModel):
    """A geo-coordinate pair."""

    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)
    country_code: str = Field(min_length=2, max_length=2)
    city: str | None = None


class IPAddress(BaseModel):
    """An IP address with network metadata."""

    address: str
    asn: int | None = None
    country_code: str | None = None
    is_proxy: bool = False
    is_tor_exit: bool = False
    is_datacenter: bool = False


class Device(BaseModel):
    """A device fingerprint."""

    fingerprint: str
    device_type: str
    os_family: str | None = None
    browser_family: str | None = None
    first_seen: datetime
    last_seen: datetime
    is_known_trusted: bool = False


class Person(BaseModel):
    """A natural person in the identity graph."""

    id: UUID = Field(default_factory=uuid4)
    name: str
    kyc_status: KYCStatus = KYCStatus.PENDING
    country_code: str = Field(min_length=2, max_length=2)
    date_of_birth: datetime | None = None
    pep_status: bool = False  # Politically Exposed Person
    sanctions_match: bool = False
    risk_score: float = Field(ge=0.0, le=1.0, default=0.0)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Account(BaseModel):
    """A bank account in the identity graph."""

    id: UUID = Field(default_factory=uuid4)
    owner_person_id: UUID | None = None
    bank_identifier: str
    account_type: AccountType = AccountType.CHECKING
    opened_at: datetime
    country_code: str
    balance_band: str | None = None  # e.g., "0-10K", "10K-100K"
    is_dormant: bool = False
    is_mule: bool = False
    risk_score: float = Field(ge=0.0, le=1.0, default=0.0)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Counterparty(BaseModel):
    """The receiving party in a payment event."""

    account_id: UUID
    account: Account | None = None
    country_code: str
    is_new_beneficiary: bool = True
    account_age_days: int = 0
    bank_identifier: str | None = None
    name_on_account: str | None = None

    @field_validator("account_age_days")
    @classmethod
    def _non_negative_age(cls, v: int) -> int:
        if v < 0:
            raise ValueError("account_age_days must be >= 0")
        return v


__all__ = [
    "Account",
    "AccountType",
    "Counterparty",
    "Currency",
    "Device",
    "GeoLocation",
    "IPAddress",
    "KYCStatus",
    "Person",
]
