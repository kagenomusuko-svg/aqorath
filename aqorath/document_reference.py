"""Pure structured source-document reference domain."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


def _require_positive_int(value, field_name):
    if type(value) is not int:
        raise TypeError(f"{field_name} must be int")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


def _require_text(value, field_name):
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be nonempty")


def _optional_text(value, field_name):
    if value is None:
        return
    _require_text(value, field_name)


@dataclass(frozen=True)
class DocumentReference:
    """Immutable metadata pointing to one source document for one JournalEntry."""

    id: Optional[int]
    entry_id: int
    third_party_id: Optional[int]
    document_type: str
    document_number: str
    issuer_name: Optional[str]
    date: datetime
    file_hash: Optional[str]
    file_path: Optional[str]
    external_url: Optional[str]
    is_validated: bool
    validation_notes: Optional[str]

    def __post_init__(self):
        if self.id is not None:
            _require_positive_int(self.id, "id")
        _require_positive_int(self.entry_id, "entry_id")
        if self.third_party_id is not None:
            _require_positive_int(self.third_party_id, "third_party_id")

        _require_text(self.document_type, "document_type")
        _require_text(self.document_number, "document_number")
        _optional_text(self.issuer_name, "issuer_name")
        _optional_text(self.file_path, "file_path")
        _optional_text(self.external_url, "external_url")
        _optional_text(self.validation_notes, "validation_notes")

        if not isinstance(self.date, datetime):
            raise TypeError("date must be datetime")
        if type(self.is_validated) is not bool:
            raise TypeError("is_validated must be bool")

        if self.file_hash is not None:
            if not isinstance(self.file_hash, str):
                raise TypeError("file_hash must be str or None")
            if len(self.file_hash) != 64:
                raise ValueError("file_hash must contain exactly 64 hexadecimal characters")
            if not all(
                character in "0123456789abcdefABCDEF"
                for character in self.file_hash
            ):
                raise ValueError("file_hash must be hexadecimal")
