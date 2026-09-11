"""AQR-015 product surface for existing first-class OSC Program authority."""

from decimal import Decimal, InvalidOperation

from . import application as _application
from . import storage as _storage
from .program import Program


def _optional_budget(value):
    if value in (None, ""):
        return None
    if type(value) is Decimal:
        return value
    if type(value) is not str:
        raise TypeError("budget must be exact decimal text or empty")
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("budget must be exact decimal text") from exc


def _program_dict(program):
    return {
        "id": program.id,
        "entity_id": program.entity_id,
        "name": program.name,
        "description": program.description,
        "budget": None if program.budget is None else str(program.budget),
    }


def list_program_surface():
    with _storage.get_session() as session:
        entity = _application.get_active_entity(session)
        if entity is None or entity.id is None:
            raise LookupError("active Entity is required")
        programs = _application.list_programs(session, entity.id)
    return [_program_dict(program) for program in programs]


def create_program_surface(payload):
    if not isinstance(payload, dict):
        raise TypeError("program payload must be an object")
    description = payload.get("description")
    if description == "":
        description = None
    with _storage.get_session() as session:
        entity = _application.get_active_entity(session)
        if entity is None or entity.id is None:
            raise LookupError("active Entity is required")
        program = Program(
            id=None,
            entity_id=entity.id,
            name=payload.get("name"),
            description=description,
            budget=_optional_budget(payload.get("budget")),
        )
        created = _application.create_program(session, program)
    return _program_dict(created)


__all__ = ["list_program_surface", "create_program_surface"]
