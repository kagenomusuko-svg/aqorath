"""SQLModel metadata for external bank evidence and reconciliation relations."""
from datetime import datetime, timezone
from typing import Optional
from aqorath import models as _core_models  # noqa: F401 - register FK target metadata
from sqlalchemy import Column, String, Text, UniqueConstraint
from sqlmodel import Field, SQLModel

class BankAccountRecord(SQLModel, table=True):
    __tablename__ = "bankaccount"
    __table_args__ = (UniqueConstraint("entity_id", "account_identifier", name="uq_bank_account_identity"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    entity_id: int = Field(foreign_key="entity.id", index=True)
    ledger_account_id: int = Field(foreign_key="account.id", index=True)
    institution_name: str = Field(sa_column=Column(String, nullable=False))
    account_identifier: str = Field(sa_column=Column(String, nullable=False))
    currency: str = Field(sa_column=Column(String, nullable=False))
    is_active: bool = Field(default=True, nullable=False, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class BankStatementRecord(SQLModel, table=True):
    __tablename__ = "bankstatement"
    __table_args__ = (UniqueConstraint("bank_account_id", "source_hash", name="uq_bank_statement_source"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    bank_account_id: int = Field(foreign_key="bankaccount.id", index=True)
    source_hash: str = Field(sa_column=Column(String, nullable=False))
    source_name: str = Field(sa_column=Column(String, nullable=False))
    date_from: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True))
    date_to: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True))
    opening_balance: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    closing_balance: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    imported_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class BankTransactionRecord(SQLModel, table=True):
    __tablename__ = "banktransaction"
    __table_args__ = (UniqueConstraint("bank_account_id", "fingerprint", name="uq_bank_transaction_fingerprint"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    bank_account_id: int = Field(foreign_key="bankaccount.id", index=True)
    statement_id: int = Field(foreign_key="bankstatement.id", index=True)
    transaction_date: str = Field(sa_column=Column(String, nullable=False, index=True))
    reference: str = Field(sa_column=Column(Text, nullable=False))
    amount: str = Field(sa_column=Column(Text, nullable=False))
    fingerprint: str = Field(sa_column=Column(String, nullable=False))
    direction: str = Field(sa_column=Column(String, nullable=False))
    external_balance: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))

class ReconciliationRecord(SQLModel, table=True):
    __tablename__ = "reconciliation"
    id: Optional[int] = Field(default=None, primary_key=True)
    bank_account_id: int = Field(foreign_key="bankaccount.id", index=True)
    statement_id: int = Field(foreign_key="bankstatement.id", index=True)
    as_of: str = Field(sa_column=Column(String, nullable=False, index=True))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ReconciliationMatchRecord(SQLModel, table=True):
    __tablename__ = "reconciliationmatch"
    __table_args__ = (UniqueConstraint("bank_transaction_id", name="uq_reconciliation_match_bank"), UniqueConstraint("journal_line_id", name="uq_reconciliation_match_line"))
    id: Optional[int] = Field(default=None, primary_key=True)
    reconciliation_id: int = Field(foreign_key="reconciliation.id", index=True)
    bank_transaction_id: int = Field(foreign_key="banktransaction.id", index=True)
    journal_line_id: int = Field(foreign_key="journalline.id", index=True)
    matched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ReconciliationMatchRevocationRecord(SQLModel, table=True):
    __tablename__ = "reconciliationmatchrevocation"
    __table_args__ = (UniqueConstraint("match_id", name="uq_reconciliation_match_revocation"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    match_id: int = Field(foreign_key="reconciliationmatch.id", index=True)
    reason: str = Field(sa_column=Column(Text, nullable=False))
    revoked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

__all__ = ["BankAccountRecord", "BankStatementRecord", "BankTransactionRecord", "ReconciliationRecord", "ReconciliationMatchRecord", "ReconciliationMatchRevocationRecord"]
