"""Pure immutable analytical-dimension domain values."""

from dataclasses import dataclass
from typing import Optional


def _require_optional_positive_id(value, field_name):
    if value is None:
        return
    _require_positive_id(value, field_name)


def _require_positive_id(value, field_name):
    if type(value) is not int:
        raise TypeError(f"{field_name} must be int")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


def _require_text(value, field_name):
    if type(value) is not str:
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


@dataclass(frozen=True)
class AnalyticalDimension:
    """One explicit analytical axis owned by an Entity."""

    id: Optional[int]
    entity_id: int
    key: str
    name: str

    def __post_init__(self):
        _require_optional_positive_id(self.id, "id")
        _require_positive_id(self.entity_id, "entity_id")
        _require_text(self.key, "key")
        _require_text(self.name, "name")


@dataclass(frozen=True)
class AnalyticalDimensionValue:
    """One explicit value belonging to one analytical axis."""

    id: Optional[int]
    dimension_id: int
    code: str
    name: str

    def __post_init__(self):
        _require_optional_positive_id(self.id, "id")
        _require_positive_id(self.dimension_id, "dimension_id")
        _require_text(self.code, "code")
        _require_text(self.name, "name")


@dataclass(frozen=True)
class AnalyticalDimensionAssignment:
    """Immutable projection of one value assigned to one existing ledger line."""

    journal_line_id: int
    dimension_id: int
    dimension_key: str
    dimension_name: str
    value_id: int
    value_code: str
    value_name: str

    def __post_init__(self):
        _require_positive_id(self.journal_line_id, "journal_line_id")
        _require_positive_id(self.dimension_id, "dimension_id")
        _require_text(self.dimension_key, "dimension_key")
        _require_text(self.dimension_name, "dimension_name")
        _require_positive_id(self.value_id, "value_id")
        _require_text(self.value_code, "value_code")
        _require_text(self.value_name, "value_name")
