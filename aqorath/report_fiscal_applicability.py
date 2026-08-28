"""Pure point-in-time fiscal applicability for report definitions."""

from datetime import date

from .entity import FiscalProfile
from .report_definition import ReportDefinition


def is_report_definition_fiscally_applicable_on(
    definition,
    fiscal_profile,
    effective_date,
):
    """Return whether explicit fiscal features apply on one explicit date."""
    if not isinstance(definition, ReportDefinition):
        raise TypeError("definition must be ReportDefinition")
    if not isinstance(fiscal_profile, FiscalProfile):
        raise TypeError("fiscal_profile must be FiscalProfile")
    if type(effective_date) is not date:
        raise TypeError("effective_date must be date")

    if effective_date < fiscal_profile.effective_from:
        return False
    if (
        fiscal_profile.effective_to is not None
        and effective_date > fiscal_profile.effective_to
    ):
        return False

    present = set(fiscal_profile.tax_characteristics)
    return set(definition.required_fiscal_features).issubset(present)
