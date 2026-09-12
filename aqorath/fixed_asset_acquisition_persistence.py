"""Atomic persisted identity for fixed-asset acquisition posting — Phase 6Q.2.

The canonical ledger remains authoritative for date, accounts, and money. The fixed-
asset registry remains authoritative for asset identity and acquisition cost. This
module adds only one-use asset/entry identity plus the structured economic provenance
that cannot be reconstructed safely from concrete ledger lines.
"""

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlmodel import select

from . import audit_event_repository as _audit_repository
from . import core as _core
from . import fixed_asset_acquisition as _fixed_asset_acquisition
from . import storage as _storage
from .audit_event import AuditEvent
from .fixed_asset_acquisition_posting import FixedAssetAcquisitionPostingInstruction
from .models import (
    FixedAssetAcquisitionPostingRecord,
    FixedAssetRecord,
    JournalEntry,
)


__all__ = [
    "PersistedFixedAssetAcquisitionPosting",
    "execute_fixed_asset_acquisition_posting_once",
    "load_fixed_asset_acquisition_posting",
]


@dataclass(frozen=True)
class PersistedFixedAssetAcquisitionPosting:
    """Minimal persisted acquisition identity reconstructed from canonical SQLite."""

    fixed_asset_id: int
    entry_id: int
    posting_date: date
    asset_class: str
    settlement_method: str

    def __post_init__(self):
        for name, value in (
            ("fixed_asset_id", self.fixed_asset_id),
            ("entry_id", self.entry_id),
        ):
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if type(self.posting_date) is not date:
            raise TypeError("posting_date must be an exact date")
        if (
            type(self.asset_class) is not str
            or self.asset_class not in _fixed_asset_acquisition._ASSET_CLASS_DEBIT_ROLES
        ):
            raise ValueError("asset_class is not a supported acquisition classification")
        if (
            type(self.settlement_method) is not str
            or self.settlement_method not in _fixed_asset_acquisition._SETTLEMENT_CREDIT_ROLES
        ):
            raise ValueError("settlement_method is not a supported acquisition settlement")


def _acquisition_truth(instruction):
    return (
        instruction.confirmed_acquisition.snapshot
        .accounting_resolution.acquisition_fact
    )


def _decimal_text_matches(text_value, expected):
    if type(text_value) is not str or not isinstance(expected, Decimal):
        return False
    try:
        parsed = Decimal(text_value)
    except (InvalidOperation, ValueError):
        return False
    if not parsed.is_finite() or not expected.is_finite():
        return False
    return parsed.as_tuple() == expected.as_tuple()


def _persisted_asset_matches_acquisition(record, acquisition):
    return (
        record.id == acquisition.fixed_asset_id
        and record.entity_id == acquisition.entity_id
        and record.code == acquisition.fixed_asset_code
        and record.acquisition_date == acquisition.acquisition_date
        and _decimal_text_matches(record.acquisition_cost, acquisition.acquisition_cost)
    )


def _entry_payload(instruction):
    return {
        "date": instruction.posting_date,
        "description": instruction.posting_instruction.description,
        "state": "posted",
        "lines": [
            {
                "account_id": line.account_id,
                "account_code": line.account_code,
                "debit": line.debit,
                "credit": line.credit,
            }
            for line in instruction.posting_instruction.lines
        ],
    }


def _audit_details(acquisition, entry_id, posting_date):
    return {
        "entry_id": entry_id,
        "decision": {
            "fact": {
                "type": "fixed_asset_acquisition",
                "amount": str(acquisition.acquisition_cost),
                "payment_method": acquisition.settlement_method,
            },
            "posting_date": posting_date.isoformat(),
            "consent": "explicit_confirmation",
            "specialized_authority": "fixed_asset_acquisition",
            "fixed_asset_id": acquisition.fixed_asset_id,
            "asset_class": acquisition.asset_class,
            "settlement_method": acquisition.settlement_method,
        },
    }


