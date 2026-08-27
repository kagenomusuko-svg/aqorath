"""Persistence authority for analytical dimensions and line assignments."""

from dataclasses import replace

from sqlmodel import select

from .analytical_dimension import (
    AnalyticalDimension,
    AnalyticalDimensionAssignment,
    AnalyticalDimensionValue,
)
from .models import (
    AnalyticalDimensionRecord,
    AnalyticalDimensionValueRecord,
    EntityRecord,
    JournalLine,
    JournalLineAnalyticalDimensionRecord,
)


def _require_positive_id(value, field_name):
    if type(value) is not int:
        raise TypeError(f"{field_name} must be int")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


def _dimension_from_record(record):
    return AnalyticalDimension(
        id=record.id,
        entity_id=record.entity_id,
        key=record.key,
        name=record.name,
    )


def _value_from_record(record):
    return AnalyticalDimensionValue(
        id=record.id,
        dimension_id=record.dimension_id,
        code=record.code,
        name=record.name,
    )


def _assignment_from_records(line_id, dimension, value):
    return AnalyticalDimensionAssignment(
        journal_line_id=line_id,
        dimension_id=dimension.id,
        dimension_key=dimension.key,
        dimension_name=dimension.name,
        value_id=value.id,
        value_code=value.code,
        value_name=value.name,
    )


def _load_dimension_record(session, dimension_id):
    _require_positive_id(dimension_id, "dimension_id")
    record = session.get(AnalyticalDimensionRecord, dimension_id)
    if record is None:
        raise LookupError(f"AnalyticalDimension {dimension_id} not found")
    return record


def _load_value_record(session, dimension_value_id):
    _require_positive_id(dimension_value_id, "dimension_value_id")
    record = session.get(AnalyticalDimensionValueRecord, dimension_value_id)
    if record is None:
        raise LookupError(
            f"AnalyticalDimensionValue {dimension_value_id} not found"
        )
    return record


def create_analytical_dimension(session, dimension):
    """Persist one explicit analytical axis for an existing active Entity."""
    if not isinstance(dimension, AnalyticalDimension):
        raise TypeError("dimension must be AnalyticalDimension")
    if dimension.id is not None:
        raise ValueError("new AnalyticalDimension id must be None")

    owner = session.get(EntityRecord, dimension.entity_id)
    if owner is None:
        raise LookupError(f"Entity {dimension.entity_id} not found")
    if owner.is_active is not True:
        raise ValueError("AnalyticalDimension owner must be the active entity")

    existing = session.exec(
        select(AnalyticalDimensionRecord).where(
            AnalyticalDimensionRecord.entity_id == dimension.entity_id,
            AnalyticalDimensionRecord.key == dimension.key,
        )
    ).first()
    if existing is not None:
        raise ValueError(
            f"AnalyticalDimension key {dimension.key!r} already exists for Entity {dimension.entity_id}"
        )

    record = AnalyticalDimensionRecord(
        entity_id=dimension.entity_id,
        key=dimension.key,
        name=dimension.name,
    )
    try:
        session.add(record)
        session.flush()
        if record.id is None:
            raise RuntimeError("AnalyticalDimension persistence did not assign identity")
        persisted_id = record.id
        session.commit()
    except Exception:
        session.rollback()
        raise
    return replace(dimension, id=persisted_id)


def get_analytical_dimension(session, entity_id, dimension_id):
    """Load one analytical axis only inside its explicit Entity scope."""
    _require_positive_id(entity_id, "entity_id")
    _require_positive_id(dimension_id, "dimension_id")
    rows = session.exec(
        select(AnalyticalDimensionRecord).where(
            AnalyticalDimensionRecord.entity_id == entity_id,
            AnalyticalDimensionRecord.id == dimension_id,
        )
    ).all()
    if not rows:
        raise LookupError(
            f"AnalyticalDimension {dimension_id} not found for Entity {entity_id}"
        )
    if len(rows) != 1:
        raise RuntimeError("AnalyticalDimension identity is structurally ambiguous")
    return _dimension_from_record(rows[0])


def list_analytical_dimensions(session, entity_id):
    """List deterministic analytical axes belonging to one existing Entity."""
    _require_positive_id(entity_id, "entity_id")
    if session.get(EntityRecord, entity_id) is None:
        raise LookupError(f"Entity {entity_id} not found")
    rows = session.exec(
        select(AnalyticalDimensionRecord)
        .where(AnalyticalDimensionRecord.entity_id == entity_id)
        .order_by(AnalyticalDimensionRecord.id)
    ).all()
    return tuple(_dimension_from_record(record) for record in rows)


