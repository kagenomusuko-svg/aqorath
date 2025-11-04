from datetime import datetime, timezone
import math
from typing import Any, Dict, Optional
from types import SimpleNamespace

from sqlalchemy import select

from .storage import get_session
from .models import Account, JournalEntry, JournalLine
from .catalog import resolve_account_by_code

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

    - Si ya es instancia de Account, se devuelve tal cual.
    - Si es Row/RowMapping, construye un SimpleNamespace.
    - Si no puede extraer nada, devuelve None.
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
    Build a preview of the journal entry lines produced by a template.
    Returns a dict with keys: template, description, date, lines[], total_debit, total_credit, balanced
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
    Persist the previewed journal entry and its lines into the DB.
    Saves account_code in all JournalLine; sets account_id if the code exists in DB.
    Does NOT create Account automatically.
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
            # resolver account_id usando el catálogo / BD; no crear cuentas
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


def trial_balance(as_of: Optional[Any] = None) -> Dict[str, Any]:
    """
    Compute trial balance (balance de comprobación) as of a given date.
    Returns a dict mapping account codes to their balances (Decimal).
    
    First tries to use modelos/libro.compute_balance() if available,
    falls back to safe sqlite direct-read strategy when models/DB mismatch.
    
    Args:
        as_of: Optional date filter (datetime.date or ISO string). 
               If provided, only entries up to this date are considered.
    
    Returns:
        Dict with account codes as keys and Decimal balances as values.
        Also includes special key "_summary" with aggregate totals by category.
    """
    from decimal import Decimal
    from datetime import datetime, date
    
    # Parse as_of date if provided
    cutoff_date = None
    if as_of:
        if isinstance(as_of, date):
            cutoff_date = as_of
        elif isinstance(as_of, datetime):
            cutoff_date = as_of.date()
        else:
            try:
                cutoff_date = datetime.fromisoformat(str(as_of)).date()
            except Exception:
                cutoff_date = None
    
    # Try to use modelos/libro.compute_balance() if available
    try:
        from modelos.libro import Libro
        # Try to load a libro if available - this is optional
        # For now we'll fall back to direct DB read
        raise ImportError("Not using Libro for trial balance")
    except (ImportError, Exception):
        pass
    
    # Fallback: Direct sqlite read strategy (safe approach)
    balances: Dict[str, Decimal] = {}
    
    with get_session() as s:
        from sqlalchemy import text
        
        # Query all journal lines with optional date filter
        if cutoff_date:
            query = text("""
                SELECT jl.account_code, jl.debit, jl.credit
                FROM journalline jl
                JOIN journalentry je ON jl.entry_id = je.id
                WHERE je.date <= :cutoff_date
                ORDER BY jl.account_code
            """)
            result = s.execute(query, {"cutoff_date": cutoff_date.isoformat()})
        else:
            query = text("""
                SELECT account_code, debit, credit
                FROM journalline
                ORDER BY account_code
            """)
            result = s.execute(query)
        
        # Accumulate balances by account code
        for row in result:
            code = str(row[0]) if row[0] else ""
            if not code:
                continue
            
            debit = Decimal(str(row[1] or 0))
            credit = Decimal(str(row[2] or 0))
            
            if code not in balances:
                balances[code] = Decimal("0.00")
            
            # Balance = debits - credits
            balances[code] += (debit - credit)
        
        # Round all balances to 2 decimals
        for code in balances:
            balances[code] = balances[code].quantize(Decimal("0.01"))
        
        # Get account info for summary by category
        accounts = s.exec(select(Account)).all()
        account_map = {}
        for acc in accounts:
            # Handle both Account objects and Row tuples
            if isinstance(acc, Account):
                account_map[str(acc.code)] = acc
            elif hasattr(acc, '_mapping'):
                # It's a Row object, access via tuple indexing
                account_map[str(acc[0].code)] = acc[0]
        
        # Categorize balances
        summary = {
            "Activo": Decimal("0.00"),
            "Pasivo": Decimal("0.00"),
            "Capital": Decimal("0.00"),
            "Ingreso": Decimal("0.00"),
            "Gasto": Decimal("0.00"),
            "Otros": Decimal("0.00"),
        }
        
        for code, balance in balances.items():
            acc = account_map.get(code)
            if not acc:
                summary["Otros"] += balance
                continue
            
            # Categorize based on account code prefix (SAT standard)
            code_prefix = code[:1] if code else ""
            if code_prefix == "1":
                summary["Activo"] += balance
            elif code_prefix == "2":
                summary["Pasivo"] += balance
            elif code_prefix == "3":
                summary["Capital"] += balance
            elif code_prefix == "4":
                summary["Ingreso"] += balance
            elif code_prefix == "5":
                summary["Gasto"] += balance
            else:
                summary["Otros"] += balance
        
        # Round summary values
        for cat in summary:
            summary[cat] = summary[cat].quantize(Decimal("0.01"))
        
        # Include summary in result
        result_dict = dict(balances)
        result_dict["_summary"] = summary
        
        return result_dict
