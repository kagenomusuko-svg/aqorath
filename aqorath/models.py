from datetime import datetime, timezone
from typing import Optional

from sqlmodel import SQLModel, Field
from sqlalchemy import Column, String, Boolean


class Account(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    # columna con UNIQUE para prevenir duplicados
    code: str = Field(sa_column=Column(String, unique=True))
    name: str
    nature: str
    vat_flag: bool = Field(default=False)  # indica si la cuenta es afectable por IVA
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


class Asset(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    # P0-2: Changed from float to str to preserve exact Decimal representation.
    value: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))