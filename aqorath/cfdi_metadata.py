"""Immutable provenance values captured from an already imported CFDI."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID


def _require_positive_id(value, field_name, *, allow_none=False):
    if value is None and allow_none:
        return
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be a positive int")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


def _require_text(value, field_name):
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_datetime(value, field_name):
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")


def _require_uuid(value):
    _require_text(value, "uuid")
    if len(value) != 36 or tuple(value[index] for index in (8, 13, 18, 23)) != (
        "-",
        "-",
        "-",
        "-",
    ):
        raise ValueError("uuid must use the canonical hyphenated shape")
    try:
        UUID(value)
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError("uuid must be a valid UUID") from exc


@dataclass(frozen=True)
class CfdiImportMetadata:
    id: Optional[int]
    document_reference_id: int
    cfdi_version: str
    uuid: str
    issuer_rfc: str
    receiver_rfc: str
    issued_at: datetime
    stamped_at: datetime
    sello_sat: str
    sat_certificate_number: str
    imported_at: datetime

    def __post_init__(self):
        _require_positive_id(self.id, "id", allow_none=True)
        _require_positive_id(self.document_reference_id, "document_reference_id")
        _require_text(self.cfdi_version, "cfdi_version")
        _require_uuid(self.uuid)
        _require_text(self.issuer_rfc, "issuer_rfc")
        _require_text(self.receiver_rfc, "receiver_rfc")
        _require_datetime(self.issued_at, "issued_at")
        _require_datetime(self.stamped_at, "stamped_at")
        _require_text(self.sello_sat, "sello_sat")
        _require_text(self.sat_certificate_number, "sat_certificate_number")
        _require_datetime(self.imported_at, "imported_at")
