"""Atomic confirmation of a user-classified operation backed by imported CFDI."""

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
import json
from uuid import uuid4

from sqlmodel import select

from . import accounting_operation as _operations
from . import accounting_operation_persistence as _persistence
from . import cfdi_source_repository as _sources
from . import donation_operations as _donations
from . import posting as _posting
from . import storage as _storage
from .banking_models import BankAccountRecord
from .cfdi_models import CfdiSourceLinkRecord, CfdiSourceRecord
from .economic_facts import EconomicFact
from .fund_models import FundRecord, FundingSourceRecord
from .models import AuditEventRecord, EntityRecord, ProgramRecord, ThirdPartyRecord


@dataclass(frozen=True)
class PreparedCfdiAccounting:
    source_id: int
    source_uuid: str
    source_hash: str
    operation_kind: str
    decision: object
    operation_id: str


@dataclass(frozen=True)
class PreparedCfdiMonetaryDonation:
    source_id: int
    source_uuid: str
    source_hash: str
    document_position: str
    payment_form: str | None
    donation: object
    operation_id: str


_KINDS = {
    "purchase_utility_bank": ("receiver", "03", "utility_expense", "bank"),
    "sale_cash": ("issuer", "01", "sale", "cash"),
}


def prepare_cfdi_accounting(session, source_id, operation_kind):
    if operation_kind not in _KINDS:
        raise ValueError("unsupported CFDI accounting operation kind")
    entity = session.exec(
        select(EntityRecord).where(EntityRecord.is_active.is_(True))
    ).one_or_none()
    if entity is None:
        raise LookupError("active Entity is required")
    source = _sources.load_cfdi_source(session, entity.id, source_id)
    expected_position, expected_payment_form, fact_type, payment_method = _KINDS[operation_kind]
    if source.document_position != expected_position:
        raise ValueError(
            "selected operation kind conflicts with CFDI document position"
        )
    if source.parsed.payment_form != expected_payment_form:
        raise ValueError("selected operation kind conflicts with CFDI FormaPago")
    decision = _operations.prepare_accounting_operation(
        session,
        EconomicFact(fact_type, source.parsed.total, payment_method),
        source.parsed.issued_at.date(),
    )
    return PreparedCfdiAccounting(
        source.id,
        source.parsed.uuid,
        source.parsed.sha256,
        operation_kind,
        decision,
        uuid4().hex,
    )


def confirm_cfdi_accounting(prepared):
    if not isinstance(prepared, PreparedCfdiAccounting):
        raise TypeError("prepared must be PreparedCfdiAccounting")
    confirmed = _operations.confirm_accounting_operation(prepared.decision)
    instruction = _posting.create_posting_instruction(confirmed.confirmed_proposal)
    with _storage.get_session() as session:
        events = session.exec(
            select(AuditEventRecord).where(AuditEventRecord.event_type == "entry_posted")
        ).all()
        for event in events:
            try:
                details = json.loads(event.details_json)
            except (TypeError, ValueError):
                continue
            if details.get("cfdi_operation_id") == prepared.operation_id:
                return details["cfdi_operation_result"]
        entity = session.exec(
            select(EntityRecord).where(EntityRecord.is_active.is_(True))
        ).one()
        source = session.get(CfdiSourceRecord, prepared.source_id)
        if source is None or source.entity_id != entity.id:
            raise LookupError("prepared CFDI source no longer belongs to active Entity")
        if source.uuid != prepared.source_uuid or source.file_hash != prepared.source_hash:
            raise ValueError("prepared CFDI source snapshot changed")
        try:
            result = _persistence.stage_posting_with_audit(
                session, instruction, confirmed
            )
            link = _sources.stage_cfdi_source_link(
                session, entity.id, source.id, result.entry_id
            )
            output = {
                "entry_id": result.entry_id,
                "audit_event_id": result.audit_event_id,
                "cfdi_source_id": source.id,
                "cfdi_source_link_id": link.id,
                "document_reference_id": link.document_reference_id,
            }
            audit = session.get(AuditEventRecord, result.audit_event_id)
            audit.details_json = json.dumps(
                {
                    **json.loads(audit.details_json),
                    "cfdi_operation_id": prepared.operation_id,
                    "cfdi_source_id": source.id,
                    "cfdi_uuid": source.uuid,
                    "cfdi_operation_result": output,
                },
                sort_keys=True,
            )
            session.add(audit)
            session.commit()
            return output
        except Exception:
            session.rollback()
            raise


