"""SQLite repository authority for Entity and FiscalProfile foundation.

All operations use the caller-supplied Session.  This module persists explicit
identity/profile truth only; it never selects, installs, or resolves fiscal rules.
"""

from dataclasses import replace
from datetime import date
import json

from sqlmodel import select

from .entity import Entity, EntityProfile, FiscalProfile
from .models import EntityProfileRecord, EntityRecord, FiscalProfileRecord


def _encode_tuple(values):
    return json.dumps(list(values), ensure_ascii=False, separators=(",", ":"))


def _decode_tuple(raw, field_name):
    if not isinstance(raw, str):
        raise RuntimeError(f"persisted {field_name} must be JSON text")
    try:
        value = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"persisted {field_name} is invalid JSON") from exc
    if not isinstance(value, list):
        raise RuntimeError(f"persisted {field_name} must decode to list")
    if any(not isinstance(item, str) for item in value):
        raise RuntimeError(f"persisted {field_name} must contain only strings")
    return tuple(value)


def _entity_from_records(entity_record, profile_record):
    profile = EntityProfile(
        economic_purpose=profile_record.economic_purpose,
        is_donor_authorized=profile_record.is_donor_authorized,
        special_capabilities=_decode_tuple(
            profile_record.special_capabilities_json,
            "special_capabilities_json",
        ),
        modules_enabled=_decode_tuple(
            profile_record.modules_enabled_json,
            "modules_enabled_json",
        ),
    )
    return Entity(
        id=entity_record.id,
        name=entity_record.name,
        rfc=entity_record.rfc,
        legal_personality=entity_record.legal_personality,
        legal_form=entity_record.legal_form,
        profile=profile,
        is_active=entity_record.is_active,
    )


def _fiscal_profile_from_record(record):
    return FiscalProfile(
        id=record.id,
        entity_id=record.entity_id,
        jurisdiction=record.jurisdiction,
        fiscal_regime_code=record.fiscal_regime_code,
        tax_characteristics=_decode_tuple(
            record.tax_characteristics_json,
            "tax_characteristics_json",
        ),
        effective_from=record.effective_from,
        effective_to=record.effective_to,
    )


def create_entity(session, entity):
    """Atomically persist one Entity aggregate through the supplied Session."""
    if not isinstance(entity, Entity):
        raise TypeError("entity must be Entity")
    if entity.id is not None:
        raise ValueError("new entity id must be None")

    if entity.is_active:
        active = session.exec(
            select(EntityRecord).where(EntityRecord.is_active == True)  # noqa: E712
        ).all()
        if active:
            raise ValueError("active entity already exists")

    record = EntityRecord(
        name=entity.name,
        rfc=entity.rfc,
        legal_personality=entity.legal_personality,
        legal_form=entity.legal_form,
        is_active=entity.is_active,
    )
    try:
        session.add(record)
        session.flush()
        if record.id is None:
            raise RuntimeError("entity persistence did not assign identity")
        session.add(
            EntityProfileRecord(
                entity_id=record.id,
                economic_purpose=entity.profile.economic_purpose,
                is_donor_authorized=entity.profile.is_donor_authorized,
                special_capabilities_json=_encode_tuple(
                    entity.profile.special_capabilities
                ),
                modules_enabled_json=_encode_tuple(entity.profile.modules_enabled),
            )
        )
        session.commit()
    except Exception:
        session.rollback()
        raise

    return replace(entity, id=record.id)


def load_active_entity(session):
    """Load the one active Entity aggregate, or None before entity setup."""
    rows = session.exec(
        select(EntityRecord).where(EntityRecord.is_active == True)  # noqa: E712
    ).all()
    if not rows:
        return None
    if len(rows) != 1:
        raise RuntimeError("multiple active entities violate monoentity authority")

    entity_record = rows[0]
    profiles = session.exec(
        select(EntityProfileRecord).where(
            EntityProfileRecord.entity_id == entity_record.id
        )
    ).all()
    if len(profiles) != 1:
        raise RuntimeError("active entity must have exactly one entity profile")
    return _entity_from_records(entity_record, profiles[0])


def register_fiscal_profile(session, profile):
    """Persist one explicit non-overlapping fiscal profile interval."""
    if not isinstance(profile, FiscalProfile):
        raise TypeError("profile must be FiscalProfile")
    if profile.id is not None:
        raise ValueError("new fiscal profile id must be None")

    entity_record = session.get(EntityRecord, profile.entity_id)
    if entity_record is None:
        raise LookupError(f"entity {profile.entity_id} not found")

    existing = session.exec(
        select(FiscalProfileRecord).where(
            FiscalProfileRecord.entity_id == profile.entity_id
        )
    ).all()
    for record in existing:
        existing_end = record.effective_to
        new_end = profile.effective_to
        starts_before_existing_ends = (
            existing_end is None or profile.effective_from <= existing_end
        )
        existing_starts_before_new_ends = (
            new_end is None or record.effective_from <= new_end
        )
        if starts_before_existing_ends and existing_starts_before_new_ends:
            raise ValueError("fiscal profile overlap")

    record = FiscalProfileRecord(
        entity_id=profile.entity_id,
        jurisdiction=profile.jurisdiction,
        fiscal_regime_code=profile.fiscal_regime_code,
        tax_characteristics_json=_encode_tuple(profile.tax_characteristics),
        effective_from=profile.effective_from,
        effective_to=profile.effective_to,
    )
    try:
        session.add(record)
        session.flush()
        if record.id is None:
            raise RuntimeError("fiscal profile persistence did not assign identity")
        session.commit()
    except Exception:
        session.rollback()
        raise
    return replace(profile, id=record.id)


def resolve_fiscal_profile(session, entity_id, effective_date):
    """Resolve exactly one explicit profile for one entity and effective date."""
    if type(entity_id) is not int:
        raise TypeError("entity_id must be int")
    if entity_id <= 0:
        raise ValueError("entity_id must be positive")
    if type(effective_date) is not date:
        raise TypeError("effective_date must be date")

    rows = session.exec(
        select(FiscalProfileRecord).where(
            FiscalProfileRecord.entity_id == entity_id
        )
    ).all()
    applicable = [
        record
        for record in rows
        if record.effective_from <= effective_date
        and (record.effective_to is None or effective_date <= record.effective_to)
    ]
    if not applicable:
        raise LookupError(
            f"no fiscal profile for entity {entity_id} on {effective_date.isoformat()}"
        )
    if len(applicable) != 1:
        raise RuntimeError("ambiguous overlapping fiscal profile history")
    return _fiscal_profile_from_record(applicable[0])
