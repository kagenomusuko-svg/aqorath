"""Pure persisted AQR-013 custom-report preset configuration.

This value wraps the frozen CustomReportPackage contract with only reusable generation
configuration. It never contains report results, balances, SQL, renderer code or
accounting calculations.
"""

from dataclasses import dataclass

from .custom_report_package import CustomReportPackage


def _require_format(value):
    if type(value) is not str or not value or value.strip() != value:
        raise ValueError("format must be nonblank str without surrounding whitespace")


def _validate_parameters(value):
    if type(value) is not tuple:
        raise TypeError("item_parameters must be tuple")
    for item in value:
        if type(item) is not tuple:
            raise TypeError("each item_parameters entry must be tuple")
        seen = set()
        for pair in item:
            if type(pair) is not tuple or len(pair) != 2:
                raise TypeError("preset parameter must be a (key, value) tuple")
            key, parameter_value = pair
            if type(key) is not str or not key or key.strip() != key:
                raise ValueError("preset parameter key must be nonblank exact text")
            if key in seen:
                raise ValueError("preset parameter keys must be unique per report")
            seen.add(key)
            if type(parameter_value) is not str or not parameter_value or parameter_value.strip() != parameter_value:
                raise ValueError("preset parameter value must be nonblank exact text")


@dataclass(frozen=True)
class PersistedReportPreset:
    """One durable custom package plus its reusable, non-monetary options."""

    package: CustomReportPackage
    format: str
    item_parameters: tuple[tuple[tuple[str, str], ...], ...]

    def __post_init__(self):
        if not isinstance(self.package, CustomReportPackage):
            raise TypeError("package must be CustomReportPackage")
        if self.package.id is None:
            raise ValueError("persisted preset package must have identity")
        _require_format(self.format)
        _validate_parameters(self.item_parameters)
        if len(self.item_parameters) != len(self.package.included_reports):
            raise ValueError("item_parameters must align exactly with included_reports")
