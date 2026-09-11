"""Persistence authority for owner-scoped AQR-013 custom report presets.

Only reusable report configuration is stored. Generated report content, balances,
ledger lines, fiscal calculations and rendered files are deliberately never persisted.
"""

from datetime import datetime, timezone
import json

from sqlmodel import select

from . import entity_repository as _entities
from . import report_product_catalog as _catalog
from .custom_report_package import CustomReportPackage
from .report_preset import PersistedReportPreset
from .report_preset_models import ReportPresetItemRecord, ReportPresetRecord

_EXECUTION_ONLY_PARAMETERS = {"from_date", "to_date", "as_of_date", "format"}


def _require_positive_id(value, field_name):
    if type(value) is not int or value <= 0:
        raise ValueError(f"{field_name} must be positive int")


def _require_name(value):
    if type(value) is not str or not value or value.strip() != value:
        raise ValueError("preset name must be nonblank exact text")


def _require_active_owner(session, entity_id):
    _require_positive_id(entity_id, "entity_id")
    entity = _entities.load_active_entity(session)
    if entity is None or entity.id is None:
        raise LookupError("active Entity not configured")
    if entity.id != entity_id:
        raise ValueError("report preset does not belong to active Entity")
    return entity


def _validate_format(definitions, format):
    if type(format) is not str or not format or format.strip() != format:
        raise ValueError("format must be nonblank exact text")
    known_formats = {
        candidate
        for definition in _catalog.list_report_definitions()
        for candidate in definition.supported_formats
    }
    if format not in known_formats:
        raise ValueError(f"unsupported preset format: {format!r}")
    for definition in definitions:
        if format not in definition.supported_formats:
            governance = _catalog.get_report_governance(definition)
            raise ValueError(
                f"format {format!r} is not supported by preset component {governance.key!r}"
            )


def _canonical_definitions(included_reports):
    if type(included_reports) is not tuple:
        raise TypeError("included_reports must be tuple")
    canonical = []
    seen = set()
    for definition in included_reports:
        definition_id = getattr(definition, "id", None)
        if type(definition_id) is not int or definition_id <= 0:
            raise ValueError("persisted preset requires governed definition identity")
        governed = _catalog.get_report_definition(definition_id)
        if governed != definition:
            raise ValueError("preset may contain only canonical governed definitions")
        if definition_id in seen:
            raise ValueError("preset must not contain duplicate report definitions")
        seen.add(definition_id)
        canonical.append(governed)
    return tuple(canonical)


def _validate_item_parameters(definitions, item_parameters):
    if item_parameters is None:
        item_parameters = tuple(() for _ in definitions)
    if type(item_parameters) is not tuple or len(item_parameters) != len(definitions):
        raise ValueError("item_parameters must align exactly with included_reports")
    normalized = []
    for definition, parameters in zip(definitions, item_parameters):
        if type(parameters) is not tuple:
            raise TypeError("each item_parameters entry must be tuple")
        governance = _catalog.get_report_governance(definition)
        allowed = set(governance.allowed_parameters) - _EXECUTION_ONLY_PARAMETERS
        seen = set()
        values = []
        for pair in parameters:
            if type(pair) is not tuple or len(pair) != 2:
                raise TypeError("preset parameter must be a (key, value) tuple")
            key, value = pair
            if type(key) is not str or not key or key.strip() != key:
                raise ValueError("preset parameter key must be nonblank exact text")
            if key in seen:
                raise ValueError("preset parameter keys must be unique per report")
            seen.add(key)
            if key not in allowed:
                raise ValueError(
                    f"unsupported persisted parameter {key!r} for {governance.key!r}"
                )
            if type(value) is not str or not value or value.strip() != value:
                raise ValueError("preset parameter value must be nonblank exact text")
            values.append((key, value))
        if governance.key == "analytical.activity.period" and "dimension_key" not in seen:
            raise ValueError("analytical preset component requires dimension_key")
        normalized.append(tuple(values))
    return tuple(normalized)


def _encode_parameters(parameters):
    return json.dumps([list(pair) for pair in parameters], ensure_ascii=False, separators=(",", ":"))


def _decode_parameters(raw):
    if type(raw) is not str:
        raise RuntimeError("persisted preset parameters must be JSON text")
    try:
        value = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("persisted preset parameters are invalid JSON") from exc
    if type(value) is not list:
        raise RuntimeError("persisted preset parameters must decode to list")
    pairs = []
    for pair in value:
        if type(pair) is not list or len(pair) != 2 or any(type(item) is not str for item in pair):
            raise RuntimeError("persisted preset parameter shape is invalid")
        pairs.append((pair[0], pair[1]))
    return tuple(pairs)


def _load_record_scoped(session, entity_id, preset_id):
    _require_active_owner(session, entity_id)
    _require_positive_id(preset_id, "preset_id")
    rows = session.exec(
        select(ReportPresetRecord).where(
            ReportPresetRecord.id == preset_id,
            ReportPresetRecord.entity_id == entity_id,
        )
    ).all()
    if not rows:
        raise LookupError(f"report preset {preset_id} not found for Entity {entity_id}")
    if len(rows) != 1:
        raise RuntimeError("report preset identity is structurally ambiguous")
    return rows[0]


