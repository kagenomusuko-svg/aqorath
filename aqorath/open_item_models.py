"""Normalized persistence metadata for AQR-006 operational subledgers.

These tables deliberately store no authoritative monetary amount or mutable open
balance. Money remains exclusively in JournalLine; these records only identify
which canonical ledger lines represent an obligation and its applications.

A single JournalEntry or DocumentReference may legitimately participate in several
open-item relationships. The invariant is therefore line-granular: one source
control line identifies at most one OpenItem, and one application control line
identifies at most one OpenItemApplication.
"""

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import CheckConstraint, Column, ForeignKey, Integer, String, UniqueConstraint
from sqlmodel import Field, SQLModel


class OpenItemRecord(SQLModel, table=True):
    __tablename__ = "openitem"
    __table_args__ = (
        CheckConstraint("kind IN ('receivable','payable')", name="ck_open_item_kind"),
        UniqueConstraint("source_line_id", name="uq_open_item_source_line"),
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
    third_party_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("thirdparty.id"),
            nullable=False,
            index=True,
        )
    )
    kind: str = Field(sa_column=Column(String, nullable=False, index=True))
    source_entry_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("journalentry.id"),
            nullable=False,
            index=True,
        )
    )
    source_line_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("journalline.id"),
            nullable=False,
            index=True,
        )
    )
    source_document_reference_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("documentreference.id"),
            nullable=False,
            index=True,
        )
    )
    due_date: date = Field(index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class OpenItemApplicationRecord(SQLModel, table=True):
    __tablename__ = "openitemapplication"
    __table_args__ = (
        UniqueConstraint(
            "application_line_id",
            name="uq_open_item_application_line",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    open_item_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("openitem.id"),
            nullable=False,
            index=True,
        )
    )
    application_entry_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("journalentry.id"),
            nullable=False,
            index=True,
        )
    )
    application_line_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("journalline.id"),
            nullable=False,
            index=True,
        )
    )
    application_document_reference_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("documentreference.id"),
            nullable=False,
            index=True,
        )
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


__all__ = ["OpenItemRecord", "OpenItemApplicationRecord"]
