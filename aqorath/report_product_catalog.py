"""Governed V1 report-product catalog for AQR-013.

Official definitions remain pure ``ReportDefinition`` values.  This module adds only
product governance around those existing values: stable identities, allowed request
parameters, period semantics and official package presets.  It owns no accounting
math, persistence, rendering or alternate monetary truth.
"""

from .report_definition import ReportDefinition
from .report_package import ReportPackage


TRIAL_BALANCE_PERIOD = ReportDefinition(
    id=1301,
    name="Balanza de comprobación",
    description="Saldos de apertura, cargos, abonos y saldos finales del período.",
    required_data=("accounts", "journal_entries", "journal_lines"),
    supported_formats=("json",),
    requires_capabilities=(),
    forbidden_capabilities=(),
    required_fiscal_features=(),
    renderer_id="report_product.json",
    query_template_id="period_trial_balance",
)

INCOME_STATEMENT_PERIOD = ReportDefinition(
    id=1302,
    name="Estado de resultados",
    description="Ingresos, costos, gastos y resultado correspondientes al período.",
    required_data=("accounts", "journal_entries", "journal_lines"),
    supported_formats=("json",),
    requires_capabilities=(),
    forbidden_capabilities=(),
    required_fiscal_features=(),
    renderer_id="report_product.json",
    query_template_id="period_income_statement",
)

BALANCE_SHEET_AS_OF = ReportDefinition(
    id=1303,
    name="Estado de situación financiera",
    description="Activos, pasivos y patrimonio al cierre del período solicitado.",
    required_data=("accounts", "journal_entries", "journal_lines"),
    supported_formats=("json",),
    requires_capabilities=(),
    forbidden_capabilities=(),
    required_fiscal_features=(),
    renderer_id="report_product.json",
    query_template_id="as_of_balance_sheet",
)

V1_REPORT_DEFINITIONS = (
    TRIAL_BALANCE_PERIOD,
    INCOME_STATEMENT_PERIOD,
    BALANCE_SHEET_AS_OF,
)

FINANCIAL_PERIOD_PACKAGE = ReportPackage(
    id=13001,
    name="Paquete financiero por período",
    included_reports=V1_REPORT_DEFINITIONS,
    suggested_parameters=(("period_semantics", "inclusive_range"),),
)

# Product-policy metadata deliberately remains separate from ReportDefinition and
# ReportRequest.  It governs what the request MAY contain; it never stores figures.
_REPORT_POLICIES = {
    1301: {
        "product_type": "trial_balance",
        "version": "1",
        "period_semantics": "inclusive_range",
        "allowed_filters": (),
        "allowed_dimensions": (),
    },
    1302: {
        "product_type": "income_statement",
        "version": "1",
        "period_semantics": "inclusive_range",
        "allowed_filters": (),
        "allowed_dimensions": (),
    },
    1303: {
        "product_type": "balance_sheet",
        "version": "1",
        "period_semantics": "as_of_range_end",
        "allowed_filters": (),
        "allowed_dimensions": (),
    },
}


def list_report_definitions():
    """Return the deterministic governed V1 report catalog."""
    return V1_REPORT_DEFINITIONS


def get_report_definition(definition_id):
    """Resolve one governed report definition by stable identity."""
    if type(definition_id) is not int:
        raise TypeError("definition_id must be int")
    for definition in V1_REPORT_DEFINITIONS:
        if definition.id == definition_id:
            return definition
    raise LookupError(f"report definition {definition_id} is not governed by V1")


def get_report_policy(definition_id):
    """Return an immutable-by-copy policy view for one governed definition."""
    definition = get_report_definition(definition_id)
    policy = _REPORT_POLICIES[definition.id]
    return {
        "product_type": policy["product_type"],
        "version": policy["version"],
        "period_semantics": policy["period_semantics"],
        "allowed_filters": tuple(policy["allowed_filters"]),
        "allowed_dimensions": tuple(policy["allowed_dimensions"]),
    }


def get_financial_period_package():
    """Return the official editable initial selection for the first V1 vertical."""
    return FINANCIAL_PERIOD_PACKAGE
