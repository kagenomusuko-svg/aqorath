"""SQLite persistence authority for ThirdParty counterparties."""

from dataclasses import replace

from sqlmodel import select

from .models import EntityRecord, ThirdPartyRecord
from .third_party import ThirdParty


def _require_positive_id(value, field_name):
    if type(value) is not int:
        raise TypeError(f"{field_name} must be int")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


def _from_record(record):
    return ThirdParty(
        id=record.id,
        entity_id=record.entity_id,
        name=record.name,
        rfc=record.rfc,
        email=record.email,
        phone=record.phone,
        party_type=record.party_type,
        address=record.address,
        contact_person=record.contact_person,
        notes=record.notes,
        is_active=record.is_active,
    )


def _load_owned_record(session, entity_id, third_party_id):
    _require_positive_id(entity_id, "entity_id")
    _require_positive_id(third_party_id, "third_party_id")
    rows = session.exec(
        select(ThirdPartyRecord).where(
            ThirdPartyRecord.entity_id == entity_id,
            ThirdPartyRecord.id == third_party_id,
        )
    ).all()
    if not rows:
        raise LookupError(
            f"ThirdParty {third_party_id} not found for Entity {entity_id}"
        )
    if len(rows) != 1:
        raise RuntimeError("ThirdParty identity is structurally ambiguous")
    return rows[0]


def create_third_party(session, third_party):
    """Persist one explicit ThirdParty owned by an existing active Entity."""
    if not isinstance(third_party, ThirdParty):
        raise TypeError("third_party must be ThirdParty")
    if third_party.id is not None:
        raise ValueError("new ThirdParty id must be None")

    owner = session.get(EntityRecord, third_party.entity_id)
    if owner is None:
        raise LookupError(f"Entity {third_party.entity_id} not found")
    if owner.is_active is not True:
        raise ValueError("ThirdParty owner must be the active entity")

    record = ThirdPartyRecord(
        entity_id=third_party.entity_id,
        name=third_party.name,
        rfc=third_party.rfc,
        email=third_party.email,
        phone=third_party.phone,
        party_type=third_party.party_type,
        address=third_party.address,
        contact_person=third_party.contact_person,
        notes=third_party.notes,
        is_active=third_party.is_active,
    )
    try:
        session.add(record)
        session.flush()
        if record.id is None:
            raise RuntimeError("ThirdParty persistence did not assign identity")
        persisted_id = record.id
        session.commit()
    except Exception:
        session.rollback()
        raise
    return replace(third_party, id=persisted_id)


def get_third_party(session, entity_id, third_party_id):
    """Load one ThirdParty only within its explicit owning Entity scope."""
    return _from_record(_load_owned_record(session, entity_id, third_party_id))


def list_third_parties(session, entity_id, include_inactive=False):
    """Return deterministic Entity-scoped counterparties ordered by identity."""
    _require_positive_id(entity_id, "entity_id")
    if type(include_inactive) is not bool:
        raise TypeError("include_inactive must be bool")

    statement = select(ThirdPartyRecord).where(
        ThirdPartyRecord.entity_id == entity_id
    )
    if not include_inactive:
        statement = statement.where(ThirdPartyRecord.is_active == True)  # noqa: E712
    statement = statement.order_by(ThirdPartyRecord.id)
    return tuple(_from_record(record) for record in session.exec(statement).all())


def set_third_party_active(session, entity_id, third_party_id, is_active):
    """Activate or deactivate one ThirdParty without deleting historical identity."""
    if type(is_active) is not bool:
        raise TypeError("is_active must be bool")
    record = _load_owned_record(session, entity_id, third_party_id)
    record.is_active = is_active
    try:
        session.add(record)
        session.commit()
        session.refresh(record)
    except Exception:
        session.rollback()
        raise
    return _from_record(record)
