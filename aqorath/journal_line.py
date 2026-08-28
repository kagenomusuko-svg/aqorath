"""Pure immutable journal-line domain value."""

from dataclasses import dataclass
from decimal import Decimal

from .account import Account
from .analytical_dimension import AnalyticalDimensionValue


def _require_optional_positive_id(value, field_name):
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


def _require_money(value, field_name):
    if type(value) is not Decimal:
        raise TypeError(f"{field_name} must be Decimal")
    if not value.is_finite():
        raise ValueError(f"{field_name} must be finite")
    if value < Decimal("0"):
        raise ValueError(f"{field_name} must be nonnegative")


def _require_optional_text(value, field_name):
    if value is None:
        return
    if type(value) is not str:
        raise TypeError(f"{field_name} must be str or None")
    if not value or value.strip() != value:
        raise ValueError(
            f"{field_name} must be nonblank without surrounding whitespace"
        )


@dataclass(frozen=True)
class JournalLine:
    """Describe one exact debit-or-credit line with optional analytical values."""

    id: int | None
    entry_id: int
    account: Account
    debit: Decimal
    credit: Decimal
    description: str | None = None
    analytics: tuple[AnalyticalDimensionValue, ...] = ()

    def __post_init__(self):
        _require_optional_positive_id(self.id, "id")
        _require_positive_id(self.entry_id, "entry_id")

        if not isinstance(self.account, Account):
            raise TypeError("account must be Account")

        _require_money(self.debit, "debit")
        _require_money(self.credit, "credit")

        debit_positive = self.debit > Decimal("0")
        credit_positive = self.credit > Decimal("0")
        if debit_positive == credit_positive:
            raise ValueError("exactly one of debit or credit must be positive")

        _require_optional_text(self.description, "description")

        if type(self.analytics) is not tuple:
            raise TypeError("analytics must be tuple")

        dimension_ids = set()
        for value in self.analytics:
            if not isinstance(value, AnalyticalDimensionValue):
                raise TypeError("analytics items must be AnalyticalDimensionValue")
            if value.dimension_id in dimension_ids:
                raise ValueError("analytics cannot repeat a dimension")
            dimension_ids.add(value.dimension_id)
