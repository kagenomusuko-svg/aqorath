"""Atomic AQR-009 composition over canonical accounting authorities."""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import uuid4
import json
from sqlmodel import select

from .economic_facts import EconomicFact
from . import accounting_operation as _operations
from . import accounting_operation_persistence as _persistence
from . import confirmation as _confirmation
from . import posting as _posting
from . import storage as _storage
from .models import Account, AuditEventRecord, DonationRecord, InKindDonationRecord, DocumentReferenceRecord, JournalEntry, JournalLine, EntityRecord, FixedAssetRecord
from .fund_models import FundRecord, FundingSourceRecord, FundReceiptRecord
from .banking_models import BankAccountRecord


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
    operation_id: str = ""
    bank_account_id: int | None = None


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
    operation_id: str = ""


def prepare_monetary_donation(session, amount, posting_date, *, donor_third_party_id, document_type, document_number, document_date, fund_id, funding_source_id, program_id=None, purpose=None, is_restricted=False, bank_account_id=None):
    fact = EconomicFact("donation", amount, "bank")
    operation_date = posting_date.date() if isinstance(posting_date, datetime) else posting_date
    if bank_account_id is None:
        decision = _operations.prepare_accounting_operation(session, fact, operation_date)
    else:
        entity = session.exec(select(EntityRecord).where(EntityRecord.is_active.is_(True))).one()
        bank_account = session.get(BankAccountRecord, bank_account_id)
        if (
            bank_account is None
            or bank_account.entity_id != entity.id
            or bank_account.is_active is not True
        ):
            raise ValueError("selected bank account does not belong to the active Entity")
        ledger_account = session.get(Account, bank_account.ledger_account_id)
        if ledger_account is None:
            raise LookupError("selected bank account ledger authority is incomplete")
        decision = _operations._prepare_accounting_operation_with_binding_overrides(
            session,
            fact,
            operation_date,
            {"bank": ledger_account.code},
        )
    return PreparedDonationOperation(decision, donor_third_party_id, document_type, document_number, document_date, fund_id, funding_source_id, program_id, purpose, is_restricted, uuid4().hex, bank_account_id)


def _existing_monetary_result(session, operation_id):
    events = session.exec(
        select(AuditEventRecord).where(AuditEventRecord.event_type == "entry_posted")
    ).all()
    for event in events:
        try:
            details = json.loads(event.details_json)
        except (TypeError, ValueError):
            continue
        if details.get("operation_id") == operation_id:
            return details.get("donation_operation_result")
    return None


