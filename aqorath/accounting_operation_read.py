"""Read-only professional projection for AQR-005.

This module belongs to the application/read side, not to presentation. It composes
existing ledger, period, document and audit authorities without recalculating
accounting or fiscal truth. Presentation adapters must not import ORM models.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlmodel import select

from . import accounting_period_repository as _periods
from . import audit_event_repository as _audit_events
from . import document_reference_repository as _documents
from . import entity_repository as _entities
from . import fiscal_posting_audit_read as _fiscal_audit
from . import models as _models
from .accounting_period import accounting_date


@dataclass(frozen=True)
class ProfessionalPeriodView:
    id: int
    year: int
    month: int
    start: date
    end: date
    state: str
    fiscal_year_state: str


@dataclass(frozen=True)
class ProfessionalLineView:
    id: int
    account_id: int
    account_code: str
    account_name: str
    debit: Decimal
    credit: Decimal
    description: str | None


@dataclass(frozen=True)
class ProfessionalEntrySummary:
    entry_id: int
    posting_date: date
    concept: str | None
    state: str
    period_id: int | None


@dataclass(frozen=True)
class ReversalView:
    original_entry_id: int
    reversal_entry_id: int
    reason: str


@dataclass(frozen=True)
class GeneralAuditView:
    id: int
    event_type: str
    timestamp: datetime
    details: dict


@dataclass(frozen=True)
class ProfessionalAccountingOperationView:
    entry_id: int
    posting_date: date
    concept: str
    state: str
    period: ProfessionalPeriodView
    lines: tuple[ProfessionalLineView, ...]
    documents: tuple
    audit: GeneralAuditView | None
    reversal: ReversalView | None
    fiscal_audit: object | None


def _decimal(value, field_name):
    if not isinstance(value, str):
        value = str(value)
    try:
        result = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid persisted Decimal in {field_name}") from exc
    if not result.is_finite() or result < Decimal("0"):
        raise ValueError(f"persisted {field_name} must be finite and non-negative")
    return result


def _load_period(session, entry):
    if type(entry.period_id) is not int or entry.period_id <= 0:
        raise ValueError("persisted JournalEntry requires a valid period_id")
    day = accounting_date(entry.date)
    fy = _periods.load_fiscal_year(session, day.year)
    matches = tuple(p for p in _periods.load_periods(session, fy) if p.id == entry.period_id)
    if len(matches) != 1:
        raise ValueError("persisted JournalEntry period does not resolve uniquely")
    period = matches[0]
    return ProfessionalPeriodView(
        id=period.id,
        year=fy.year,
        month=period.month,
        start=period.start,
        end=period.end,
        state=period.state,
        fiscal_year_state=fy.state,
    )


def _load_lines(session, entry_id):
    rows = session.exec(
        select(_models.JournalLine)
        .where(_models.JournalLine.entry_id == entry_id)
        .order_by(_models.JournalLine.id)
    ).all()
    if not rows:
        raise ValueError("JournalEntry has no persisted lines")

    result = []
    for row in rows:
        if type(row.id) is not int or type(row.account_id) is not int:
            raise ValueError("persisted JournalLine requires identities")
        account = session.get(_models.Account, row.account_id)
        if account is None:
            raise ValueError("persisted JournalLine references a missing Account")
        if row.account_code != account.code:
            raise ValueError("persisted JournalLine account identity/code mismatch")
        result.append(
            ProfessionalLineView(
                id=row.id,
                account_id=account.id,
                account_code=account.code,
                account_name=account.name,
                debit=_decimal(row.debit, "debit"),
                credit=_decimal(row.credit, "credit"),
                description=row.description,
            )
        )
    return tuple(result)


def _load_general_audit(session, entity_id, entry_id):
    matches = tuple(
        event
        for event in _audit_events.list_audit_events(session, entity_id)
        if event.event_type == "entry_posted"
        and event.details.get("entry_id") == entry_id
    )
    if len(matches) > 1:
        raise ValueError("multiple entry_posted AuditEvents found for JournalEntry")
    if not matches:
        return None
    event = matches[0]
    if type(event.id) is not int:
        raise ValueError("persisted AuditEvent has no identity")
    return GeneralAuditView(
        id=event.id,
        event_type=event.event_type,
        timestamp=event.timestamp,
        details=event.details,
    )


def _load_reversal(session, entry_id):
    rows = session.exec(
        select(_models.JournalEntryReversalRecord).where(
            (_models.JournalEntryReversalRecord.original_entry_id == entry_id)
            | (_models.JournalEntryReversalRecord.reversal_entry_id == entry_id)
        )
    ).all()
    if len(rows) > 1:
        raise ValueError("JournalEntry participates in multiple reversal relations")
    if not rows:
        return None
    row = rows[0]
    return ReversalView(
        original_entry_id=row.original_entry_id,
        reversal_entry_id=row.reversal_entry_id,
        reason=row.reason,
    )


def _load_fiscal_audit(session, entry_id):
    try:
        return _fiscal_audit.load_fiscal_posting_audit_snapshot(session, entry_id)
    except LookupError:
        return None


def list_professional_accounting_operations(session, limit=50):
    """List recent JournalEntry identities directly from the canonical ledger."""
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError("limit must be an integer between 1 and 200")
    rows = session.exec(
        select(_models.JournalEntry)
        .order_by(_models.JournalEntry.id.desc())
        .limit(limit)
    ).all()
    result = []
    for row in rows:
        if type(row.id) is not int:
            raise ValueError("persisted JournalEntry has no identity")
        result.append(
            ProfessionalEntrySummary(
                entry_id=row.id,
                posting_date=accounting_date(row.date),
                concept=row.concept,
                state=row.state,
                period_id=row.period_id,
            )
        )
    return tuple(result)


def load_professional_accounting_operation(session, entry_id):
    """Return one professional read model from existing persisted authorities."""
    if type(entry_id) is not int or entry_id <= 0:
        raise ValueError("entry_id must be a positive integer")
    entry = session.get(_models.JournalEntry, entry_id)
    if entry is None:
        raise LookupError(f"JournalEntry {entry_id} does not exist")
    if not isinstance(entry.concept, str) or not entry.concept.strip():
        raise ValueError("JournalEntry concept must be nonblank")

    entity = _entities.load_active_entity(session)
    if entity is None or type(entity.id) is not int:
        raise LookupError("active Entity is required to inspect accounting audit")

    return ProfessionalAccountingOperationView(
        entry_id=entry_id,
        posting_date=accounting_date(entry.date),
        concept=entry.concept,
        state=entry.state,
        period=_load_period(session, entry),
        lines=_load_lines(session, entry_id),
        documents=_documents.list_document_references(session, entry_id),
        audit=_load_general_audit(session, entity.id, entry_id),
        reversal=_load_reversal(session, entry_id),
        fiscal_audit=_load_fiscal_audit(session, entry_id),
    )


__all__ = [
    "ProfessionalPeriodView",
    "ProfessionalLineView",
    "ProfessionalEntrySummary",
    "ReversalView",
    "GeneralAuditView",
    "ProfessionalAccountingOperationView",
    "list_professional_accounting_operations",
    "load_professional_accounting_operation",
]
