"""SQLModel records for AQR-013 report preset configuration only."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


class ReportPresetRecord(SQLModel, table=True):
    __tablename__ = "reportpreset"
    __table_args__ = (
        UniqueConstraint("entity_id", "name", name="uq_report_preset_entity_name"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    entity_id: int = Field(
        sa_column=Column(Integer, ForeignKey("entity.id"), nullable=False, index=True)
    )
    name: str = Field(sa_column=Column(String, nullable=False))
    format: str = Field(sa_column=Column(String, nullable=False))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ReportPresetItemRecord(SQLModel, table=True):
    __tablename__ = "reportpresetitem"
    __table_args__ = (
        UniqueConstraint("preset_id", "position", name="uq_report_preset_item_position"),
        UniqueConstraint(
            "preset_id",
            "report_definition_id",
            name="uq_report_preset_item_definition",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    preset_id: int = Field(
        sa_column=Column(Integer, ForeignKey("reportpreset.id"), nullable=False, index=True)
    )
    position: int = Field(sa_column=Column(Integer, nullable=False))
    report_definition_id: int = Field(sa_column=Column(Integer, nullable=False, index=True))
    parameters_json: str = Field(default="[]", sa_column=Column(Text, nullable=False))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


__all__ = ["ReportPresetRecord", "ReportPresetItemRecord"]
