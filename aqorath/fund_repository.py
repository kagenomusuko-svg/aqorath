"""Transactional persistence for OSC fund traceability over JournalLine."""
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
import json
from sqlmodel import select
from .fund import Fund, FundingSource, FundReceipt, FundApplication, FundBalance
from .fund_models import FundRecord, FundingSourceRecord, FundReceiptRecord, FundApplicationRecord
from .models import Account, AuditEventRecord, DonationRecord, EntityRecord, JournalEntry, JournalEntryReversalRecord, JournalLine, ProgramRecord, ThirdPartyRecord

def _entity(session, entity_id):
    row = session.get(EntityRecord, entity_id)
    if row is None or row.is_active is not True: raise LookupError("active Entity not found")
    return row
def _fund(session, entity_id, fund_id):
    row = session.get(FundRecord, fund_id)
    if row is None or row.entity_id != entity_id: raise LookupError("Fund not found for Entity")
    return row
def _source(session, entity_id, source_id):
    row = session.get(FundingSourceRecord, source_id)
    if row is None or row.entity_id != entity_id: raise LookupError("FundingSource not found for Entity")
    return row
def _program(session, entity_id, program_id):
    row = session.get(ProgramRecord, program_id)
    if row is None or row.entity_id != entity_id: raise LookupError("Program not found for Entity")
    return row
def _line_amount(session, line_id, *, kind):
    line = session.get(JournalLine, line_id)
    if line is None: raise LookupError("JournalLine not found")
    entry = session.get(JournalEntry, line.entry_id)
    if entry is None or entry.state not in ("posted", "reversed"): raise ValueError("JournalLine must belong to a posted JournalEntry")
    context = _posting_context(session, entry.id)
    account = session.get(Account, line.account_id)
    if account is None: raise LookupError("JournalLine account not found")
    debit, credit = Decimal(line.debit), Decimal(line.credit)
    if debit != 0 and credit != 0 or debit == credit: raise ValueError("JournalLine must have one nonzero monetary side")
    if kind == "receipt" and (credit <= 0 or account.nature.upper() != "CREDIT"):
        raise ValueError("FundReceipt requires a credit JournalLine on a credit-nature account")
    if kind == "application" and (debit <= 0 or account.nature.upper() != "DEBIT"):
        raise ValueError("FundApplication requires a debit JournalLine on a debit-nature account")
    allowed_roles = {
        "utility_expense": {"utilities_expense"},
        "utility_expense_incurred": {"utilities_expense"},
        "supplier_payment": {"accounts_payable"},
    }
    if kind == "application" and (context[0] != "active" or context[1] not in allowed_roles or not set(context[2]) & allowed_roles[context[1]]):
        raise ValueError("FundApplication requires canonical posted expense/payment provenance")
    return line, entry, abs(debit - credit)


def _posting_context(session, entry_id):
    """Return canonical owner and fact type from the durable posting audit."""
    rows = session.exec(select(AuditEventRecord).where(AuditEventRecord.event_type == "entry_posted")).all()
    matches = []
    for event in rows:
        try:
            details = json.loads(event.details_json)
        except (TypeError, ValueError):
            continue
        if details.get("entry_id") != entry_id:
            continue
        decision = details.get("decision", {})
        fact_type = decision.get("fact", {}).get("type")
        if type(fact_type) is str:
            roles = tuple(effect["account_role"] for effect in decision.get("explanation", {}).get("effects", ()) if effect.get("side") == "debit" and type(effect.get("account_role")) is str)
            matches.append((event.entity_id, fact_type, roles))
    if len(matches) != 1:
        return ("ambiguous", None, ())
    active = session.exec(select(EntityRecord).where(EntityRecord.is_active.is_(True))).all()
    if len(active) != 1 or active[0].id != matches[0][0]:
        return ("foreign", matches[0][1], matches[0][2])
    return ("active", matches[0][1], matches[0][2])


