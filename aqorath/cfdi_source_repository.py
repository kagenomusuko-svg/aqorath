"""Atomic persistence authority for external CFDI evidence before posting."""

from datetime import datetime, timezone
from decimal import Decimal
import json

from sqlmodel import select

from . import audit_event_repository as _audit_events
from .audit_event import AuditEvent
from .cfdi_models import CfdiSourceLinkRecord, CfdiSourceRecord, CfdiTaxEvidenceRecord
from .cfdi_source import (
    CfdiImportResult,
    CfdiSourceEvidence,
    CfdiTaxEvidence,
    ParsedCfdi,
    parse_cfdi_xml,
)
from .cfdi_metadata import CfdiImportMetadata
from . import cfdi_metadata_repository as _metadata
from .document_reference import DocumentReference
from . import document_reference_repository as _documents
from .models import (
    AuditEventRecord,
    DocumentReferenceRecord,
    EntityRecord,
    JournalEntry,
    JournalLine,
    ThirdPartyRecord,
)


def _active_entity(session):
    rows = session.exec(select(EntityRecord).where(EntityRecord.is_active.is_(True))).all()
    if len(rows) != 1:
        raise LookupError("exactly one active Entity is required")
    entity = rows[0]
    if not entity.rfc or not entity.rfc.strip():
        raise ValueError("active Entity RFC is required for CFDI relationship")
    return entity


def _relationship_and_party(session, entity, parsed):
    entity_rfc = entity.rfc.strip().upper()
    is_issuer = parsed.issuer_rfc == entity_rfc
    is_receiver = parsed.receiver_rfc == entity_rfc
    if is_issuer == is_receiver:
        raise ValueError("active Entity must be issuer or receiver, but not both")
    relationship = "sale" if is_issuer else "purchase"
    counterparty_rfc = parsed.receiver_rfc if is_issuer else parsed.issuer_rfc
    rows = session.exec(
        select(ThirdPartyRecord).where(
            ThirdPartyRecord.entity_id == entity.id,
            ThirdPartyRecord.is_active.is_(True),
        )
    ).all()
    matches = [row for row in rows if row.rfc and row.rfc.strip().upper() == counterparty_rfc]
    if len(matches) != 1:
        raise LookupError("counterparty RFC must identify exactly one active ThirdParty")
    return relationship, matches[0]


def _parsed_from_rows(source, tax_rows):
    taxes = tuple(
        CfdiTaxEvidence(
            direction=row.direction,
            base=Decimal(row.base),
            tax_code=row.tax_code,
            factor_type=row.factor_type,
            rate_or_quota=None if row.rate_or_quota is None else Decimal(row.rate_or_quota),
            amount=None if row.amount is None else Decimal(row.amount),
        )
        for row in tax_rows
    )
    return ParsedCfdi(
        version=source.version, uuid=source.uuid, voucher_type=source.voucher_type,
        issuer_rfc=source.issuer_rfc, issuer_name=source.issuer_name, issuer_regime=source.issuer_regime,
        receiver_rfc=source.receiver_rfc, receiver_name=source.receiver_name, receiver_regime=source.receiver_regime,
        receiver_use=source.receiver_use, issued_at=datetime.fromisoformat(source.issued_at),
        stamped_at=datetime.fromisoformat(source.stamped_at), currency=source.currency,
        subtotal=Decimal(source.subtotal), discount=None if source.discount is None else Decimal(source.discount),
        total=Decimal(source.total), total_transferred=Decimal(source.total_transferred),
        total_withheld=Decimal(source.total_withheld), payment_form=source.payment_form,
        payment_method=source.payment_method, place_of_issue=source.place_of_issue,
        document_number=source.document_number, sello_sat=source.sello_sat,
        sat_certificate_number=source.sat_certificate_number, taxes=taxes,
        sha256=source.file_hash, xml_bytes=bytes(source.xml_bytes),
    )


