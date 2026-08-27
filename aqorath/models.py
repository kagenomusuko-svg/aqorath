from datetime import date, datetime, timezone
from typing import Optional

from sqlmodel import SQLModel, Field
from sqlalchemy import Column, String, Boolean, UniqueConstraint, Integer, ForeignKey


class Account(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    # columna con UNIQUE para prevenir duplicados
    code: str = Field(sa_column=Column(String, unique=True))
    name: str
    nature: str
    vat_flag: bool = Field(default=False)  # indica si la cuenta es afectable por IVA
    # P1-3: origin distingue cuentas canónicas de extensiones de entidad
    origin: str = Field(default="canonical")  # "canonical" | "entity"
    # P1-3: parent_id vincula extensión de entidad a su cuenta canónica padre
    parent_id: Optional[int] = Field(default=None, foreign_key="account.id", index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AccountRoleBinding(SQLModel, table=True):
    """Persistent role -> Account identity binding for the current entity database."""

    id: Optional[int] = Field(default=None, primary_key=True)
    role: str = Field(sa_column=Column(String, unique=True, nullable=False))
    account_id: int = Field(foreign_key="account.id", index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FiscalRuleVersion(SQLModel, table=True):
    """One exact, effective-dated fiscal rule record for one explicit context."""

    __table_args__ = (
        UniqueConstraint(
            "rule_key",
            "jurisdiction",
            "regime",
            "entity_type",
            "effective_from",
            name="uq_fiscal_rule_scope_start",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    rule_key: str = Field(index=True)
    jurisdiction: str = Field(index=True)
    regime: str = Field(index=True)
    entity_type: str = Field(index=True)
    effective_from: date = Field(index=True)
    effective_to: Optional[date] = Field(default=None, index=True)
    value: str
    unit: str
    source_ref: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AppConfig(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    key: str
    value: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class JournalEntry(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    date: datetime
    concept: Optional[str] = None
    doc_ref: Optional[str] = None
    period_id: Optional[int] = None
    posted_by: Optional[str] = None
    state: str = "draft"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class JournalLine(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    entry_id: Optional[int] = Field(default=None)
    # Guardamos el código de cuenta siempre (clave en el catálogo)
    account_code: Optional[str] = Field(default=None)
    # P0-4: account_id es Optional en schema para compatibilidad, pero toda JournalLine
    # persistida por la aplicación DEBE resolver una Account existente.
    # _verify_accounts() y _persist_entry() garantizan que nunca se persiste sin una Account válida.
    account_id: Optional[int] = Field(default=None)
    # P0-2: Changed from float to str to preserve exact Decimal representation.
    # Values are stored as string representation of Decimal to avoid float precision loss.
    # Reading code must convert str -> Decimal for calculations.
    debit: str = "0"
    credit: str = "0"
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FiscalPostingAuditRecord(SQLModel, table=True):
    """Persisted fiscal provenance metadata linked one-to-one to a JournalEntry.

    This table is audit metadata only. Positive debit/credit lines remain exclusively
    in JournalLine; the confirmed explanation remains in JournalEntry.concept.
    Decimal-valued provenance is stored as exact text.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    entry_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("journalentry.id"),
            unique=True,
            nullable=False,
            index=True,
        )
    )
    fact_type: str
    fact_amount: str
    payment_method: str
    effective_date: date
    jurisdiction: str
    regime: str
    entity_type: str
    rule_key: str
    base: str
    rate: str
    unit: str
    rule_effective_from: date
    rule_effective_to: Optional[date] = None
    rule_source_ref: str
    exact_fiscal_amount: str
    rounding_policy_key: str
    rounding_quantizer: str
    rounding_mode: str
    rounding_source_ref: str
    rounded_fiscal_amount: str
    amount_basis: str
    adjustment_role: str
    fiscal_role: str
    fiscal_side: str
    zero_fiscal_line_policy: str
    omitted_zero_account_role: Optional[str] = None
    omitted_zero_account_id: Optional[int] = None
    omitted_zero_account_code: Optional[str] = None
    omitted_zero_account_name: Optional[str] = None
    omitted_zero_side: Optional[str] = None
    omitted_zero_amount: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FiscalPostingAuditEffectRecord(SQLModel, table=True):
    """Ordered persisted provenance for fiscal effects after the primary v4 effect."""

    __table_args__ = (
        UniqueConstraint(
            "audit_record_id",
            "position",
            name="uq_fiscal_posting_audit_effect_position",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    audit_record_id: int = Field(
        foreign_key="fiscalpostingauditrecord.id",
        index=True,
    )
    position: int = Field(index=True)
    rule_key: str
    base: str
    rate: str
    unit: str
    rule_effective_from: date
    rule_effective_to: Optional[date] = None
    rule_source_ref: str
    exact_fiscal_amount: str
    rounding_policy_key: str
    rounding_quantizer: str
    rounding_mode: str
    rounding_source_ref: str
    rounded_fiscal_amount: str
    fiscal_role: str
    fiscal_side: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Asset(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    # P0-2: Changed from float to str to preserve exact Decimal representation.
    value: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))