"""Governed AQR-013 report products and official packages.

The frozen ReportDefinition remains the authority for WHAT document exists. Product
metadata in ReportProductGovernance is a deterministic 1:1 constraint keyed by that
definition identity; it is not another report definition and owns no monetary truth,
SQL, rendering, fiscal classification or generated result.
"""

from .report_definition import ReportDefinition
from .report_package import ReportPackage
from .report_product_governance import ReportProductGovernance


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
)

JOURNAL_PERIOD = ReportDefinition(
    id=1304,
    name="Diario por período",
    description="Pólizas y líneas cronológicas del ledger para un rango explícito.",
    required_data=("accounts", "journal_entries", "journal_lines"),
    supported_formats=("json", "xlsx"),
    requires_capabilities=(),
    forbidden_capabilities=(),
    required_fiscal_features=(),
    renderer_id="journal_period",
    query_template_id="journal_period",
)

GENERAL_LEDGER_PERIOD = ReportDefinition(
    id=1305,
    name="Mayor por período",
    description="Saldo inicial, movimientos y saldo final por cuenta para un rango.",
    required_data=("accounts", "journal_entries", "journal_lines"),
    supported_formats=("json", "xlsx"),
    requires_capabilities=(),
    forbidden_capabilities=(),
    required_fiscal_features=(),
    renderer_id="general_ledger_period",
    query_template_id="general_ledger_period",
)

REPORT_DEFINITIONS = (
    TRIAL_BALANCE_PERIOD,
    INCOME_STATEMENT_PERIOD,
    BALANCE_SHEET_AS_OF,
    JOURNAL_PERIOD,
    GENERAL_LEDGER_PERIOD,
)

REPORT_GOVERNANCE = (
    ReportProductGovernance(
        1301,
        "financial.trial_balance.period",
        "financial",
        ("from_date", "to_date", "format"),
        (),
        "range",
        "1",
        ("ledger-derived",),
    ),
    ReportProductGovernance(
        1302,
        "financial.income_statement.period",
        "financial",
        ("from_date", "to_date", "format"),
        (),
        "range",
        "1",
        ("ledger-derived", "canonical-catalog-semantics"),
    ),
    ReportProductGovernance(
        1303,
        "financial.balance_sheet.as_of",
        "financial",
        ("as_of_date", "format"),
        (),
        "as_of",
        "1",
        ("ledger-derived", "canonical-catalog-semantics"),
    ),
    ReportProductGovernance(
        1304,
        "professional.journal.period",
        "professional",
        ("from_date", "to_date", "format"),
        (),
        "range",
        "1",
        ("ledger-detail",),
    ),
    ReportProductGovernance(
        1305,
        "professional.general_ledger.period",
        "professional",
        ("from_date", "to_date", "format"),
        (),
        "range",
        "1",
        ("ledger-detail",),
    ),
)

FINANCIAL_PERIOD_PACKAGE = ReportPackage(
    id=1391,
    name="Paquete financiero por período",
    included_reports=(
        TRIAL_BALANCE_PERIOD,
        INCOME_STATEMENT_PERIOD,
        BALANCE_SHEET_AS_OF,
    ),
    suggested_parameters=(("format", "xlsx"),),
)

PROFESSIONAL_DETAIL_PACKAGE = ReportPackage(
    id=1392,
    name="Detalle contable por período",
    included_reports=(JOURNAL_PERIOD, GENERAL_LEDGER_PERIOD, TRIAL_BALANCE_PERIOD),
    suggested_parameters=(("format", "xlsx"),),
)

REPORT_PACKAGES = (FINANCIAL_PERIOD_PACKAGE, PROFESSIONAL_DETAIL_PACKAGE)


def _validate_catalog():
    ids = [item.id for item in REPORT_DEFINITIONS]
    if any(value is None for value in ids):
        raise RuntimeError("governed report definitions require stable ids")
    if len(ids) != len(set(ids)):
        raise RuntimeError("report definition ids must be unique")

    governed_ids = [item.definition_id for item in REPORT_GOVERNANCE]
    keys = [item.key for item in REPORT_GOVERNANCE]
    if governed_ids != ids:
        raise RuntimeError("report governance must match definitions 1:1 and in order")
    if len(keys) != len(set(keys)):
        raise RuntimeError("report product keys must be unique")

    package_ids = [item.id for item in REPORT_PACKAGES]
    if any(value is None for value in package_ids):
        raise RuntimeError("official report packages require stable ids")
    if len(package_ids) != len(set(package_ids)):
        raise RuntimeError("report package ids must be unique")
    governed = set(ids)
    for package in REPORT_PACKAGES:
        for definition in package.included_reports:
            if definition.id not in governed:
                raise RuntimeError("report package contains ungoverned definition")


_validate_catalog()


def list_report_definitions():
    return REPORT_DEFINITIONS


def list_report_governance():
    return REPORT_GOVERNANCE


def get_report_definition(definition_id):
    for item in REPORT_DEFINITIONS:
        if item.id == definition_id:
            return item
    raise LookupError(f"unknown report definition: {definition_id!r}")


def get_report_governance(definition_or_id):
    definition_id = getattr(definition_or_id, "id", definition_or_id)
    for item in REPORT_GOVERNANCE:
        if item.definition_id == definition_id:
            return item
    raise LookupError(f"unknown report governance: {definition_id!r}")


def get_report_definition_by_key(key):
    for governance in REPORT_GOVERNANCE:
        if governance.key == key:
            return get_report_definition(governance.definition_id)
    raise LookupError(f"unknown report definition key: {key!r}")


def list_report_packages():
    return REPORT_PACKAGES


def get_report_package(package_id):
    for item in REPORT_PACKAGES:
        if item.id == package_id:
            return item
    raise LookupError(f"unknown report package: {package_id!r}")
