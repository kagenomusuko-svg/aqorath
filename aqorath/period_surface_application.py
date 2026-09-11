"""Product-facing period and annual-closing composition for V1-10.

This module owns no calendar, ledger or closing rules. It exposes the canonical
accounting-period repository and annual-close authority in user-operable projections.
"""

from datetime import date
from pathlib import Path

from sqlalchemy import text

from . import storage as _storage
from .accounting_period_repository import (
    close_period,
    load_fiscal_year,
    load_periods,
    open_fiscal_year,
)
from .exercise import close_exercise


def _year(value):
    if type(value) is int:
        result = value
    elif type(value) is str and value.isdigit():
        result = int(value)
    else:
        raise ValueError("year must be a four-digit integer")
    if result < 1 or result > 9999:
        raise ValueError("year must be between 1 and 9999")
    return result


def _period_id(value):
    if type(value) is int:
        result = value
    elif type(value) is str and value.isdigit():
        result = int(value)
    else:
        raise ValueError("period_id must be YYYYMM integer")
    if result < 101 or result > 999912:
        raise ValueError("period_id must be YYYYMM integer")
    return result


def list_period_surface(year):
    target = _year(year)
    with _storage.get_session() as session:
        fy = load_fiscal_year(session, target)
        periods = load_periods(session, fy)
        closing_entry_id = session.execute(
            text("SELECT closing_entry_id FROM fiscalyear WHERE year=:y"),
            {"y": target},
        ).scalar_one()
        return {
            "year": fy.year,
            "state": fy.state,
            "start": fy.start.isoformat(),
            "end": fy.end.isoformat(),
            "closing_entry_id": closing_entry_id,
            "periods": [
                {
                    "id": period.id,
                    "month": period.month,
                    "start": period.start.isoformat(),
                    "end": period.end.isoformat(),
                    "state": period.state,
                }
                for period in periods
            ],
        }


def open_period_surface_year(year):
    target = _year(year)
    with _storage.get_session() as session:
        try:
            fy = load_fiscal_year(session, target)
        except Exception:
            fy = open_fiscal_year(session, target)
            session.commit()
            created = True
        else:
            created = False
        return {
            "year": fy.year,
            "state": fy.state,
            "created": created,
        }


def close_period_surface(period_id):
    target = _period_id(period_id)
    with _storage.get_session() as session:
        fy = load_fiscal_year(session, target // 100)
        periods = load_periods(session, fy)
        current = next((period for period in periods if period.id == target), None)
        if current is None:
            raise LookupError("accounting period not found")
        if current.state == "closed":
            return {
                "period_id": target,
                "state": "closed",
                "already_closed": True,
            }
        close_period(session, target)
        session.commit()
        return {
            "period_id": target,
            "state": "closed",
            "already_closed": False,
        }


def close_fiscal_year_surface(year, backup_root=None):
    target = _year(year)
    root = None
    if backup_root not in (None, ""):
        if type(backup_root) is not str:
            raise TypeError("backup_root must be path text")
        root = Path(backup_root).expanduser()
    result = close_exercise(carry_over=True, out_root=root, year=target)
    if not result.get("ok"):
        raise RuntimeError(result.get("error") or "annual close failed")
    return {
        "ok": True,
        "year": target,
        "backup_path": result.get("path"),
        "entry_id": result.get("entry_id"),
        "transferred": result.get("transferred"),
        "already_closed": bool(result.get("already_closed")),
    }


__all__ = [
    "list_period_surface",
    "open_period_surface_year",
    "close_period_surface",
    "close_fiscal_year_surface",
]
