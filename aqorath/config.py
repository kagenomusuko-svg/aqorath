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
    Defensive: try to import AppConfig and a session getter from aqorath.storage.
    Return None if any of these pieces are missing or an error happens.
    """
    try:
        from aqorath.models import AppConfig  # type: ignore
        from aqorath.storage import get_session  # type: ignore
        from sqlmodel import select  # type: ignore
    except Exception as e:
        LOG.debug("DB access not available for config read: %s", e)
        return None

    try:
        s = get_session()
        try:
            # Try to locate config row; adapt if your AppConfig schema differs
            row = s.exec(select(AppConfig).where(AppConfig.key == DB_KEY)).one_or_none()
            if row:
                return getattr(row, "value", None)
        finally:
            s.close()
    except Exception as e:
        LOG.exception("Error reading accounting_model from DB: %s", e)
    return None


def _write_db(value: str) -> bool:
    try:
        from aqorath.models import AppConfig  # type: ignore
        from aqorath.storage import get_session  # type: ignore
        from sqlmodel import select  # type: ignore
    except Exception as e:
        LOG.debug("DB access not available for config write: %s", e)
        return False

    try:
        s = get_session()
        try:
            row = s.exec(select(AppConfig).where(AppConfig.key == DB_KEY)).one_or_none()
            if row:
                setattr(row, "value", value)
                s.add(row)
            else:
                # adapt fields names if AppConfig uses different schema
                new = AppConfig(key=DB_KEY, value=value)
                s.add(new)
            s.commit()
            return True
        finally:
            s.close()
    except Exception as e:
        LOG.exception("Error writing accounting_model to DB: %s", e)
        return False


def get_accounting_model() -> Optional[str]:
    """
    Return 'comercial' or 'sin_fines' if set, otherwise None.
    Preference: read DB first, then fallback file.
    """
    val = _read_db()
    if val:
        return val
    return _read_fallback_file()


def set_accounting_model(value: str) -> bool:
    """
    Try to set value in DB; on failure write fallback file.
    Returns True on success, False if neither approach worked.
    """
    # Defensive check: accept only known values
    if value not in ("comercial", "sin_fines"):
        LOG.error("Invalid accounting_model value: %r", value)
        return False

    ok = _write_db(value)
    if ok:
        return True
    # fallback
    return _write_fallback_file(value)


def is_accounting_model_set() -> bool:
    return get_accounting_model() is not None