def prepare_cfdi_monetary_donation(
    session,
    source_id,
    *,
    donor_third_party_id,
    bank_account_id,
    fund_id,
    funding_source_id,
    program_id,
    purpose,
    is_restricted,
):
    """Classify imported evidence explicitly and prepare the canonical AQR-009 flow."""
    entity = session.exec(
        select(EntityRecord).where(EntityRecord.is_active.is_(True))
    ).one_or_none()
    if entity is None:
        raise LookupError("active Entity is required")
    source = _sources.load_cfdi_source(session, entity.id, source_id)
    if source.document_position != "issuer":
        raise ValueError("bank donation requires Entity issuer document position")
    if source.parsed.payment_form != "03":
        raise ValueError("bank donation requires CFDI FormaPago 03")
    if source.third_party_id != donor_third_party_id:
        raise ValueError("selected donor differs from the RFC-identified counterparty")
    donor = session.get(ThirdPartyRecord, donor_third_party_id)
    if donor is None or donor.entity_id != entity.id or donor.is_active is not True:
        raise ValueError("selected donor does not belong to active Entity")
    bank = session.get(BankAccountRecord, bank_account_id)
    if bank is None or bank.entity_id != entity.id or bank.is_active is not True:
        raise ValueError("selected bank account does not belong to active Entity")
    fund = session.get(FundRecord, fund_id)
    if fund is None or fund.entity_id != entity.id:
        raise ValueError("fund does not belong to active Entity")
    funding_source = session.get(FundingSourceRecord, funding_source_id)
    if funding_source is None or funding_source.entity_id != entity.id:
        raise ValueError("funding source does not belong to active Entity")
    if funding_source.donor_third_party_id not in (None, donor.id):
        raise ValueError("funding source belongs to a different donor")
    program = session.get(ProgramRecord, program_id)
    if program is None or program.entity_id != entity.id:
        raise ValueError("program does not belong to active Entity")
    if fund.program_id not in (None, program.id):
        raise ValueError("fund does not allow the selected program")
    operation_id = uuid4().hex
    donation = _donations.prepare_monetary_donation(
        session,
        source.parsed.total,
        source.parsed.issued_at,
        donor_third_party_id=donor.id,
        document_type="cfdi",
        document_number=source.parsed.document_number,
        document_date=source.parsed.issued_at,
        fund_id=fund.id,
        funding_source_id=funding_source.id,
        program_id=program.id,
        purpose=purpose,
        is_restricted=is_restricted,
        bank_account_id=bank.id,
    )
    donation = replace(donation, operation_id=operation_id)
    return PreparedCfdiMonetaryDonation(
        source.id,
        source.parsed.uuid,
        source.parsed.sha256,
        source.document_position,
        source.parsed.payment_form,
        donation,
        operation_id,
    )


def _existing_cfdi_donation_result(session, operation_id):
    events = session.exec(
        select(AuditEventRecord).where(AuditEventRecord.event_type == "entry_posted")
    ).all()
    for event in events:
        try:
            details = json.loads(event.details_json)
        except (TypeError, ValueError):
            continue
        if details.get("cfdi_donation_operation_id") == operation_id:
            return details.get("cfdi_donation_operation_result")
    return None


def confirm_cfdi_monetary_donation(prepared):
    """Commit posting, Donation, OSC receipt and one CFDI document atomically."""
    if not isinstance(prepared, PreparedCfdiMonetaryDonation):
        raise TypeError("prepared must be PreparedCfdiMonetaryDonation")
    with _storage.get_session() as session:
        existing = _existing_cfdi_donation_result(session, prepared.operation_id)
        if existing is not None:
            return existing
        entity = session.exec(
            select(EntityRecord).where(EntityRecord.is_active.is_(True))
        ).one()
        source = session.get(CfdiSourceRecord, prepared.source_id)
        if source is None or source.entity_id != entity.id:
            raise LookupError("prepared CFDI source no longer belongs to active Entity")
        if (
            source.uuid != prepared.source_uuid
            or source.file_hash != prepared.source_hash
            or source.document_position != prepared.document_position
            or source.payment_form != prepared.payment_form
        ):
            raise ValueError("prepared CFDI source snapshot changed")
        if prepared.document_position != "issuer" or prepared.payment_form != "03":
            raise ValueError("prepared CFDI donation classification is incompatible")
        issued_at = datetime.fromisoformat(source.issued_at)
        if prepared.donation.donor_third_party_id != source.third_party_id:
            raise ValueError("prepared donor differs from the RFC-identified counterparty")
        if prepared.donation.decision.fact.type != "donation":
            raise ValueError("prepared classification is not a monetary donation")
        if prepared.donation.decision.fact.amount != Decimal(source.total):
            raise ValueError("prepared donation amount differs from CFDI evidence")
        if prepared.donation.decision.posting_date != issued_at.date():
            raise ValueError("prepared donation date differs from CFDI evidence")
        linked = session.exec(
            select(CfdiSourceLinkRecord).where(
                CfdiSourceLinkRecord.cfdi_source_id == source.id
            )
        ).one_or_none()
        if linked is not None:
            raise ValueError("CFDI source is already linked to another operation")
        try:
            result = _donations.stage_monetary_donation(
                session,
                prepared.donation,
                document_fields={
                    "issuer_name": source.issuer_name,
                    "file_hash": source.file_hash,
                    "file_path": None,
                    "external_url": None,
                    "is_validated": True,
                    "validation_notes": (
                        "CFDI 4.0 structure and extracted totals validated offline; "
                        "SAT status and specific tax treatment not determined."
                    ),
                },
            )
            link = _sources.stage_cfdi_source_link(
                session,
                entity.id,
                source.id,
                result["entry_id"],
                document_reference_id=result["document_reference_id"],
            )
            output = {
                **result,
                "cfdi_source_id": source.id,
                "cfdi_source_link_id": link.id,
            }
            audit = session.get(AuditEventRecord, result["audit_event_id"])
            audit.details_json = json.dumps(
                {
                    **json.loads(audit.details_json),
                    "cfdi_donation_operation_id": prepared.operation_id,
                    "cfdi_source_id": source.id,
                    "cfdi_uuid": source.uuid,
                    "cfdi_donation_operation_result": output,
                },
                sort_keys=True,
            )
            session.add(audit)
            session.commit()
            return output
        except Exception:
            session.rollback()
            raise


__all__ = [
    "PreparedCfdiAccounting",
    "PreparedCfdiMonetaryDonation",
    "prepare_cfdi_accounting",
    "confirm_cfdi_accounting",
    "prepare_cfdi_monetary_donation",
    "confirm_cfdi_monetary_donation",
]
