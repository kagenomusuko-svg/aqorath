"""Pure first-class OSC program management identity."""

from dataclasses import dataclass
from decimal import Decimal


def _require_positive_id(value, field_name):
    if type(value) is not int:
        raise TypeError(f"{field_name} must be int")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


def _require_text(value, field_name):
    if type(value) is not str:
        raise TypeError(f"{field_name} must be str")
    if not value or value.strip() != value:
        raise ValueError(f"{field_name} must be nonblank without surrounding whitespace")


@dataclass(frozen=True)
class Program:
    """Immutable management program owned by one accounting Entity."""

    id: int | None
    entity_id: int
    name: str
    description: str | None
    budget: Decimal | None

    def __post_init__(self):
        if self.id is not None:
            _require_positive_id(self.id, "id")
        _require_positive_id(self.entity_id, "entity_id")
        _require_text(self.name, "name")

        if self.description is not None:
            _require_text(self.description, "description")

        if self.budget is not None:
            if type(self.budget) is not Decimal:
                raise TypeError("budget must be Decimal or None")
            if not self.budget.is_finite() or self.budget < Decimal("0"):
                raise ValueError("budget must be finite and nonnegative")
