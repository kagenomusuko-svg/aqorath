"""Transactional persistence for OSC fund traceability over JournalLine."""
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
import json
from sqlmodel import select
from .fund import Fund, FundingSource, FundReceipt, FundApplication
from .fund_models import FundRecord, FundingSourceRecord, FundReceiptRecord, FundApplicationRecord
from .models import AuditEventRecord, DonationRecord, EntityRecord, JournalLine, ProgramRecord, ThirdPartyRecord

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
def _line_amount(session, line_id):
    line = session.get(JournalLine, line_id)
    if line is None: raise LookupError("JournalLine not found")
    debit, credit = Decimal(line.debit), Decimal(line.credit)
    if debit != 0 and credit != 0 or debit == credit: raise ValueError("JournalLine must have one nonzero monetary side")
    return line, abs(debit - credit)
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
    _entity(session, receipt.entity_id); _fund(session, receipt.entity_id, receipt.fund_id); _source(session, receipt.entity_id, receipt.funding_source_id)
    line, line_amount = _line_amount(session, receipt.journal_line_id)
    if line_amount != receipt.amount: raise ValueError("receipt amount must equal the canonical JournalLine amount")
    if receipt.donation_id is not None:
        donation = session.get(DonationRecord, receipt.donation_id)
        if donation is None or donation.entity_id != receipt.entity_id or Decimal(donation.amount) != receipt.amount: raise ValueError("receipt donation must match Entity and exact amount")
    row = FundReceiptRecord(entity_id=receipt.entity_id, fund_id=receipt.fund_id, funding_source_id=receipt.funding_source_id, journal_line_id=receipt.journal_line_id, donation_id=receipt.donation_id, amount=str(receipt.amount), received_at=receipt.received_at.isoformat())
    try:
        session.add(row); session.flush(); _audit(session, receipt.entity_id, "fund_receipt_recorded", {"receipt_id": row.id, "journal_line_id": line.id}); session.commit()
    except Exception: session.rollback(); raise
    return replace(receipt, id=row.id)

def record_fund_application(session, application):
    if not isinstance(application, FundApplication) or application.id is not None: raise TypeError("application must be a new FundApplication")
    fund = _fund(session, application.entity_id, application.fund_id); _entity(session, application.entity_id); _program(session, application.entity_id, application.program_id)
    line, line_amount = _line_amount(session, application.journal_line_id)
    if application.amount > line_amount: raise ValueError("application cannot exceed the canonical JournalLine amount")
    if fund.program_id is not None and fund.program_id != application.program_id: raise ValueError("application Program differs from Fund destination")
    if application.receipt_id is not None:
        receipt = session.get(FundReceiptRecord, application.receipt_id)
        if receipt is None or receipt.entity_id != application.entity_id or receipt.fund_id != application.fund_id: raise ValueError("application receipt does not belong to Fund and Entity")
    existing = session.exec(select(FundApplicationRecord).where(FundApplicationRecord.journal_line_id == application.journal_line_id)).all()
    if sum((Decimal(row.amount) for row in existing), Decimal("0")) + application.amount > line_amount: raise ValueError("applications exceed the canonical JournalLine amount")
    row = FundApplicationRecord(entity_id=application.entity_id, fund_id=application.fund_id, program_id=application.program_id, journal_line_id=application.journal_line_id, receipt_id=application.receipt_id, amount=str(application.amount), applied_at=application.applied_at.isoformat(), purpose=application.purpose)
    try:
        session.add(row); session.flush(); _audit(session, application.entity_id, "fund_application_recorded", {"application_id": row.id, "journal_line_id": line.id}); session.commit()
    except Exception: session.rollback(); raise
    return replace(application, id=row.id)

def list_fund_applications(session, entity_id, fund_id):
    _fund(session, entity_id, fund_id)
    return tuple(session.exec(select(FundApplicationRecord).where(FundApplicationRecord.entity_id == entity_id, FundApplicationRecord.fund_id == fund_id).order_by(FundApplicationRecord.id)).all())
