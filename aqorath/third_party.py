"""Pure ThirdParty counterparty domain for one Aqorath Entity."""

from dataclasses import dataclass
from typing import Optional


_ALLOWED_PARTY_TYPES = frozenset(
    {
        "customer",
        "supplier",
        "donor",
        "creditor",
        "debtor",
        "employee",
        "other",
    }
)


def _require_nonempty_text(value, field_name):
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be nonempty")


def _require_optional_text(value, field_name):
    if value is not None:
        _require_nonempty_text(value, field_name)


def _require_optional_id(value, field_name):
    if value is None:
        return
    if type(value) is not int:
        raise TypeError(f"{field_name} must be int or None")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


def _require_positive_id(value, field_name):
    if type(value) is not int:
        raise TypeError(f"{field_name} must be int")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


@dataclass(frozen=True)
class ThirdParty:
    """Immutable counterparty identity owned by exactly one accounting Entity."""

    id: Optional[int]
    entity_id: int
    name: str
    rfc: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    party_type: str
    address: Optional[str]
    contact_person: Optional[str]
    notes: Optional[str]
    is_active: bool

    def __post_init__(self):
        _require_optional_id(self.id, "id")
        _require_positive_id(self.entity_id, "entity_id")
        _require_nonempty_text(self.name, "name")
        _require_optional_text(self.rfc, "rfc")
        _require_optional_text(self.email, "email")
        _require_optional_text(self.phone, "phone")
        _require_nonempty_text(self.party_type, "party_type")
        if self.party_type not in _ALLOWED_PARTY_TYPES:
            raise ValueError(f"unsupported party_type: {self.party_type}")
        _require_optional_text(self.address, "address")
        _require_optional_text(self.contact_person, "contact_person")
        _require_optional_text(self.notes, "notes")
        if type(self.is_active) is not bool:
            raise TypeError("is_active must be bool")
