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
    1301, "Balanza por período",
    "Balanza con saldo inicial, cargos, abonos y saldo final para un rango.",
    ("accounts", "journal_entries", "journal_lines"), ("json", "xlsx"),
    (), (), (), "period_trial_balance", "period_trial_balance",
)
INCOME_STATEMENT_PERIOD = ReportDefinition(
    1302, "Estado de resultados por período",
    "Ingresos, costos, gastos y resultado derivados de movimientos del rango.",
    ("accounts", "journal_entries", "journal_lines"), ("json", "xlsx"),
    (), (), (), "period_income_statement", "period_income_statement",
)
BALANCE_SHEET_AS_OF = ReportDefinition(
    1303, "Estado de situación financiera",
    "Activo, pasivo y patrimonio a una fecha de corte.",
    ("accounts", "journal_entries", "journal_lines"), ("json", "xlsx"),
    (), (), (), "balance_sheet", "financial_snapshot",
)
JOURNAL_PERIOD = ReportDefinition(
    1304, "Diario por período",
    "Pólizas y líneas cronológicas del ledger para un rango explícito.",
    ("accounts", "journal_entries", "journal_lines"), ("json", "xlsx"),
    (), (), (), "journal_period", "journal_period",
)
GENERAL_LEDGER_PERIOD = ReportDefinition(
    1305, "Mayor por período",
    "Saldo inicial, movimientos y saldo final por cuenta para un rango.",
    ("accounts", "journal_entries", "journal_lines"), ("json", "xlsx"),
    (), (), (), "general_ledger_period", "general_ledger_period",
)
ANALYTICAL_ACTIVITY_PERIOD = ReportDefinition(
    1306, "Actividad por dimensión analítica",
    "Movimientos del ledger agrupados por valores de una dimensión analítica existente.",
    ("journal_entries", "journal_lines", "analytical_dimensions"), ("json",),
    (), (), (), "analytical_activity_period", "analytical_activity_period",
)
INVENTORY_VALUATION_AS_OF = ReportDefinition(
    1307, "Valuación de inventario",
    "Existencias, valor en libros y promedio vigente a una fecha según AQR-012.",
    ("inventory_products", "inventory_movements", "journal_lines"), ("json",),
    ("inventory_control",), (), (), "inventory_valuation_as_of", "inventory_state",
)
FISCAL_EVIDENCE_PERIOD = ReportDefinition(
    1308, "Evidencia fiscal y documental",
    "Auditoría fiscal persistida y documentos/CFDI vinculados, sin reinterpretación.",
    ("fiscal_posting_audit", "document_references", "cfdi_metadata"), ("json",),
    (), (), (), "fiscal_evidence_period", "fiscal_audit_read",
)

REPORT_DEFINITIONS = (
    TRIAL_BALANCE_PERIOD,
    INCOME_STATEMENT_PERIOD,
    BALANCE_SHEET_AS_OF,
    JOURNAL_PERIOD,
    GENERAL_LEDGER_PERIOD,
    ANALYTICAL_ACTIVITY_PERIOD,
    INVENTORY_VALUATION_AS_OF,
    FISCAL_EVIDENCE_PERIOD,
)

REPORT_GOVERNANCE = (
    ReportProductGovernance(1301, "financial.trial_balance.period", "financial", ("from_date", "to_date", "format"), (), "range", "1", ("ledger-derived",)),
    ReportProductGovernance(1302, "financial.income_statement.period", "financial", ("from_date", "to_date", "format"), (), "range", "1", ("ledger-derived", "canonical-catalog-semantics")),
    ReportProductGovernance(1303, "financial.balance_sheet.as_of", "financial", ("as_of_date", "format"), (), "as_of", "1", ("ledger-derived", "canonical-catalog-semantics")),
    ReportProductGovernance(1304, "professional.journal.period", "professional", ("from_date", "to_date", "format"), (), "range", "1", ("ledger-detail",)),
    ReportProductGovernance(1305, "professional.general_ledger.period", "professional", ("from_date", "to_date", "format"), (), "range", "1", ("ledger-detail",)),
    ReportProductGovernance(1306, "analytical.activity.period", "analytical", ("from_date", "to_date", "format", "dimension_key"), ("analytical_value",), "range", "1", ("AQR-008-view", "assigned-lines-only")),
    ReportProductGovernance(1307, "inventory.valuation.as_of", "inventory", ("as_of_date", "format"), (), "as_of", "1", ("AQR-012-authority", "no-cost-recalculation")),
    ReportProductGovernance(1308, "fiscal.evidence.period", "fiscal", ("from_date", "to_date", "format"), (), "range", "1", ("AQR-011-audit-only", "AQR-010-document-evidence", "no-tax-recalculation")),
)

FINANCIAL_PERIOD_PACKAGE = ReportPackage(
    id=1391,
    name="Paquete financiero por período",
    included_reports=(TRIAL_BALANCE_PERIOD, INCOME_STATEMENT_PERIOD, BALANCE_SHEET_AS_OF),
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
    if any(value is None for value in package_ids) or len(package_ids) != len(set(package_ids)):
        raise RuntimeError("official report package ids must be present and unique")
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
