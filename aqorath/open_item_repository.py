"""Canonical operational projection for AQR-006 open items.

The repository persists relationships only. Every monetary value exposed here is
read from JournalLine and every cancellation is derived from the canonical reversal
relationship. No outstanding balance, settlement state or aging bucket is stored.
"""

from datetime import date
from decimal import Decimal, InvalidOperation

from sqlmodel import select

from . import audit_event_repository as _audit_events
from . import entity_repository as _entities
from . import models as _models
from . import open_item_models as _records
from .accounting_period import accounting_date
from .open_item import (
    OpenItemApplicationView,
    OpenItemView,
    SubledgerDivergenceError,
    SubledgerReconciliation,
)


_KIND_ROLE = {
    "receivable": "accounts_receivable",
    "payable": "accounts_payable",
}
_SOURCE_SIDE = {"receivable": "debit", "payable": "credit"}
_APPLICATION_SIDE = {"receivable": "credit", "payable": "debit"}


def _positive_id(value, name):
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _require_kind(kind):
    if kind not in _KIND_ROLE:
        raise ValueError("kind must be 'receivable' or 'payable'")


def _decimal(value, name):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise SubledgerDivergenceError(f"invalid ledger Decimal in {name}") from exc
    if not result.is_finite() or result < Decimal("0"):
        raise SubledgerDivergenceError(f"invalid ledger amount in {name}")
    return result


def _line_amount(line, side):
    debit = _decimal(line.debit, "debit")
    credit = _decimal(line.credit, "credit")
    if side == "debit":
        if debit <= 0 or credit != Decimal("0"):
            raise SubledgerDivergenceError("linked control line is not an exact debit")
        return debit
    if side == "credit":
        if credit <= 0 or debit != Decimal("0"):
            raise SubledgerDivergenceError("linked control line is not an exact credit")
        return credit
    raise SubledgerDivergenceError("invalid linked control-line side")


def _active_entity(session):
    entity = _entities.load_active_entity(session)
    if entity is None or type(entity.id) is not int:
        raise LookupError("active Entity is required")
    return entity


def _binding_account_id(session, kind):
    role = _KIND_ROLE[kind]
    rows = session.exec(
        select(_models.AccountRoleBinding).where(
            _models.AccountRoleBinding.role == role
        )
    ).all()
    if len(rows) != 1:
        raise LookupError(f"configured account binding required for {role}")
    return rows[0].account_id


def _require_party(session, entity_id, third_party_id):
    _positive_id(third_party_id, "third_party_id")
    party = session.get(_models.ThirdPartyRecord, third_party_id)
    if party is None:
        raise LookupError("ThirdParty not found")
    if party.entity_id != entity_id:
        raise ValueError("ThirdParty belongs to a different Entity")
    if party.is_active is not True:
        raise ValueError("ThirdParty must be active for a new subledger operation")
    return party


def _require_document(session, document_id, entry_id, third_party_id):
    _positive_id(document_id, "document_reference_id")
    document = session.get(_models.DocumentReferenceRecord, document_id)
    if document is None:
        raise LookupError("DocumentReference not found")
    if document.entry_id != entry_id:
        raise ValueError("DocumentReference must belong to the same JournalEntry")
    if document.third_party_id != third_party_id:
        raise ValueError("DocumentReference must identify the same ThirdParty")
    return document


def _reversal_record(session, entry_id):
    rows = session.exec(
        select(_models.JournalEntryReversalRecord).where(
            _models.JournalEntryReversalRecord.original_entry_id == entry_id
        )
    ).all()
    if len(rows) > 1:
        raise SubledgerDivergenceError("multiple reversals for one JournalEntry")
    return None if not rows else rows[0]


def _entry_effective_as_of(session, entry_id, as_of):
    entry = session.get(_models.JournalEntry, entry_id)
    if entry is None:
        raise SubledgerDivergenceError("subledger references a missing JournalEntry")
    posting_date = accounting_date(entry.date)
    if posting_date > as_of:
        return False
    reversal = _reversal_record(session, entry_id)
    if reversal is None:
        if entry.state == "reversed":
            raise SubledgerDivergenceError("reversed JournalEntry lacks reversal relation")
        return entry.state == "posted"
    reversal_entry = session.get(_models.JournalEntry, reversal.reversal_entry_id)
    if reversal_entry is None:
        raise SubledgerDivergenceError("reversal relation references a missing entry")
    return accounting_date(reversal_entry.date) > as_of


