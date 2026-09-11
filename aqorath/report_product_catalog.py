"""Governed AQR-013 report products and official packages.

The catalog describes information products only. It owns no balances, SQL, fiscal
classification, rendering or generated results. Runtime execution resolves these
opaque query/renderer identifiers through the existing reporting authorities.
"""

from .report_definition import ReportDefinition
from .report_package import ReportPackage


TRIAL_BALANCE_PERIOD = ReportDefinition(
    id=1301,
    name="Balanza por período",
    description="Balanza con saldo inicial, cargos, abonos y saldo final para un rango.",
    required_data=("accounts", "journal_entries", "journal_lines"),
    supported_formats=("json", "xlsx"),
    requires_capabilities=(),
    forbidden_capabilities=(),
    required_fiscal_features=(),
    renderer_id="period_trial_balance",
    query_template_id="period_trial_balance",
    key="financial.trial_balance.period",
    report_type="financial",
    allowed_parameters=("from_date", "to_date", "format"),
    allowed_dimensions=(),
    period_mode="range",
    version="1",
)

INCOME_STATEMENT_PERIOD = ReportDefinition(
    id=1302,
    name="Estado de resultados por período",
    description="Ingresos, costos, gastos y resultado derivados de movimientos del rango.",
    required_data=("accounts", "journal_entries", "journal_lines"),
    supported_formats=("json", "xlsx"),
    requires_capabilities=(),
    forbidden_capabilities=(),
    required_fiscal_features=(),
    renderer_id="period_income_statement",
    query_template_id="period_income_statement",
    key="financial.income_statement.period",
    report_type="financial",
    allowed_parameters=("from_date", "to_date", "format"),
    allowed_dimensions=(),
    period_mode="range",
    version="1",
)

BALANCE_SHEET_AS_OF = ReportDefinition(
    id=1303,
    name="Estado de situación financiera",
    description="Activo, pasivo y patrimonio a una fecha de corte.",
    required_data=("accounts", "journal_entries", "journal_lines"),
    supported_formats=("json", "xlsx"),
    requires_capabilities=(),
    forbidden_capabilities=(),
    required_fiscal_features=(),
    renderer_id="balance_sheet",
    query_template_id="financial_snapshot",
    key="financial.balance_sheet.as_of",
    report_type="financial",
    allowed_parameters=("as_of_date", "format"),
    allowed_dimensions=(),
    period_mode="as_of",
    version="1",
)


REPORT_DEFINITIONS = (
    TRIAL_BALANCE_PERIOD,
    INCOME_STATEMENT_PERIOD,
    BALANCE_SHEET_AS_OF,
)

FINANCIAL_PERIOD_PACKAGE = ReportPackage(
    id=1391,
    name="Paquete financiero por período",
    included_reports=REPORT_DEFINITIONS,
    suggested_parameters=(("format", "xlsx"),),
)

REPORT_PACKAGES = (FINANCIAL_PERIOD_PACKAGE,)


def _validate_catalog():
    ids = [item.id for item in REPORT_DEFINITIONS]
    keys = [item.key for item in REPORT_DEFINITIONS]
    if any(value is None for value in ids):
        raise RuntimeError("governed report definitions require stable ids")
    if any(value is None for value in keys):
        raise RuntimeError("governed report definitions require stable keys")
    if len(ids) != len(set(ids)):
        raise RuntimeError("report definition ids must be unique")
    if len(keys) != len(set(keys)):
        raise RuntimeError("report definition keys must be unique")
    for item in REPORT_DEFINITIONS:
        if item.report_type is None or item.period_mode is None or item.version is None:
            raise RuntimeError("governed report definitions require product metadata")

    package_ids = [item.id for item in REPORT_PACKAGES]
    if any(value is None for value in package_ids):
        raise RuntimeError("official report packages require stable ids")
    if len(package_ids) != len(set(package_ids)):
        raise RuntimeError("report package ids must be unique")


_validate_catalog()


def list_report_definitions():
    return REPORT_DEFINITIONS


def get_report_definition(definition_id):
    for item in REPORT_DEFINITIONS:
        if item.id == definition_id:
            return item
    raise LookupError(f"unknown report definition: {definition_id!r}")


def get_report_definition_by_key(key):
    for item in REPORT_DEFINITIONS:
        if item.key == key:
            return item
    raise LookupError(f"unknown report definition key: {key!r}")


def list_report_packages():
    return REPORT_PACKAGES


def get_report_package(package_id):
    for item in REPORT_PACKAGES:
        if item.id == package_id:
            return item
    raise LookupError(f"unknown report package: {package_id!r}")
