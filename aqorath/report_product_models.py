"""AQR-013 persistence records for report-product configuration only.

No report figure, balance or rendered output is stored here.  Official
ReportDefinition values remain governed by the versioned product catalog; this table
stores only an Entity-owned custom selection of their stable identities.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


class CustomReportPackageRecord(SQLModel, table=True):
    __tablename__ = "customreportpackage"
    __table_args__ = (
        UniqueConstraint(
            "entity_id",
            "name",
            name="uq_custom_report_package_entity_name",
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
    name: str = Field(sa_column=Column(String, nullable=False))
    report_definition_ids_json: str = Field(sa_column=Column(Text, nullable=False))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