def _aging_bucket(due_date, open_balance, as_of):
    if open_balance == Decimal("0"):
        return "settled"
    days = (as_of - due_date).days
    if days <= 0:
        return "current"
    if days <= 30:
        return "1-30"
    if days <= 60:
        return "31-60"
    if days <= 90:
        return "61-90"
    return "91+"


def _load_item_record(session, open_item_id):
    _positive_id(open_item_id, "open_item_id")
    record = session.get(_records.OpenItemRecord, open_item_id)
    if record is None:
        raise LookupError("OpenItem not found")
    return record


def stage_open_item(
    session,
    *,
    entity_id,
    third_party_id,
    kind,
    source_entry_id,
    source_line_id,
    source_document_reference_id,
    due_date,
):
    """Stage one obligation identity; authoritative money remains in source_line."""
    _require_kind(kind)
    _positive_id(entity_id, "entity_id")
    _positive_id(source_entry_id, "source_entry_id")
    _positive_id(source_line_id, "source_line_id")
    if type(due_date) is not date:
        raise TypeError("due_date must be date")

    entity = _active_entity(session)
    if entity.id != entity_id:
        raise ValueError("OpenItem entity must be the active Entity")
    _require_party(session, entity_id, third_party_id)

    if session.exec(
        select(_records.OpenItemRecord.id).where(
            _records.OpenItemRecord.source_line_id == source_line_id
        )
    ).first() is not None:
        raise ValueError("source control line already identifies an OpenItem")

    entry = session.get(_models.JournalEntry, source_entry_id)
    line = session.get(_models.JournalLine, source_line_id)
    if entry is None or line is None or line.entry_id != source_entry_id:
        raise LookupError("source JournalEntry/JournalLine relationship not found")
    if entry.state != "posted":
        raise ValueError("OpenItem source entry must be posted")
    if due_date < accounting_date(entry.date):
        raise ValueError("due_date cannot precede the source posting date")

    expected_account_id = _binding_account_id(session, kind)
    if line.account_id != expected_account_id:
        raise ValueError("source line is not the configured control account")
    _line_amount(line, _SOURCE_SIDE[kind])
    _require_document(
        session,
        source_document_reference_id,
        source_entry_id,
        third_party_id,
    )

    record = _records.OpenItemRecord(
        entity_id=entity_id,
        third_party_id=third_party_id,
        kind=kind,
        source_entry_id=source_entry_id,
        source_line_id=source_line_id,
        source_document_reference_id=source_document_reference_id,
        due_date=due_date,
    )
    session.add(record)
    session.flush()
    if record.id is None:
        raise RuntimeError("OpenItem identity was not assigned")
    return record


def stage_open_item_application(
    session,
    *,
    open_item_id,
    application_entry_id,
    application_line_id,
    application_document_reference_id,
):
    """Stage one application identity after validating the exact ledger reduction."""
    item = _load_item_record(session, open_item_id)
    _positive_id(application_entry_id, "application_entry_id")
    _positive_id(application_line_id, "application_line_id")

    if session.exec(
        select(_records.OpenItemApplicationRecord.id).where(
            _records.OpenItemApplicationRecord.application_line_id == application_line_id
        )
    ).first() is not None:
        raise ValueError("application control line already belongs to an OpenItemApplication")

    source_line = session.get(_models.JournalLine, item.source_line_id)
    entry = session.get(_models.JournalEntry, application_entry_id)
    line = session.get(_models.JournalLine, application_line_id)
    if source_line is None or entry is None or line is None:
        raise LookupError("application ledger relationship not found")
    if line.entry_id != application_entry_id:
        raise ValueError("application line belongs to a different JournalEntry")
    if entry.state != "posted":
        raise ValueError("application entry must be posted")
    if line.account_id != source_line.account_id:
        raise ValueError("application must reduce the same concrete control account")
    amount = _line_amount(line, _APPLICATION_SIDE[item.kind])

    _require_document(
        session,
        application_document_reference_id,
        application_entry_id,
        item.third_party_id,
    )

    current = load_open_item(session, open_item_id, as_of=accounting_date(entry.date))
    if current.status == "cancelled":
        raise ValueError("cannot apply a payment/collection to a reversed obligation")
    if current.open_balance == Decimal("0"):
        raise ValueError("open item is already settled")
    if amount > current.open_balance:
        raise ValueError("application amount exceeds the open item balance")

    record = _records.OpenItemApplicationRecord(
        open_item_id=open_item_id,
        application_entry_id=application_entry_id,
        application_line_id=application_line_id,
        application_document_reference_id=application_document_reference_id,
    )
    session.add(record)
    session.flush()
    if record.id is None:
        raise RuntimeError("OpenItemApplication identity was not assigned")
    return record


