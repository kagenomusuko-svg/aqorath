from datetime import datetime, timezone
from typing import Optional

from sqlmodel import SQLModel, Field


class Company(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    rfc: Optional[str] = None
    denominacion: Optional[str] = None
    phrase: Optional[str] = None  # lema institucional para reportes
    logo_path: Optional[str] = None  # ruta relativa/absoluta al logo subido
    primary_color: Optional[str] = None  # e.g. "#0055aa"
    secondary_color: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
