"""AQR-013 governed report-product application service.

The service composes existing ReportDefinition/ReportRequest/ReportPackage contracts,
entity-profile applicability and canonical reporting authorities. It does not persist
monetary results and it does not contain accounting, inventory or fiscal calculations.
"""

from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
import json

from . import accounting_rules as _accounting_rules
from . import entity_repository as _entities
from . import report_capability_applicability as _capability
from . import report_detail_source as _detail
from . import report_period_runtime as _period_runtime
from . import report_product_catalog as _catalog
from . import report_product_rendering as _rendering
from . import report_request_compatibility as _compatibility
from . import report_specialized_source as _specialized
from . import storage as _storage
from .custom_report_package import CustomReportPackage
from .report_definition import ReportDefinition
from .report_package import ReportPackage
from .report_request import ReportRequest


@dataclass(frozen=True)
class PreparedReportPackage:
    package: object
    requests: tuple[ReportRequest, ...]


@dataclass(frozen=True)
class ReportProductResult:
    definition: ReportDefinition
    request: ReportRequest
    policy_version: str
    source_authority: str
    content: object


@dataclass(frozen=True)
class ReportPackageResult:
    package: object
    requests: tuple[ReportRequest, ...]
    reports: tuple[ReportProductResult, ...]


def _active_entity(session):
    entity = _entities.load_active_entity(session)
    if entity is None or entity.id is None:
        raise LookupError("active Entity is required to generate reports")
    return entity


def _validate_policy(definition, request):
    policy = _catalog.get_report_policy(definition.id)
    allowed_filters = set(policy["allowed_filters"])
    supplied_filters = {key for key, _value in request.filters}
    unsupported_filters = supplied_filters.difference(allowed_filters)
    if unsupported_filters:
        raise ValueError(
            "unsupported report filters: " + ", ".join(sorted(unsupported_filters))
        )
    allowed_dimensions = set(policy["allowed_dimensions"])
    unsupported_dimensions = set(request.dimensions_to_group).difference(
        allowed_dimensions
    )
    if unsupported_dimensions:
        raise ValueError(
            "unsupported report dimensions: "
            + ", ".join(sorted(unsupported_dimensions))
        )
    return policy


def _validate_request_for_active_entity(session, request):
    if not isinstance(request, ReportRequest):
        raise TypeError("request must be ReportRequest")
    entity = _active_entity(session)
    if request.entity_id != entity.id:
        raise ValueError("ReportRequest does not belong to the active Entity")
    definition = _catalog.get_report_definition(request.report_definition_id)
    _compatibility.validate_report_request_against_definition(definition, request)
    if not _capability.is_report_definition_capability_applicable(
        definition,
        entity.profile,
    ):
        raise ValueError("report definition is not applicable to the active Entity")
    policy = _validate_policy(definition, request)
    return entity, definition, policy


def prepare_report_request(
    session,
    definition_id,
    *,
    from_date,
    to_date,
    format,
    filters=(),
    dimensions_to_group=(),
):
    """Prepare one governed concrete request without writing persistent state."""
    entity = _active_entity(session)
    definition = _catalog.get_report_definition(definition_id)
    if not _capability.is_report_definition_capability_applicable(
        definition,
        entity.profile,
    ):
        raise ValueError("report definition is not applicable to the active Entity")
    request = ReportRequest(
        id=None,
        report_definition_id=definition.id,
        entity_id=entity.id,
        from_date=from_date,
        to_date=to_date,
        as_of_date=to_date,
        filters=filters,
        dimensions_to_group=dimensions_to_group,
        format=format,
    )
    _compatibility.validate_report_request_against_definition(definition, request)
    _validate_policy(definition, request)
    return request


def _prepare_package(session, package, *, from_date, to_date, format):
    requests = tuple(
        prepare_report_request(
            session,
            definition.id,
            from_date=from_date,
            to_date=to_date,
            format=format,
        )
        for definition in package.included_reports
    )
    return PreparedReportPackage(package=package, requests=requests)


def prepare_financial_period_package(session, *, from_date, to_date, format):
    """Expand the official financial preset into ordinary governed requests."""
    return _prepare_package(
        session,
        _catalog.get_financial_period_package(),
        from_date=from_date,
        to_date=to_date,
        format=format,
    )


def prepare_custom_report_package(
    session,
    package,
    *,
    from_date,
    to_date,
    format,
):
    """Expand a saved selection without allowing it to redefine report semantics."""
    if not isinstance(package, CustomReportPackage):
        raise TypeError("package must be CustomReportPackage")
    entity = _active_entity(session)
    if package.owner_entity_id != entity.id:
        raise ValueError("custom report package does not belong to the active Entity")
    for supplied in package.included_reports:
        if supplied.id is None or supplied != _catalog.get_report_definition(supplied.id):
            raise ValueError("custom report package contains non-governed definition")
    return _prepare_package(
        session,
        package,
        from_date=from_date,
        to_date=to_date,
        format=format,
    )


def _financial_content(definition, bundle):
    key = definition.query_template_id
    if key == "period_trial_balance":
        return bundle.trial_balance
    if key == "period_income_statement":
        return bundle.income_statement
    if key == "as_of_balance_sheet":
        return bundle.balance_sheet
    return None


def _detail_pair(request, cache):
    key = (request.from_date, request.to_date)
    if key not in cache:
        cache[key] = _detail.build_journal_and_ledger_from_sqlite(
            _storage.get_db_path(),
            _accounting_rules.load_catalog(),
            from_date=request.from_date,
            to_date=request.to_date,
        )
    return cache[key]