def _application_views(session, item, as_of):
    rows = session.exec(
        select(_records.OpenItemApplicationRecord)
        .where(_records.OpenItemApplicationRecord.open_item_id == item.id)
        .order_by(_records.OpenItemApplicationRecord.id)
    ).all()
    views = []
    for row in rows:
        entry = session.get(_models.JournalEntry, row.application_entry_id)
        line = session.get(_models.JournalLine, row.application_line_id)
        if entry is None or line is None or line.entry_id != row.application_entry_id:
            raise SubledgerDivergenceError("application metadata references missing ledger truth")
        amount = _line_amount(line, _APPLICATION_SIDE[item.kind])
        views.append(
            OpenItemApplicationView(
                id=row.id,
                entry_id=row.application_entry_id,
                line_id=row.application_line_id,
                document_reference_id=row.application_document_reference_id,
                posting_date=accounting_date(entry.date),
                amount=amount,
                is_effective=_entry_effective_as_of(
                    session,
                    row.application_entry_id,
                    as_of,
                ),
            )
        )
    return tuple(views)


def load_open_item(session, open_item_id, as_of=None):
    item = _load_item_record(session, open_item_id)
    as_of = date.today() if as_of is None else accounting_date(as_of)
    entry = session.get(_models.JournalEntry, item.source_entry_id)
    line = session.get(_models.JournalLine, item.source_line_id)
    party = session.get(_models.ThirdPartyRecord, item.third_party_id)
    document = session.get(_models.DocumentReferenceRecord, item.source_document_reference_id)
    if entry is None or line is None or party is None or document is None:
        raise SubledgerDivergenceError("OpenItem metadata references missing canonical records")
    if line.entry_id != item.source_entry_id:
        raise SubledgerDivergenceError("OpenItem source line/entry mismatch")
    if document.entry_id != item.source_entry_id or document.third_party_id != item.third_party_id:
        raise SubledgerDivergenceError("OpenItem document provenance mismatch")
    if accounting_date(entry.date) > as_of:
        raise LookupError("OpenItem did not yet exist at as_of")

    original_amount = _line_amount(line, _SOURCE_SIDE[item.kind])
    source_effective = _entry_effective_as_of(session, item.source_entry_id, as_of)
    applications = _application_views(session, item, as_of)
    effective_applications = tuple(app for app in applications if app.is_effective)
    applied_amount = sum((app.amount for app in effective_applications), Decimal("0"))
    if not source_effective:
        if applied_amount != Decimal("0"):
            raise SubledgerDivergenceError(
                "reversed obligation still has effective applications"
            )
        open_balance = Decimal("0")
        status = "cancelled"
    else:
        if applied_amount > original_amount:
            raise SubledgerDivergenceError("applications exceed canonical source amount")
        open_balance = original_amount - applied_amount
        status = "settled" if open_balance == Decimal("0") else "open"

    return OpenItemView(
        id=item.id,
        entity_id=item.entity_id,
        third_party_id=item.third_party_id,
        third_party_name=party.name,
        kind=item.kind,
        source_entry_id=item.source_entry_id,
        source_line_id=item.source_line_id,
        source_document_reference_id=item.source_document_reference_id,
        document_type=document.document_type,
        document_number=document.document_number,
        posting_date=accounting_date(entry.date),
        due_date=item.due_date,
        original_amount=original_amount,
        applied_amount=applied_amount,
        open_balance=open_balance,
        status=status,
        aging_bucket=_aging_bucket(item.due_date, open_balance, as_of),
        applications=applications,
    )


def list_open_items(session, kind=None, third_party_id=None, as_of=None, include_settled=True):
    if kind is not None:
        _require_kind(kind)
    if third_party_id is not None:
        _positive_id(third_party_id, "third_party_id")
    if type(include_settled) is not bool:
        raise TypeError("include_settled must be bool")
    as_of = date.today() if as_of is None else accounting_date(as_of)

    entity = _active_entity(session)
    statement = select(_records.OpenItemRecord).where(
        _records.OpenItemRecord.entity_id == entity.id
    )
    if kind is not None:
        statement = statement.where(_records.OpenItemRecord.kind == kind)
    if third_party_id is not None:
        statement = statement.where(_records.OpenItemRecord.third_party_id == third_party_id)
    rows = session.exec(statement.order_by(_records.OpenItemRecord.id)).all()

    views = []
    for row in rows:
        entry = session.get(_models.JournalEntry, row.source_entry_id)
        if entry is None:
            raise SubledgerDivergenceError("OpenItem source JournalEntry is missing")
        if accounting_date(entry.date) > as_of:
            continue
        views.append(load_open_item(session, row.id, as_of=as_of))
    views = tuple(views)
    if include_settled:
        return views
    return tuple(view for view in views if view.status == "open")


