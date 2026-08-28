"""SQLite persistence authority for first-class OSC Donation identity."""

from dataclasses import replace
from datetime import datetime
from decimal import Decimal
import json

from sqlmodel import select

from .donation import Donation
from .models import (
    DonationRecord,
    EntityProfileRecord,
    EntityRecord,
    ThirdPartyRecord,
)


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
    return Donation(
        id=record.id,
        entity_id=record.entity_id,
        date=datetime.fromisoformat(record.date),
        amount=Decimal(record.amount),
        donor_third_party_id=record.donor_third_party_id,
        purpose=record.purpose,
        is_restricted=record.is_restricted,
    )


def _load_owned_record(session, entity_id, donation_id):
    _require_positive_id(entity_id, "entity_id")
    _require_positive_id(donation_id, "donation_id")
    rows = session.exec(
        select(DonationRecord).where(
            DonationRecord.entity_id == entity_id,
            DonationRecord.id == donation_id,
        )
    ).all()
    if not rows:
        raise LookupError("Donation not found for Entity")
    if len(rows) != 1:
        raise RuntimeError("Ambiguous Donation identity")
    return rows[0]


def create_donation(session, donation):
    """Persist one explicit Donation for an active OSC-capable Entity."""
    if not isinstance(donation, Donation):
        raise TypeError("donation must be Donation")
    if donation.id is not None:
        raise ValueError("new Donation id must be None")

    owner = session.get(EntityRecord, donation.entity_id)
    if owner is None:
        raise LookupError("Donation owner Entity does not exist")
    if owner.is_active is not True:
        raise ValueError("Donation owner Entity must be active")

    profiles = session.exec(
        select(EntityProfileRecord).where(
            EntityProfileRecord.entity_id == donation.entity_id
        )
    ).all()
    if len(profiles) != 1:
        raise RuntimeError("Donation owner Entity must have exactly one profile")
    capabilities = _decode_capabilities(profiles[0].special_capabilities_json)
    if "osc" not in capabilities:
        raise ValueError("Donation owner Entity must have explicit osc capability")

    if donation.donor_third_party_id is not None:
        donor = session.get(ThirdPartyRecord, donation.donor_third_party_id)
        if donor is None:
            raise LookupError("Donation donor ThirdParty does not exist")
        if donor.entity_id != donation.entity_id:
            raise ValueError("Donation donor must belong to the same Entity")

    record = DonationRecord(
        entity_id=donation.entity_id,
        date=donation.date.isoformat(),
        amount=str(donation.amount),
        donor_third_party_id=donation.donor_third_party_id,
        purpose=donation.purpose,
        is_restricted=donation.is_restricted,
    )
    try:
        session.add(record)
        session.flush()
        if record.id is None:
            raise RuntimeError("Donation identity was not assigned")
        persisted_id = record.id
        session.commit()
    except Exception:
        session.rollback()
        raise
    return replace(donation, id=persisted_id)


def get_donation(session, entity_id, donation_id):
    """Load one Entity-scoped Donation."""
    return _from_record(_load_owned_record(session, entity_id, donation_id))


def list_donations(session, entity_id):
    """List Entity-scoped Donations deterministically by identity."""
    _require_positive_id(entity_id, "entity_id")
    records = session.exec(
        select(DonationRecord)
        .where(DonationRecord.entity_id == entity_id)
        .order_by(DonationRecord.id)
    ).all()
    return tuple(_from_record(record) for record in records)
