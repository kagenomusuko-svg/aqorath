"""Canonical read-only fixed-asset book-state projection.

Book state is derived from persisted fixed-asset registry metadata plus depreciation
postings explicitly linked to that asset by the Phase 6M period registry.  This module
does not project a theoretical schedule and does not use a global contra-asset balance.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlmodel import select

from .models import (
    FixedAssetDepreciationPostingRecord,
    FixedAssetRecord,
    JournalEntry,
    JournalLine,
)


def _require_positive_int(value, field_name):
    if type(value) is not int:
        raise TypeError(f"{field_name} must be an int")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")
    return value


def _require_date_or_none(value):
    if value is not None and type(value) is not date:
        raise TypeError("as_of must be a date or None")
    return value


def _decimal_from_text(value, field_name):
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must contain exact Decimal text")
    try:
        amount = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name} contains invalid Decimal text") from exc
    if not amount.is_finite():
        raise ValueError(f"{field_name} must be finite")
    return amount


def _require_nonnegative_decimal(value, field_name):
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be Decimal")
    if not value.is_finite() or value < 0:
        raise ValueError(f"{field_name} must be finite and non-negative")
    return value


@dataclass(frozen=True)
class FixedAssetRecognizedDepreciationPeriod:
    period_number: int
    entry_id: int
    posting_date: date
    recognition_source_ref: str
    amount: Decimal

    def __post_init__(self):
        _require_positive_int(self.period_number, "period_number")
        _require_positive_int(self.entry_id, "entry_id")
        if type(self.posting_date) is not date:
            raise TypeError("posting_date must be a date")
        if not isinstance(self.recognition_source_ref, str) or not self.recognition_source_ref.strip():
            raise ValueError("recognition_source_ref must be non-empty")
        _require_nonnegative_decimal(self.amount, "amount")
        if self.amount <= 0:
            raise ValueError("recognized depreciation amount must be positive")


@dataclass(frozen=True)
class FixedAssetBookState:
    fixed_asset_id: int
    entity_id: int
    code: str
    as_of: date | None
    acquisition_cost: Decimal
    residual_value: Decimal
    accumulated_depreciation: Decimal
    carrying_value: Decimal
    recognized_periods: tuple

    def __post_init__(self):
        _require_positive_int(self.fixed_asset_id, "fixed_asset_id")
        _require_positive_int(self.entity_id, "entity_id")
        if not isinstance(self.code, str) or not self.code.strip():
            raise ValueError("code must be non-empty")
        _require_date_or_none(self.as_of)
        _require_nonnegative_decimal(self.acquisition_cost, "acquisition_cost")
        _require_nonnegative_decimal(self.residual_value, "residual_value")
        _require_nonnegative_decimal(self.accumulated_depreciation, "accumulated_depreciation")
        _require_nonnegative_decimal(self.carrying_value, "carrying_value")
        if self.residual_value > self.acquisition_cost:
            raise ValueError("residual_value cannot exceed acquisition_cost")
        if not isinstance(self.recognized_periods, tuple):
            raise TypeError("recognized_periods must be a tuple")
        if any(type(period) is not FixedAssetRecognizedDepreciationPeriod for period in self.recognized_periods):
            raise TypeError("recognized_periods must contain nominal period snapshots")
        positions = tuple(period.period_number for period in self.recognized_periods)
        if positions != tuple(sorted(positions)) or len(set(positions)) != len(positions):
            raise ValueError("recognized_periods must be uniquely ordered by period_number")
        expected_accumulated = sum(
            (period.amount for period in self.recognized_periods),
            Decimal("0"),
        )
        if self.accumulated_depreciation != expected_accumulated:
            raise ValueError("accumulated_depreciation must equal recognized period truth")
        expected_carrying = self.acquisition_cost - self.accumulated_depreciation
        if self.carrying_value.as_tuple() != expected_carrying.as_tuple():
            raise ValueError("carrying_value must preserve exact acquisition less recognized depreciation")
        if self.carrying_value < self.residual_value:
            raise ValueError("recognized depreciation cannot reduce carrying value below residual value")


def _load_asset_record(session, entity_id, fixed_asset_id):
    record = session.get(FixedAssetRecord, fixed_asset_id)
    if record is None or record.entity_id != entity_id:
        raise LookupError(
            f"Fixed asset {fixed_asset_id} does not exist for entity {entity_id}"
        )
    return record


def _load_entry_amount(session, entry_id):
    entry = session.get(JournalEntry, entry_id)
    if entry is None:
        raise LookupError(f"Journal entry {entry_id} linked to depreciation does not exist")
    if not isinstance(entry.date, datetime):
        raise ValueError("linked JournalEntry.date is invalid")

    lines = tuple(
        session.exec(
            select(JournalLine)
            .where(JournalLine.entry_id == entry_id)
            .order_by(JournalLine.id)
        ).all()
    )
    if len(lines) != 2:
        raise ValueError("linked depreciation entry must contain exactly two lines")

    debit_amount = None
    credit_amount = None
    for line in lines:
        debit = _decimal_from_text(line.debit, "JournalLine.debit")
        credit = _decimal_from_text(line.credit, "JournalLine.credit")
        if debit < 0 or credit < 0:
            raise ValueError("linked depreciation line amounts cannot be negative")
        if debit > 0 and credit == 0:
            if debit_amount is not None:
                raise ValueError("linked depreciation entry must have exactly one debit line")
            debit_amount = debit
        elif credit > 0 and debit == 0:
            if credit_amount is not None:
                raise ValueError("linked depreciation entry must have exactly one credit line")
            credit_amount = credit
        else:
            raise ValueError("linked depreciation lines must be one-sided and positive")

    if debit_amount is None or credit_amount is None:
        raise ValueError("linked depreciation entry must contain one debit and one credit")
    if debit_amount.as_tuple() != credit_amount.as_tuple():
        raise ValueError("linked depreciation entry must be exactly balanced")
    return entry, debit_amount


def load_fixed_asset_book_state(session, entity_id, fixed_asset_id, as_of=None):
    """Project recognized fixed-asset book state from canonical persisted truth."""

    _require_positive_int(entity_id, "entity_id")
    _require_positive_int(fixed_asset_id, "fixed_asset_id")
    _require_date_or_none(as_of)

    asset = _load_asset_record(session, entity_id, fixed_asset_id)
    acquisition_cost = _decimal_from_text(asset.acquisition_cost, "FixedAsset.acquisition_cost")
    residual_value = _decimal_from_text(asset.residual_value, "FixedAsset.residual_value")
    if acquisition_cost < 0 or residual_value < 0:
        raise ValueError("fixed-asset monetary metadata cannot be negative")
    if residual_value > acquisition_cost:
        raise ValueError("residual_value cannot exceed acquisition_cost")

    records = tuple(
        session.exec(
            select(FixedAssetDepreciationPostingRecord)
            .where(FixedAssetDepreciationPostingRecord.fixed_asset_id == fixed_asset_id)
            .order_by(FixedAssetDepreciationPostingRecord.period_number)
        ).all()
    )

    periods = []
    seen_periods = set()
    for record in records:
        _require_positive_int(record.period_number, "persisted period_number")
        _require_positive_int(record.entry_id, "persisted entry_id")
        if record.period_number in seen_periods:
            raise ValueError("duplicate persisted depreciation period identity")
        seen_periods.add(record.period_number)
        if not isinstance(record.recognition_source_ref, str) or not record.recognition_source_ref.strip():
            raise ValueError("persisted recognition_source_ref is invalid")

        entry, amount = _load_entry_amount(session, record.entry_id)
        posting_date = entry.date.date()
        if as_of is not None and posting_date > as_of:
            continue
        periods.append(
            FixedAssetRecognizedDepreciationPeriod(
                period_number=record.period_number,
                entry_id=record.entry_id,
                posting_date=posting_date,
                recognition_source_ref=record.recognition_source_ref,
                amount=amount,
            )
        )

    recognized_periods = tuple(periods)
    accumulated = sum(
        (period.amount for period in recognized_periods),
        Decimal("0"),
    )
    maximum_depreciation = acquisition_cost - residual_value
    if accumulated > maximum_depreciation:
        raise ValueError("recognized depreciation exceeds depreciable fixed-asset amount")
    carrying_value = acquisition_cost - accumulated

    return FixedAssetBookState(
        fixed_asset_id=fixed_asset_id,
        entity_id=entity_id,
        code=asset.code,
        as_of=as_of,
        acquisition_cost=acquisition_cost,
        residual_value=residual_value,
        accumulated_depreciation=accumulated,
        carrying_value=carrying_value,
        recognized_periods=recognized_periods,
    )