def _effective(session, line_id, as_of):
    line = session.get(JournalLine, line_id)
    entry = None if line is None else session.get(JournalEntry, line.entry_id)
    if line is None or entry is None or entry.date.date() > as_of: return False
    if entry.state == "posted": return True
    if entry.state != "reversed": return False
    reversal = session.exec(select(JournalEntryReversalRecord).where(JournalEntryReversalRecord.original_entry_id == entry.id)).first()
    return reversal is not None and session.get(JournalEntry, reversal.reversal_entry_id).date.date() > as_of
def _audit(session, entity_id, event_type, details):
    session.add(AuditEventRecord(entity_id=entity_id, event_type=event_type, timestamp=datetime.now(timezone.utc).isoformat(), details_json=json.dumps(details, sort_keys=True)))

def create_fund(session, fund):
    if not isinstance(fund, Fund) or fund.id is not None: raise TypeError("fund must be a new Fund")
    _entity(session, fund.entity_id)
    if fund.program_id is not None: _program(session, fund.entity_id, fund.program_id)
    if session.exec(select(FundRecord).where(FundRecord.entity_id == fund.entity_id, FundRecord.code == fund.code)).first(): raise ValueError("Fund code already exists for Entity")
    row = FundRecord(entity_id=fund.entity_id, code=fund.code, name=fund.name, restriction=fund.restriction, purpose=fund.purpose, program_id=fund.program_id, valid_from=None if fund.valid_from is None else fund.valid_from.isoformat(), valid_until=None if fund.valid_until is None else fund.valid_until.isoformat())
    try:
        session.add(row); session.flush(); _audit(session, fund.entity_id, "fund_created", {"fund_id": row.id}); session.commit()
    except Exception: session.rollback(); raise
    return replace(fund, id=row.id)

def create_funding_source(session, source):
    if not isinstance(source, FundingSource) or source.id is not None: raise TypeError("source must be a new FundingSource")
    _entity(session, source.entity_id)
    if source.donor_third_party_id is not None:
        donor = session.get(ThirdPartyRecord, source.donor_third_party_id)
        if donor is None or donor.entity_id != source.entity_id: raise LookupError("FundingSource donor is not owned by Entity")
    if session.exec(select(FundingSourceRecord).where(FundingSourceRecord.entity_id == source.entity_id, FundingSourceRecord.name == source.name)).first(): raise ValueError("FundingSource name already exists for Entity")
    row = FundingSourceRecord(entity_id=source.entity_id, name=source.name, donor_third_party_id=source.donor_third_party_id, external_reference=source.external_reference)
    try:
        session.add(row); session.flush(); _audit(session, source.entity_id, "funding_source_created", {"source_id": row.id}); session.commit()
    except Exception: session.rollback(); raise
    return replace(source, id=row.id)

def record_fund_receipt(session, receipt):
    if not isinstance(receipt, FundReceipt) or receipt.id is not None: raise TypeError("receipt must be a new FundReceipt")
    _entity(session, receipt.entity_id); fund = _fund(session, receipt.entity_id, receipt.fund_id); _source(session, receipt.entity_id, receipt.funding_source_id)
    line = session.get(JournalLine, receipt.journal_line_id)
    if line is None: raise LookupError("JournalLine not found")
    entry = session.get(JournalEntry, line.entry_id)
    if entry is None or entry.state not in ("posted", "reversed"): raise ValueError("JournalLine must belong to a posted JournalEntry")
    context = _posting_context(session, entry.id)
    if context[0] != "active": raise ValueError("JournalLine has no unambiguous active Entity ownership")
    if not _effective(session, receipt.journal_line_id, entry.date.date()): raise ValueError("FundReceipt cannot reference an ineffective or reverted JournalLine")
    line, entry, line_amount = _line_amount(session, receipt.journal_line_id, kind="receipt")
    if line_amount != receipt.amount: raise ValueError("receipt amount must equal the canonical JournalLine amount")
    if receipt.received_at.date() != entry.date.date(): raise ValueError("received_at must equal the canonical JournalEntry date")
    if fund.valid_from and entry.date.date().isoformat() < fund.valid_from: raise ValueError("receipt is before Fund validity")
    if fund.valid_until and entry.date.date().isoformat() > fund.valid_until: raise ValueError("receipt is after Fund validity")
    if receipt.donation_id is None: raise ValueError("FundReceipt requires Donation provenance for a resource receipt")
    donation = session.get(DonationRecord, receipt.donation_id)
    if donation is None or donation.entity_id != receipt.entity_id or Decimal(donation.amount) != receipt.amount or donation.date != entry.date.isoformat(): raise ValueError("receipt donation must match Entity, canonical date and exact amount")
    already = session.exec(select(FundReceiptRecord).where(FundReceiptRecord.journal_line_id == receipt.journal_line_id)).first()
    if already is not None: raise ValueError("JournalLine is already attributed to a FundReceipt")
    row = FundReceiptRecord(entity_id=receipt.entity_id, fund_id=receipt.fund_id, funding_source_id=receipt.funding_source_id, journal_line_id=receipt.journal_line_id, donation_id=receipt.donation_id, amount=str(receipt.amount), received_at=entry.date.isoformat())
    try:
        session.add(row); session.flush(); _audit(session, receipt.entity_id, "fund_receipt_recorded", {"receipt_id": row.id, "journal_line_id": line.id}); session.commit()
    except Exception: session.rollback(); raise
    return replace(receipt, id=row.id)

