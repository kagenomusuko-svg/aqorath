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


def trial_balance(as_of: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Compute trial balance (balance of accounts) as of a given date.
    Returns dict mapping account_code to Decimal balance.
    
    Uses SQLModel-based aggregation when possible; falls back to direct
    sqlite read strategy if there are schema mismatches.
    
    Args:
        as_of: Optional date to compute balance as of. If None, uses all entries.
    
    Returns:
        Dict with account_code as keys and Decimal balance as values.
        Also includes metadata: {"balances": {...}, "total_debit": Decimal, "total_credit": Decimal}
    """
    from decimal import Decimal
    
    balances = {}
    total_debit = Decimal("0.00")
    total_credit = Decimal("0.00")
    
    try:
        # Try SQLModel-based approach
        with get_session() as s:
            query = select(JournalLine)
            
            # Filter by date if provided
            if as_of:
                # Join with JournalEntry to filter by date
                from sqlalchemy import and_
                query = query.join(JournalEntry).where(JournalEntry.date <= as_of)
            
            lines = s.exec(query).all()
            
            for line in lines:
                code = line.account_code
                if not code:
                    continue
                
                debit = Decimal(str(line.debit or 0))
                credit = Decimal(str(line.credit or 0))
                
                if code not in balances:
                    balances[code] = Decimal("0.00")
                
                balances[code] += (debit - credit)
                total_debit += debit
                total_credit += credit
    
    except Exception as e:
        # Fallback to direct sqlite read (similar to exercise.py strategy)
        import sqlite3
        from .storage import get_db_path
        
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        try:
            if as_of:
                # With date filter
                cursor.execute("""
                    SELECT jl.account_code, jl.debit, jl.credit
                    FROM journalline jl
                    JOIN journalentry je ON jl.entry_id = je.id
                    WHERE je.date <= ?
                """, (as_of.isoformat() if hasattr(as_of, 'isoformat') else str(as_of),))
            else:
                # All entries
                cursor.execute("""
                    SELECT account_code, debit, credit
                    FROM journalline
                """)
            
            for row in cursor.fetchall():
                code = row[0]
                if not code:
                    continue
                
                debit = Decimal(str(row[1] or 0))
                credit = Decimal(str(row[2] or 0))
                
                if code not in balances:
                    balances[code] = Decimal("0.00")
                
                balances[code] += (debit - credit)
                total_debit += debit
                total_credit += credit
        
        finally:
            conn.close()
    
    return {
        "balances": balances,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "as_of": as_of.isoformat() if as_of else None
    }
