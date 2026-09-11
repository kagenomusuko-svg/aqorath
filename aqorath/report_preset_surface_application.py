"""Presentation-safe CRUD and execution for persisted AQR-013 report presets."""

from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
import base64

from . import entity_repository as _entities
from . import report_product_catalog as _catalog
from . import report_product_rendering as _rendering
from . import report_preset_repository as _repository
from . import storage as _storage
from .custom_report_package import CustomReportPackage
from .custom_report_product_runtime import generate_persisted_report_preset


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


def _date(value, field_name):
    if type(value) is date:
        return value
    if type(value) is not str or not value:
        raise ValueError(f"{field_name} must be ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be ISO date") from exc


def _active_entity(session):
    entity = _entities.load_active_entity(session)
    if entity is None or entity.id is None:
        raise LookupError("active Entity not configured")
    return entity


def _parse_reports(raw):
    if type(raw) is not list:
        raise TypeError("reports must be list")
    definitions = []
    parameters = []
    for item in raw:
        if type(item) is not dict:
            raise TypeError("reports items must be objects")
        definition_id = item.get("definition_id")
        if type(definition_id) is not int or definition_id <= 0:
            raise ValueError("definition_id must be positive int")
        definition = _catalog.get_report_definition(definition_id)
        raw_parameters = item.get("parameters", {})
        if type(raw_parameters) is not dict:
            raise TypeError("report parameters must be object")
        pairs = tuple(sorted(raw_parameters.items()))
        definitions.append(definition)
        parameters.append(pairs)
    return tuple(definitions), tuple(parameters)


def _preset_value(preset):
    reports = []
    for definition, parameters in zip(
        preset.package.included_reports, preset.item_parameters
    ):
        governance = _catalog.get_report_governance(definition)
        reports.append(
            {
                "definition_id": definition.id,
                "key": governance.key,
                "name": definition.name,
                "parameters": dict(parameters),
                "supported_formats": list(definition.supported_formats),
            }
        )
    return {
        "id": preset.package.id,
        "name": preset.package.name,
        "format": preset.format,
        "reports": reports,
        "created_at": preset.package.created_at.isoformat(),
    }


def list_report_presets_surface():
    with _storage.get_session() as session:
        entity = _active_entity(session)
        return [
            _preset_value(item)
            for item in _repository.list_report_presets(session, entity.id)
        ]


def get_report_preset_surface(preset_id):
    with _storage.get_session() as session:
        entity = _active_entity(session)
        return _preset_value(
            _repository.get_report_preset(session, entity.id, preset_id)
        )


def create_report_preset_surface(payload):
    if type(payload) is not dict:
        raise TypeError("payload must be dict")
    definitions, parameters = _parse_reports(payload.get("reports"))
    name = payload.get("name")
    format = payload.get("format", "json")
    with _storage.get_session() as session:
        entity = _active_entity(session)
        package = CustomReportPackage(
            id=None,
            owner_entity_id=entity.id,
            name=name,
            included_reports=definitions,
            created_at=datetime.now(timezone.utc),
        )
        preset = _repository.create_report_preset(
            session, package, format, parameters
        )
        return _preset_value(preset)


def update_report_preset_surface(preset_id, payload):
    if type(payload) is not dict:
        raise TypeError("payload must be dict")
    definitions, parameters = _parse_reports(payload.get("reports"))
    with _storage.get_session() as session:
        entity = _active_entity(session)
        preset = _repository.replace_report_preset(
            session,
            entity.id,
            preset_id,
            name=payload.get("name"),
            included_reports=definitions,
            format=payload.get("format", "json"),
            item_parameters=parameters,
        )
        return _preset_value(preset)


def delete_report_preset_surface(preset_id):
    with _storage.get_session() as session:
        entity = _active_entity(session)
        return _repository.delete_report_preset(session, entity.id, preset_id)


def _load_and_generate(preset_id, payload):
    if type(payload) is not dict:
        raise TypeError("payload must be dict")
    from_date = _date(payload.get("from_date"), "from_date")
    to_date = _date(payload.get("to_date"), "to_date")
    with _storage.get_session() as session:
        entity = _active_entity(session)
        preset = _repository.get_report_preset(session, entity.id, preset_id)
    generated = generate_persisted_report_preset(
        preset, entity.id, from_date, to_date
    )
    rendered = _rendering.render_generated_package(generated)
    return preset, generated, rendered, from_date, to_date


def execute_report_preset_surface(preset_id, payload):
    preset, generated, rendered, from_date, to_date = _load_and_generate(
        preset_id, payload
    )
    common = {
        "preset": preset.package.name,
        "from_date": from_date.isoformat(),
        "to_date": to_date.isoformat(),
        "format": rendered.format,
        "included_reports": [item.definition.name for item in generated.reports],
        "document": [
            {"report": item.definition.name, "content": _json_value(item.content)}
            for item in generated.reports
        ],
        "limitations": [
            "El preset guarda configuración, no cifras.",
            "Cada ejecución consulta nuevamente las autoridades contables vigentes.",
        ],
    }
    if rendered.format == "xlsx":
        common["document_base64"] = base64.b64encode(rendered.payload).decode("ascii")
        common["media_type"] = rendered.media_type
    return common


def professional_report_preset_surface(preset_id, payload):
    preset, generated, rendered, _from_date, _to_date = _load_and_generate(
        preset_id, payload
    )
    return {
        "preset": _preset_value(preset),
        "entity_id": preset.package.owner_entity_id,
        "requests": [
            {
                "definition": _json_value(report.definition),
                "governance": _json_value(
                    _catalog.get_report_governance(report.definition)
                ),
                "request": _json_value(report.request),
                "source_authorities": list(report.source_authorities),
                "content": _json_value(report.content),
            }
            for report in generated.reports
        ],
        "render": {
            "format": rendered.format,
            "media_type": rendered.media_type,
        },
    }


__all__ = [
    "list_report_presets_surface",
    "get_report_preset_surface",
    "create_report_preset_surface",
    "update_report_preset_surface",
    "delete_report_preset_surface",
    "execute_report_preset_surface",
    "professional_report_preset_surface",
]