def _materialize(session, record):
    items = session.exec(
        select(ReportPresetItemRecord)
        .where(ReportPresetItemRecord.preset_id == record.id)
        .order_by(ReportPresetItemRecord.position, ReportPresetItemRecord.id)
    ).all()
    positions = tuple(item.position for item in items)
    if positions != tuple(range(len(items))):
        raise RuntimeError("persisted report preset positions are not contiguous")
    definitions = tuple(
        _catalog.get_report_definition(item.report_definition_id) for item in items
    )
    parameters = tuple(_decode_parameters(item.parameters_json) for item in items)
    canonical = _canonical_definitions(definitions)
    normalized_parameters = _validate_item_parameters(canonical, parameters)
    _validate_format(canonical, record.format)
    package = CustomReportPackage(
        id=record.id,
        owner_entity_id=record.entity_id,
        name=record.name,
        included_reports=canonical,
        created_at=record.created_at,
    )
    return PersistedReportPreset(package, record.format, normalized_parameters)


def create_report_preset(session, package, format, item_parameters=None):
    if not isinstance(package, CustomReportPackage):
        raise TypeError("package must be CustomReportPackage")
    if package.id is not None:
        raise ValueError("new preset package id must be None")
    _require_active_owner(session, package.owner_entity_id)
    _require_name(package.name)
    definitions = _canonical_definitions(package.included_reports)
    parameters = _validate_item_parameters(definitions, item_parameters)
    _validate_format(definitions, format)

    existing = session.exec(
        select(ReportPresetRecord).where(
            ReportPresetRecord.entity_id == package.owner_entity_id,
            ReportPresetRecord.name == package.name,
        )
    ).first()
    if existing is not None:
        raise ValueError("report preset name already exists for Entity")

    record = ReportPresetRecord(
        entity_id=package.owner_entity_id,
        name=package.name,
        format=format,
        created_at=package.created_at,
        updated_at=datetime.now(timezone.utc),
    )
    try:
        session.add(record)
        session.flush()
        if record.id is None:
            raise RuntimeError("report preset persistence did not assign identity")
        for position, (definition, options) in enumerate(zip(definitions, parameters)):
            session.add(
                ReportPresetItemRecord(
                    preset_id=record.id,
                    position=position,
                    report_definition_id=definition.id,
                    parameters_json=_encode_parameters(options),
                )
            )
        session.flush()
        preset_id = record.id
        session.commit()
    except Exception:
        session.rollback()
        raise
    return get_report_preset(session, package.owner_entity_id, preset_id)


def get_report_preset(session, entity_id, preset_id):
    record = _load_record_scoped(session, entity_id, preset_id)
    return _materialize(session, record)


def list_report_presets(session, entity_id):
    _require_active_owner(session, entity_id)
    records = session.exec(
        select(ReportPresetRecord)
        .where(ReportPresetRecord.entity_id == entity_id)
        .order_by(ReportPresetRecord.id)
    ).all()
    return tuple(_materialize(session, record) for record in records)


def replace_report_preset(
    session,
    entity_id,
    preset_id,
    *,
    name,
    included_reports,
    format,
    item_parameters=None,
):
    record = _load_record_scoped(session, entity_id, preset_id)
    _require_name(name)
    definitions = _canonical_definitions(included_reports)
    parameters = _validate_item_parameters(definitions, item_parameters)
    _validate_format(definitions, format)
    conflict = session.exec(
        select(ReportPresetRecord).where(
            ReportPresetRecord.entity_id == entity_id,
            ReportPresetRecord.name == name,
            ReportPresetRecord.id != preset_id,
        )
    ).first()
    if conflict is not None:
        raise ValueError("report preset name already exists for Entity")

    try:
        items = session.exec(
            select(ReportPresetItemRecord).where(
                ReportPresetItemRecord.preset_id == preset_id
            )
        ).all()
        for item in items:
            session.delete(item)
        record.name = name
        record.format = format
        record.updated_at = datetime.now(timezone.utc)
        session.add(record)
        session.flush()
        for position, (definition, options) in enumerate(zip(definitions, parameters)):
            session.add(
                ReportPresetItemRecord(
                    preset_id=preset_id,
                    position=position,
                    report_definition_id=definition.id,
                    parameters_json=_encode_parameters(options),
                )
            )
        session.commit()
    except Exception:
        session.rollback()
        raise
    return get_report_preset(session, entity_id, preset_id)


def delete_report_preset(session, entity_id, preset_id):
    record = _load_record_scoped(session, entity_id, preset_id)
    try:
        items = session.exec(
            select(ReportPresetItemRecord).where(
                ReportPresetItemRecord.preset_id == preset_id
            )
        ).all()
        for item in items:
            session.delete(item)
        session.delete(record)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return {"preset_id": preset_id, "deleted": True}


__all__ = [
    "create_report_preset",
    "get_report_preset",
    "list_report_presets",
    "replace_report_preset",
    "delete_report_preset",
]
