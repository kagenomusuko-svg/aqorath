"""Atomic AQR-009 composition over canonical accounting authorities."""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from sqlmodel import select

from .economic_facts import EconomicFact
from . import accounting_operation as _operations
from . import accounting_operation_persistence as _persistence
from . import confirmation as _confirmation
from . import posting as _posting
from . import storage as _storage
from .models import DonationRecord, InKindDonationRecord, DocumentReferenceRecord, JournalLine, EntityRecord, FixedAssetRecord
from .fund_models import FundRecord, FundingSourceRecord, FundReceiptRecord


@dataclass(frozen=True)
class PreparedDonationOperation:
    decision: object
    donor_third_party_id: int | None
    document_type: str
    document_number: str
    document_date: datetime
    fund_id: int
    funding_source_id: int
    program_id: int | None
    purpose: str | None
    is_restricted: bool


@dataclass(frozen=True)
class PreparedInKindDonationOperation:
    decision: object
    donor_third_party_id: int | None
    document_type: str
    document_number: str
    document_date: datetime
    received_at: datetime
    description: str
    quantity: Decimal | None
    valuation_method: str
    valuation_evidence: str
    external_reference: str
    asset_code: str
    asset_name: str
    useful_life_months: int
    program_id: int | None
    fund_id: int | None


def prepare_monetary_donation(session, amount, posting_date, *, donor_third_party_id, document_type, document_number, document_date, fund_id, funding_source_id, program_id=None, purpose=None, is_restricted=False):
    decision = _operations.prepare_accounting_operation(session, EconomicFact("donation", amount, "bank"), posting_date.date() if isinstance(posting_date, datetime) else posting_date)
    return PreparedDonationOperation(decision, donor_third_party_id, document_type, document_number, document_date, fund_id, funding_source_id, program_id, purpose, is_restricted)


def confirm_monetary_donation(prepared):
    if not isinstance(prepared, PreparedDonationOperation):
        raise TypeError("prepared must be PreparedDonationOperation")
    confirmed = _operations.confirm_accounting_operation(prepared.decision)
    instruction = _posting.create_posting_instruction(confirmed.confirmed_proposal)
    with _storage.get_session() as session:
        entity = session.exec(select(EntityRecord).where(EntityRecord.is_active.is_(True))).one()
        fund = session.get(FundRecord, prepared.fund_id)
        source = session.get(FundingSourceRecord, prepared.funding_source_id)
        if fund is None or fund.entity_id != entity.id: raise ValueError("fund does not belong to active Entity")
        if source is None or source.entity_id != entity.id: raise ValueError("funding source does not belong to active Entity")
        result = _persistence.stage_posting_with_audit(session, instruction, confirmed)
        entry = session.get(__import__("aqorath.models", fromlist=["JournalEntry"]).JournalEntry, result.entry_id)
        bank_line = session.exec(select(JournalLine).where(JournalLine.entry_id == entry.id, JournalLine.debit != "0")).one()
        donation = DonationRecord(entity_id=entity.id, date=entry.date.isoformat(), amount=str(prepared.decision.fact.amount), donor_third_party_id=prepared.donor_third_party_id, purpose=prepared.purpose, is_restricted=prepared.is_restricted)
        session.add(donation); session.flush()
        document = DocumentReferenceRecord(entry_id=entry.id, third_party_id=prepared.donor_third_party_id, document_type=prepared.document_type, document_number=prepared.document_number, date=prepared.document_date.isoformat(), is_validated=False)
        session.add(document); session.flush()
        receipt = FundReceiptRecord(entity_id=entity.id, fund_id=fund.id, funding_source_id=source.id, journal_line_id=bank_line.id, donation_id=donation.id, amount=str(prepared.decision.fact.amount), received_at=entry.date.isoformat())
        session.add(receipt); session.flush(); session.commit()
        return {"entry_id": entry.id, "donation_id": donation.id, "document_reference_id": document.id, "fund_receipt_id": receipt.id, "audit_event_id": result.audit_event_id}


