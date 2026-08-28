"""SQLite persistence authority for append-only general AuditEvent traceability."""

from dataclasses import replace
from datetime import datetime
import json

from sqlmodel import select

from .audit_event import AuditEvent
from .models import AuditEventRecord, EntityRecord


def _require_positive_id(value, field_name):
    if type(value) is not int:
        raise TypeError(f"{field_name} must be int")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


def _canonical_details(details):
    return json.dumps(
        details,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _from_record(record):
    try:
        details = json.loads(record.details_json)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("persisted AuditEvent details_json is invalid JSON") from exc
    if type(details) is not dict:
        raise RuntimeError("persisted AuditEvent details_json must decode to object")
    return AuditEvent(
        id=record.id,
        entity_id=record.entity_id,
        event_type=record.event_type,
        timestamp=datetime.fromisoformat(record.timestamp),
        details=details,
    )


def _load_owned_record(session, entity_id, event_id):
    _require_positive_id(entity_id, "entity_id")
    _require_positive_id(event_id, "event_id")
    rows = session.exec(
        select(AuditEventRecord).where(
            AuditEventRecord.entity_id == entity_id,
            AuditEventRecord.id == event_id,
        )
    ).all()
    if not rows:
        raise LookupError("AuditEvent not found for Entity")
    if len(rows) != 1:
        raise RuntimeError("Ambiguous AuditEvent identity")
    return rows[0]


def create_audit_event(session, event):
    """Append one explicit AuditEvent for an existing active Entity."""
    if not isinstance(event, AuditEvent):
        raise TypeError("event must be AuditEvent")
    if event.id is not None:
        raise ValueError("new AuditEvent id must be None")

    owner = session.get(EntityRecord, event.entity_id)
    if owner is None:
        raise LookupError("AuditEvent owner Entity does not exist")
    if owner.is_active is not True:
        raise ValueError("AuditEvent owner Entity must be active")

    record = AuditEventRecord(
        entity_id=event.entity_id,
        event_type=event.event_type,
        timestamp=event.timestamp.isoformat(),
        details_json=_canonical_details(event.details),
    )
    try:
        session.add(record)
        session.flush()
        if record.id is None:
            raise RuntimeError("AuditEvent identity was not assigned")
        persisted_id = record.id
        session.commit()
    except Exception:
        session.rollback()
        raise
    return replace(event, id=persisted_id)


def get_audit_event(session, entity_id, event_id):
    """Load one Entity-scoped AuditEvent."""
    return _from_record(_load_owned_record(session, entity_id, event_id))


def list_audit_events(session, entity_id):
    """List Entity-scoped AuditEvents deterministically by identity."""
    _require_positive_id(entity_id, "entity_id")
    records = session.exec(
        select(AuditEventRecord)
        .where(AuditEventRecord.entity_id == entity_id)
        .order_by(AuditEventRecord.id)
    ).all()
    return tuple(_from_record(record) for record in records)
