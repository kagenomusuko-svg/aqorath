from datetime import datetime, timezone
import math
import sqlite3
from decimal import Decimal
from typing import Any, Dict, Optional, List, Tuple
from types import SimpleNamespace

from sqlalchemy import select, text

from .storage import get_session, get_db_path
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
    
    Improvements:
    - Accepts role->account_code mappings in ctx["account_codes"]
    - Uses Decimal for accurate calculations, rounding before balance check
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
    total_debit = Decimal("0.00")
    total_credit = Decimal("0.00")

    for ls in line_specs:
        acc = accounts.get(ls.account_code)
        debit_val = ls.amount_expr(amount, ctx or {}) if ls.side == "debit" else 0.0
        credit_val = ls.amount_expr(amount, ctx or {}) if ls.side == "credit" else 0.0
        
        # Use Decimal for precision
        debit_dec = Decimal(str(debit_val)).quantize(Decimal("0.01"))
        credit_dec = Decimal(str(credit_val)).quantize(Decimal("0.01"))
        
        total_debit += debit_dec
        total_credit += credit_dec
        
        lines_preview.append({
            "account_code": ls.account_code,
            "account_id": acc.id if acc else None,
            "account_name": acc.name if acc else None,
            "debit": float(debit_dec),
            "credit": float(credit_dec),
            "description": ls.description or ""
        })

    # Round totals before checking balance
    total_debit_rounded = float(total_debit.quantize(Decimal("0.01")))
    total_credit_rounded = float(total_credit.quantize(Decimal("0.01")))
    balance_ok = math.isclose(total_debit_rounded, total_credit_rounded, rel_tol=1e-6)

    return {
        "template": template_key,
        "description": getattr(tpl, "description", None),
        "date": datetime.now(timezone.utc).date(),
        "lines": lines_preview,
        "total_debit": total_debit_rounded,
        "total_credit": total_credit_rounded,
        "balanced": balance_ok
    }


