from datetime import date, datetime, timezone
from typing import Optional

from sqlmodel import SQLModel, Field
from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)


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


class EntityRecord(SQLModel, table=True):
    """Persisted legal/economic identity for the local accounting entity."""

    __tablename__ = "entity"
    __table_args__ = (
        Index(
            "uq_entity_single_active",
            "is_active",
            unique=True,
            sqlite_where=text("is_active = 1"),
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(sa_column=Column(String, nullable=False))
    rfc: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True))
    legal_personality: str = Field(sa_column=Column(String, nullable=False))
    legal_form: str = Field(sa_column=Column(String, nullable=False))
    is_active: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False),
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FixedAssetRecord(SQLModel, table=True):
    """Persisted canonical fixed-asset registry metadata owned by one Entity."""

    __tablename__ = "fixedasset"
    __table_args__ = (
        UniqueConstraint(
            "entity_id",
            "code",
            name="uq_fixed_asset_entity_code",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    entity_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("entity.id"),
            nullable=False,
            index=True,
        )
    )
    code: str = Field(sa_column=Column(String, nullable=False))
    name: str = Field(sa_column=Column(String, nullable=False))
    acquisition_date: date = Field(index=True)
    in_service_date: date = Field(index=True)
    acquisition_cost: str = Field(sa_column=Column(Text, nullable=False))
    residual_value: str = Field(sa_column=Column(Text, nullable=False))
    useful_life_months: int = Field(sa_column=Column(Integer, nullable=False))
    depreciation_method: str = Field(sa_column=Column(String, nullable=False))
    is_active: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, index=True),
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AnalyticalDimensionRecord(SQLModel, table=True):
    """Persisted analytical axis owned by one Entity."""

    __tablename__ = "analyticaldimension"
    __table_args__ = (
        UniqueConstraint(
            "entity_id",
            "key",
            name="uq_analytical_dimension_entity_key",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    entity_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("entity.id"),
            nullable=False,
            index=True,
        )
    )
    key: str = Field(sa_column=Column(String, nullable=False))
    name: str = Field(sa_column=Column(String, nullable=False))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AnalyticalDimensionValueRecord(SQLModel, table=True):
    """Persisted value belonging to one analytical axis."""

    __tablename__ = "analyticaldimensionvalue"
    __table_args__ = (
        UniqueConstraint(
            "dimension_id",
            "code",
            name="uq_analytical_dimension_value_code",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    dimension_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("analyticaldimension.id"),
            nullable=False,
            index=True,
        )
    )
    code: str = Field(sa_column=Column(String, nullable=False))
    name: str = Field(sa_column=Column(String, nullable=False))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EntityProfileRecord(SQLModel, table=True):
    """One persisted compositional profile for one Entity."""

    __tablename__ = "entityprofile"

    id: Optional[int] = Field(default=None, primary_key=True)
    entity_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("entity.id"),
            unique=True,
            nullable=False,
            index=True,
        )
    )
    economic_purpose: str = Field(sa_column=Column(String, nullable=False))
    is_donor_authorized: bool = Field(sa_column=Column(Boolean, nullable=False))
    special_capabilities_json: str = Field(sa_column=Column(Text, nullable=False))
    modules_enabled_json: str = Field(sa_column=Column(Text, nullable=False))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FiscalProfileRecord(SQLModel, table=True):
    """Persisted effective-dated fiscal profile history for one Entity."""

    __tablename__ = "fiscalprofile"
    __table_args__ = (
        UniqueConstraint(
            "entity_id",
            "effective_from",
            name="uq_fiscal_profile_entity_start",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    entity_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("entity.id"),
            nullable=False,
            index=True,
        )
    )
    jurisdiction: str = Field(sa_column=Column(String, nullable=False))
    fiscal_regime_code: str = Field(sa_column=Column(String, nullable=False))
    tax_characteristics_json: str = Field(sa_column=Column(Text, nullable=False))
    effective_from: date = Field(index=True)
    effective_to: Optional[date] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ThirdPartyRecord(SQLModel, table=True):
    """Persisted counterparty identity owned by one accounting Entity."""

    __tablename__ = "thirdparty"

    id: Optional[int] = Field(default=None, primary_key=True)
    entity_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("entity.id"),
            nullable=False,
            index=True,
        )
    )
    name: str = Field(sa_column=Column(String, nullable=False))
    rfc: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True))
    email: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True))
    phone: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True))
    party_type: str = Field(sa_column=Column(String, nullable=False, index=True))
    address: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True))
    contact_person: Optional[str] = Field(
        default=None,
        sa_column=Column(String, nullable=True),
    )
    notes: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    is_active: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, index=True),
    )
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