def _build_content(session, entity, definition, request, caches):
    query = definition.query_template_id
    if query in {
        "period_trial_balance",
        "period_income_statement",
        "as_of_balance_sheet",
    }:
        key = (request.from_date, request.to_date)
        if key not in caches["financial"]:
            caches["financial"][key] = _period_runtime.get_period_financial_bundle(
                request.from_date,
                request.to_date,
            )
        return (
            _financial_content(definition, caches["financial"][key]),
            "JournalEntry/JournalLine via canonical SQLite reporting",
        )
    if query == "period_journal":
        journal, _ledger = _detail_pair(request, caches["detail"])
        return journal, "JournalEntry/JournalLine canonical professional detail"
    if query == "period_general_ledger":
        _journal, ledger = _detail_pair(request, caches["detail"])
        return ledger, "JournalEntry/JournalLine reconciled to canonical trial balance"
    if query == "as_of_osc_funds":
        return (
            _specialized.build_osc_fund_report(
                session, entity.id, as_of=request.to_date
            ),
            "AQR-008 FundBalance/FundTraceability anchored to JournalLine",
        )
    if query == "as_of_inventory":
        return (
            _specialized.build_inventory_as_of_report(
                session, entity.id, as_of=request.to_date
            ),
            "AQR-012 InventoryMovement/inventory_state reconciled to JournalLine",
        )
    if query == "period_fiscal_evidence":
        return (
            _specialized.build_fiscal_evidence_report(
                session,
                entity.id,
                from_date=request.from_date,
                to_date=request.to_date,
            ),
            "AQR-011 persisted fiscal posting audit",
        )
    if query == "period_cfdi_evidence":
        return (
            _specialized.build_cfdi_evidence_report(
                session,
                entity.id,
                from_date=request.from_date,
                to_date=request.to_date,
            ),
            "AQR-010 CfdiSource documentary evidence",
        )
    raise ValueError(f"unsupported governed query_template_id: {query}")


def _caches():
    return {"financial": {}, "detail": {}}


def _build_validated_result(session, request, caches):
    entity, definition, policy = _validate_request_for_active_entity(session, request)
    content, authority = _build_content(session, entity, definition, request, caches)
    return ReportProductResult(
        definition=definition,
        request=request,
        policy_version=policy["version"],
        source_authority=authority,
        content=content,
    )


def build_report_product(session, request):
    """Build semantic report content from canonical authorities without rendering."""
    return _build_validated_result(session, request, _caches())


def _validate_prepared_package(session, prepared):
    if not isinstance(prepared, PreparedReportPackage):
        raise TypeError("prepared must be PreparedReportPackage")
    included = getattr(prepared.package, "included_reports", None)
    if type(included) is not tuple:
        raise TypeError("prepared package must expose included_reports tuple")
    expected_ids = tuple(definition.id for definition in included)
    actual_ids = tuple(request.report_definition_id for request in prepared.requests)
    if actual_ids != expected_ids:
        raise ValueError("prepared package request selection differs from package preset")
    if not prepared.requests:
        raise ValueError("prepared package must contain report requests")
    first = prepared.requests[0]
    for request in prepared.requests:
        _validate_request_for_active_entity(session, request)
        if (
            request.entity_id != first.entity_id
            or request.from_date != first.from_date
            or request.to_date != first.to_date
            or request.as_of_date != first.as_of_date
            or request.format != first.format
        ):
            raise ValueError("package requests must share Entity, range and format")


def build_report_package(session, prepared):
    """Build any governed official/custom package with shared source caches."""
    _validate_prepared_package(session, prepared)
    caches = _caches()
    reports = tuple(
        _build_validated_result(session, request, caches)
        for request in prepared.requests
    )
    return ReportPackageResult(
        package=prepared.package,
        requests=prepared.requests,
        reports=reports,
    )


def build_financial_period_package(session, prepared):
    """Build the first V1 official package and preserve its exact governed preset."""
    if prepared.package != _catalog.get_financial_period_package():
        raise ValueError("prepared package is not the governed financial-period preset")
    return build_report_package(session, prepared)


def _json_value(value):
    if value is None or type(value) in (str, int, bool):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if type(value) in (date, datetime):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if is_dataclass(value):
        return {
            field.name: _json_value(getattr(value, field.name))
            for field in fields(value)
        }
    raise TypeError(f"unsupported report JSON value: {type(value).__name__}")


def _render_json_result(result):
    payload = {
        "definition": _json_value(result.definition),
        "request": _json_value(result.request),
        "policy_version": result.policy_version,
        "source_authority": result.source_authority,
        "content": _json_value(result.content),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def render_report_product(result):
    """Render one semantic result using exactly the requested governed format."""
    if not isinstance(result, ReportProductResult):
        raise TypeError("result must be ReportProductResult")
    format_key = result.request.format
    if format_key == "json":
        return _render_json_result(result)
    if format_key == "xlsx":
        return _rendering.render_report_xlsx(result)
    if format_key == "pdf":
        return _rendering.render_report_pdf(result)
    raise ValueError("requested report format has no AQR-013 renderer")


def render_report_package(result):
    """Render one package without recalculating any semantic report."""
    if not isinstance(result, ReportPackageResult):
        raise TypeError("result must be ReportPackageResult")
    formats = {report.request.format for report in result.reports}
    if len(formats) != 1:
        raise ValueError("package reports must share one explicit output format")
    format_key = next(iter(formats))
    if format_key == "json":
        payload = {
            "package": _json_value(result.package),
            "requests": _json_value(result.requests),
            "reports": [
                {
                    "definition": _json_value(report.definition),
                    "policy_version": report.policy_version,
                    "source_authority": report.source_authority,
                    "content": _json_value(report.content),
                }
                for report in result.reports
            ],
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if format_key == "xlsx":
        return _rendering.render_package_xlsx(result)
    if format_key == "pdf":
        return _rendering.render_package_pdf(result)
    raise ValueError("requested package format has no AQR-013 renderer")