def _from_record(session, source):
    taxes = session.exec(
        select(CfdiTaxEvidenceRecord)
        .where(CfdiTaxEvidenceRecord.cfdi_source_id == source.id)
        .order_by(CfdiTaxEvidenceRecord.position)
    ).all()
    return CfdiSourceEvidence(
        id=source.id,
        entity_id=source.entity_id,
        third_party_id=source.third_party_id,
        relationship=source.relationship,
        parsed=_parsed_from_rows(source, taxes),
        imported_at=datetime.fromisoformat(source.imported_at),
    )


def import_cfdi_source(session, xml_bytes, *, imported_at=None):
    """Persist one parsed source and audit atomically; exact repeats are idempotent."""
    parsed = parse_cfdi_xml(xml_bytes)
    entity = _active_entity(session)
    relationship, party = _relationship_and_party(session, entity, parsed)
    existing = session.exec(select(CfdiSourceRecord).where(CfdiSourceRecord.uuid == parsed.uuid)).one_or_none()
    if existing is not None:
        if existing.file_hash != parsed.sha256 or bytes(existing.xml_bytes) != parsed.xml_bytes:
            raise ValueError("CFDI UUID already exists with different XML evidence")
        return CfdiImportResult(_from_record(session, existing), True)
    hash_owner = session.exec(select(CfdiSourceRecord).where(CfdiSourceRecord.file_hash == parsed.sha256)).one_or_none()
    if hash_owner is not None:
        raise ValueError("CFDI XML file hash already belongs to another UUID")
    if imported_at is None:
        imported_at = datetime.now(timezone.utc)
    if type(imported_at) is not datetime:
        raise TypeError("imported_at must be datetime")

    row = CfdiSourceRecord(
        entity_id=entity.id, third_party_id=party.id, relationship=relationship,
        version=parsed.version, uuid=parsed.uuid, voucher_type=parsed.voucher_type,
        issuer_rfc=parsed.issuer_rfc, issuer_name=parsed.issuer_name, issuer_regime=parsed.issuer_regime,
        receiver_rfc=parsed.receiver_rfc, receiver_name=parsed.receiver_name, receiver_regime=parsed.receiver_regime,
        receiver_use=parsed.receiver_use, issued_at=parsed.issued_at.isoformat(), stamped_at=parsed.stamped_at.isoformat(),
        currency=parsed.currency, subtotal=str(parsed.subtotal), discount=None if parsed.discount is None else str(parsed.discount),
        total=str(parsed.total), total_transferred=str(parsed.total_transferred), total_withheld=str(parsed.total_withheld),
        payment_form=parsed.payment_form, payment_method=parsed.payment_method, place_of_issue=parsed.place_of_issue,
        document_number=parsed.document_number, sello_sat=parsed.sello_sat,
        sat_certificate_number=parsed.sat_certificate_number, file_hash=parsed.sha256,
        xml_bytes=parsed.xml_bytes, imported_at=imported_at.isoformat(),
    )
    try:
        session.add(row)
        session.flush()
        if row.id is None:
            raise RuntimeError("CFDI source identity was not assigned")
        for position, tax in enumerate(parsed.taxes):
            session.add(CfdiTaxEvidenceRecord(
                cfdi_source_id=row.id, position=position, direction=tax.direction,
                base=str(tax.base), tax_code=tax.tax_code, factor_type=tax.factor_type,
                rate_or_quota=None if tax.rate_or_quota is None else str(tax.rate_or_quota),
                amount=None if tax.amount is None else str(tax.amount),
            ))
        session.flush()
        _audit_events.stage_audit_event(session, AuditEvent(
            None, entity.id, "cfdi_source_imported", imported_at,
            {"cfdi_source_id": row.id, "uuid": parsed.uuid, "file_hash": parsed.sha256,
             "relationship": relationship, "third_party_id": party.id},
        ))
        session.commit()
    except Exception:
        session.rollback()
        raise
    return CfdiImportResult(_from_record(session, row), False)


def load_cfdi_source(session, entity_id, source_id):
    if type(entity_id) is not int or entity_id <= 0 or type(source_id) is not int or source_id <= 0:
        raise ValueError("entity_id and source_id must be positive ints")
    row = session.get(CfdiSourceRecord, source_id)
    if row is None or row.entity_id != entity_id:
        raise LookupError("CFDI source not found for Entity")
    return _from_record(session, row)


