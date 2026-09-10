"""SQLite persistence authority for structured source-document references."""

from dataclasses import replace
from datetime import datetime

from sqlmodel import select

from .document_reference import DocumentReference
from .models import DocumentReferenceRecord, JournalEntry, ThirdPartyRecord


def _require_positive_id(value, field_name):
    if type(value) is not int:
        raise TypeError(f"{field_name} must be int")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


def _from_record(record):
    return DocumentReference(
        id=record.id,
        entry_id=record.entry_id,
        third_party_id=record.third_party_id,
        document_type=record.document_type,
        document_number=record.document_number,
        issuer_name=record.issuer_name,
        date=datetime.fromisoformat(record.date),
        file_hash=record.file_hash,
        file_path=record.file_path,
        external_url=record.external_url,
        is_validated=record.is_validated,
        validation_notes=record.validation_notes,
    )


def _require_entry(session, entry_id):
    _require_positive_id(entry_id, "entry_id")
    entry = session.get(JournalEntry, entry_id)
    if entry is None:
        raise LookupError(f"JournalEntry {entry_id} not found")
    return entry


def stage_document_reference(session, document_reference):
    """Stage one source reference inside the caller's transaction without commit."""
    if not isinstance(document_reference, DocumentReference):
        raise TypeError("document_reference must be DocumentReference")
    if document_reference.id is not None:
        raise ValueError("new DocumentReference id must be None")

    _require_entry(session, document_reference.entry_id)
    if document_reference.third_party_id is not None:
        third_party = session.get(
            ThirdPartyRecord,
            document_reference.third_party_id,
        )
        if third_party is None:
            raise LookupError(
                f"ThirdParty {document_reference.third_party_id} not found"
            )

    record = DocumentReferenceRecord(
        entry_id=document_reference.entry_id,
        third_party_id=document_reference.third_party_id,
        document_type=document_reference.document_type,
        document_number=document_reference.document_number,
        issuer_name=document_reference.issuer_name,
        date=document_reference.date.isoformat(),
        file_hash=document_reference.file_hash,
        file_path=document_reference.file_path,
        external_url=document_reference.external_url,
        is_validated=document_reference.is_validated,
        validation_notes=document_reference.validation_notes,
    )
    session.add(record)
    session.flush()
    if record.id is None:
        raise RuntimeError("DocumentReference persistence did not assign identity")
    return replace(document_reference, id=record.id)


def create_document_reference(session, document_reference):
    """Persist one explicit source-document reference for an existing entry."""
    try:
        result = stage_document_reference(session, document_reference)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return result


def get_document_reference(session, document_reference_id):
    """Load one persisted DocumentReference by identity."""
    _require_positive_id(document_reference_id, "document_reference_id")
    record = session.get(DocumentReferenceRecord, document_reference_id)
    if record is None:
        raise LookupError(f"DocumentReference {document_reference_id} not found")
    return _from_record(record)


def list_document_references(session, entry_id):
    """Return deterministic structured source evidence for one existing entry."""
    _require_entry(session, entry_id)
    rows = session.exec(
        select(DocumentReferenceRecord)
        .where(DocumentReferenceRecord.entry_id == entry_id)
        .order_by(DocumentReferenceRecord.id)
    ).all()
    return tuple(_from_record(record) for record in rows)


__all__ = [
    "stage_document_reference",
    "create_document_reference",
    "get_document_reference",
    "list_document_references",
]