class FixedAssetDepreciationPostingRecord(SQLModel, table=True):
    """One-use persisted identity for one fixed-asset depreciation period."""

    __tablename__ = "fixedassetdepreciationpostingrecord"
    __table_args__ = (
        UniqueConstraint(
            "fixed_asset_id",
            "period_number",
            name="uq_fixed_asset_depreciation_period",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    fixed_asset_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("fixedasset.id"),
            nullable=False,
            index=True,
        )
    )
    period_number: int = Field(sa_column=Column(Integer, nullable=False))
    entry_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("journalentry.id"),
            nullable=False,
            index=True,
        )
    )
    recognition_source_ref: str = Field(sa_column=Column(String, nullable=False))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DocumentReferenceRecord(SQLModel, table=True):
    """Structured source-document metadata linked to one JournalEntry."""

    __tablename__ = "documentreference"

    id: Optional[int] = Field(default=None, primary_key=True)
    entry_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("journalentry.id"),
            nullable=False,
            index=True,
        )
    )
    third_party_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            Integer,
            ForeignKey("thirdparty.id"),
            nullable=True,
            index=True,
        ),
    )
    document_type: str = Field(
        sa_column=Column(String, nullable=False, index=True)
    )
    document_number: str = Field(sa_column=Column(String, nullable=False))
    issuer_name: Optional[str] = Field(
        default=None,
        sa_column=Column(String, nullable=True),
    )
    date: str = Field(sa_column=Column(String, nullable=False, index=True))
    file_hash: Optional[str] = Field(
        default=None,
        sa_column=Column(String, nullable=True),
    )
    file_path: Optional[str] = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    external_url: Optional[str] = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    is_validated: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, index=True),
    )
    validation_notes: Optional[str] = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CfdiImportMetadataRecord(SQLModel, table=True):
    """Stamped CFDI provenance linked one-to-one to a DocumentReference."""

    __tablename__ = "cfdiimportmetadata"

    id: Optional[int] = Field(default=None, primary_key=True)
    document_reference_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("documentreference.id"),
            unique=True,
            nullable=False,
            index=True,
        )
    )
    cfdi_version: str = Field(sa_column=Column(String, nullable=False))
    uuid: str = Field(
        sa_column=Column(String, unique=True, nullable=False, index=True)
    )
    issuer_rfc: str = Field(sa_column=Column(String, nullable=False))
    receiver_rfc: str = Field(sa_column=Column(String, nullable=False))
    issued_at: str = Field(sa_column=Column(String, nullable=False))
    stamped_at: str = Field(sa_column=Column(String, nullable=False))
    sello_sat: str = Field(sa_column=Column(Text, nullable=False))
    sat_certificate_number: str = Field(sa_column=Column(String, nullable=False))
    imported_at: str = Field(sa_column=Column(String, nullable=False))
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


class JournalLineAnalyticalDimensionRecord(SQLModel, table=True):
    """One analytical value assignment for one dimension on one ledger line."""

    __tablename__ = "journallineanalyticaldimension"
    __table_args__ = (
        UniqueConstraint(
            "journal_line_id",
            "dimension_id",
            name="uq_journal_line_analytical_dimension",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    journal_line_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("journalline.id"),
            nullable=False,
            index=True,
        )
    )
    dimension_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("analyticaldimension.id"),
            nullable=False,
            index=True,
        )
    )
    dimension_value_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("analyticaldimensionvalue.id"),
            nullable=False,
            index=True,
        )
    )
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


