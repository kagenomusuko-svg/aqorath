"""
aqorath.core - utilidades principales de contabilidad

Exposición:
  - trial_balance(as_of: Optional[date]) -> Dict[str, Decimal]
  - generate_preview(...)
  - post_entry(...)

Implementación:
  - trial_balance primero intenta usar modelos/libro.compute_balance() si está disponible.
  - Si falla (mismatch modelos/DB), hace fallback a lectura sqlite directa sumando debit-credit.
  - El resto de funciones gestiona la vista previa y publicación de asientos contables.
"""

from __future__ import annotations
from decimal import Decimal
from typing import Dict, Optional, Any
import logging
from datetime import datetime, timezone
import math
from types import SimpleNamespace

from sqlalchemy import select

from .storage import get_session
from .models import Account, JournalEntry, JournalLine
from .catalog import resolve_account_by_code

LOG = logging.getLogger(__name__)

# Intentar importar Libro si existe
try:
    from modelos.libro import Libro
except Exception:
    Libro = None


# === NUEVA FUNCIÓN: trial_balance ===
def _trial_balance_from_libro() -> Dict[str, Decimal]:
    """Usa la lógica existente en modelos/libro.py para calcular balances."""
    if Libro is None:
        raise RuntimeError("modelos.libro.Libro no disponible")
    libro = Libro()
    df = libro.compute_balance()
    balances: Dict[str, Decimal] = {}
    try:
        for idx, row in df.iterrows():
            code = str(row.get("code") or row.get("Cuenta") or idx)
            saldo = Decimal(str(row.get("saldo") or row.get("Saldo") or row.get("balance") or 0))
            balances[code] = saldo
    except Exception as e:
        LOG.exception("Error extrayendo balances desde modelos.libro: %s", e)
        raise
    return balances


def _trial_balance_sqlite_fallback(db_path: str | None = None) -> Dict[str, Decimal]:
    """
    Fallback directo a SQLite: lee journalline y suma debit-credit por cuenta.
    Si detecta estructura diferente, intenta localizar columnas por nombre.
    """
    try:
        from aqorath.exercise import _get_3103_balance_sqlite  # reuse approach
    except Exception:
        _get_3103_balance_sqlite = None

    import sqlite3
    from pathlib import Path
    db_candidates = [db_path, "tests/test.db", "datos/aqorath.db", "aqorath.db"]
    db_file = None
    for p in db_candidates:
        if not p:
            continue
        if Path(p).exists():
            db_file = Path(p)
            break
    if db_file is None:
        raise RuntimeError("No se encontró base de datos para fallback")

    conn = sqlite3.connect(str(db_file))
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info('journalline')")
        cols = [r[1] for r in cur.fetchall()]
        debit = next((c for c in cols if c.lower() in ("debit", "debe", "cargo")), None)
        credit = next((c for c in cols if c.lower() in ("credit", "haber", "abono")), None)
        acct = next((c for c in cols if "account" in c.lower() or c.endswith("_id")), None)
        if not acct:
            raise RuntimeError("No se pudo detectar columna de cuenta en journalline")
        cur.execute(f"SELECT {acct}, {debit or '0'}, {credit or '0'} FROM journalline")
        rows = cur.fetchall()
        balances: Dict[str, Decimal] = {}
        for a, d, c in rows:
            key = str(a)
            dval = Decimal(str(d or 0))
            cval = Decimal(str(c or 0))
            balances[key] = balances.get(key, Decimal(0)) + (dval - cval)
        return balances
    finally:
        conn.close()


def trial_balance(as_of: Optional[str] = None) -> Dict[str, Decimal]:
    """
    Devuelve un dict {account_code: Decimal(saldo)}.
    as_of puede pasarse (no implementado en fallback).
    """
    try:
        return _trial_balance_from_libro()
    except Exception as e:
        LOG.debug("trial_balance: falló libro.compute_balance(), usando fallback sqlite: %s", e)
        return _trial_balance_sqlite_fallback()


