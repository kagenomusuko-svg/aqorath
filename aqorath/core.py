from datetime import datetime, timezone
import math
from typing import Any, Dict, Optional, cast, List
from types import SimpleNamespace

from sqlalchemy import select

from .storage import get_session
from .models import Account, JournalEntry, JournalLine

# get_template / list of templates come from the templates module if present
# keep the import lazy/guarded to avoid import-time errors if the module is absent
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
    Convierte un resultado devuelto por Session.exec(select(Account)).all()
    a un objeto con atributos accesibles (.code, .name, .nature, ...).

    - Si ya es instancia de Account, la devuelve tal cual.
    - Si es un Row/RowMapping, extrae el mapping y construye un SimpleNamespace.
    - Si no puede extraer nada, devuelve None.

    Esto hace la lectura robusta frente a distintas versiones de SQLAlchemy/SQLModel
    que devuelven modelos o RowMappings.
    """
    if row is None:
        return None

    if isinstance(row, Account):
        return row

    mapping = {}
    # Row suele exponer _mapping en muchas versiones
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

    # Normalizar posibles claves bytes/str si fuera necesario (poco común aquí)
    # Construimos un objeto ligero con atributos a partir del mapping
    return SimpleNamespace(**mapping)


def generate_preview(template_key: str, amount: float, ctx: Optional[Dict[str, Any]] = None):
    """
    Build a preview of the journal entry lines produced by a template.
    Returns a dict with keys: template, description, date, lines[], total_debit, total_credit, balanced
    """
    if get_template is None:
        raise RuntimeError("templates module not available (get_template missing)")

    tpl = get_template(template_key)
    # line_specs: lista de LineSpec (con properties: account_code, side, amount_expr, description)
    line_specs = tpl.create_lines(amount, ctx or {})

    with get_session() as s:
        # Ejecutar la consulta y convertir cada fila a objeto accesible (.code, .name, .nature, ...)
        rows = s.exec(select(Account)).all()
        accounts: Dict[str, Any] = {}
        for r in rows:
            obj = _row_to_obj(r)
            if obj is None:
                continue
            # intentar obtener código por atributo 'code' (o por key en mapping)
            code = None
            if hasattr(obj, "code"):
                code = getattr(obj, "code")
            else:
                try:
                    code = obj["code"]  # type: ignore
                except Exception:
                    code = None
            if code is not None:
                accounts[str(code)] = obj

    lines_preview = []
    total_debit = 0.0
    total_credit = 0.0

    for ls in line_specs:
        acc = accounts.get(ls.account_code)
        # calcular monto según side y la expresion provista
        try:
            debit = ls.amount_expr(amount, ctx or {}) if ls.side == "debit" else 0.0
        except Exception:
            # si la expresión falla por falta de ctx, propagar con contexto para debugging
            raise
        try:
            credit = ls.amount_expr(amount, ctx or {}) if ls.side == "credit" else 0.0
        except Exception:
            raise

        total_debit += debit
        total_credit += credit
        lines_preview.append({
            "account_code": ls.account_code,
            "account_id": acc.id if acc and hasattr(acc, "id") else None,
            "account_name": acc.name if acc and hasattr(acc, "name") else None,
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
    Persist the previewed journal entry and its lines into the DB.
    Returns the created journal entry id.
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
            acc_id = l["account_id"]
            if acc_id is None:
                # intentar resolver account por código
                acc = cast(Optional[Account], s.exec(select(Account).where(Account.code == l["account_code"])).one_or_none())
                if acc:
                    acc_id = acc.id
            jl = JournalLine(
                entry_id=entry.id,
                account_id=acc_id or None,
                debit=l["debit"],
                credit=l["credit"],
                description=l["description"]
            )
            s.add(jl)

        s.commit()
        return entry.id