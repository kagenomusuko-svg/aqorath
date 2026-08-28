"""Pure immutable official report preset value."""

from dataclasses import dataclass

from .report_definition import ReportDefinition


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


def _validate_included_reports(value):
    if type(value) is not tuple:
        raise TypeError("included_reports must be tuple")
    for report in value:
        if not isinstance(report, ReportDefinition):
            raise TypeError("included_reports items must be ReportDefinition")


def _validate_suggested_parameters(value):
    if type(value) is not tuple:
        raise TypeError("suggested_parameters must be tuple")

    seen = set()
    for item in value:
        if type(item) is not tuple:
            raise TypeError("suggested_parameters entries must be tuple")
        if len(item) != 2:
            raise ValueError(
                "suggested_parameters entries must contain exactly two items"
            )
        key, _opaque_value = item
        _require_text(key, "suggested parameter key")
        if key in seen:
            raise ValueError("suggested parameter keys must be unique")
        seen.add(key)


@dataclass(frozen=True)
class ReportPackage:
    """Describe one official initial selection of report definitions."""

    id: int | None
    name: str
    included_reports: tuple[ReportDefinition, ...]
    suggested_parameters: tuple
    is_official: bool = True

    def __post_init__(self):
        _require_optional_positive_id(self.id, "id")
        _require_text(self.name, "name")
        _validate_included_reports(self.included_reports)
        _validate_suggested_parameters(self.suggested_parameters)

        if type(self.is_official) is not bool:
            raise TypeError("is_official must be bool")
        if self.is_official is not True:
            raise ValueError("is_official must be True")