def record_fund_application(session, application):
    if not isinstance(application, FundApplication) or application.id is not None: raise TypeError("application must be a new FundApplication")
    fund = _fund(session, application.entity_id, application.fund_id); _entity(session, application.entity_id); _program(session, application.entity_id, application.program_id)
    line, entry, line_amount = _line_amount(session, application.journal_line_id, kind="application")
    if not _effective(session, application.journal_line_id, entry.date.date()): raise ValueError("FundApplication cannot reference an ineffective or reverted JournalLine")
    if application.amount > line_amount: raise ValueError("application cannot exceed the canonical JournalLine amount")
    if application.applied_at.date() != entry.date.date(): raise ValueError("applied_at must equal the canonical JournalEntry date")
    if fund.valid_from and entry.date.date().isoformat() < fund.valid_from: raise ValueError("application is before Fund validity")
    if fund.valid_until and entry.date.date().isoformat() > fund.valid_until: raise ValueError("application is after Fund validity")
    if fund.program_id is not None and fund.program_id != application.program_id: raise ValueError("application Program differs from Fund destination")
    if application.receipt_id is not None:
        receipt = session.get(FundReceiptRecord, application.receipt_id)
        if receipt is None or receipt.entity_id != application.entity_id or receipt.fund_id != application.fund_id: raise ValueError("application receipt does not belong to Fund and Entity")
        if not _effective(session, receipt.journal_line_id, entry.date.date()): raise ValueError("application receipt is not effective at the application date")
    existing = session.exec(select(FundApplicationRecord).where(FundApplicationRecord.journal_line_id == application.journal_line_id)).all()
    if sum((Decimal(row.amount) for row in existing), Decimal("0")) + application.amount > line_amount: raise ValueError("applications exceed the canonical JournalLine amount")
    fund_receipts = session.exec(select(FundReceiptRecord).where(FundReceiptRecord.fund_id == application.fund_id)).all()
    received = sum((Decimal(row.amount) for row in fund_receipts if _effective(session, row.journal_line_id, entry.date.date())), Decimal("0"))
    fund_apps = session.exec(select(FundApplicationRecord).where(FundApplicationRecord.fund_id == application.fund_id)).all()
    applied = sum((Decimal(row.amount) for row in fund_apps if _effective(session, row.journal_line_id, entry.date.date())), Decimal("0"))
    if applied + application.amount > received: raise ValueError("application exceeds effective Fund availability")
    if application.receipt_id is not None:
        receipt_apps = session.exec(select(FundApplicationRecord).where(FundApplicationRecord.receipt_id == application.receipt_id)).all()
        receipt = session.get(FundReceiptRecord, application.receipt_id)
        if sum((Decimal(row.amount) for row in receipt_apps if _effective(session, row.journal_line_id, entry.date.date())), Decimal("0")) + application.amount > Decimal(receipt.amount): raise ValueError("applications exceed effective receipt availability")
    row = FundApplicationRecord(entity_id=application.entity_id, fund_id=application.fund_id, program_id=application.program_id, journal_line_id=application.journal_line_id, receipt_id=application.receipt_id, amount=str(application.amount), applied_at=entry.date.isoformat(), purpose=application.purpose)
    try:
        session.add(row); session.flush(); _audit(session, application.entity_id, "fund_application_recorded", {"application_id": row.id, "journal_line_id": line.id}); session.commit()
    except Exception: session.rollback(); raise
    return replace(application, id=row.id)

