"""
Utilities to read/write the accounting model selection in a single place.

Behavior:
- Try to persist/read the "accounting_model" key in AppConfig table via DB if available.
- If DB API or model are not available, fallback to a JSON config file at:
    ~/.local/share/aqorath/config.json

API:
- get_accounting_model() -> Optional[str]
- set_accounting_model(value: str) -> bool
- is_accounting_model_set() -> bool
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

LOG = logging.getLogger(__name__)

FALLBACK_PATH = Path.home() / ".local" / "share" / "aqorath" / "config.json"
DB_KEY = "accounting_model"


def _read_fallback_file() -> Optional[str]:
    try:
        if FALLBACK_PATH.exists():
            with FALLBACK_PATH.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data.get(DB_KEY)
    except Exception as e:
        LOG.debug("Failed to read fallback config file: %s", e)
    return None


def _write_fallback_file(value: str) -> bool:
    try:
        FALLBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
        with FALLBACK_PATH.open("w", encoding="utf-8") as fh:
            json.dump({DB_KEY: value}, fh, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        LOG.exception("Failed to write fallback config file: %s", e)
        return False


def _read_db() -> Optional[str]:
    """
    P1-2: Read accounting_model from SQLite via ORM.
    SQLite is the sole authority; no JSON fallback.
    """
    try:
        from aqorath.models import AppConfig  # type: ignore
        from aqorath.storage import get_session  # type: ignore
        from sqlmodel import select  # type: ignore
    except Exception as e:
        LOG.debug("DB access not available for config read: %s", e)
        return None

    try:
        with get_session() as s:
            # P1-2: Use select(AppConfig) not AppConfig.select()
            row = s.exec(select(AppConfig).where(AppConfig.key == DB_KEY)).one_or_none()
            if row:
                return getattr(row, "value", None)
    except Exception as e:
        LOG.exception("Error reading accounting_model from DB: %s", e)
    return None


def _write_db(value: str) -> bool:
    """
    P1-2: Write accounting_model to SQLite via ORM.
    SQLite is the sole authority; no JSON fallback.
    """
    try:
        from aqorath.models import AppConfig  # type: ignore
        from aqorath.storage import get_session  # type: ignore
        from sqlmodel import select  # type: ignore
    except Exception as e:
        LOG.debug("DB access not available for config write: %s", e)
        return False

    try:
        with get_session() as s:
            # P1-2: Use select(AppConfig) not AppConfig.select()
            row = s.exec(select(AppConfig).where(AppConfig.key == DB_KEY)).one_or_none()
            if row:
                setattr(row, "value", value)
                s.add(row)
            else:
                # Create new config row
                new = AppConfig(key=DB_KEY, value=value)
                s.add(new)
            s.commit()
            return True
    except Exception as e:
        LOG.exception("Error writing accounting_model to DB: %s", e)
        return False


def get_accounting_model() -> Optional[str]:
    """
    P1-2: Return accounting_model from SQLite only.
    SQLite is the sole authority; no JSON fallback.
    Returns None if not set.
    """
    return _read_db()


def set_accounting_model(value: str) -> bool:
    """
    P1-2: Write accounting_model to SQLite only.
    SQLite is the sole authority; no JSON fallback.
    Returns True on success, False on failure.
    """
    # Defensive check: accept only known values
    if value not in ("comercial", "sin_fines"):
        LOG.error("Invalid accounting_model value: %r", value)
        return False

    return _write_db(value)


def is_accounting_model_set() -> bool:
    return get_accounting_model() is not None