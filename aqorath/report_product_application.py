"""AQR-013 governed report-product application service.

The service composes existing ReportDefinition/ReportRequest/ReportPackage contracts,
entity-profile applicability and canonical reporting runtime.  It does not persist
monetary results and it does not contain accounting calculations.
"""

from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
import json

from . import entity_repository as _entities
from . import report_capability_applicability as _capability
from . import report_period_runtime as _period_runtime
from . import report_product_catalog as _catalog
from . import report_request_compatibility as _compatibility
from .report_definition import ReportDefinition
from .report_package import ReportPackage
from .report_request import ReportRequest


@dataclass(frozen=True)
class PreparedReportPackage:
    package: ReportPackage
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
    package: ReportPackage
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


def prepare_financial_period_package(
    session,
    *,
    from_date,
    to_date,
    format,
):
    """Expand the official preset into ordinary governed ReportRequest values."""
    package = _catalog.get_financial_period_package()
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


def _content_from_bundle(definition, bundle):
    key = definition.query_template_id
    if key == "period_trial_balance":
        return bundle.trial_balance
    if key == "period_income_statement":
        return bundle.income_statement
    if key == "as_of_balance_sheet":
        return bundle.balance_sheet
    raise ValueError(f"unsupported governed query_template_id: {key}")


def build_report_product(session, request):
    """Build semantic report content from canonical authorities without rendering."""
    _entity, definition, policy = _validate_request_for_active_entity(session, request)
    bundle = _period_runtime.get_period_financial_bundle(
        request.from_date,
        request.to_date,
    )
    return ReportProductResult(
        definition=definition,
        request=request,
        policy_version=policy["version"],
        source_authority="JournalEntry/JournalLine via canonical SQLite reporting",
        content=_content_from_bundle(definition, bundle),
    )


def build_financial_period_package(session, prepared):
    """Build the first V1 package from one shared canonical reporting snapshot."""
    if not isinstance(prepared, PreparedReportPackage):
        raise TypeError("prepared must be PreparedReportPackage")
    official = _catalog.get_financial_period_package()
    if prepared.package != official:
        raise ValueError("prepared package is not the governed financial-period preset")
    expected_ids = tuple(definition.id for definition in official.included_reports)
    actual_ids = tuple(request.report_definition_id for request in prepared.requests)
    if actual_ids != expected_ids:
        raise ValueError("prepared package request selection differs from preset")
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

    bundle = _period_runtime.get_period_financial_bundle(
        first.from_date,
        first.to_date,
    )
    reports = []
    for request in prepared.requests:
        definition = _catalog.get_report_definition(request.report_definition_id)
        policy = _catalog.get_report_policy(definition.id)
        reports.append(
            ReportProductResult(
                definition=definition,
                request=request,
                policy_version=policy["version"],
                source_authority=(
                    "JournalEntry/JournalLine via canonical SQLite reporting"
                ),
                content=_content_from_bundle(definition, bundle),
            )
        )
    return ReportPackageResult(
        package=official,
        requests=prepared.requests,
        reports=tuple(reports),
    )


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


def render_report_product(result):
    """Render one semantic result using the explicitly requested governed format."""
    if not isinstance(result, ReportProductResult):
        raise TypeError("result must be ReportProductResult")
    if result.request.format != "json":
        raise ValueError("requested report format has no AQR-013 renderer")
    payload = {
        "definition": _json_value(result.definition),
        "request": _json_value(result.request),
        "policy_version": result.policy_version,
        "source_authority": result.source_authority,
        "content": _json_value(result.content),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def render_report_package(result):
    """Render one package without recalculating any of its semantic reports."""
    if not isinstance(result, ReportPackageResult):
        raise TypeError("result must be ReportPackageResult")
    formats = {report.request.format for report in result.reports}
    if formats != {"json"}:
        raise ValueError("requested package format has no AQR-013 renderer")
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