def list_fund_applications(session, entity_id, fund_id):
    _fund(session, entity_id, fund_id)
    return tuple(session.exec(select(FundApplicationRecord).where(FundApplicationRecord.entity_id == entity_id, FundApplicationRecord.fund_id == fund_id).order_by(FundApplicationRecord.id)).all())


def load_fund_balance(session, entity_id, fund_id, as_of):
    fund = _fund(session, entity_id, fund_id)
    if type(as_of) is not date: raise TypeError("as_of must be date")
    receipts = session.exec(select(FundReceiptRecord).where(FundReceiptRecord.entity_id == entity_id, FundReceiptRecord.fund_id == fund_id)).all()
    applications = session.exec(select(FundApplicationRecord).where(FundApplicationRecord.entity_id == entity_id, FundApplicationRecord.fund_id == fund_id)).all()
    received = sum((Decimal(row.amount) for row in receipts if _effective(session, row.journal_line_id, as_of)), Decimal("0"))
    applied = sum((Decimal(row.amount) for row in applications if _effective(session, row.journal_line_id, as_of)), Decimal("0"))
    if applied > received: raise ValueError("fund traceability is inconsistent: applications exceed receipts")
    return FundBalance(fund_id=fund_id, as_of=as_of, received=received, applied=applied, available=received-applied, restriction=fund.restriction, program_id=fund.program_id)


def load_fund_traceability(session, entity_id, fund_id, as_of):
    """Return a fail-closed professional projection with canonical ledger evidence."""
    fund = _fund(session, entity_id, fund_id)
    balance = load_fund_balance(session, entity_id, fund_id, as_of)
    receipts = session.exec(select(FundReceiptRecord).where(FundReceiptRecord.entity_id == entity_id, FundReceiptRecord.fund_id == fund_id).order_by(FundReceiptRecord.id)).all()
    applications = session.exec(select(FundApplicationRecord).where(FundApplicationRecord.entity_id == entity_id, FundApplicationRecord.fund_id == fund_id).order_by(FundApplicationRecord.id)).all()
    source_ids = {row.funding_source_id for row in receipts}
    sources = {row.id: row for row in session.exec(select(FundingSourceRecord).where(FundingSourceRecord.id.in_(source_ids))).all()} if source_ids else {}
    def ledger(line_id):
        line = session.get(JournalLine, line_id)
        entry = None if line is None else session.get(JournalEntry, line.entry_id)
        if line is None or entry is None: raise ValueError("fund traceability references missing ledger evidence")
        reversal = session.exec(select(JournalEntryReversalRecord).where(JournalEntryReversalRecord.original_entry_id == entry.id)).first()
        return {"entry_id": entry.id, "line_id": line.id, "date": entry.date.isoformat(), "account_id": line.account_id, "debit": str(line.debit), "credit": str(line.credit), "state": entry.state, "reversal_entry_id": None if reversal is None else reversal.reversal_entry_id}
    return {
        "fund": {"id": fund.id, "code": fund.code, "name": fund.name, "restriction": fund.restriction, "purpose": fund.purpose, "program_id": fund.program_id, "valid_from": fund.valid_from, "valid_until": fund.valid_until},
        "as_of": as_of.isoformat(),
        "received": str(balance.received), "applied": str(balance.applied), "available": str(balance.available),
        "receipts": [{"id": row.id, "source": {"id": sources[row.funding_source_id].id, "name": sources[row.funding_source_id].name}, "amount": str(row.amount), "effective": _effective(session, row.journal_line_id, as_of), "ledger": ledger(row.journal_line_id)} for row in receipts],
        "applications": [{"id": row.id, "program_id": row.program_id, "receipt_id": row.receipt_id, "amount": str(row.amount), "effective": _effective(session, row.journal_line_id, as_of), "ledger": ledger(row.journal_line_id)} for row in applications],
    }
