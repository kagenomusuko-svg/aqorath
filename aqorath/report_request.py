"""Pure immutable request describing one concrete report generation intent."""

from dataclasses import dataclass
from datetime import date


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


def _require_text(value, field_name):
    if type(value) is not str:
        raise TypeError(f"{field_name} must be str")
    if not value or value.strip() != value:
        raise ValueError(
            f"{field_name} must be nonblank without surrounding whitespace"
        )


def _require_exact_date(value, field_name):
    if type(value) is not date:
        raise TypeError(f"{field_name} must be date")


def _validate_filters(filters):
    if type(filters) is not tuple:
        raise TypeError("filters must be tuple")

    seen = set()
    for item in filters:
        if type(item) is not tuple:
            raise TypeError("filter entries must be tuple")
        if len(item) != 2:
            raise ValueError("filter entries must contain exactly two items")
        key, _value = item
        _require_text(key, "filter key")
        if key in seen:
            raise ValueError("filter keys must be unique")
        seen.add(key)


def _validate_dimensions(dimensions):
    if type(dimensions) is not tuple:
        raise TypeError("dimensions_to_group must be tuple")

    seen = set()
    for value in dimensions:
        _require_text(value, "dimension")
        if value in seen:
            raise ValueError("dimensions_to_group must be unique")
        seen.add(value)


@dataclass(frozen=True)
class ReportRequest:
    """Describe one concrete report request without resolving or executing it."""

    id: int | None
    report_definition_id: int
    entity_id: int
    from_date: date
    to_date: date
    as_of_date: date | None
    filters: tuple
    dimensions_to_group: tuple[str, ...]
    format: str

    def __post_init__(self):
        _require_optional_positive_id(self.id, "id")
        _require_positive_id(self.report_definition_id, "report_definition_id")
        _require_positive_id(self.entity_id, "entity_id")

        _require_exact_date(self.from_date, "from_date")
        _require_exact_date(self.to_date, "to_date")
        if self.to_date < self.from_date:
            raise ValueError("to_date cannot precede from_date")

        if self.as_of_date is not None:
            _require_exact_date(self.as_of_date, "as_of_date")

        _validate_filters(self.filters)
        _validate_dimensions(self.dimensions_to_group)
        _require_text(self.format, "format")
