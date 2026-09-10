"""Persistence authority for non-cash donation evidence."""
from dataclasses import replace
from .inkind_donation import InKindDonation
from .models import InKindDonationRecord, EntityRecord, EntityProfileRecord, ThirdPartyRecord
from sqlmodel import select

def create_inkind_donation(session, donation):
    if not isinstance(donation, InKindDonation) or donation.id is not None: raise TypeError("new InKindDonation required")
    owner = session.get(EntityRecord, donation.entity_id)
    if owner is None or owner.is_active is not True: raise ValueError("InKindDonation owner Entity must be active")
    profile = session.exec(select(EntityProfileRecord).where(EntityProfileRecord.entity_id == donation.entity_id)).all()
    if len(profile) != 1 or "osc" not in __import__("json").loads(profile[0].special_capabilities_json): raise ValueError("InKindDonation owner must have osc capability")
    if donation.donor_third_party_id is not None:
        donor = session.get(ThirdPartyRecord, donation.donor_third_party_id)
        if donor is None or donor.entity_id != donation.entity_id: raise ValueError("donor must belong to the same Entity")
    record = InKindDonationRecord(entity_id=donation.entity_id, donor_third_party_id=donation.donor_third_party_id, document_reference_id=donation.document_reference_id, fund_id=donation.fund_id, program_id=donation.program_id, journal_line_id=donation.journal_line_id, received_at=donation.received_at.isoformat(), description=donation.description, quantity=None if donation.quantity is None else str(donation.quantity), valuation_amount=str(donation.valuation_amount), valuation_currency=donation.valuation_currency, valuation_method=donation.valuation_method, valuation_evidence=donation.valuation_evidence, external_reference=donation.external_reference)
    try:
        session.add(record); session.flush()
        if record.id is None: raise RuntimeError("InKindDonation identity was not assigned")
        result = replace(donation, id=record.id); session.commit(); return result
    except Exception:
        session.rollback(); raise