class FixedAssetAcquisitionPostingRecord(SQLModel, table=True):
    """One-use persisted identity and semantic provenance for one asset acquisition."""

    __tablename__ = "fixedassetacquisitionpostingrecord"
    __table_args__ = (
        UniqueConstraint(
            "fixed_asset_id",
            name="uq_fixed_asset_acquisition_asset",
        ),
        UniqueConstraint(
            "entry_id",
            name="uq_fixed_asset_acquisition_entry",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    fixed_asset_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("fixedasset.id"),
            nullable=False,
            index=True,
        )
    )
    entry_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("journalentry.id"),
            nullable=False,
            index=True,
        )
    )
    asset_class: str = Field(sa_column=Column(String, nullable=False))
    settlement_method: str = Field(sa_column=Column(String, nullable=False))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


from sqlalchemy import CheckConstraint


class UserKnowledgeStateRecord(SQLModel, table=True):
    """Persisted singleton local pedagogical and presentation preference state."""

    __tablename__ = "userknowledgestate"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_user_knowledge_state_singleton"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    explanation_level: str = Field(sa_column=Column(String, nullable=False))
    concepts_seen_json: str = Field(sa_column=Column(Text, nullable=False))
    ui_language: str = Field(sa_column=Column(String, nullable=False))
    decimal_separator: str = Field(sa_column=Column(String, nullable=False))
    currency_symbol: str = Field(sa_column=Column(String, nullable=False))
    preferred_report_format: str = Field(sa_column=Column(String, nullable=False))
    always_show_professional_view: bool = Field(
        sa_column=Column(Boolean, nullable=False)
    )
    learned_topics_json: str = Field(sa_column=Column(Text, nullable=False))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ProgramRecord(SQLModel, table=True):
    """Persisted first-class OSC management program owned by one Entity."""

    __tablename__ = "program"

    id: Optional[int] = Field(default=None, primary_key=True)
    entity_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("entity.id"),
            nullable=False,
            index=True,
        )
    )
    name: str = Field(sa_column=Column(String, nullable=False))
    description: Optional[str] = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    budget: Optional[str] = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DonationRecord(SQLModel, table=True):
    """Persisted first-class OSC donation resource event owned by one Entity."""

    __tablename__ = "donation"

    id: Optional[int] = Field(default=None, primary_key=True)
    entity_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("entity.id"),
            nullable=False,
            index=True,
        )
    )
    date: str = Field(sa_column=Column(Text, nullable=False, index=True))
    amount: str = Field(sa_column=Column(Text, nullable=False))
    donor_third_party_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            Integer,
            ForeignKey("thirdparty.id"),
            nullable=True,
            index=True,
        ),
    )
    purpose: Optional[str] = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    is_restricted: bool = Field(sa_column=Column(Boolean, nullable=False))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AuditEventRecord(SQLModel, table=True):
    """Persisted append-only general traceability metadata owned by one Entity."""

    __tablename__ = "auditevent"

    id: Optional[int] = Field(default=None, primary_key=True)
    entity_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("entity.id"),
            nullable=False,
            index=True,
        )
    )
    event_type: str = Field(sa_column=Column(String, nullable=False, index=True))
    timestamp: str = Field(sa_column=Column(Text, nullable=False, index=True))
    details_json: str = Field(sa_column=Column(Text, nullable=False))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AccountingCalendarRecord(SQLModel, table=True):
    __tablename__ = 'accountingcalendar'
    __table_args__ = (CheckConstraint('id = 1', name='ck_calendar_singleton'),)
    id: int = Field(default=1, primary_key=True)
    entity_id: int = Field(foreign_key='entity.id', unique=True)
    activity_start: str
    declaration_json: str = "{}"


class FiscalYearRecord(SQLModel, table=True):
    __tablename__ = 'fiscalyear'
    __table_args__ = (CheckConstraint("state IN ('open', 'closed')", name='ck_year_state'),)
    year: int = Field(primary_key=True)
    calendar_id: int = Field(default=1, foreign_key='accountingcalendar.id')
    start_date: str
    end_date: str
    state: str = 'open'
    closing_entry_id: Optional[int] = Field(default=None, foreign_key='journalentry.id')


class AccountingPeriodRecord(SQLModel, table=True):
    __tablename__ = 'accountingperiod'
    __table_args__ = (
        UniqueConstraint('year', 'month', name='uq_period_month'),
        CheckConstraint("state IN ('open', 'closed')", name='ck_period_state'),
    )
    id: int = Field(primary_key=True)
    year: int = Field(foreign_key='fiscalyear.year')
    month: int
    start_date: str
    end_date: str
    state: str = 'open'