# === FUNCIONALIDADES ORIGINALES ===

# get_template / list of templates from templates module if present
try:
    from .templates import get_template, list_templates as _list_templates
except Exception:
    get_template = None
    _list_templates = None


def list_templates():
    """Return list of available template keys (if templates module exposes it)."""
    if _list_templates:
        try:
            return _list_templates()
        except Exception:
            return []
    return []


def _row_to_obj(row):
    """
    Convierte un resultado de Session.exec(select(Account)).all()
    a un objeto con atributos accesibles (.code, .name, .nature, ...).
    """
    if row is None:
        return None

    if isinstance(row, Account):
        return row

    mapping = {}
    if hasattr(row, "_mapping"):
        try:
            mapping = dict(row._mapping)
        except Exception:
            mapping = {}
    else:
        try:
            mapping = dict(row)
        except Exception:
            mapping = {}

    if not mapping:
        return None

    return SimpleNamespace(**mapping)


def generate_preview(template_key: str, amount: float, ctx: Optional[Dict[str, Any]] = None):
    """
    Construye una vista previa del asiento contable generado por una plantilla.
    Retorna un dict con claves: template, description, date, lines[], total_debit, total_credit, balanced.
    """
    if get_template is None:
        raise RuntimeError("templates module not available (get_template missing)")

    tpl = get_template(template_key)
    line_specs = tpl.create_lines(amount, ctx or {})

    with get_session() as s:
        rows = s.exec(select(Account)).all()
        accounts: Dict[str, Any] = {}
        for r in rows:
            obj = _row_to_obj(r)
            if obj is None:
                continue
            code = getattr(obj, "code", None)
            if code is not None:
                accounts[str(code)] = obj

    lines_preview = []
    total_debit = 0.0
    total_credit = 0.0

    for ls in line_specs:
        acc = accounts.get(ls.account_code)
        debit = ls.amount_expr(amount, ctx or {}) if ls.side == "debit" else 0.0
        credit = ls.amount_expr(amount, ctx or {}) if ls.side == "credit" else 0.0
        total_debit += debit
        total_credit += credit
        lines_preview.append({
            "account_code": ls.account_code,
            "account_id": acc.id if acc else None,
            "account_name": acc.name if acc else None,
            "debit": round(debit, 2),
            "credit": round(credit, 2),
            "description": ls.description or ""
        })

    balance_ok = math.isclose(total_debit, total_credit, rel_tol=1e-6)

    return {
        "template": template_key,
        "description": getattr(tpl, "description", None),
        "date": datetime.now(timezone.utc).date(),
        "lines": lines_preview,
        "total_debit": round(total_debit, 2),
        "total_credit": round(total_credit, 2),
        "balanced": balance_ok
    }


def post_entry(template_key: str, amount: float, ctx: Optional[Dict[str, Any]] = None, user: Optional[str] = None):
    """
    Persiste el asiento contable generado por una plantilla en la BD.
    No crea cuentas automáticamente; usa las existentes en el catálogo.
    """
    preview = generate_preview(template_key, amount, ctx or {})
    if not preview["balanced"]:
        raise ValueError("El asiento no está balanceado. Revisa las reglas del template.")

    with get_session() as s:
        entry = JournalEntry(
            date=preview["date"],
            concept=(ctx or {}).get("desc"),
            doc_ref=(ctx or {}).get("doc_ref"),
            period_id=(ctx or {}).get("period_id"),
            posted_by=user,
            state="posted"
        )
        s.add(entry)
        s.commit()
        s.refresh(entry)

        for l in preview["lines"]:
            code = l.get("account_code")
            acc_row = resolve_account_by_code(s, code)
            acc_id = acc_row.id if acc_row else None

            line = JournalLine(
                entry_id=entry.id,
                account_code=code,
                account_id=acc_id,
                debit=l.get("debit", 0.0),
                credit=l.get("credit", 0.0),
                description=l.get("description")
            )
            s.add(line)

        s.commit()
        return entry.id
