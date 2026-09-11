"""Presentation-safe AQR-013 reporting surface over the governed product runtime."""

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
import base64

from . import entity_repository as _entities
from . import report_product_catalog as _catalog
from . import report_product_rendering as _rendering
from . import report_product_runtime as _runtime
from . import storage as _storage
from .report_request import ReportRequest


def _date(value, field_name):
    if type(value) is date:
        return value
    if type(value) is not str or not value:
        raise ValueError(f"{field_name} must be ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be ISO date") from exc


def _json_value(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if is_dataclass(value):
        return {key: _json_value(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value


def list_reporting_surface_catalog():
    definitions = _catalog.list_report_definitions()
    packages = _catalog.list_report_packages()
    return {
        "definitions": [
            {
                "id": item.id,
                "key": _catalog.get_report_governance(item).key,
                "name": item.name,
                "description": item.description,
                "type": _catalog.get_report_governance(item).report_type,
                "supported_formats": list(item.supported_formats),
                "allowed_dimensions": list(_catalog.get_report_governance(item).allowed_dimensions),
                "period_mode": _catalog.get_report_governance(item).period_mode,
                "version": _catalog.get_report_governance(item).version,
                "restrictions": list(_catalog.get_report_governance(item).restrictions),
            }
            for item in definitions
        ],
        "packages": [
            {
                "id": item.id,
                "name": item.name,
                "reports": [_catalog.get_report_governance(report).key for report in item.included_reports],
                "suggested_parameters": dict(item.suggested_parameters),
            }
            for item in packages
        ],
    }


def _active_entity_id():
    with _storage.get_session() as session:
        entity = _entities.load_active_entity(session)
        if entity is None or entity.id is None:
            raise LookupError("active Entity not configured")
        return entity.id


def _export_payload(common, rendered):
    if rendered.format == "xlsx":
        common["document_base64"] = base64.b64encode(rendered.payload).decode("ascii")
        common["media_type"] = rendered.media_type
    return common


def _package_surface(generated, rendered, from_date, to_date):
    common = {
        "package": generated.package.name,
        "from_date": from_date.isoformat(),
        "to_date": to_date.isoformat(),
        "format": rendered.format,
        "included_reports": [item.definition.name for item in generated.reports],
        "limitations": [
            "Las cifras se derivan de las autoridades contables existentes.",
            "El paquete es un preset y no modifica la semántica de cada reporte.",
        ],
        "document": [
            {"report": report.definition.name, "content": _json_value(report.content)}
            for report in generated.reports
        ],
    }
    return _export_payload(common, rendered)


def generate_financial_period_surface(payload):
    if type(payload) is not dict:
        raise TypeError("payload must be dict")
    from_date = _date(payload.get("from_date"), "from_date")
    to_date = _date(payload.get("to_date"), "to_date")
    format = payload.get("format", "json")
    generated = _runtime.generate_financial_period_package(
        _active_entity_id(), from_date, to_date, format
    )
    rendered = _rendering.render_generated_package(generated)
    return {"common": _package_surface(generated, rendered, from_date, to_date), "generated": generated, "rendered": rendered}


def generate_professional_detail_surface(payload):
    if type(payload) is not dict:
        raise TypeError("payload must be dict")
    from_date = _date(payload.get("from_date"), "from_date")
    to_date = _date(payload.get("to_date"), "to_date")
    format = payload.get("format", "json")
    generated = _runtime.generate_professional_detail_package(
        _active_entity_id(), from_date, to_date, format
    )
    rendered = _rendering.render_generated_package(generated)
    return {"common": _package_surface(generated, rendered, from_date, to_date), "generated": generated, "rendered": rendered}


def _professional_package(result):
    generated = result["generated"]
    return {
        "package": {"id": generated.package.id, "name": generated.package.name, "official": generated.package.is_official},
        "entity_id": generated.requests[0].entity_id,
        "requests": [
            {
                "definition": _json_value(report.definition),
                "governance": _json_value(_catalog.get_report_governance(report.definition)),
                "request": _json_value(report.request),
                "source_authorities": list(report.source_authorities),
                "content": _json_value(report.content),
            }
            for report in generated.reports
        ],
        "render": {"format": result["rendered"].format, "media_type": result["rendered"].media_type},
    }


def professional_financial_period_surface(payload):
    return _professional_package(generate_financial_period_surface(payload))


def professional_detail_surface(payload):
    return _professional_package(generate_professional_detail_surface(payload))


def _individual_result(request, filters_label=None):
    generated = _runtime.generate_report(request)
    rendered = _rendering.render_generated_report(generated)
    governance = _catalog.get_report_governance(generated.definition)
    common = {
        "report": generated.definition.name,
        "format": rendered.format,
        "period_mode": governance.period_mode,
        "from_date": request.from_date.isoformat(),
        "to_date": request.to_date.isoformat(),
        "as_of_date": None if request.as_of_date is None else request.as_of_date.isoformat(),
        "filters": filters_label or {},
        "limitations": list(governance.restrictions),
        "document": _json_value(generated.content),
    }
    _export_payload(common, rendered)
    professional = {
        "definition": _json_value(generated.definition),
        "governance": _json_value(governance),
        "request": _json_value(generated.request),
        "entity_id": request.entity_id,
        "source_authorities": list(generated.source_authorities),
        "content": _json_value(generated.content),
        "render": {"format": rendered.format, "media_type": rendered.media_type},
    }
    return {"common": common, "professional": professional, "generated": generated, "rendered": rendered}


def generate_analytical_surface(payload):
    if type(payload) is not dict:
        raise TypeError("payload must be dict")
    from_date = _date(payload.get("from_date"), "from_date")
    to_date = _date(payload.get("to_date"), "to_date")
    dimension_key = payload.get("dimension_key")
    if type(dimension_key) is not str or not dimension_key:
        raise ValueError("dimension_key is required")
    request = ReportRequest(
        id=None,
        report_definition_id=_catalog.ANALYTICAL_ACTIVITY_PERIOD.id,
        entity_id=_active_entity_id(),
        from_date=from_date,
        to_date=to_date,
        as_of_date=None,
        filters=(("dimension_key", dimension_key),),
        dimensions_to_group=("analytical_value",),
        format=payload.get("format", "json"),
    )
    return _individual_result(request, {"dimension": dimension_key})


def generate_inventory_valuation_surface(payload):
    if type(payload) is not dict:
        raise TypeError("payload must be dict")
    as_of = _date(payload.get("as_of_date"), "as_of_date")
    request = ReportRequest(
        id=None,
        report_definition_id=_catalog.INVENTORY_VALUATION_AS_OF.id,
        entity_id=_active_entity_id(),
        from_date=as_of,
        to_date=as_of,
        as_of_date=as_of,
        filters=(),
        dimensions_to_group=(),
        format=payload.get("format", "json"),
    )
    return _individual_result(request)


def generate_fiscal_evidence_surface(payload):
    if type(payload) is not dict:
        raise TypeError("payload must be dict")
    from_date = _date(payload.get("from_date"), "from_date")
    to_date = _date(payload.get("to_date"), "to_date")
    request = ReportRequest(
        id=None,
        report_definition_id=_catalog.FISCAL_EVIDENCE_PERIOD.id,
        entity_id=_active_entity_id(),
        from_date=from_date,
        to_date=to_date,
        as_of_date=None,
        filters=(),
        dimensions_to_group=(),
        format=payload.get("format", "json"),
    )
    return _individual_result(request)