def stage_monetary_donation(session, prepared, *, document_fields=None):
    """Stage the complete AQR-009 monetary operation in a caller transaction."""
    if not isinstance(prepared, PreparedDonationOperation):
        raise TypeError("prepared must be PreparedDonationOperation")
    existing = _existing_monetary_result(session, prepared.operation_id)
    if existing is not None:
        return existing
    confirmed = _operations.confirm_accounting_operation(prepared.decision)
    instruction = _posting.create_posting_instruction(confirmed.confirmed_proposal)
    entity = session.exec(select(EntityRecord).where(EntityRecord.is_active.is_(True))).one()
    fund = session.get(FundRecord, prepared.fund_id)
    source = session.get(FundingSourceRecord, prepared.funding_source_id)
    if fund is None or fund.entity_id != entity.id:
        raise ValueError("fund does not belong to active Entity")
    if source is None or source.entity_id != entity.id:
        raise ValueError("funding source does not belong to active Entity")
    result = _persistence.stage_posting_with_audit(session, instruction, confirmed)
    audit = session.get(AuditEventRecord, result.audit_event_id)
    audit.details_json = json.dumps(
        {**json.loads(audit.details_json), "operation_id": prepared.operation_id},
        sort_keys=True,
    )
    entry = session.get(JournalEntry, result.entry_id)
    bank_line = session.exec(
        select(JournalLine).where(
            JournalLine.entry_id == entry.id,
            JournalLine.debit != "0",
        )
    ).one()
    if prepared.bank_account_id is not None:
        bank_account = session.get(BankAccountRecord, prepared.bank_account_id)
        if (
            bank_account is None
            or bank_account.entity_id != entity.id
            or bank_account.is_active is not True
        ):
            raise ValueError("selected bank account does not belong to the active Entity")
        if bank_line.account_id != bank_account.ledger_account_id:
            raise ValueError("selected bank account differs from the prepared bank line")
    donation = DonationRecord(
        entity_id=entity.id,
        date=entry.date.isoformat(),
        amount=str(prepared.decision.fact.amount),
        donor_third_party_id=prepared.donor_third_party_id,
        purpose=prepared.purpose,
        is_restricted=prepared.is_restricted,
    )
    session.add(donation)
    session.flush()
    fields = {
        "entry_id": entry.id,
        "third_party_id": prepared.donor_third_party_id,
        "document_type": prepared.document_type,
        "document_number": prepared.document_number,
        "date": prepared.document_date.isoformat(),
        "is_validated": False,
    }
    if document_fields:
        allowed = {
            "issuer_name",
            "file_hash",
            "file_path",
            "external_url",
            "is_validated",
            "validation_notes",
        }
        unexpected = set(document_fields) - allowed
        if unexpected:
            raise ValueError(
                "document_fields cannot replace canonical donation ownership: "
                + ", ".join(sorted(unexpected))
            )
        fields.update(document_fields)
    document = DocumentReferenceRecord(**fields)
    session.add(document)
    session.flush()
    receipt = FundReceiptRecord(
        entity_id=entity.id,
        fund_id=fund.id,
        funding_source_id=source.id,
        journal_line_id=bank_line.id,
        donation_id=donation.id,
        amount=str(prepared.decision.fact.amount),
        received_at=entry.date.isoformat(),
    )
    session.add(receipt)
    session.flush()
    output = {
        "entry_id": entry.id,
        "donation_id": donation.id,
        "document_reference_id": document.id,
        "fund_receipt_id": receipt.id,
        "audit_event_id": result.audit_event_id,
    }
    audit.details_json = json.dumps(
        {
            **json.loads(audit.details_json),
            "bank_account_id": prepared.bank_account_id,
            "donation_operation_result": output,
        },
        sort_keys=True,
    )
    session.add(audit)
    session.flush()
    return output


def confirm_monetary_donation(prepared):
    if not isinstance(prepared, PreparedDonationOperation):
        raise TypeError("prepared must be PreparedDonationOperation")
    with _storage.get_session() as session:
        try:
            output = stage_monetary_donation(session, prepared)
            session.commit()
            return output
        except Exception:
            session.rollback()
            raise


def load_monetary_donation_trace(session, entity_id, donation_id):
    donation = session.get(DonationRecord, donation_id)
    if donation is None or donation.entity_id != entity_id: raise LookupError("Donation not found for Entity")
    receipt = session.exec(select(FundReceiptRecord).where(FundReceiptRecord.donation_id == donation.id)).first()
    if receipt is None: raise LookupError("Donation has no FundReceipt")
    line = session.get(JournalLine, receipt.journal_line_id)
    entry = session.get(__import__("aqorath.models", fromlist=["JournalEntry"]).JournalEntry, line.entry_id)
    document = session.exec(select(DocumentReferenceRecord).where(DocumentReferenceRecord.entry_id == entry.id)).first()
    reversal = session.exec(select(__import__("aqorath.models", fromlist=["JournalEntryReversalRecord"]).JournalEntryReversalRecord).where(__import__("aqorath.models", fromlist=["JournalEntryReversalRecord"]).JournalEntryReversalRecord.original_entry_id == entry.id)).first()
    return {"donation": {"id": donation.id, "date": donation.date, "amount": donation.amount, "donor_third_party_id": donation.donor_third_party_id, "purpose": donation.purpose, "is_restricted": donation.is_restricted}, "ledger": {"entry_id": entry.id, "lines": [{"line_id": item.id, "account_id": item.account_id, "debit": item.debit, "credit": item.credit} for item in session.exec(select(JournalLine).where(JournalLine.entry_id == entry.id)).all()], "state": entry.state, "reversal_entry_id": None if reversal is None else reversal.reversal_entry_id}, "document": None if document is None else {"id": document.id, "type": document.document_type, "number": document.document_number}, "fund_receipt": {"id": receipt.id, "fund_id": receipt.fund_id, "funding_source_id": receipt.funding_source_id, "amount": receipt.amount}}


