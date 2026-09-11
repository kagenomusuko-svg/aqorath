"""AQR-012 persistence records.

These tables own product identity and physical inventory provenance only. Monetary
truth remains in JournalEntry/JournalLine; every movement points back to that truth.
"""

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


class ProductRecord(SQLModel, table=True):
    __tablename__ = "inventoryproduct"
    __table_args__ = (
        UniqueConstraint("entity_id", "sku", name="uq_inventory_product_entity_sku"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    entity_id: int = Field(sa_column=Column(Integer, ForeignKey("entity.id"), nullable=False, index=True))
    sku: str = Field(sa_column=Column(String, nullable=False))
    name: str = Field(sa_column=Column(String, nullable=False))
    unit: str = Field(sa_column=Column(String, nullable=False))
    is_active: bool = Field(default=True, sa_column=Column(Boolean, nullable=False, index=True))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class InventoryMovementRecord(SQLModel, table=True):
    __tablename__ = "inventorymovement"
    __table_args__ = (
        UniqueConstraint("operation_id", name="uq_inventory_movement_operation"),
        UniqueConstraint("source_movement_id", name="uq_inventory_movement_single_reversal"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    operation_id: str = Field(sa_column=Column(String, nullable=False))
    entity_id: int = Field(sa_column=Column(Integer, ForeignKey("entity.id"), nullable=False, index=True))
    product_id: int = Field(sa_column=Column(Integer, ForeignKey("inventoryproduct.id"), nullable=False, index=True))
    entry_id: int = Field(sa_column=Column(Integer, ForeignKey("journalentry.id"), nullable=False, index=True))
    movement_kind: str = Field(sa_column=Column(String, nullable=False, index=True))
    occurred_on: date = Field(index=True)
    quantity_delta: str = Field(sa_column=Column(Text, nullable=False))
    value_delta: str = Field(sa_column=Column(Text, nullable=False))
    unit_price: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    unit_cost_basis: str = Field(sa_column=Column(Text, nullable=False))
    quantity_after: str = Field(sa_column=Column(Text, nullable=False))
    value_after: str = Field(sa_column=Column(Text, nullable=False))
    moving_average_after: str = Field(sa_column=Column(Text, nullable=False))
    third_party_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("thirdparty.id"), nullable=True, index=True),
    )
    document_reference_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("documentreference.id"), nullable=True, index=True),
    )
    inventory_line_id: int = Field(sa_column=Column(Integer, ForeignKey("journalline.id"), nullable=False, unique=True))
    cogs_line_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("journalline.id"), nullable=True, unique=True),
    )
    source_movement_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("inventorymovement.id"), nullable=True, index=True),
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


__all__ = ["ProductRecord", "InventoryMovementRecord"]