def _entry_owner(session, entry_id):
    events = session.exec(
        select(AuditEventRecord).where(AuditEventRecord.event_type == "entry_posted")
    ).all()
    owners = []
    for event in events:
        try:
            details = json.loads(event.details_json)
        except (TypeError, ValueError):
            continue
        if details.get("entry_id") == entry_id:
            owners.append(event.entity_id)
    if len(owners) != 1:
        raise ValueError("JournalEntry must have exactly one canonical posting audit")
    return owners[0]


def stage_cfdi_source_link(session, entity_id, source_id, entry_id, *, linked_at=None):
    """Stage source→document/metadata linkage inside a caller-owned transaction."""
    source = session.get(CfdiSourceRecord, source_id)
    if source is None or source.entity_id != entity_id:
        raise LookupError("CFDI source not found for Entity")
    entry = session.get(JournalEntry, entry_id)
    if entry is None or entry.state != "posted":
        raise ValueError("CFDI source requires a posted JournalEntry")
    if _entry_owner(session, entry_id) != entity_id:
        raise ValueError("CFDI source and JournalEntry must belong to the same Entity")
    if entry.date.date() != datetime.fromisoformat(source.issued_at).date():
        raise ValueError("CFDI issue date differs from JournalEntry date")
    lines = session.exec(select(JournalLine).where(JournalLine.entry_id == entry_id)).all()
    debit_total = sum((Decimal(line.debit) for line in lines), Decimal("0"))
    if debit_total != Decimal(source.total):
        raise ValueError("CFDI total differs from canonical JournalLine debit total")
    existing = session.exec(
        select(CfdiSourceLinkRecord).where(CfdiSourceLinkRecord.cfdi_source_id == source_id)
    ).one_or_none()
    if existing is not None:
        document = session.get(DocumentReferenceRecord, existing.document_reference_id)
        if document is not None and document.entry_id == entry_id:
            return existing
        raise ValueError("CFDI source is already linked to another operation")
    if linked_at is None:
        linked_at = datetime.now(timezone.utc)
    document = _documents.stage_document_reference(session, DocumentReference(
        id=None, entry_id=entry_id, third_party_id=source.third_party_id,
        document_type="cfdi", document_number=source.document_number,
        issuer_name=source.issuer_name, date=datetime.fromisoformat(source.issued_at),
        file_hash=source.file_hash, file_path=None, external_url=None,
        is_validated=True,
        validation_notes="CFDI 4.0 structure and extracted totals validated offline; SAT status not consulted.",
    ))
    _metadata.stage_cfdi_import_metadata(session, CfdiImportMetadata(
        id=None, document_reference_id=document.id, cfdi_version=source.version,
        uuid=source.uuid, issuer_rfc=source.issuer_rfc, receiver_rfc=source.receiver_rfc,
        issued_at=datetime.fromisoformat(source.issued_at),
        stamped_at=datetime.fromisoformat(source.stamped_at), sello_sat=source.sello_sat,
        sat_certificate_number=source.sat_certificate_number,
        imported_at=datetime.fromisoformat(source.imported_at),
    ))
    link = CfdiSourceLinkRecord(cfdi_source_id=source_id, document_reference_id=document.id)
    session.add(link)
    session.flush()
    _audit_events.stage_audit_event(session, AuditEvent(
        None, entity_id, "cfdi_source_linked", linked_at,
        {"cfdi_source_id": source_id, "document_reference_id": document.id,
         "entry_id": entry_id, "uuid": source.uuid},
    ))
    session.flush()
    return link


def link_cfdi_source_to_entry(session, entity_id, source_id, entry_id, *, linked_at=None):
    try:
        result = stage_cfdi_source_link(
            session, entity_id, source_id, entry_id, linked_at=linked_at
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    return result


__all__ = [
    "import_cfdi_source",
    "load_cfdi_source",
    "stage_cfdi_source_link",
    "link_cfdi_source_to_entry",
]