def create_analytical_dimension_value(session, dimension_value):
    """Persist one explicit value under one existing analytical axis."""
    if not isinstance(dimension_value, AnalyticalDimensionValue):
        raise TypeError("dimension_value must be AnalyticalDimensionValue")
    if dimension_value.id is not None:
        raise ValueError("new AnalyticalDimensionValue id must be None")

    _load_dimension_record(session, dimension_value.dimension_id)
    existing = session.exec(
        select(AnalyticalDimensionValueRecord).where(
            AnalyticalDimensionValueRecord.dimension_id
            == dimension_value.dimension_id,
            AnalyticalDimensionValueRecord.code == dimension_value.code,
        )
    ).first()
    if existing is not None:
        raise ValueError(
            f"AnalyticalDimensionValue code {dimension_value.code!r} already exists for AnalyticalDimension {dimension_value.dimension_id}"
        )

    record = AnalyticalDimensionValueRecord(
        dimension_id=dimension_value.dimension_id,
        code=dimension_value.code,
        name=dimension_value.name,
    )
    try:
        session.add(record)
        session.flush()
        if record.id is None:
            raise RuntimeError(
                "AnalyticalDimensionValue persistence did not assign identity"
            )
        persisted_id = record.id
        session.commit()
    except Exception:
        session.rollback()
        raise
    return replace(dimension_value, id=persisted_id)


def list_analytical_dimension_values(session, dimension_id):
    """List deterministic values belonging to one existing analytical axis."""
    _load_dimension_record(session, dimension_id)
    rows = session.exec(
        select(AnalyticalDimensionValueRecord)
        .where(AnalyticalDimensionValueRecord.dimension_id == dimension_id)
        .order_by(AnalyticalDimensionValueRecord.id)
    ).all()
    return tuple(_value_from_record(record) for record in rows)


def assign_analytical_dimension_value(session, journal_line_id, dimension_value_id):
    """Attach one explicit analytical value to one existing ledger line."""
    _require_positive_id(journal_line_id, "journal_line_id")
    _require_positive_id(dimension_value_id, "dimension_value_id")

    line = session.get(JournalLine, journal_line_id)
    if line is None:
        raise LookupError(f"JournalLine {journal_line_id} not found")
    value_record = _load_value_record(session, dimension_value_id)
    dimension_record = _load_dimension_record(session, value_record.dimension_id)

    existing = session.exec(
        select(JournalLineAnalyticalDimensionRecord).where(
            JournalLineAnalyticalDimensionRecord.journal_line_id == journal_line_id,
            JournalLineAnalyticalDimensionRecord.dimension_id
            == dimension_record.id,
        )
    ).first()
    if existing is not None:
        raise ValueError(
            f"JournalLine {journal_line_id} already has a value for AnalyticalDimension {dimension_record.id}"
        )

    assignment_record = JournalLineAnalyticalDimensionRecord(
        journal_line_id=journal_line_id,
        dimension_id=dimension_record.id,
        dimension_value_id=value_record.id,
    )
    try:
        session.add(assignment_record)
        session.flush()
        if assignment_record.id is None:
            raise RuntimeError("Analytical assignment persistence did not assign identity")
        session.commit()
    except Exception:
        session.rollback()
        raise

    return _assignment_from_records(
        journal_line_id,
        dimension_record,
        value_record,
    )


def list_journal_line_analytics(session, journal_line_id):
    """List assigned analytical values for one existing ledger line."""
    _require_positive_id(journal_line_id, "journal_line_id")
    if session.get(JournalLine, journal_line_id) is None:
        raise LookupError(f"JournalLine {journal_line_id} not found")

    rows = session.exec(
        select(JournalLineAnalyticalDimensionRecord)
        .where(
            JournalLineAnalyticalDimensionRecord.journal_line_id == journal_line_id
        )
        .order_by(JournalLineAnalyticalDimensionRecord.id)
    ).all()

    result = []
    for assignment in rows:
        dimension = session.get(
            AnalyticalDimensionRecord,
            assignment.dimension_id,
        )
        value = session.get(
            AnalyticalDimensionValueRecord,
            assignment.dimension_value_id,
        )
        if dimension is None or value is None:
            raise RuntimeError("Analytical assignment references missing identity")
        if value.dimension_id != dimension.id:
            raise RuntimeError("Analytical assignment dimension/value mismatch")
        result.append(
            _assignment_from_records(journal_line_id, dimension, value)
        )
    return tuple(result)