def load_inkind_donation_trace(session, entity_id, donation_id):
    item = session.get(InKindDonationRecord, donation_id)
    if item is None or item.entity_id != entity_id: raise LookupError("InKindDonation not found for Entity")
    line = session.get(JournalLine, item.journal_line_id)
    entry = session.get(__import__("aqorath.models", fromlist=["JournalEntry"]).JournalEntry, line.entry_id)
    document = session.get(DocumentReferenceRecord, item.document_reference_id)
    asset = session.get(FixedAssetRecord, item.fixed_asset_id)
    reversal = session.exec(select(__import__("aqorath.models", fromlist=["JournalEntryReversalRecord"]).JournalEntryReversalRecord).where(__import__("aqorath.models", fromlist=["JournalEntryReversalRecord"]).JournalEntryReversalRecord.original_entry_id == entry.id)).first()
    lines = session.exec(select(JournalLine).where(JournalLine.entry_id == entry.id)).all()
    return {"inkind_donation": {"id": item.id, "description": item.description, "quantity": item.quantity, "valuation_amount": item.valuation_amount, "valuation_method": item.valuation_method, "valuation_evidence": item.valuation_evidence, "journal_line_id": item.journal_line_id, "fixed_asset_id": item.fixed_asset_id}, "fixed_asset": None if asset is None else {"id": asset.id, "code": asset.code, "acquisition_cost": asset.acquisition_cost}, "document": None if document is None else {"id": document.id, "number": document.document_number}, "ledger": {"entry_id": entry.id, "state": entry.state, "reversal_entry_id": None if reversal is None else reversal.reversal_entry_id, "lines": [{"line_id": x.id, "account_id": x.account_id, "debit": x.debit, "credit": x.credit} for x in lines], "cash_or_bank_lines": [x.id for x in lines if x.account_code in ("1101", "1102")]}}


def prepare_inkind_donation(session, amount, posting_date, **metadata):
    decision = _operations.prepare_accounting_operation(session, EconomicFact("inkind_donation", amount, "noncash"), posting_date.date() if isinstance(posting_date, datetime) else posting_date)
    return PreparedInKindDonationOperation(decision=decision, operation_id=uuid4().hex, **metadata)


def confirm_inkind_donation(prepared):
    if not isinstance(prepared, PreparedInKindDonationOperation): raise TypeError("prepared must be PreparedInKindDonationOperation")
    confirmed = _operations.confirm_accounting_operation(prepared.decision)
    instruction = _posting.create_posting_instruction(confirmed.confirmed_proposal)
    with _storage.get_session() as session:
        existing = [event for event in session.exec(select(__import__("aqorath.models", fromlist=["AuditEventRecord"]).AuditEventRecord)).all() if prepared.operation_id in event.details_json]
        if existing:
            return json.loads(existing[0].details_json)["donation_operation_result"]
        entity = session.exec(select(EntityRecord).where(EntityRecord.is_active.is_(True))).one()
        result = _persistence.stage_posting_with_audit(session, instruction, confirmed)
        audit = session.get(__import__("aqorath.models", fromlist=["AuditEventRecord"]).AuditEventRecord, result.audit_event_id)
        audit.details_json = json.dumps({**json.loads(audit.details_json), "operation_id": prepared.operation_id}, sort_keys=True)
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
        session.add(item); session.flush()
        output = {"entry_id": entry.id, "fixed_asset_id": asset.id, "inkind_donation_id": item.id, "document_reference_id": document.id, "audit_event_id": result.audit_event_id}
        audit.details_json = json.dumps({**json.loads(audit.details_json), "donation_operation_result": output}, sort_keys=True)
        session.commit(); return output