def _audit_control_account_ids(session, entity_id, kind):
    """Recover control-account identities even when one confirmed effect is split."""
    role = _KIND_ROLE[kind]
    account_ids = set()
    for event in _audit_events.list_audit_events(session, entity_id):
        if event.event_type != "entry_posted":
            continue
        entry_id = event.details.get("entry_id")
        decision = event.details.get("decision")
        if type(entry_id) is not int or type(decision) is not dict:
            continue
        explanation = decision.get("explanation")
        if type(explanation) is not dict:
            continue
        for effect in explanation.get("effects", ()):
            if type(effect) is not dict or effect.get("account_role") != role:
                continue
            side = effect.get("side")
            try:
                amount = Decimal(str(effect.get("amount")))
            except Exception as exc:
                raise SubledgerDivergenceError("invalid accounting audit amount") from exc
            if side not in ("debit", "credit") or not amount.is_finite() or amount <= 0:
                raise SubledgerDivergenceError("invalid accounting audit control effect")

            rows = session.exec(
                select(_models.JournalLine).where(
                    _models.JournalLine.entry_id == entry_id
                )
            ).all()
            totals = {}
            for line in rows:
                if type(line.account_id) is not int:
                    continue
                try:
                    line_amount = _line_amount(line, side)
                except SubledgerDivergenceError:
                    continue
                totals[line.account_id] = totals.get(line.account_id, Decimal("0")) + line_amount
            matches = [account_id for account_id, total in totals.items() if total == amount]
            if len(matches) != 1:
                raise SubledgerDivergenceError(
                    "accounting audit cannot resolve one canonical control account"
                )
            account_ids.add(matches[0])
    return account_ids


def _reversal_line_id(session, original_entry_id, original_line):
    """Map a reversed line by preserved JournalLine order, never by amount alone."""
    reversal = _reversal_record(session, original_entry_id)
    if reversal is None:
        return None

    original_rows = session.exec(
        select(_models.JournalLine)
        .where(_models.JournalLine.entry_id == original_entry_id)
        .order_by(_models.JournalLine.id)
    ).all()
    reversal_rows = session.exec(
        select(_models.JournalLine)
        .where(_models.JournalLine.entry_id == reversal.reversal_entry_id)
        .order_by(_models.JournalLine.id)
    ).all()
    if len(original_rows) != len(reversal_rows):
        raise SubledgerDivergenceError("reversal changed JournalLine cardinality")

    positions = [index for index, row in enumerate(original_rows) if row.id == original_line.id]
    if len(positions) != 1:
        raise SubledgerDivergenceError("cannot locate original control-line position")
    candidate = reversal_rows[positions[0]]
    if candidate.account_id != original_line.account_id:
        raise SubledgerDivergenceError("reversal line changed control account identity")
    if (
        _decimal(candidate.debit, "debit") != _decimal(original_line.credit, "credit")
        or _decimal(candidate.credit, "credit") != _decimal(original_line.debit, "debit")
    ):
        raise SubledgerDivergenceError("reversal line does not exactly invert original line")
    if type(candidate.id) is not int:
        raise SubledgerDivergenceError("reversal control line lacks identity")
    return candidate.id


