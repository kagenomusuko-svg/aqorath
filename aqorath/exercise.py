from __future__ import annotations
"""Canonical year-end closing workflow.

The closing keeps its historical backup and result-calculation behavior, but it no
longer owns an accounting persistence path. JournalEntry/JournalLine construction and
commit authority belong exclusively to ``aqorath.core.post_entry``.
"""

import logging
import shutil
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Optional

from sqlmodel import select

from aqorath.accounting_rules import compute_resultado_ejercicio, load_catalog
from aqorath.core import post_entry, trial_balance
from aqorath.models import Account
from aqorath.storage import get_db_path, get_session


LOG = logging.getLogger(__name__)
LOG.addHandler(logging.NullHandler())

OUT_ROOT_DEFAULT = Path.home() / ".local" / "share" / "aqorath" / "ejercicios"


def _copy_files(dest: Path, db_path: Path) -> None:
    """Create the non-destructive closing backup before any carry-over posting."""
    dest.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        shutil.copy2(db_path, dest / db_path.name)

    catalog_path = Path(__file__).resolve().parent / "data" / "catalogo_base.json"
    if catalog_path.exists():
        shutil.copy2(catalog_path, dest / catalog_path.name)


def _resolve_closing_accounts() -> tuple[Account | None, Account | None]:
    """Resolve the two governed accounts without creating or mutating catalog rows."""
    with get_session() as session:
        account_3103 = session.exec(
            select(Account).where(Account.code == "3103")
        ).one_or_none()
        account_3104 = session.exec(
            select(Account).where(Account.code == "3104")
        ).one_or_none()
        return account_3103, account_3104


def _closing_lines(
    resultado: Decimal,
    account_3103: Account,
    account_3104: Account,
) -> list[dict[str, Any]]:
    """Build an exact, balanced proposal; persistence remains owned by post_entry."""
    if resultado > 0:
        amount = str(resultado)
        return [
            {
                "account_id": account_3103.id,
                "account_code": account_3103.code,
                "debit": amount,
                "credit": "0",
                "description": "Cierre: traslado a 3104",
            },
            {
                "account_id": account_3104.id,
                "account_code": account_3104.code,
                "debit": "0",
                "credit": amount,
                "description": "Cierre: contrapartida desde 3103",
            },
        ]

    amount = str(abs(resultado))
    return [
        {
            "account_id": account_3104.id,
            "account_code": account_3104.code,
            "debit": amount,
            "credit": "0",
            "description": "Cierre pérdida: traslado a 3104",
        },
        {
            "account_id": account_3103.id,
            "account_code": account_3103.code,
            "debit": "0",
            "credit": amount,
            "description": "Cierre pérdida: contrapartida desde 3104",
        },
    ]


def close_exercise(
    carry_over: bool = True,
    out_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Backup the database and optionally post the 3103→3104 year-end transfer.

    The function never creates accounts and never writes JournalEntry/JournalLine by
    direct ORM or sqlite. A carry-over can become durable only through ``post_entry``
    and therefore through the canonical persistence invariants.
    """
    root = out_root or OUT_ROOT_DEFAULT
    dest = root / datetime.now().strftime("%Y%m%d_%H%M%S")
    db_path = Path(get_db_path())

    try:
        _copy_files(dest, db_path)
    except Exception as exc:
        LOG.exception("Error creando backup: %s", exc)
        return {"ok": False, "error": f"Error creando backup: {exc}"}

    if not carry_over:
        return {
            "ok": True,
            "path": str(dest),
            "note": "Backup creado, no se realizó traslado de saldos.",
        }

    try:
        balances = trial_balance()
        catalog = load_catalog()
        resultado, _totals = compute_resultado_ejercicio(balances, catalog)
        resultado = Decimal(str(resultado))
    except Exception as exc:
        LOG.exception("Error calculando resultado del ejercicio: %s", exc)
        return {
            "ok": False,
            "path": str(dest),
            "error": f"No se pudo calcular resultado: {exc}",
        }

    try:
        account_3103, account_3104 = _resolve_closing_accounts()
    except Exception as exc:
        return {
            "ok": False,
            "path": str(dest),
            "error": f"Error verificando cuentas de cierre: {exc}",
        }

    missing = []
    if account_3103 is None:
        missing.append("3103")
    if account_3104 is None:
        missing.append("3104")
    if missing:
        return {
            "ok": False,
            "path": str(dest),
            "error": (
                "Cuentas necesarias para cierre faltan en DB: "
                f"{', '.join(missing)}. El sistema no creará cuentas automáticamente."
            ),
        }

    if resultado == Decimal("0"):
        return {
            "ok": True,
            "path": str(dest),
            "note": "No hay resultado del ejercicio para trasladar.",
        }

    payload = {
        "description": f"Cierre ejercicio: traslado {resultado}",
        "date": datetime.now(timezone.utc),
        "state": "posted",
        "lines": _closing_lines(resultado, account_3103, account_3104),
    }
    result = post_entry(payload)
    if not isinstance(result, dict) or not result.get("ok"):
        error = result.get("error") if isinstance(result, dict) else result
        return {
            "ok": False,
            "path": str(dest),
            "error": f"No se pudo insertar asiento de cierre: {error}",
        }

    return {
        "ok": True,
        "path": str(dest),
        "transferred": str(resultado),
        "entry_id": result.get("entry_id"),
    }
