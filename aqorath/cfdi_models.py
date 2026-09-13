"""Persistence records for independent external CFDI source evidence."""

from datetime import datetime, timezone
from typing import Optional

from aqorath import models as _core_models  # noqa: F401 - register FK target metadata
from sqlalchemy import Column, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


class CfdiSourceRecord(SQLModel, table=True):
    __tablename__ = "cfdisource"

    id: Optional[int] = Field(default=None, primary_key=True)
    entity_id: int = Field(sa_column=Column(Integer, ForeignKey("entity.id"), nullable=False, index=True))
    third_party_id: int = Field(sa_column=Column(Integer, ForeignKey("thirdparty.id"), nullable=False, index=True))
    document_position: str = Field(sa_column=Column(String, nullable=False, index=True))
    version: str = Field(sa_column=Column(String, nullable=False))
    uuid: str = Field(sa_column=Column(String, nullable=False, unique=True, index=True))
    voucher_type: str = Field(sa_column=Column(String, nullable=False))
    issuer_rfc: str = Field(sa_column=Column(String, nullable=False, index=True))
    issuer_name: str = Field(sa_column=Column(String, nullable=False))
    issuer_regime: str = Field(sa_column=Column(String, nullable=False))
    receiver_rfc: str = Field(sa_column=Column(String, nullable=False, index=True))
    receiver_name: str = Field(sa_column=Column(String, nullable=False))
    receiver_regime: str = Field(sa_column=Column(String, nullable=False))
    receiver_use: str = Field(sa_column=Column(String, nullable=False))
    issued_at: str = Field(sa_column=Column(String, nullable=False, index=True))
    stamped_at: str = Field(sa_column=Column(String, nullable=False))
    currency: str = Field(sa_column=Column(String, nullable=False))
    subtotal: str = Field(sa_column=Column(Text, nullable=False))
    discount: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    total: str = Field(sa_column=Column(Text, nullable=False))
    total_transferred: str = Field(sa_column=Column(Text, nullable=False))
    total_withheld: str = Field(sa_column=Column(Text, nullable=False))
    payment_form: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True))
    payment_method: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True))
    place_of_issue: str = Field(sa_column=Column(String, nullable=False))
    document_number: str = Field(sa_column=Column(String, nullable=False))
    sello_sat: str = Field(sa_column=Column(Text, nullable=False))
    sat_certificate_number: str = Field(sa_column=Column(String, nullable=False))
    file_hash: str = Field(sa_column=Column(String, nullable=False, unique=True, index=True))
    xml_bytes: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    imported_at: str = Field(sa_column=Column(String, nullable=False))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CfdiTaxEvidenceRecord(SQLModel, table=True):
    __tablename__ = "cfditaxevidence"
    __table_args__ = (
        UniqueConstraint("cfdi_source_id", "position", name="uq_cfdi_tax_source_position"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    cfdi_source_id: int = Field(sa_column=Column(Integer, ForeignKey("cfdisource.id"), nullable=False, index=True))
    position: int = Field(sa_column=Column(Integer, nullable=False))
    direction: str = Field(sa_column=Column(String, nullable=False))
    base: str = Field(sa_column=Column(Text, nullable=False))
    tax_code: str = Field(sa_column=Column(String, nullable=False))
    factor_type: str = Field(sa_column=Column(String, nullable=False))
    rate_or_quota: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    amount: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CfdiSourceLinkRecord(SQLModel, table=True):
    """One confirmed use of a source through the canonical DocumentReference."""

    __tablename__ = "cfdisourcelink"

    id: Optional[int] = Field(default=None, primary_key=True)
    cfdi_source_id: int = Field(
        sa_column=Column(Integer, ForeignKey("cfdisource.id"), nullable=False, unique=True, index=True)
    )
    document_reference_id: int = Field(
        sa_column=Column(Integer, ForeignKey("documentreference.id"), nullable=False, unique=True, index=True)
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


__all__ = ["CfdiSourceRecord", "CfdiTaxEvidenceRecord", "CfdiSourceLinkRecord"]
