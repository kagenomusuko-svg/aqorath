from datetime import datetime, timezone
import math
from typing import Any, Dict, Optional, cast, List

from sqlalchemy import select

from .storage import get_session
from .models import Account, JournalEntry, JournalLine
# get_template / list of templates comes from the templates module if present
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


def generate_preview(template_key: str, amount: float, ctx: Optional[Dict[str, Any]] = None):
    """
    Build a preview of the journal entry lines produced by a template.
    Returns a dict with keys: template, description, date, lines[], total_debit, total_credit, balanced
    """
    if get_template is None:
        raise RuntimeError("templates module not available (get_template missing)")

    tpl = get_template(template_key)
    line_specs = tpl.create_lines(amount, ctx or {})
    with get_session() as s:
        # Use scalars().all() and cast to help static type checkers (Pylance)
        accounts = {a.code: a for a in cast(List[Account], s.exec(select(Account)).all())}

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
                # use scalars().one_or_none() and cast for type-checkers
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