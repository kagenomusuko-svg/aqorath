"""Pure immutable journal-entry domain value."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from .journal_line import JournalLine


_ALLOWED_STATES = frozenset({"draft", "posted", "reversed"})


def _require_optional_positive_id(value, field_name):
    if value is None:
        return
    if type(value) is not int:
        raise TypeError(f"{field_name} must be int or None")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


def _require_text(value, field_name):
    if type(value) is not str:
        raise TypeError(f"{field_name} must be str")
    if not value or value.strip() != value:
        raise ValueError(
            f"{field_name} must be nonblank without surrounding whitespace"
        )


def _authoritative_signed_value(entry):
    """Resolve the signed-value authority lazily to preserve the dependency boundary."""
    from .account_balance import journal_entry_signed_balance

    return journal_entry_signed_balance(entry)


@dataclass(frozen=True)
class JournalEntry:
    """Describe one immutable accounting entry and its exact lifecycle state."""

    id: int | None
    date: datetime
    concept: str
    lines: tuple[JournalLine, ...]
    period_id: int | None = None
    fiscal_rule_set_id: int | None = None
    state: str = "draft"

    def __post_init__(self):
        _require_optional_positive_id(self.id, "id")

        if type(self.date) is not datetime:
            raise TypeError("date must be datetime")

        _require_text(self.concept, "concept")

        if type(self.lines) is not tuple:
            raise TypeError("lines must be tuple")
        for line in self.lines:
            if not isinstance(line, JournalLine):
                raise TypeError("lines items must be JournalLine")

        _require_optional_positive_id(self.period_id, "period_id")
        _require_optional_positive_id(
            self.fiscal_rule_set_id,
            "fiscal_rule_set_id",
        )

        if type(self.state) is not str:
            raise TypeError("state must be str")
        if self.state not in _ALLOWED_STATES:
            raise ValueError("state must be draft, posted, or reversed")

        if self.state in {"posted", "reversed"} and not self.is_balanced():
            raise ValueError("posted or reversed entry must be balanced")

    def is_balanced(self):
        """Return whether the authoritative exact signed value is zero."""
        return _authoritative_signed_value(self) == Decimal("0")
