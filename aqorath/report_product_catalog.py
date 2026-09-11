"""Governed V1 report-product catalog for AQR-013.

Official definitions remain pure ``ReportDefinition`` values.  This module adds only
product governance around those existing values: stable identities, allowed request
parameters, period semantics and official package presets.  It owns no accounting
math, persistence, rendering or alternate monetary truth.
"""

from .report_definition import ReportDefinition
from .report_package import ReportPackage


_FINANCIAL_FORMATS = ("json", "xlsx", "pdf")
_JSON_ONLY = ("json",)

TRIAL_BALANCE_PERIOD = ReportDefinition(
    id=1301,
    name="Balanza de comprobación",
    description="Saldos de apertura, cargos, abonos y saldos finales del período.",
    required_data=("accounts", "journal_entries", "journal_lines"),
    supported_formats=_FINANCIAL_FORMATS,
    requires_capabilities=(),
    forbidden_capabilities=(),
    required_fiscal_features=(),
    renderer_id="report_product.v1",
    query_template_id="period_trial_balance",
)

INCOME_STATEMENT_PERIOD = ReportDefinition(
    id=1302,
    name="Estado de resultados",
    description="Ingresos, costos, gastos y resultado correspondientes al período.",
    required_data=("accounts", "journal_entries", "journal_lines"),
    supported_formats=_FINANCIAL_FORMATS,
    requires_capabilities=(),
    forbidden_capabilities=(),
    required_fiscal_features=(),
    renderer_id="report_product.v1",
    query_template_id="period_income_statement",
)

BALANCE_SHEET_AS_OF = ReportDefinition(
    id=1303,
    name="Estado de situación financiera",
    description="Activos, pasivos y patrimonio al cierre del período solicitado.",
    required_data=("accounts", "journal_entries", "journal_lines"),
    supported_formats=_FINANCIAL_FORMATS,
    requires_capabilities=(),
    forbidden_capabilities=(),
    required_fiscal_features=(),
    renderer_id="report_product.v1",
    query_template_id="as_of_balance_sheet",
)

JOURNAL_PERIOD = ReportDefinition(
    id=1304,
    name="Diario",
    description="Pólizas y líneas contables del período en orden cronológico.",
    required_data=("journal_entries", "journal_lines", "accounts"),
    supported_formats=_JSON_ONLY,
    requires_capabilities=(),
    forbidden_capabilities=(),
    required_fiscal_features=(),
    renderer_id="report_product.json",
    query_template_id="period_journal",
)

GENERAL_LEDGER_PERIOD = ReportDefinition(
    id=1305,
    name="Mayor",
    description="Movimientos y saldos por cuenta reconciliados con la balanza del período.",
    required_data=("journal_entries", "journal_lines", "accounts"),
    supported_formats=_JSON_ONLY,
    requires_capabilities=(),
    forbidden_capabilities=(),
    required_fiscal_features=(),
    renderer_id="report_product.json",
    query_template_id="period_general_ledger",
)

OSC_FUNDS_AS_OF = ReportDefinition(
    id=1310,
    name="Fondos y trazabilidad OSC",
    description="Disponibilidad y trazabilidad de fondos derivadas de AQR-008.",
    required_data=("funds", "journal_lines"),
    supported_formats=_JSON_ONLY,
    requires_capabilities=(),
    forbidden_capabilities=(),
    required_fiscal_features=(),
    renderer_id="report_product.json",
    query_template_id="as_of_osc_funds",
)

INVENTORY_AS_OF = ReportDefinition(
    id=1320,
    name="Existencias y valuación de inventario",
    description="Existencia, valuación y promedio consolidado por AQR-012 a una fecha.",
    required_data=("inventory_products", "inventory_movements", "journal_lines"),
    supported_formats=_JSON_ONLY,
    requires_capabilities=("inventory_control",),
    forbidden_capabilities=(),
    required_fiscal_features=(),
    renderer_id="report_product.json",
    query_template_id="as_of_inventory",
)

FISCAL_EVIDENCE_PERIOD = ReportDefinition(
    id=1330,
    name="Tratamientos fiscales aplicados",
    description="Auditoría fiscal AQR-011 ya persistida para operaciones del período.",
    required_data=("fiscal_posting_audit", "journal_entries"),
    supported_formats=_JSON_ONLY,
    requires_capabilities=(),
    forbidden_capabilities=(),
    required_fiscal_features=(),
    renderer_id="report_product.json",
    query_template_id="period_fiscal_evidence",
)

CFDI_EVIDENCE_PERIOD = ReportDefinition(
    id=1331,
    name="CFDI documentales",
    description="Evidencia CFDI AQR-010 importada durante el rango solicitado.",
    required_data=("cfdi_sources",),
    supported_formats=_JSON_ONLY,
    requires_capabilities=(),
    forbidden_capabilities=(),
    required_fiscal_features=(),
    renderer_id="report_product.json",
    query_template_id="period_cfdi_evidence",
)

V1_REPORT_DEFINITIONS = (
    TRIAL_BALANCE_PERIOD,
    INCOME_STATEMENT_PERIOD,
    BALANCE_SHEET_AS_OF,
    JOURNAL_PERIOD,
    GENERAL_LEDGER_PERIOD,
    OSC_FUNDS_AS_OF,
    INVENTORY_AS_OF,
    FISCAL_EVIDENCE_PERIOD,
    CFDI_EVIDENCE_PERIOD,
)

FINANCIAL_PERIOD_PACKAGE = ReportPackage(
    id=13001,
    name="Paquete financiero por período",
    included_reports=(
        TRIAL_BALANCE_PERIOD,
        INCOME_STATEMENT_PERIOD,
        BALANCE_SHEET_AS_OF,
    ),
    suggested_parameters=(("period_semantics", "inclusive_range"),),
)

# Product-policy metadata deliberately remains separate from ReportDefinition and
# ReportRequest. It governs what the request MAY contain; it never stores figures.
_REPORT_POLICIES = {
    1301: ("trial_balance", "inclusive_range"),
    1302: ("income_statement", "inclusive_range"),
    1303: ("balance_sheet", "as_of_range_end"),
    1304: ("journal", "inclusive_range"),
    1305: ("general_ledger", "inclusive_range"),
    1310: ("osc_funds", "as_of_range_end"),
    1320: ("inventory", "as_of_range_end"),
    1330: ("fiscal_evidence", "inclusive_range"),
    1331: ("cfdi_evidence", "inclusive_range"),
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
    product_type, period_semantics = _REPORT_POLICIES[definition.id]
    return {
        "product_type": product_type,
        "version": "1",
        "period_semantics": period_semantics,
        "allowed_filters": (),
        "allowed_dimensions": (),
    }


def get_financial_period_package():
    """Return the official editable initial selection for the first V1 vertical."""
    return FINANCIAL_PERIOD_PACKAGE