def execute_fixed_asset_acquisition_posting_once(instruction):
    """Atomically post one confirmed fixed-asset acquisition at most once."""
    if not isinstance(instruction, FixedAssetAcquisitionPostingInstruction):
        raise TypeError(
            "instruction must be a FixedAssetAcquisitionPostingInstruction"
        )

    acquisition = _acquisition_truth(instruction)
    fixed_asset_id = acquisition.fixed_asset_id
    if type(fixed_asset_id) is not int or fixed_asset_id <= 0:
        return {
            "ok": False,
            "error": "Fixed asset must have a persistent positive identity before acquisition posting",
        }

    session = None
    try:
        with _storage.get_session() as session:
            persisted_asset = session.get(FixedAssetRecord, fixed_asset_id)
            if persisted_asset is None:
                session.rollback()
                return {
                    "ok": False,
                    "error": f"Fixed asset {fixed_asset_id} does not exist in canonical SQLite",
                }
            if not _persisted_asset_matches_acquisition(
                persisted_asset,
                acquisition,
            ):
                session.rollback()
                return {
                    "ok": False,
                    "error": f"Fixed asset {fixed_asset_id} persisted identity does not match confirmed acquisition truth",
                }

            existing = session.exec(
                select(FixedAssetAcquisitionPostingRecord).where(
                    FixedAssetAcquisitionPostingRecord.fixed_asset_id == fixed_asset_id
                )
            ).one_or_none()
            if existing is not None:
                session.rollback()
                return {
                    "ok": False,
                    "error": f"Fixed asset acquisition {fixed_asset_id} is already posted",
                }

            entry, error = _core._stage_entry_in_session(
                session,
                _entry_payload(instruction),
            )
            if error is not None:
                session.rollback()
                return {"ok": False, "error": error}
            if entry is None or entry.id is None:
                session.rollback()
                return {
                    "ok": False,
                    "error": "ORM staging returned no JournalEntry identity",
                }

            _audit_repository.stage_audit_event(
                session,
                AuditEvent(
                    id=None,
                    entity_id=acquisition.entity_id,
                    event_type="entry_posted",
                    timestamp=datetime.now(timezone.utc),
                    details=_audit_details(
                        acquisition,
                        entry.id,
                        instruction.posting_date,
                    ),
                ),
            )

            record = FixedAssetAcquisitionPostingRecord(
                fixed_asset_id=fixed_asset_id,
                entry_id=entry.id,
                asset_class=acquisition.asset_class,
                settlement_method=acquisition.settlement_method,
            )
            session.add(record)
            session.commit()
            return {"ok": True, "entry_id": entry.id}
    except Exception as exc:
        if session is not None:
            try:
                session.rollback()
            except Exception:
                pass
        return {"ok": False, "error": str(exc)}


def _validate_positive_integer(name, value):
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def load_fixed_asset_acquisition_posting(session, fixed_asset_id):
    """Read one persisted acquisition identity using only the supplied session."""
    _validate_positive_integer("fixed_asset_id", fixed_asset_id)

    records = session.exec(
        select(FixedAssetAcquisitionPostingRecord).where(
            FixedAssetAcquisitionPostingRecord.fixed_asset_id == fixed_asset_id
        )
    ).all()
    if not records:
        raise LookupError(
            f"No persisted acquisition posting for fixed asset {fixed_asset_id}"
        )
    if len(records) != 1:
        raise LookupError(
            f"Ambiguous persisted acquisition posting for fixed asset {fixed_asset_id}"
        )
    record = records[0]

    entry = session.get(JournalEntry, record.entry_id)
    if entry is None:
        raise LookupError(
            f"Acquisition registry references missing JournalEntry {record.entry_id}"
        )
    if not isinstance(entry.date, datetime):
        raise ValueError("Persisted JournalEntry date is not a datetime")

    return PersistedFixedAssetAcquisitionPosting(
        fixed_asset_id=record.fixed_asset_id,
        entry_id=record.entry_id,
        posting_date=entry.date.date(),
        asset_class=record.asset_class,
        settlement_method=record.settlement_method,
    )
