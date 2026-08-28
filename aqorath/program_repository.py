"""SQLite persistence authority for first-class OSC Program identity."""

from dataclasses import replace
from decimal import Decimal
import json

from sqlmodel import select

from .models import EntityProfileRecord, EntityRecord, ProgramRecord
from .program import Program


def _require_positive_id(value, field_name):
    if type(value) is not int:
        raise TypeError(f"{field_name} must be int")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


def _decode_capabilities(raw):
    if type(raw) is not str:
        raise RuntimeError("persisted special_capabilities_json must be text")
    try:
        values = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("persisted special_capabilities_json is invalid JSON") from exc
    if type(values) is not list or any(type(value) is not str for value in values):
        raise RuntimeError("persisted special_capabilities_json must be a string list")
    return tuple(values)


def _from_record(record):
    return Program(
        id=record.id,
        entity_id=record.entity_id,
        name=record.name,
        description=record.description,
        budget=None if record.budget is None else Decimal(record.budget),
    )


def _load_owned_record(session, entity_id, program_id):
    _require_positive_id(entity_id, "entity_id")
    _require_positive_id(program_id, "program_id")
    rows = session.exec(
        select(ProgramRecord).where(
            ProgramRecord.entity_id == entity_id,
            ProgramRecord.id == program_id,
        )
    ).all()
    if not rows:
        raise LookupError("Program not found for Entity")
    if len(rows) != 1:
        raise RuntimeError("Ambiguous Program identity")
    return rows[0]


def create_program(session, program):
    """Persist one explicit Program for an active OSC-capable Entity."""
    if not isinstance(program, Program):
        raise TypeError("program must be Program")
    if program.id is not None:
        raise ValueError("new Program id must be None")

    owner = session.get(EntityRecord, program.entity_id)
    if owner is None:
        raise LookupError("Program owner Entity does not exist")
    if owner.is_active is not True:
        raise ValueError("Program owner Entity must be active")

    profiles = session.exec(
        select(EntityProfileRecord).where(
            EntityProfileRecord.entity_id == program.entity_id
        )
    ).all()
    if len(profiles) != 1:
        raise RuntimeError("Program owner Entity must have exactly one profile")
    capabilities = _decode_capabilities(profiles[0].special_capabilities_json)
    if "osc" not in capabilities:
        raise ValueError("Program owner Entity must have explicit osc capability")

    record = ProgramRecord(
        entity_id=program.entity_id,
        name=program.name,
        description=program.description,
        budget=None if program.budget is None else str(program.budget),
    )
    try:
        session.add(record)
        session.flush()
        if record.id is None:
            raise RuntimeError("Program identity was not assigned")
        persisted_id = record.id
        session.commit()
    except Exception:
        session.rollback()
        raise
    return replace(program, id=persisted_id)


def get_program(session, entity_id, program_id):
    """Load one Entity-scoped Program."""
    return _from_record(_load_owned_record(session, entity_id, program_id))


def list_programs(session, entity_id):
    """List Entity-scoped Programs deterministically by identity."""
    _require_positive_id(entity_id, "entity_id")
    records = session.exec(
        select(ProgramRecord)
        .where(ProgramRecord.entity_id == entity_id)
        .order_by(ProgramRecord.id)
    ).all()
    return tuple(_from_record(record) for record in records)
