"""Pure first-class OSC donation resource event."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


def _require_positive_id(value, field_name):
    if type(value) is not int:
        raise TypeError(f"{field_name} must be int")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


def _require_optional_positive_id(value, field_name):
    if value is None:
        return
    _require_positive_id(value, field_name)


def _require_optional_text(value, field_name):
    if value is None:
        return
    if type(value) is not str:
        raise TypeError(f"{field_name} must be str or None")
    if not value or value.strip() != value:
        raise ValueError(f"{field_name} must be nonblank without surrounding whitespace")


@dataclass(frozen=True)
class Donation:
    """Immutable OSC donation identity owned by one accounting Entity."""

    id: int | None
    entity_id: int
    date: datetime
    amount: Decimal
    donor_third_party_id: int | None
    purpose: str | None
    is_restricted: bool

    def __post_init__(self):
        _require_optional_positive_id(self.id, "id")
        _require_positive_id(self.entity_id, "entity_id")
        if type(self.date) is not datetime:
            raise TypeError("date must be datetime")
        if type(self.amount) is not Decimal:
            raise TypeError("amount must be Decimal")
        if not self.amount.is_finite() or self.amount <= Decimal("0"):
            raise ValueError("amount must be finite and positive")
        _require_optional_positive_id(
            self.donor_third_party_id,
            "donor_third_party_id",
        )
        _require_optional_text(self.purpose, "purpose")
        if type(self.is_restricted) is not bool:
            raise TypeError("is_restricted must be bool")
