from dataclasses import replace
from datetime import datetime

from sqlmodel import select

from .cfdi_metadata import CfdiImportMetadata
from .models import CfdiImportMetadataRecord, DocumentReferenceRecord


def _require_positive_id(value, field_name):
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be a positive int")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


def _from_record(record):
    return CfdiImportMetadata(
        id=record.id,
        document_reference_id=record.document_reference_id,
        cfdi_version=record.cfdi_version,
        uuid=record.uuid,
        issuer_rfc=record.issuer_rfc,
        receiver_rfc=record.receiver_rfc,
        issued_at=datetime.fromisoformat(record.issued_at),
        stamped_at=datetime.fromisoformat(record.stamped_at),
        sello_sat=record.sello_sat,
        sat_certificate_number=record.sat_certificate_number,
        imported_at=datetime.fromisoformat(record.imported_at),
    )


def _require_cfdi_document(session, document_reference_id):
    _require_positive_id(document_reference_id, "document_reference_id")
    document = session.get(DocumentReferenceRecord, document_reference_id)
    if document is None:
        raise LookupError(
            f"DocumentReference id={document_reference_id} does not exist"
        )
    if document.document_type != "cfdi":
        raise ValueError("DocumentReference document_type must be 'cfdi'")
    return document


def register_cfdi_import_metadata(session, metadata):
    if not isinstance(metadata, CfdiImportMetadata):
        raise TypeError("metadata must be CfdiImportMetadata")
    if metadata.id is not None:
        raise ValueError("new CFDI metadata must not already have id")

    _require_cfdi_document(session, metadata.document_reference_id)
    record = CfdiImportMetadataRecord(
        document_reference_id=metadata.document_reference_id,
        cfdi_version=metadata.cfdi_version,
        uuid=metadata.uuid,
        issuer_rfc=metadata.issuer_rfc,
        receiver_rfc=metadata.receiver_rfc,
        issued_at=metadata.issued_at.isoformat(),
        stamped_at=metadata.stamped_at.isoformat(),
        sello_sat=metadata.sello_sat,
        sat_certificate_number=metadata.sat_certificate_number,
        imported_at=metadata.imported_at.isoformat(),
    )
    try:
        session.add(record)
        session.flush()
        if record.id is None:
            raise RuntimeError("CFDI metadata identity was not assigned")
        persisted_id = record.id
        session.commit()
    except Exception:
        session.rollback()
        raise
    return replace(metadata, id=persisted_id)


def get_cfdi_import_metadata(session, document_reference_id):
    _require_positive_id(document_reference_id, "document_reference_id")
    record = session.exec(
        select(CfdiImportMetadataRecord).where(
            CfdiImportMetadataRecord.document_reference_id == document_reference_id
        )
    ).one_or_none()
    if record is None:
        raise LookupError(
            f"CFDI metadata for DocumentReference id={document_reference_id} does not exist"
        )
    return _from_record(record)