def load_monetary_donation_trace(session, entity_id, donation_id):
    donation = session.get(DonationRecord, donation_id)
    if donation is None or donation.entity_id != entity_id: raise LookupError("Donation not found for Entity")
    receipt = session.exec(select(FundReceiptRecord).where(FundReceiptRecord.donation_id == donation.id)).first()
    if receipt is None: raise LookupError("Donation has no FundReceipt")
    line = session.get(JournalLine, receipt.journal_line_id)
    entry = session.get(__import__("aqorath.models", fromlist=["JournalEntry"]).JournalEntry, line.entry_id)
    document = session.exec(select(DocumentReferenceRecord).where(DocumentReferenceRecord.entry_id == entry.id)).first()
    return {"donation": {"id": donation.id, "date": donation.date, "amount": donation.amount, "donor_third_party_id": donation.donor_third_party_id, "purpose": donation.purpose, "is_restricted": donation.is_restricted}, "ledger": {"entry_id": entry.id, "lines": [{"line_id": item.id, "account_id": item.account_id, "debit": item.debit, "credit": item.credit} for item in session.exec(select(JournalLine).where(JournalLine.entry_id == entry.id)).all()], "state": entry.state}, "document": None if document is None else {"id": document.id, "type": document.document_type, "number": document.document_number}, "fund_receipt": {"id": receipt.id, "fund_id": receipt.fund_id, "funding_source_id": receipt.funding_source_id, "amount": receipt.amount}}


def prepare_inkind_donation(session, amount, posting_date, **metadata):
    decision = _operations.prepare_accounting_operation(session, EconomicFact("inkind_donation", amount, "noncash"), posting_date.date() if isinstance(posting_date, datetime) else posting_date)
    return PreparedInKindDonationOperation(decision=decision, **metadata)


def confirm_inkind_donation(prepared):
    if not isinstance(prepared, PreparedInKindDonationOperation): raise TypeError("prepared must be PreparedInKindDonationOperation")
    confirmed = _operations.confirm_accounting_operation(prepared.decision)
    instruction = _posting.create_posting_instruction(confirmed.confirmed_proposal)
    with _storage.get_session() as session:
        entity = session.exec(select(EntityRecord).where(EntityRecord.is_active.is_(True))).one()
        result = _persistence.stage_posting_with_audit(session, instruction, confirmed)
        entry = session.get(__import__("aqorath.models", fromlist=["JournalEntry"]).JournalEntry, result.entry_id)
        asset_line = session.exec(select(JournalLine).where(JournalLine.entry_id == entry.id, JournalLine.account_id == instruction.lines[0].account_id)).one()
        if instruction.lines[0].account_role != "fixed_asset_computer_equipment": raise ValueError("in-kind fixture requires a durable computer asset role")
        existing = session.exec(select(FixedAssetRecord).where(FixedAssetRecord.entity_id == entity.id, FixedAssetRecord.code == prepared.asset_code)).first()
        if existing is not None: raise ValueError("fixed asset code already belongs to another operation")
        asset = FixedAssetRecord(entity_id=entity.id, code=prepared.asset_code, name=prepared.asset_name, acquisition_date=entry.date.date(), in_service_date=entry.date.date(), acquisition_cost=str(prepared.decision.fact.amount), residual_value="0", useful_life_months=prepared.useful_life_months, depreciation_method="straight_line", is_active=True)
        session.add(asset); session.flush()
        document = DocumentReferenceRecord(entry_id=entry.id, third_party_id=prepared.donor_third_party_id, document_type=prepared.document_type, document_number=prepared.document_number, date=prepared.document_date.isoformat(), is_validated=False)
        session.add(document); session.flush()
        item = InKindDonationRecord(entity_id=entity.id, donor_third_party_id=prepared.donor_third_party_id, document_reference_id=document.id, fund_id=prepared.fund_id, program_id=prepared.program_id, journal_line_id=asset_line.id, fixed_asset_id=asset.id, received_at=prepared.received_at.isoformat(), description=prepared.description, quantity=None if prepared.quantity is None else str(prepared.quantity), valuation_amount=str(prepared.decision.fact.amount), valuation_currency="MXN", valuation_method=prepared.valuation_method, valuation_evidence=prepared.valuation_evidence, external_reference=prepared.external_reference)
        session.add(item); session.flush(); session.commit()
        return {"entry_id": entry.id, "fixed_asset_id": asset.id, "inkind_donation_id": item.id, "document_reference_id": document.id, "audit_event_id": result.audit_event_id}
