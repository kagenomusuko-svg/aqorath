"""Pure base economic event domain value."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any


def _require_optional_positive_id(value, field_name):
    if value is None:
        return
    if type(value) is not int:
        raise TypeError(f"{field_name} must be int or None")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


def _require_text(value, field_name):
    if type(value) is not str:
        raise TypeError(f"{field_name} must be text")
    if not value or value.strip() != value:
        raise ValueError(
            f"{field_name} must be nonblank without surrounding whitespace"
        )


def _require_optional_text(value, field_name):
    if value is None:
        return
    _require_text(value, field_name)


@dataclass(frozen=True)
class EconomicEvent:
    id: int | None
    event_type: str
    date: datetime
    amount: Decimal
    description: str
    third_party: str | None
    context: dict[str, Any]

    def __post_init__(self):
        _require_optional_positive_id(self.id, "id")
        _require_text(self.event_type, "event_type")

        if type(self.date) is not datetime:
            raise TypeError("date must be datetime")

        if type(self.amount) is not Decimal:
            raise TypeError("amount must be Decimal")
        if not self.amount.is_finite():
            raise ValueError("amount must be finite")

        _require_text(self.description, "description")
        _require_optional_text(self.third_party, "third_party")

        if type(self.context) is not dict:
            raise TypeError("context must be dict")
        for key in self.context:
            if type(key) is not str:
                raise TypeError("context keys must be text")
