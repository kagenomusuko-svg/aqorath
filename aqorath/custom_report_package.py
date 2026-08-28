"""Pure immutable saved custom report selection."""

from dataclasses import dataclass
from datetime import datetime

from .report_definition import ReportDefinition


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


def _validate_included_reports(value):
    if type(value) is not tuple:
        raise TypeError("included_reports must be tuple")
    for report in value:
        if not isinstance(report, ReportDefinition):
            raise TypeError("included_reports items must be ReportDefinition")


@dataclass(frozen=True)
class CustomReportPackage:
    """Describe one owner-scoped saved report selection."""

    id: int | None
    owner_entity_id: int
    name: str
    included_reports: tuple[ReportDefinition, ...]
    created_at: datetime

    def __post_init__(self):
        _require_optional_positive_id(self.id, "id")
        _require_positive_id(self.owner_entity_id, "owner_entity_id")
        _require_text(self.name, "name")
        _validate_included_reports(self.included_reports)
        if type(self.created_at) is not datetime:
            raise TypeError("created_at must be datetime")