def reconcile_subledger(session, kind, as_of=None):
    _require_kind(kind)
    as_of = date.today() if as_of is None else accounting_date(as_of)
    entity = _active_entity(session)
    items = list_open_items(session, kind=kind, as_of=as_of, include_settled=True)

    control_account_ids = {_binding_account_id(session, kind)}
    control_account_ids.update(_audit_control_account_ids(session, entity.id, kind))
    assigned_line_ids = set()

    for item in items:
        source_line = session.get(_models.JournalLine, item.source_line_id)
        if source_line is None or type(source_line.account_id) is not int:
            raise SubledgerDivergenceError("missing source control line")
        control_account_ids.add(source_line.account_id)
        assigned_line_ids.add(source_line.id)
        reversal_line_id = _reversal_line_id(session, item.source_entry_id, source_line)
        if reversal_line_id is not None:
            assigned_line_ids.add(reversal_line_id)

        rows = session.exec(
            select(_records.OpenItemApplicationRecord).where(
                _records.OpenItemApplicationRecord.open_item_id == item.id
            )
        ).all()
        for row in rows:
            line = session.get(_models.JournalLine, row.application_line_id)
            if line is None or type(line.account_id) is not int:
                raise SubledgerDivergenceError("missing application control line")
            control_account_ids.add(line.account_id)
            assigned_line_ids.add(line.id)
            reversal_line_id = _reversal_line_id(session, row.application_entry_id, line)
            if reversal_line_id is not None:
                assigned_line_ids.add(reversal_line_id)

    ledger_balance = Decimal("0")
    ledger_line_ids = []
    if control_account_ids:
        lines = session.exec(
            select(_models.JournalLine).where(
                _models.JournalLine.account_id.in_(tuple(control_account_ids))
            )
        ).all()
        for line in lines:
            entry = session.get(_models.JournalEntry, line.entry_id)
            if entry is None:
                raise SubledgerDivergenceError("control line references missing JournalEntry")
            if accounting_date(entry.date) > as_of or entry.state not in ("posted", "reversed"):
                continue
            debit = _decimal(line.debit, "debit")
            credit = _decimal(line.credit, "credit")
            ledger_balance += debit - credit if kind == "receivable" else credit - debit
            if type(line.id) is int:
                ledger_line_ids.append(line.id)

    subledger_balance = sum((item.open_balance for item in items), Decimal("0"))
    unassigned = tuple(sorted(set(ledger_line_ids) - assigned_line_ids))
    difference = ledger_balance - subledger_balance
    return SubledgerReconciliation(
        kind=kind,
        as_of=as_of,
        ledger_balance=ledger_balance,
        subledger_balance=subledger_balance,
        difference=difference,
        control_account_ids=tuple(sorted(control_account_ids)),
        unassigned_line_ids=unassigned,
    )


def assert_subledger_reconciled(session, kind, as_of=None):
    result = reconcile_subledger(session, kind, as_of=as_of)
    if not result.is_reconciled:
        raise SubledgerDivergenceError(
            f"{kind} subledger diverges from ledger: "
            f"ledger={result.ledger_balance}, subledger={result.subledger_balance}, "
            f"difference={result.difference}, unassigned_lines={result.unassigned_line_ids}"
        )
    return result


def assert_reconciliation_transition_preserved(before, after):
    """Permit known historical gaps only when the new operation does not worsen them."""
    if not isinstance(before, SubledgerReconciliation) or not isinstance(
        after, SubledgerReconciliation
    ):
        raise TypeError("before and after must be SubledgerReconciliation")
    if before.kind != after.kind or before.as_of != after.as_of:
        raise ValueError("reconciliation snapshots must share kind and as_of")
    if before.difference != after.difference:
        raise SubledgerDivergenceError("subledger operation changed pre-existing reconciliation difference")
    if before.unassigned_line_ids != after.unassigned_line_ids:
        raise SubledgerDivergenceError("subledger operation changed pre-existing unassigned control lines")
    return after


def assert_entry_reversible(session, entry_id):
    """Protect obligation origins while any linked application remains effective."""
    _positive_id(entry_id, "entry_id")
    items = session.exec(
        select(_records.OpenItemRecord).where(
            _records.OpenItemRecord.source_entry_id == entry_id
        )
    ).all()
    for item in items:
        applications = session.exec(
            select(_records.OpenItemApplicationRecord).where(
                _records.OpenItemApplicationRecord.open_item_id == item.id
            )
        ).all()
        for application in applications:
            if _entry_effective_as_of(session, application.application_entry_id, date.max):
                raise ValueError("reverse open-item applications before reversing the obligation")


def assert_entry_correctable(session, entry_id):
    """Generic reverse+replacement cannot invent replacement subledger metadata."""
    _positive_id(entry_id, "entry_id")
    source = session.exec(
        select(_records.OpenItemRecord.id).where(
            _records.OpenItemRecord.source_entry_id == entry_id
        )
    ).first()
    application = session.exec(
        select(_records.OpenItemApplicationRecord.id).where(
            _records.OpenItemApplicationRecord.application_entry_id == entry_id
        )
    ).first()
    if source is not None or application is not None:
        raise ValueError(
            "subledger entries must be reversed and re-entered through AQR-006; "
            "generic replacement would lose open-item provenance"
        )


__all__ = [
    "stage_open_item",
    "stage_open_item_application",
    "load_open_item",
    "list_open_items",
    "reconcile_subledger",
    "assert_subledger_reconciled",
    "assert_reconciliation_transition_preserved",
    "assert_entry_reversible",
    "assert_entry_correctable",
]