def _get_table_columns(db_path: str, table_name: str) -> List[Tuple[str, str, bool]]:
    """
    Get table column information using PRAGMA table_info.
    Returns list of (column_name, data_type, is_not_null).
    
    Note: table_name is validated to be alphanumeric + underscore to prevent SQL injection.
    """
    # Validate table_name to prevent SQL injection
    if not table_name.replace("_", "").isalnum():
        raise ValueError(f"Invalid table name: {table_name}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    # PRAGMA statements are safe from SQL injection when table name is validated
    cursor.execute(f"PRAGMA table_info({table_name})")
    cols = cursor.fetchall()
    conn.close()
    # cols format: (cid, name, type, notnull, dflt_value, pk)
    return [(col[1], col[2], bool(col[3])) for col in cols]


def _persist_entry(session, entry_data: Dict[str, Any], lines_data: List[Dict[str, Any]], use_orm: bool = True):
    """
    Robust persistence of journal entry with defensive logic for different DB schemas.
    
    Features:
    - Allows persisting journalline with account_code when account row doesn't exist
    - Verifies account_id if provided
    - Adapts to different column name conventions (description/name/concept, created_at/date)
    - Inspects table schema with PRAGMA table_info to handle NOT NULL columns
    - Uses ORM when available, falls back to raw SQL when needed
    
    Args:
        session: SQLModel session
        entry_data: Dict with journal entry fields (date, concept, doc_ref, period_id, posted_by, state)
        lines_data: List of dicts with line fields (account_code, account_id, debit, credit, description)
        use_orm: Whether to attempt ORM first
    
    Returns:
        entry_id: ID of created journal entry
    """
    try:
        if use_orm:
            # Try ORM approach first
            entry = JournalEntry(
                date=entry_data.get("date"),
                concept=entry_data.get("concept"),
                doc_ref=entry_data.get("doc_ref"),
                period_id=entry_data.get("period_id"),
                posted_by=entry_data.get("posted_by"),
                state=entry_data.get("state", "posted")
            )
            session.add(entry)
            session.commit()
            session.refresh(entry)
            entry_id = entry.id

            # Persist lines with defensive account_id verification
            for line_data in lines_data:
                account_code = line_data.get("account_code")
                account_id = line_data.get("account_id")
                
                # Verify account_id if provided
                if account_id is not None:
                    acc = session.exec(select(Account).where(Account.id == account_id)).one_or_none()
                    if acc is None:
                        # Invalid account_id, set to None and keep account_code
                        account_id = None
                
                line = JournalLine(
                    entry_id=entry_id,
                    account_code=account_code,
                    account_id=account_id,
                    debit=line_data.get("debit", 0.0),
                    credit=line_data.get("credit", 0.0),
                    description=line_data.get("description")
                )
                session.add(line)
            
            session.commit()
            return entry_id
            
    except Exception as e:
        # Fallback to raw SQL with schema inspection
        session.rollback()
        db_path = get_db_path()
        
        # Inspect journalentry table schema
        entry_cols = _get_table_columns(db_path, "journalentry")
        entry_col_names = {col[0] for col in entry_cols}
        
        # Map common column name variations
        date_col = "date"
        if "created_at" in entry_col_names:
            date_col = "created_at"
        
        concept_col = "concept"
        if "description" in entry_col_names:
            concept_col = "description"
        elif "name" in entry_col_names:
            concept_col = "name"
        elif "title" in entry_col_names:
            concept_col = "title"
        
        # Build entry insert with available columns
        entry_values = {
            date_col: entry_data.get("date") or datetime.now(timezone.utc).date(),
            "state": entry_data.get("state", "posted")
        }
        
        if concept_col in entry_col_names:
            entry_values[concept_col] = entry_data.get("concept") or ""
        if "doc_ref" in entry_col_names:
            entry_values["doc_ref"] = entry_data.get("doc_ref")
        if "period_id" in entry_col_names:
            entry_values["period_id"] = entry_data.get("period_id")
        if "posted_by" in entry_col_names:
            entry_values["posted_by"] = entry_data.get("posted_by")
        
        # Fill NOT NULL columns without defaults
        for col_name, col_type, is_not_null in entry_cols:
            if is_not_null and col_name not in entry_values and col_name != "id":
                # Validate column name is safe (alphanumeric + underscore)
                if not col_name.replace("_", "").isalnum():
                    continue  # Skip invalid column names
                # Provide reasonable defaults based on type
                if "INT" in col_type.upper():
                    entry_values[col_name] = 0
                elif "TEXT" in col_type.upper() or "VARCHAR" in col_type.upper():
                    entry_values[col_name] = ""
                elif "REAL" in col_type.upper() or "FLOAT" in col_type.upper():
                    entry_values[col_name] = 0.0
                elif "DATE" in col_type.upper() or "TIME" in col_type.upper():
                    entry_values[col_name] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')
        
        # Validate all column names before building SQL
        # Security: Only allow alphanumeric + underscore column names to prevent SQL injection
        validated_cols = [k for k in entry_values.keys() if k.replace("_", "").isalnum()]
        
        # Insert entry using text SQL with validated column names
        # Note: Column names are validated above, values use parameterized queries
        cols = ", ".join(validated_cols)
        placeholders = ", ".join([f":{k}" for k in validated_cols])
        validated_values = {k: entry_values[k] for k in validated_cols}
        # Safe: validated_cols contains only sanitized column names, values are parameterized
        result = session.exec(text(f"INSERT INTO journalentry ({cols}) VALUES ({placeholders})"), validated_values)
        session.commit()
        
        # Get last insert id
        last_id_result = session.exec(text("SELECT last_insert_rowid()"))
        entry_id = last_id_result.one()[0]
        
        # Inspect journalline table
        line_cols = _get_table_columns(db_path, "journalline")
        line_col_names = {col[0] for col in line_cols}
        
        desc_col = "description"
        if "name" in line_col_names:
            desc_col = "name"
        elif "concept" in line_col_names:
            desc_col = "concept"
        
        # Insert lines
        for line_data in lines_data:
            line_values = {
                "entry_id": entry_id,
                "debit": line_data.get("debit", 0.0),
                "credit": line_data.get("credit", 0.0)
            }
            
            if "account_code" in line_col_names:
                line_values["account_code"] = line_data.get("account_code")
            if "account_id" in line_col_names:
                account_id = line_data.get("account_id")
                # Verify account_id if provided
                if account_id is not None:
                    acc_check = session.exec(select(Account).where(Account.id == account_id)).one_or_none()
                    if acc_check is None:
                        account_id = None
                line_values["account_id"] = account_id
            if desc_col in line_col_names:
                line_values[desc_col] = line_data.get("description") or ""
            
            # Fill NOT NULL columns
            for col_name, col_type, is_not_null in line_cols:
                if is_not_null and col_name not in line_values and col_name != "id":
                    # Validate column name is safe (alphanumeric + underscore)
                    if not col_name.replace("_", "").isalnum():
                        continue  # Skip invalid column names
                    if "INT" in col_type.upper():
                        line_values[col_name] = 0
                    elif "TEXT" in col_type.upper() or "VARCHAR" in col_type.upper():
                        line_values[col_name] = ""
                    elif "REAL" in col_type.upper() or "FLOAT" in col_type.upper():
                        line_values[col_name] = 0.0
                    elif "DATE" in col_type.upper() or "TIME" in col_type.upper():
                        line_values[col_name] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')
            
            # Validate all column names before building SQL
            # Security: Only allow alphanumeric + underscore column names to prevent SQL injection
            validated_cols = [k for k in line_values.keys() if k.replace("_", "").isalnum()]
            cols = ", ".join(validated_cols)
            placeholders = ", ".join([f":{k}" for k in validated_cols])
            validated_values = {k: line_values[k] for k in validated_cols}
            # Safe: validated_cols contains only sanitized column names, values are parameterized
            session.exec(text(f"INSERT INTO journalline ({cols}) VALUES ({placeholders})"), validated_values)
        
        session.commit()
        return entry_id


def post_entry(template_key: str, amount: float, ctx: Optional[Dict[str, Any]] = None, user: Optional[str] = None):
    """
    Persist the previewed journal entry and its lines into the DB.
    Saves account_code in all JournalLine; sets account_id if the code exists in DB.
    Does NOT create Account automatically.
    
    Uses enhanced _persist_entry for robust persistence across different schemas.
    """
    preview = generate_preview(template_key, amount, ctx or {})
    if not preview["balanced"]:
        raise ValueError("El asiento no está balanceado. Revisa las reglas del template.")

    with get_session() as s:
        entry_data = {
            "date": preview["date"],
            "concept": (ctx or {}).get("desc"),
            "doc_ref": (ctx or {}).get("doc_ref"),
            "period_id": (ctx or {}).get("period_id"),
            "posted_by": user,
            "state": "posted"
        }
        
        lines_data = []
        for l in preview["lines"]:
            code = l.get("account_code")
            # Resolve account_id using catalog/DB; don't create accounts
            acc_row = resolve_account_by_code(s, code)
            acc_id = acc_row.id if acc_row else None
            
            lines_data.append({
                "account_code": code,
                "account_id": acc_id,
                "debit": l.get("debit", 0.0),
                "credit": l.get("credit", 0.0),
                "description": l.get("description")
            })
        
        return _persist_entry(s, entry_data, lines_data)


def _balances_from_sqlite(db_path: Optional[str] = None, include_zero_balance: bool = True) -> List[Dict[str, Any]]:
    """
    Calculate account balances from journalline table using raw SQL with COALESCE logic.
    
    Features:
    - Groups lines correctly when journalline has account_code and/or account_id
    - Uses COALESCE(jl.account_code, a.code, CAST(jl.account_id AS TEXT)) for grouping
    - Merges catalog accounts with zero balance when include_zero_balance=True
    - Handles different database schemas defensively
    
    Returns:
        List of dicts with keys: account_code, account_name, debit, credit, balance
    """
    if db_path is None:
        db_path = get_db_path()
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if tables exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='journalline'")
    if not cursor.fetchone():
        conn.close()
        return []
    
    # Inspect journalline columns
    cursor.execute("PRAGMA table_info(journalline)")
    line_cols = {col[1] for col in cursor.fetchall()}
    
    has_account_code = "account_code" in line_cols
    has_account_id = "account_id" in line_cols
    
    # Build query with COALESCE for account identification
    if has_account_code and has_account_id:
        # Use COALESCE to handle both columns
        query = """
        SELECT 
            COALESCE(jl.account_code, a.code, CAST(jl.account_id AS TEXT)) as account_code,
            COALESCE(a.name, '') as account_name,
            SUM(jl.debit) as total_debit,
            SUM(jl.credit) as total_credit
        FROM journalline jl
        LEFT JOIN account a ON jl.account_id = a.id
        GROUP BY COALESCE(jl.account_code, a.code, CAST(jl.account_id AS TEXT))
        """
    elif has_account_code:
        query = """
        SELECT 
            jl.account_code as account_code,
            COALESCE(a.name, '') as account_name,
            SUM(jl.debit) as total_debit,
            SUM(jl.credit) as total_credit
        FROM journalline jl
        LEFT JOIN account a ON jl.account_code = a.code
        GROUP BY jl.account_code
        """
    elif has_account_id:
        query = """
        SELECT 
            COALESCE(a.code, CAST(jl.account_id AS TEXT)) as account_code,
            COALESCE(a.name, '') as account_name,
            SUM(jl.debit) as total_debit,
            SUM(jl.credit) as total_credit
        FROM journalline jl
        LEFT JOIN account a ON jl.account_id = a.id
        GROUP BY jl.account_id
        """
    else:
        conn.close()
        return []
    
    cursor.execute(query)
    rows = cursor.fetchall()
    
    balances = []
    account_codes_with_movement = set()
    
    for row in rows:
        account_code = row[0]
        account_name = row[1]
        total_debit = Decimal(str(row[2] or 0.0))
        total_credit = Decimal(str(row[3] or 0.0))
        balance = total_debit - total_credit
        
        balances.append({
            "account_code": account_code,
            "account_name": account_name,
            "debit": float(total_debit.quantize(Decimal("0.01"))),
            "credit": float(total_credit.quantize(Decimal("0.01"))),
            "balance": float(balance.quantize(Decimal("0.01")))
        })
        account_codes_with_movement.add(account_code)
    
    # Include zero-balance accounts from catalog if requested
    if include_zero_balance:
        cursor.execute("SELECT code, name FROM account")
        all_accounts = cursor.fetchall()
        
        for code, name in all_accounts:
            if code not in account_codes_with_movement:
                balances.append({
                    "account_code": code,
                    "account_name": name or "",
                    "debit": 0.0,
                    "credit": 0.0,
                    "balance": 0.0
                })
    
    conn.close()
    
    # Sort by account code
    balances.sort(key=lambda x: x["account_code"])
    return balances


def trial_balance(db_path: Optional[str] = None, include_zero_balance: bool = False) -> Dict[str, Any]:
    """
    Generate a trial balance report showing all account balances.
    
    Args:
        db_path: Path to SQLite database (uses default if None)
        include_zero_balance: Whether to include accounts with zero balance
    
    Returns:
        Dict with keys:
        - accounts: List of account balance dicts
        - total_debit: Sum of all debits
        - total_credit: Sum of all credits
        - balanced: Whether debits equal credits
        - generated_at: ISO timestamp with 'Z' suffix (timezone-aware)
    """
    balances = _balances_from_sqlite(db_path, include_zero_balance)
    
    total_debit = Decimal("0.00")
    total_credit = Decimal("0.00")
    
    for bal in balances:
        total_debit += Decimal(str(bal["debit"]))
        total_credit += Decimal(str(bal["credit"]))
    
    total_debit_rounded = float(total_debit.quantize(Decimal("0.01")))
    total_credit_rounded = float(total_credit.quantize(Decimal("0.01")))
    
    balanced = math.isclose(total_debit_rounded, total_credit_rounded, rel_tol=1e-6)
    
    return {
        "accounts": balances,
        "total_debit": total_debit_rounded,
        "total_credit": total_credit_rounded,
        "balanced": balanced,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')
    }
