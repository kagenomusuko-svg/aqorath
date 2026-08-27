"""Atomic persisted identity for fixed-asset depreciation posting — Phase 6M.2.

The ledger remains authoritative for date, accounts, and money. This module adds only
one-use fixed-asset/period identity plus recognition provenance, committed atomically
with the JournalEntry and JournalLine rows staged by the canonical core primitive.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlmodel import select

from . import core as _core
from . import storage as _storage
from .fixed_asset_depreciation_posting import (
    FixedAssetDepreciationPostingInstruction,
)
from .models import (
    FixedAssetDepreciationPostingRecord,
    FixedAssetRecord,
    JournalEntry,
)


__all__ = [
    "PersistedFixedAssetDepreciationPosting",
    "execute_fixed_asset_depreciation_posting_once",
    "load_fixed_asset_depreciation_posting",
]


@dataclass(frozen=True)
class PersistedFixedAssetDepreciationPosting:
    """Minimal persisted depreciation-period identity reconstructed from SQLite."""

    fixed_asset_id: int
    period_number: int
    entry_id: int
    posting_date: date
    recognition_source_ref: str

    def __post_init__(self):
        for name, value in (
            ("fixed_asset_id", self.fixed_asset_id),
            ("period_number", self.period_number),
            ("entry_id", self.entry_id),
        ):
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if type(self.posting_date) is not date:
            raise TypeError("posting_date must be an exact date")
        if (
            not isinstance(self.recognition_source_ref, str)
            or not self.recognition_source_ref
            or self.recognition_source_ref.strip() != self.recognition_source_ref
        ):
            raise ValueError(
                "recognition_source_ref must be a non-empty string without surrounding whitespace"
            )


def _recognition_truth(instruction):
    return (
        instruction.confirmed_depreciation.snapshot
        .accounting_resolution.recognition_fact
    )


def _calculation_truth(recognition):
    return recognition.allocation.calculation


def _decimal_text_matches(text_value, expected):
    if not isinstance(text_value, str) or not isinstance(expected, Decimal):
        return False
    try:
        parsed = Decimal(text_value)
    except (InvalidOperation, ValueError):
        return False
    return parsed.as_tuple() == expected.as_tuple()


def _persisted_asset_matches_calculation(record, calculation):
    return (
        record.entity_id == calculation.entity_id
        and record.code == calculation.fixed_asset_code
        and record.in_service_date == calculation.in_service_date
        and _decimal_text_matches(record.acquisition_cost, calculation.acquisition_cost)
        and _decimal_text_matches(record.residual_value, calculation.residual_value)
        and record.useful_life_months == calculation.useful_life_months
        and record.depreciation_method == calculation.depreciation_method
    )


def _entry_payload(instruction):
    return {
        "date": instruction.posting_date,
        "description": instruction.posting_instruction.description,
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


def execute_fixed_asset_depreciation_posting_once(instruction):
    """Atomically post one confirmed depreciation period exactly once."""
    if not isinstance(instruction, FixedAssetDepreciationPostingInstruction):
        raise TypeError(
            "instruction must be a FixedAssetDepreciationPostingInstruction"
        )

    recognition = _recognition_truth(instruction)
    calculation = _calculation_truth(recognition)
    fixed_asset_id = calculation.fixed_asset_id
    if type(fixed_asset_id) is not int or fixed_asset_id <= 0:
        return {
            "ok": False,
            "error": "Fixed asset must have a persistent positive identity before depreciation posting",
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
            if not _persisted_asset_matches_calculation(
                persisted_asset,
                calculation,
            ):
                session.rollback()
                return {
                    "ok": False,
                    "error": f"Fixed asset {fixed_asset_id} persisted identity does not match confirmed depreciation truth",
                }

            existing = session.exec(
                select(FixedAssetDepreciationPostingRecord).where(
                    FixedAssetDepreciationPostingRecord.fixed_asset_id
                    == fixed_asset_id,
                    FixedAssetDepreciationPostingRecord.period_number
                    == recognition.period_number,
                )
            ).one_or_none()
            if existing is not None:
                session.rollback()
                return {
                    "ok": False,
                    "error": (
                        f"Depreciation period {recognition.period_number} for fixed asset "
                        f"{fixed_asset_id} is already posted"
                    ),
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

            record = FixedAssetDepreciationPostingRecord(
                fixed_asset_id=fixed_asset_id,
                period_number=recognition.period_number,
                entry_id=entry.id,
                recognition_source_ref=recognition.recognition_source_ref,
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


def load_fixed_asset_depreciation_posting(session, fixed_asset_id, period_number):
    """Read one persisted asset-period identity using only the supplied session."""
    _validate_positive_integer("fixed_asset_id", fixed_asset_id)
    _validate_positive_integer("period_number", period_number)

    record = session.exec(
        select(FixedAssetDepreciationPostingRecord).where(
            FixedAssetDepreciationPostingRecord.fixed_asset_id == fixed_asset_id,
            FixedAssetDepreciationPostingRecord.period_number == period_number,
        )
    ).one_or_none()
    if record is None:
        raise LookupError(
            f"No persisted depreciation period {period_number} for fixed asset {fixed_asset_id}"
        )

    entry = session.get(JournalEntry, record.entry_id)
    if entry is None:
        raise LookupError(
            f"Depreciation period registry references missing JournalEntry {record.entry_id}"
        )
    if not isinstance(entry.date, datetime):
        raise ValueError("Persisted JournalEntry date is not a datetime")

    return PersistedFixedAssetDepreciationPosting(
        fixed_asset_id=record.fixed_asset_id,
        period_number=record.period_number,
        entry_id=record.entry_id,
        posting_date=entry.date.date(),
        recognition_source_ref=record.recognition_source_ref,
    )
