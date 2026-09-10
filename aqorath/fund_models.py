"""Schema 9 persistence for OSC fund traceability, never a monetary ledger."""
from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, ForeignKey, Index, Integer, String, Text, UniqueConstraint

class FundRecord(SQLModel, table=True):
    __tablename__ = "fund"; __table_args__ = (UniqueConstraint("entity_id", "code", name="uq_fund_entity_code"),)
    id: Optional[int] = Field(default=None, primary_key=True); entity_id: int = Field(sa_column=Column(Integer, ForeignKey("entity.id"), nullable=False, index=True)); code: str = Field(sa_column=Column(String, nullable=False)); name: str = Field(sa_column=Column(String, nullable=False)); restriction: str = Field(sa_column=Column(String, nullable=False)); purpose: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True)); program_id: Optional[int] = Field(default=None, sa_column=Column(Integer, ForeignKey("program.id"), nullable=True, index=True)); valid_from: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True)); valid_until: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True)); created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class FundingSourceRecord(SQLModel, table=True):
    __tablename__ = "fundingsource"; __table_args__ = (UniqueConstraint("entity_id", "name", name="uq_funding_source_entity_name"),)
    id: Optional[int] = Field(default=None, primary_key=True); entity_id: int = Field(sa_column=Column(Integer, ForeignKey("entity.id"), nullable=False, index=True)); name: str = Field(sa_column=Column(String, nullable=False)); donor_third_party_id: Optional[int] = Field(default=None, sa_column=Column(Integer, ForeignKey("thirdparty.id"), nullable=True, index=True)); external_reference: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True)); created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class FundReceiptRecord(SQLModel, table=True):
    __tablename__ = "fundreceipt"; __table_args__ = (UniqueConstraint("fund_id", "journal_line_id", name="uq_fund_receipt_line"),)
    id: Optional[int] = Field(default=None, primary_key=True); entity_id: int = Field(sa_column=Column(Integer, ForeignKey("entity.id"), nullable=False, index=True)); fund_id: int = Field(sa_column=Column(Integer, ForeignKey("fund.id"), nullable=False, index=True)); funding_source_id: int = Field(sa_column=Column(Integer, ForeignKey("fundingsource.id"), nullable=False, index=True)); journal_line_id: int = Field(sa_column=Column(Integer, ForeignKey("journalline.id"), nullable=False, index=True)); donation_id: Optional[int] = Field(default=None, sa_column=Column(Integer, ForeignKey("donation.id"), nullable=True, index=True)); amount: str = Field(sa_column=Column(Text, nullable=False)); received_at: str = Field(sa_column=Column(String, nullable=False, index=True)); created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class FundApplicationRecord(SQLModel, table=True):
    __tablename__ = "fundapplication"; __table_args__ = (Index("ix_fund_application_line", "journal_line_id"),)
    id: Optional[int] = Field(default=None, primary_key=True); entity_id: int = Field(sa_column=Column(Integer, ForeignKey("entity.id"), nullable=False, index=True)); fund_id: int = Field(sa_column=Column(Integer, ForeignKey("fund.id"), nullable=False, index=True)); program_id: int = Field(sa_column=Column(Integer, ForeignKey("program.id"), nullable=False, index=True)); journal_line_id: int = Field(sa_column=Column(Integer, ForeignKey("journalline.id"), nullable=False, index=True)); receipt_id: Optional[int] = Field(default=None, sa_column=Column(Integer, ForeignKey("fundreceipt.id"), nullable=True, index=True)); amount: str = Field(sa_column=Column(Text, nullable=False)); applied_at: str = Field(sa_column=Column(String, nullable=False, index=True)); purpose: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True)); created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
