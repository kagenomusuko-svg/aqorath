"""AQR-006 Application use cases for operational receivable/payable subledgers.

Accounting remains AQR-004 truth.  This module adds counterparty/document/due-date
provenance and links the resulting canonical control lines as OpenItems or
applications inside the same transaction.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation

from sqlmodel import select

from . import accounting_operation as _operations
from . import accounting_operation_persistence as _persistence
from . import audit_event_repository as _audit_repository
from . import document_reference_repository as _documents
from . import entity_repository as _entities
from . import models as _models
from . import open_item_repository as _open_items
from . import posting as _posting
from . import storage as _storage
from .audit_event import AuditEvent
from .document_reference import DocumentReference
from .economic_facts import EconomicFact


_ORIGIN_KINDS = {
    "sale_credit": ("receivable", "sale", "credit", "accounts_receivable"),
    "utility_credit": (
        "payable",
        "utility_expense_incurred",
        "credit",
        "accounts_payable",
    ),
}
_APPLICATION_FACT = {
    "receivable": ("receivable_collection", "bank", "accounts_receivable"),
    "payable": ("supplier_payment", "bank", "accounts_payable"),
}


@dataclass(frozen=True)
class DocumentInput:
    document_type: str
    document_number: str
    document_date: date
    issuer_name: str | None = None

    def __post_init__(self):
        for value, name in (
            (self.document_type, "document_type"),
            (self.document_number, "document_number"),
        ):
            if type(value) is not str or not value.strip():
                raise ValueError(f"{name} must be nonblank text")
        if type(self.document_date) is not date:
            raise TypeError("document_date must be date")
        if self.issuer_name is not None and (
            type(self.issuer_name) is not str or not self.issuer_name.strip()
        ):
            raise ValueError("issuer_name must be nonblank text or None")


@dataclass(frozen=True)
class PreparedOpenItemOrigin:
    kind: str
    third_party_id: int
    due_date: date
    document: DocumentInput
    decision: object


@dataclass(frozen=True)
class PreparedOpenItemApplication:
    open_item_id: int
    kind: str
    third_party_id: int
    document: DocumentInput
    decision: object


@dataclass(frozen=True)
class ConfirmedOpenItemOrigin:
    prepared: PreparedOpenItemOrigin
    confirmed_decision: object


@dataclass(frozen=True)
class ConfirmedOpenItemApplication:
    prepared: PreparedOpenItemApplication
    confirmed_decision: object


def _amount(value):
    if type(value) is Decimal:
        result = value
    elif type(value) is str:
        try:
            result = Decimal(value)
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("amount must be exact decimal text") from exc
    else:
        raise TypeError("amount must be Decimal or exact decimal text")
    if not result.is_finite() or result <= Decimal("0"):
        raise ValueError("amount must be finite and greater than zero")
    return result


def _date(value, name):
    if type(value) is date:
        return value
    if type(value) is not str:
        raise TypeError(f"{name} must be date or ISO date text")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be YYYY-MM-DD") from exc


def _document(document_type, document_number, document_date, issuer_name=None):
    return DocumentInput(
        document_type=document_type,
        document_number=document_number,
        document_date=_date(document_date, "document_date"),
        issuer_name=issuer_name,
    )


def _party(session, third_party_id):
    if type(third_party_id) is not int or third_party_id <= 0:
        raise ValueError("third_party_id must be a positive integer")
    entity = _entities.load_active_entity(session)
    if entity is None or type(entity.id) is not int:
        raise LookupError("active Entity is required")
    party = session.get(_models.ThirdPartyRecord, third_party_id)
    if party is None or party.entity_id != entity.id:
        raise LookupError("ThirdParty not found for active Entity")
    if party.is_active is not True:
        raise ValueError("ThirdParty must be active")
    return entity, party


def prepare_open_item_origin(
    session,
    operation_key,
    amount,
    posting_date,
    third_party_id,
    due_date,
    document_type,
    document_number,
    document_date,
    issuer_name=None,
):
    """Prepare one credit-origin decision without writing any subledger state."""
    if operation_key not in _ORIGIN_KINDS:
        raise ValueError("operation_key must be sale_credit or utility_credit")
    kind, fact_type, payment_method, _ = _ORIGIN_KINDS[operation_key]
    _, party = _party(session, third_party_id)
    posting_date = _date(posting_date, "posting_date")
    due_date = _date(due_date, "due_date")
    if due_date < posting_date:
        raise ValueError("due_date cannot precede posting_date")
    document = _document(
        document_type,
        document_number,
        document_date,
        issuer_name or party.name,
    )
    _open_items.assert_subledger_reconciled(session, kind, as_of=posting_date)
    decision = _operations.prepare_accounting_operation(
        session,
        EconomicFact(fact_type, _amount(amount), payment_method),
        posting_date,
    )
    return PreparedOpenItemOrigin(
        kind=kind,
        third_party_id=third_party_id,
        due_date=due_date,
        document=document,
        decision=decision,
    )


def confirm_open_item_origin(prepared):
    if not isinstance(prepared, PreparedOpenItemOrigin):
        raise TypeError("prepared must be PreparedOpenItemOrigin")
    return ConfirmedOpenItemOrigin(
        prepared=prepared,
        confirmed_decision=_operations.confirm_accounting_operation(prepared.decision),
    )


def prepare_open_item_application(
    session,
    open_item_id,
    amount,
    posting_date,
    document_type,
    document_number,
    document_date,
):
    """Prepare a collection/payment against one concrete currently-open item."""
    posting_date = _date(posting_date, "posting_date")
    item = _open_items.load_open_item(session, open_item_id, as_of=posting_date)
    _open_items.assert_subledger_reconciled(session, item.kind, as_of=posting_date)
    if item.status != "open":
        raise ValueError("OpenItem is not open at posting_date")
    amount = _amount(amount)
    if amount > item.open_balance:
        raise ValueError("application amount exceeds open balance")
    _, fact_type, payment_method = (
        item.kind,
        *_APPLICATION_FACT[item.kind][:2],
    )
    document = _document(
        document_type,
        document_number,
        document_date,
        item.third_party_name,
    )
    decision = _operations.prepare_accounting_operation(
        session,
        EconomicFact(fact_type, amount, payment_method),
        posting_date,
    )
    return PreparedOpenItemApplication(
        open_item_id=open_item_id,
        kind=item.kind,
        third_party_id=item.third_party_id,
        document=document,
        decision=decision,
    )


def confirm_open_item_application(prepared):
    if not isinstance(prepared, PreparedOpenItemApplication):
        raise TypeError("prepared must be PreparedOpenItemApplication")
    return ConfirmedOpenItemApplication(
        prepared=prepared,
        confirmed_decision=_operations.confirm_accounting_operation(prepared.decision),
    )


def _control_line(session, result, confirmed_decision, account_role):
    resolved = tuple(
        line
        for line in confirmed_decision.decision.resolved_proposal.lines
        if line.account_role == account_role
    )
    if len(resolved) != 1:
        raise RuntimeError("prepared decision does not contain one control-account effect")
    expected = resolved[0]
    rows = session.exec(
        select(_models.JournalLine).where(
            _models.JournalLine.entry_id == result.entry_id,
            _models.JournalLine.account_id == expected.account_id,
        )
    ).all()
    matches = []
    for row in rows:
        debit = Decimal(str(row.debit))
        credit = Decimal(str(row.credit))
        if expected.side == "debit" and debit == expected.amount and credit == Decimal("0"):
            matches.append(row)
        if expected.side == "credit" and credit == expected.amount and debit == Decimal("0"):
            matches.append(row)
    if len(matches) != 1 or type(matches[0].id) is not int:
        raise RuntimeError("posted decision does not resolve to one canonical control line")
    return matches[0]


def _stage_document(session, entry_id, third_party_id, document):
    value = DocumentReference(
        id=None,
        entry_id=entry_id,
        third_party_id=third_party_id,
        document_type=document.document_type,
        document_number=document.document_number,
        issuer_name=document.issuer_name,
        date=datetime.combine(
            document.document_date,
            time.min,
            tzinfo=timezone.utc,
        ),
        file_hash=None,
        file_path=None,
        external_url=None,
        is_validated=False,
        validation_notes=None,
    )
    return _documents.stage_document_reference(session, value)


def _stage_subledger_audit(session, entity_id, event_type, details):
    return _audit_repository.stage_audit_event(
        session,
        AuditEvent(
            id=None,
            entity_id=entity_id,
            event_type=event_type,
            timestamp=datetime.now(timezone.utc),
            details=details,
        ),
    )


def execute_open_item_origin(confirmed):
    """Post + audit + document + OpenItem in one canonical transaction."""
    if not isinstance(confirmed, ConfirmedOpenItemOrigin):
        raise TypeError("confirmed must be ConfirmedOpenItemOrigin")
    prepared = confirmed.prepared
    _, _, _, account_role = next(
        value
        for key, value in _ORIGIN_KINDS.items()
        if value[0] == prepared.kind
        and value[1] == confirmed.confirmed_decision.decision.fact.type
    )
    instruction = _posting.create_posting_instruction(
        confirmed.confirmed_decision.confirmed_proposal
    )

    session = None
    try:
        with _storage.get_session() as session:
            entity, _ = _party(session, prepared.third_party_id)
            _open_items.assert_subledger_reconciled(
                session,
                prepared.kind,
                as_of=prepared.decision.posting_date,
            )
            result = _persistence.stage_posting_with_audit(
                session,
                instruction,
                confirmed.confirmed_decision,
            )
            control_line = _control_line(
                session,
                result,
                confirmed.confirmed_decision,
                account_role,
            )
            document = _stage_document(
                session,
                result.entry_id,
                prepared.third_party_id,
                prepared.document,
            )
            item = _open_items.stage_open_item(
                session,
                entity_id=entity.id,
                third_party_id=prepared.third_party_id,
                kind=prepared.kind,
                source_entry_id=result.entry_id,
                source_line_id=control_line.id,
                source_document_reference_id=document.id,
                due_date=prepared.due_date,
            )
            _stage_subledger_audit(
                session,
                entity.id,
                "open_item_created",
                {
                    "open_item_id": item.id,
                    "kind": prepared.kind,
                    "third_party_id": prepared.third_party_id,
                    "entry_id": result.entry_id,
                    "line_id": control_line.id,
                    "document_reference_id": document.id,
                    "due_date": prepared.due_date.isoformat(),
                },
            )
            reconciliation = _open_items.assert_subledger_reconciled(
                session,
                prepared.kind,
                as_of=prepared.decision.posting_date,
            )
            session.commit()
            return {
                "entry_id": result.entry_id,
                "audit_event_id": result.audit_event_id,
                "open_item_id": item.id,
                "state": result.state,
                "reconciliation": reconciliation,
            }
    except Exception:
        if session is not None:
            try:
                session.rollback()
            except Exception:
                pass
        raise


def execute_open_item_application(confirmed):
    """Post one partial/full collection/payment and link its exact control line."""
    if not isinstance(confirmed, ConfirmedOpenItemApplication):
        raise TypeError("confirmed must be ConfirmedOpenItemApplication")
    prepared = confirmed.prepared
    _, _, account_role = _APPLICATION_FACT[prepared.kind]
    instruction = _posting.create_posting_instruction(
        confirmed.confirmed_decision.confirmed_proposal
    )

    session = None
    try:
        with _storage.get_session() as session:
            entity, _ = _party(session, prepared.third_party_id)
            before = _open_items.load_open_item(
                session,
                prepared.open_item_id,
                as_of=prepared.decision.posting_date,
            )
            _open_items.assert_subledger_reconciled(
                session,
                prepared.kind,
                as_of=prepared.decision.posting_date,
            )
            if before.status != "open":
                raise ValueError("OpenItem is no longer open")
            if confirmed.confirmed_decision.decision.fact.amount > before.open_balance:
                raise ValueError("application amount exceeds current open balance")

            result = _persistence.stage_posting_with_audit(
                session,
                instruction,
                confirmed.confirmed_decision,
            )
            control_line = _control_line(
                session,
                result,
                confirmed.confirmed_decision,
                account_role,
            )
            document = _stage_document(
                session,
                result.entry_id,
                prepared.third_party_id,
                prepared.document,
            )
            application = _open_items.stage_open_item_application(
                session,
                open_item_id=prepared.open_item_id,
                application_entry_id=result.entry_id,
                application_line_id=control_line.id,
                application_document_reference_id=document.id,
            )
            # Re-evaluate across all dated applications, not only the posting-date cut.
            after_all = _open_items.load_open_item(
                session,
                prepared.open_item_id,
                as_of=date.max,
            )
            _stage_subledger_audit(
                session,
                entity.id,
                "open_item_applied",
                {
                    "open_item_id": prepared.open_item_id,
                    "application_id": application.id,
                    "third_party_id": prepared.third_party_id,
                    "entry_id": result.entry_id,
                    "line_id": control_line.id,
                    "document_reference_id": document.id,
                    "resulting_status": after_all.status,
                },
            )
            reconciliation = _open_items.assert_subledger_reconciled(
                session,
                prepared.kind,
                as_of=prepared.decision.posting_date,
            )
            session.commit()
            return {
                "entry_id": result.entry_id,
                "audit_event_id": result.audit_event_id,
                "open_item_id": prepared.open_item_id,
                "application_id": application.id,
                "state": result.state,
                "open_balance": after_all.open_balance,
                "status": after_all.status,
                "reconciliation": reconciliation,
            }
    except Exception:
        if session is not None:
            try:
                session.rollback()
            except Exception:
                pass
        raise


__all__ = [
    "DocumentInput",
    "PreparedOpenItemOrigin",
    "PreparedOpenItemApplication",
    "ConfirmedOpenItemOrigin",
    "ConfirmedOpenItemApplication",
    "prepare_open_item_origin",
    "confirm_open_item_origin",
    "execute_open_item_origin",
    "prepare_open_item_application",
    "confirm_open_item_application",
    "execute_open_item_application",
]
