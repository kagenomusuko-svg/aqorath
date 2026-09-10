"""Persistence authority for non-cash donation evidence."""
from dataclasses import replace
from .inkind_donation import InKindDonation
from .models import (InKindDonationRecord, EntityRecord, EntityProfileRecord,
                     ThirdPartyRecord, DocumentReferenceRecord, JournalLine,
                     JournalEntry, JournalEntryReversalRecord, ProgramRecord)
from .models import FixedAssetRecord
from .fund_models import FundRecord
from .fund_repository import _posting_context
from sqlmodel import select

def create_inkind_donation(session, donation):
    if not isinstance(donation, InKindDonation) or donation.id is not None: raise TypeError("new InKindDonation required")
    if donation.valuation_currency != "MXN": raise ValueError("AQR-009 V1 supports MXN only")
    owner = session.get(EntityRecord, donation.entity_id)
    if owner is None or owner.is_active is not True: raise ValueError("InKindDonation owner Entity must be active")
    profile = session.exec(select(EntityProfileRecord).where(EntityProfileRecord.entity_id == donation.entity_id)).all()
    if len(profile) != 1 or "osc" not in __import__("json").loads(profile[0].special_capabilities_json): raise ValueError("InKindDonation owner must have osc capability")
    if donation.donor_third_party_id is not None:
        donor = session.get(ThirdPartyRecord, donation.donor_third_party_id)
        if donor is None or donor.entity_id != donation.entity_id: raise ValueError("donor must belong to the same Entity")
    if donation.program_id is not None:
        program = session.get(ProgramRecord, donation.program_id)
        if program is None or program.entity_id != donation.entity_id: raise ValueError("program must belong to the same Entity")
    if donation.fund_id is not None:
        fund = session.get(FundRecord, donation.fund_id)
        if fund is None or fund.entity_id != donation.entity_id: raise ValueError("fund must belong to the same Entity")
        if fund.program_id is not None and fund.program_id != donation.program_id: raise ValueError("program conflicts with fund destination")
    if donation.document_reference_id is not None:
        document = session.get(DocumentReferenceRecord, donation.document_reference_id)
        if document is None: raise LookupError("DocumentReference not found")
        context = _posting_context(session, document.entry_id)
        if context[0] != "active" or context[0] == "foreign": raise ValueError("DocumentReference is not owned by Entity")
    if donation.journal_line_id is not None:
        line = session.get(JournalLine, donation.journal_line_id)
        entry = None if line is None else session.get(JournalEntry, line.entry_id)
        if line is None or entry is None: raise LookupError("JournalLine not found")
        context = _posting_context(session, entry.id)
        if context[0] != "active" or context[1] not in ("donation", "inkind_donation"): raise ValueError("JournalLine lacks canonical in-kind donation provenance")
        if entry.state != "posted": raise ValueError("JournalLine is not effective")
        if session.exec(select(InKindDonationRecord).where(InKindDonationRecord.journal_line_id == line.id)).first(): raise ValueError("JournalLine already attributes an in-kind donation")
        if entry.date != donation.received_at.isoformat(): raise ValueError("donation date must equal canonical posting date")
    if donation.fixed_asset_id is not None:
        asset = session.get(FixedAssetRecord, donation.fixed_asset_id)
        if asset is None or asset.entity_id != donation.entity_id: raise ValueError("fixed asset must belong to the same Entity")
    if session.exec(select(InKindDonationRecord).where(InKindDonationRecord.entity_id == donation.entity_id, InKindDonationRecord.external_reference == donation.external_reference)).first(): raise ValueError("external_reference already exists")
    record = InKindDonationRecord(entity_id=donation.entity_id, donor_third_party_id=donation.donor_third_party_id, document_reference_id=donation.document_reference_id, fund_id=donation.fund_id, program_id=donation.program_id, journal_line_id=donation.journal_line_id, fixed_asset_id=donation.fixed_asset_id, received_at=donation.received_at.isoformat(), description=donation.description, quantity=None if donation.quantity is None else str(donation.quantity), valuation_amount=str(donation.valuation_amount), valuation_currency=donation.valuation_currency, valuation_method=donation.valuation_method, valuation_evidence=donation.valuation_evidence, external_reference=donation.external_reference)
    try:
        session.add(record); session.flush()
        if record.id is None: raise RuntimeError("InKindDonation identity was not assigned")
        result = replace(donation, id=record.id); session.commit(); return result
    except Exception:
        session.rollback(); raise
