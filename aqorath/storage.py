from contextlib import contextmanager
import os
from sqlmodel import SQLModel, create_engine, Session
from typing import Optional
from pathlib import Path

DB_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "aqorath"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "aqorath.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

_engine = create_engine(DATABASE_URL, echo=False, connect_args={"check_same_thread": False})


def init_db():
    SQLModel.metadata.create_all(_engine)


@contextmanager
def get_session() -> Session:
    with Session(_engine) as session:
        yield session


def engine():
    return _engine