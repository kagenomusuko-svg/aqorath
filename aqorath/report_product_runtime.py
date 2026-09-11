"""AQR-013 Application composition for governed report products.

This module connects ReportDefinition/ReportRequest/ReportPackage to existing report,
ledger, analytical, inventory and fiscal-document authorities. It persists no monetary
result and performs no independent posting, tax or inventory-cost calculation.
"""

from dataclasses import dataclass
from datetime import date
from types import SimpleNamespace

from . import accounting_rules as _accounting_rules
from . import entity_repository as _entities
from . import income_statement as _income_statement
from . import ledger_detail_reporting as _ledger_detail
from . import period_reporting as _period_reporting
from . import report_authority_views as _authority_views
from . import report_capability_applicability as _capability
from . import report_fiscal_applicability as _fiscal_applicability
from . import report_product_catalog as _catalog
from . import reporting as _reporting
from . import reporting_runtime as _reporting_runtime
from . import storage as _storage
from .report_product_validation import validate_governed_report_request
from .report_request import ReportRequest


@dataclass(frozen=True)
class GeneratedReport:
    definition: object
    request: ReportRequest
    content: object
    source_authorities: tuple[str, ...]


@dataclass(frozen=True)
class GeneratedReportPackage:
    package: object
    requests: tuple[ReportRequest, ...]
    reports: tuple[GeneratedReport, ...]


def _require_date(value, field_name):
    if type(value) is not date:
        raise TypeError(f"{field_name} must be date")


def _require_format(format):
    if type(format) is not str or not format or format.strip() != format:
        raise ValueError("format must be nonblank str without surrounding whitespace")


def _require_active_owner(request, definition):
    with _storage.get_session() as session:
        entity = _entities.load_active_entity(session)
        if entity is None or entity.id is None:
            raise LookupError("active Entity not configured")
        if request.entity_id != entity.id:
            raise ValueError("report request does not belong to active Entity")
        if not _capability.is_report_definition_capability_applicable(definition, entity.profile):
            raise ValueError("report definition is not applicable to active Entity")
        if definition.required_fiscal_features:
            effective_date = request.as_of_date or request.to_date
            fiscal_profile = _entities.resolve_fiscal_profile(session, entity.id, effective_date)
            if fiscal_profile is None:
                raise ValueError("report requires a fiscal profile for requested date")
            if not _fiscal_applicability.is_report_definition_fiscally_applicable_on(
                definition, fiscal_profile, effective_date
            ):
                raise ValueError("report fiscal requirements are not satisfied")
        return entity


def get_period_trial_balance(from_date, to_date):
    _require_date(from_date, "from_date")
    _require_date(to_date, "to_date")
    return _period_reporting.build_period_trial_balance_from_sqlite(
        _storage.get_db_path(), from_date, to_date
    )


def get_period_income_statement(from_date, to_date):
    """Build period P&L from exact range movement using canonical statement semantics."""
    trial = get_period_trial_balance(from_date, to_date)
    movement_balances = {line.account_code: line.debit - line.credit for line in trial.lines}
    identities = {
        line.account_code: SimpleNamespace(
            code=line.account_code, name=line.account_name, nature=line.nature
        )
        for line in trial.lines
    }
    snapshot = _reporting.build_financial_report_snapshot(
        movement_balances,
        identities,
        _accounting_rules.load_catalog(),
        as_of=to_date.isoformat(),
    )
    return _income_statement.build_income_statement_view(snapshot)


def get_journal_report(from_date, to_date):
    return _ledger_detail.build_journal_report_from_sqlite(
        _storage.get_db_path(), from_date, to_date
    )


def get_general_ledger_report(from_date, to_date):
    return _ledger_detail.build_general_ledger_from_sqlite(
        _storage.get_db_path(), from_date, to_date
    )


def _filter_map(request):
    return dict(request.filters)


