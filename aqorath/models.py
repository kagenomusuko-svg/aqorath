from typing import Optional
from datetime import date, datetime
from sqlmodel import SQLModel, Field


class AppConfig(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: str


class Period(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    year: int
    start_date: date
    end_date: date
    type: str  # "COMERCIAL" or "OSC"
    is_open: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Account(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    code: str
    name: str
    nature: str  # "DEBIT" or "CREDIT"
    account_type: Optional[str] = None
    vat_flag: bool = False
    vat_rate: Optional[float] = 0.0
    created_at: datetime = Field(default_factory=datetime.utcnow)


class JournalEntry(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    date: date
    concept: Optional[str] = None
    doc_ref: Optional[str] = None
    period_id: Optional[int] = Field(default=None, foreign_key="period.id")
    posted_by: Optional[str] = None
    state: str = "draft"  # draft | posted | void
    created_at: datetime = Field(default_factory=datetime.utcnow)


class JournalLine(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    entry_id: Optional[int] = Field(default=None, foreign_key="journalentry.id")
    account_id: Optional[int] = Field(default=None, foreign_key="account.id")
    debit: float = 0.0
    credit: float = 0.0
    description: Optional[str] = None
    cfdi_uuid: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AuditLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    action: str
    object_type: str
    object_id: Optional[int] = None
    payload: Optional[str] = None
    user: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class Asset(SQLModel, table=True):
    """
    Registro de activo para depreciación.
    life_years: vida útil fiscal en años
    acquisition_cost: costo inicial
    salvage_value: valor residual (si aplica)
    depreciation_method: 'straight_line' (por ahora)
    start_date: fecha de inicio de depreciación
    depreciation_period: 'monthly' or 'annual' (default monthly)
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    code: str
    description: Optional[str] = None
    acquisition_date: date
    acquisition_cost: float
    salvage_value: float = 0.0
    life_years: int = 5
    depreciation_method: str = "straight_line"
    depreciation_period: str = "monthly"
    active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)from datetime import datetime, timezone
from pydantic import Field
...
# Antes:
# created_at: datetime = Field(default_factory=datetime.utcnow)
# Después:
created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
...
# Aplica lo mismo para todas las ocurrencias listadas por grepsed -i "s/from datetime import datetime/from datetime import datetime, timezone/" aqorath/models.py

# reemplazar Field(default_factory=datetime.utcnow) por lambda que usa timezone
sed -i "s/Field(default_factory=datetime.utcnow)/Field(default_factory=lambda: datetime.now(timezone.utc))/g" aqorath/models.py