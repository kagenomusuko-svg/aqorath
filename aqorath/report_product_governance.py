"""Pure AQR-013 governance metadata attached 1:1 to frozen ReportDefinition ids.

ReportDefinition remains the pre-existing authority for WHAT document exists. This
module supplies product-governance constraints that the frozen foundation deliberately
did not include. It never contains balances, queries, SQL, rendered output or fiscal
calculation.
"""

from dataclasses import dataclass


def _text(value, field_name):
    if type(value) is not str:
        raise TypeError(f"{field_name} must be str")
    if not value or value.strip() != value:
        raise ValueError(f"{field_name} must be nonblank without surrounding whitespace")


def _tokens(value, field_name):
    if type(value) is not tuple:
        raise TypeError(f"{field_name} must be tuple")
    seen = set()
    for token in value:
        _text(token, f"{field_name} item")
        if token in seen:
            raise ValueError(f"{field_name} must not contain duplicates")
        seen.add(token)


@dataclass(frozen=True)
class ReportProductGovernance:
    """Govern one frozen ReportDefinition without becoming another definition."""

    definition_id: int
    key: str
    report_type: str
    allowed_parameters: tuple[str, ...]
    allowed_dimensions: tuple[str, ...]
    period_mode: str
    version: str
    restrictions: tuple[str, ...] = ()

    def __post_init__(self):
        if type(self.definition_id) is not int or self.definition_id <= 0:
            raise ValueError("definition_id must be positive int")
        _text(self.key, "key")
        _text(self.report_type, "report_type")
        _tokens(self.allowed_parameters, "allowed_parameters")
        _tokens(self.allowed_dimensions, "allowed_dimensions")
        _text(self.period_mode, "period_mode")
        _text(self.version, "version")
        _tokens(self.restrictions, "restrictions")
        if self.period_mode not in {"range", "as_of"}:
            raise ValueError("period_mode must be 'range' or 'as_of'")