def generate_report(request):
    if not isinstance(request, ReportRequest):
        raise TypeError("request must be ReportRequest")
    definition = _catalog.get_report_definition(request.report_definition_id)
    governance = _catalog.get_report_governance(definition)
    validate_governed_report_request(definition, request)
    _require_active_owner(request, definition)

    if governance.key == "financial.trial_balance.period":
        content = get_period_trial_balance(request.from_date, request.to_date)
        authorities = ("JournalEntry", "JournalLine", "Account")
    elif governance.key == "financial.income_statement.period":
        content = get_period_income_statement(request.from_date, request.to_date)
        authorities = ("JournalEntry", "JournalLine", "Account", "CanonicalCatalog")
    elif governance.key == "financial.balance_sheet.as_of":
        content = _reporting_runtime.get_balance_sheet_view(as_of=request.as_of_date.isoformat())
        authorities = ("JournalEntry", "JournalLine", "Account", "CanonicalCatalog")
    elif governance.key == "professional.journal.period":
        content = get_journal_report(request.from_date, request.to_date)
        authorities = ("JournalEntry", "JournalLine", "Account")
    elif governance.key == "professional.general_ledger.period":
        content = get_general_ledger_report(request.from_date, request.to_date)
        authorities = ("JournalEntry", "JournalLine", "Account")
    elif governance.key == "analytical.activity.period":
        filters = _filter_map(request)
        dimension_key = filters.get("dimension_key")
        if type(dimension_key) is not str or not dimension_key:
            raise ValueError("analytical report requires dimension_key")
        if request.dimensions_to_group not in ((), ("analytical_value",)):
            raise ValueError("analytical report only groups by analytical_value")
        with _storage.get_session() as session:
            content = _authority_views.build_analytical_period_view(
                session,
                request.entity_id,
                dimension_key,
                request.from_date,
                request.to_date,
            )
        authorities = (
            "JournalEntry",
            "JournalLine",
            "AnalyticalDimension",
            "AnalyticalDimensionValue",
        )
    elif governance.key == "inventory.valuation.as_of":
        with _storage.get_session() as session:
            content = _authority_views.build_inventory_valuation_view(
                session, request.entity_id, request.as_of_date
            )
        authorities = (
            "AQR-012.inventory_state",
            "InventoryMovementRecord",
            "JournalLine",
        )
    elif governance.key == "fiscal.evidence.period":
        with _storage.get_session() as session:
            content = _authority_views.build_fiscal_evidence_period_view(
                session, request.from_date, request.to_date
            )
        authorities = (
            "AQR-011.FiscalPostingAuditRecord",
            "AQR-011.load_fiscal_posting_audit_snapshot",
            "AQR-010.CfdiSourceRecord",
            "AQR-010.CfdiSourceLinkRecord",
            "AQR-010.DocumentReferenceRecord",
        )
    else:
        raise LookupError(f"no report runtime for definition {governance.key!r}")

    return GeneratedReport(definition, request, content, authorities)


def _range_request(definition, entity_id, from_date, to_date, format):
    return ReportRequest(
        id=None,
        report_definition_id=definition.id,
        entity_id=entity_id,
        from_date=from_date,
        to_date=to_date,
        as_of_date=None,
        filters=(),
        dimensions_to_group=(),
        format=format,
    )


def _validate_package_format(package, format):
    _require_format(format)
    for definition in package.included_reports:
        if format not in definition.supported_formats:
            governance = _catalog.get_report_governance(definition)
            raise ValueError(
                f"format {format!r} is not supported by package component {governance.key!r}"
            )


def _validate_range_args(entity_id, from_date, to_date):
    _require_date(from_date, "from_date")
    _require_date(to_date, "to_date")
    if to_date < from_date:
        raise ValueError("to_date cannot precede from_date")
    if type(entity_id) is not int or entity_id <= 0:
        raise ValueError("entity_id must be positive int")


def build_financial_period_requests(entity_id, from_date, to_date, format):
    _validate_range_args(entity_id, from_date, to_date)
    package = _catalog.FINANCIAL_PERIOD_PACKAGE
    _validate_package_format(package, format)
    trial = _range_request(_catalog.TRIAL_BALANCE_PERIOD, entity_id, from_date, to_date, format)
    income = _range_request(_catalog.INCOME_STATEMENT_PERIOD, entity_id, from_date, to_date, format)
    balance = ReportRequest(
        id=None,
        report_definition_id=_catalog.BALANCE_SHEET_AS_OF.id,
        entity_id=entity_id,
        from_date=to_date,
        to_date=to_date,
        as_of_date=to_date,
        filters=(),
        dimensions_to_group=(),
        format=format,
    )
    return (trial, income, balance)


def build_professional_detail_requests(entity_id, from_date, to_date, format):
    _validate_range_args(entity_id, from_date, to_date)
    package = _catalog.PROFESSIONAL_DETAIL_PACKAGE
    _validate_package_format(package, format)
    return tuple(
        _range_request(definition, entity_id, from_date, to_date, format)
        for definition in package.included_reports
    )


def _generate_package(package, requests):
    reports = tuple(generate_report(request) for request in requests)
    expected = tuple(item.id for item in package.included_reports)
    actual = tuple(item.definition.id for item in reports)
    if actual != expected:
        raise RuntimeError("generated package does not match governed package definition")
    return GeneratedReportPackage(package, tuple(requests), reports)


def generate_financial_period_package(entity_id, from_date, to_date, format="json"):
    return _generate_package(
        _catalog.FINANCIAL_PERIOD_PACKAGE,
        build_financial_period_requests(entity_id, from_date, to_date, format),
    )


def generate_professional_detail_package(entity_id, from_date, to_date, format="json"):
    return _generate_package(
        _catalog.PROFESSIONAL_DETAIL_PACKAGE,
        build_professional_detail_requests(entity_id, from_date, to_date, format),
    )
