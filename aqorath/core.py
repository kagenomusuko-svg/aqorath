"""
aqorath.core - utilities for templates, persistence and trial balance

This module exposes:
- generate_preview(template_key, amount, ctx=None) -> dict
- list_templates() -> list[str]
- post_entry(template_key|entry_dict, amount=None, ctx=None, user=None) -> int | dict
- trial_balance(as_of=None) -> dict[str, Decimal]

Notes:
- Defensive implementation: prefer ORM/SQLModel when available and fall back to direct sqlite access.
- NEVER create account rows automatically. All account existence checks are validations.
- generate_preview resolves role mappings passed in ctx["account_codes"] so templates
  can use semantic roles (e.g. "bank") mapped to real account codes by caller.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import datetime
import math
from decimal import Decimal
from decimal import InvalidOperation, getcontext, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Dict, Optional, List
from types import SimpleNamespace

LOG = logging.getLogger(__name__)
LOG.addHandler(logging.NullHandler())

# P0-2: Import to_decimal_exact from money module
# money.py is mandatory; if it cannot be imported, aqorath must fail
from aqorath.money import to_decimal_exact

try:
    from aqorath.storage import get_session
except Exception:
    get_session = None  # type: ignore

try:
    from aqorath.models import Account, JournalEntry, JournalLine  # type: ignore
except Exception:
    Account = None  # type: ignore
    JournalEntry = None  # type: ignore
    JournalLine = None  # type: ignore

# Templates helper (if present in package)
try:
    from aqorath.templates import get_template, list_templates as _list_templates  # type: ignore
except Exception:
    get_template = None
    _list_templates = None

# Try to import Libro for fallback balance computation
try:
    from modelos.libro import Libro  # type: ignore
except Exception:
    Libro = None  # type: ignore


# -------------------------
# Helpers: DB path & templates
# -------------------------
def _find_db_path() -> Optional[Path]:
    """
    Locate sqlite DB. Prefer env AQORATH_DB (if set, use it even if not yet created)
    then common locations used in tests.
    """
    cand = os.environ.get("AQORATH_DB")
    if cand:
        # If AQORATH_DB is explicitly set, use it (even if it doesn't exist yet; init_db will create it)
        return Path(cand)
    # Otherwise search standard locations
    for p in ("tests/test.db", "datos/aqorath.db", "aqorath.db", "test.db"):
        if Path(p).exists():
            return Path(p)
    return None


def list_templates() -> List[str]:
    """
    List available template keys (delegates to templates.list_templates if available).
    """
    if _list_templates:
        try:
            return _list_templates()
        except Exception:
            LOG.debug("templates.list_templates failed", exc_info=True)
    tdir = Path("templates")
    if not tdir.exists():
        return []
    # return stem names for supported template files
    return [p.stem for p in sorted(tdir.iterdir()) if p.is_file() and p.suffix in (".html", ".jinja", ".j2", "")]


def _row_to_obj(row: Any) -> Optional[SimpleNamespace]:
    """
    Convert a DB row / SQLModel object to a simple object with attributes id, code, name.
    Defensive for different row/ORM representations.
    """
    if row is None:
        return None
    try:
        code = getattr(row, "code", None)
        name = getattr(row, "name", None)
        id_ = getattr(row, "id", None)
        return SimpleNamespace(id=id_, code=str(code) if code is not None else None, name=name)
    except Exception:
        try:
            if isinstance(row, dict):
                return SimpleNamespace(id=row.get("id"), code=row.get("code"), name=row.get("name"))
        except Exception:
            return None
    return None


def _load_accounts_map() -> Dict[str, Any]:
    """
    Return mapping account_code -> object (with id, code, name).
    Prefer ORM/SQLModel when available; fallback to sqlite direct query.
    """
    accounts: Dict[str, Any] = {}
    # ORM path
    try:
        if Account is not None and get_session is not None:
            with get_session() as s:
                rows = s.exec(__import__("sqlmodel").sql.select(Account)).all()
                for r in rows:
                    obj = _row_to_obj(r)
                    if obj and obj.code is not None:
                        accounts[str(obj.code)] = obj
            return accounts
    except Exception:
        LOG.debug("ORM account load failed; falling back to sqlite", exc_info=True)

    # sqlite fallback
    db = _find_db_path()
    if not db:
        return accounts
    conn = sqlite3.connect(str(db))
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, code, name FROM account")
        for id_, code, name in cur.fetchall():
            if code is None:
                continue
            accounts[str(code)] = SimpleNamespace(id=id_, code=str(code), name=name)
    finally:
        conn.close()
    return accounts


# -------------------------
# Preview generation (resolves roles -> real account codes)
# -------------------------
def generate_preview(template_key: str, amount: float | Decimal, ctx: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Build a preview of the journal entry lines produced by a template.

    Resolves account roles via ctx.get('account_codes', {}) before returning the preview.
    For preview we accept declared account codes or role names; persistence will validate.
    Accumulates with Decimal and decides 'balanced' by comparing totals rounded to 2 decimals.
    """
    # set Decimal precision for intermediate calculations
    getcontext().prec = 28

    ctx = ctx or {}
    # If templates module not available, return safe minimal preview-like dict
    if get_template is None:
        return {
            "template": template_key,
            "description": None,
            "date": datetime.datetime.now(datetime.timezone.utc).date(),
            "lines": [],
            "total_debit": 0.0,
            "total_credit": 0.0,
            "balanced": True,
            "missing_accounts": [],
        }

    tpl = get_template(template_key)
    line_specs = tpl.create_lines(amount, ctx or {})

    accounts_map = _load_accounts_map()  # code -> obj (may be empty)
    # mapping provided by caller: role -> account_code (strings)
    try:
        role_map: Dict[str, str] = dict((k, str(v)) for k, v in (ctx.get("account_codes") or {}).items())
    except Exception:
        role_map = {}

    lines_preview: List[Dict[str, Any]] = []
    total_debit_dec = Decimal("0")
    total_credit_dec = Decimal("0")
    missing_accounts: List[str] = []

    for ls in line_specs:
        # declared identifier (may be a role name or a direct code)
        declared = None
        if hasattr(ls, "account_code") and getattr(ls, "account_code") is not None:
            declared = str(getattr(ls, "account_code"))
        elif hasattr(ls, "account_id") and getattr(ls, "account_id") is not None:
            declared = str(getattr(ls, "account_id"))

        resolved_code: Optional[str] = None
        resolved_id: Optional[int] = None

        # For preview we accept declared or mapping; try to resolve id if present in DB
        if declared:
            # if declared is a role name and caller provided mapping, use it
            if declared in role_map:
                candidate = role_map[declared]
                resolved_code = candidate
                if candidate in accounts_map:
                    resolved_id = getattr(accounts_map[candidate], "id", None)
            else:
                # treat declared as a direct code string (even if not in DB)
                resolved_code = declared
                if declared in accounts_map:
                    resolved_id = getattr(accounts_map[declared], "id", None)
        else:
            missing_accounts.append("(sin cuenta en línea)")

        # Compute amounts defensively (use Decimal)
        debit_dec = Decimal("0")
        credit_dec = Decimal("0")
        try:
            side = getattr(ls, "side", None)
            amount_expr = getattr(ls, "amount_expr", None)
            if callable(amount_expr) and (side == "debit" or side == "credit"):
                raw = amount_expr(amount, ctx or {})
                # P0-2: use to_decimal_exact to avoid float authority
                val_dec = to_decimal_exact(raw)
                if side == "debit":
                    debit_dec = val_dec
                else:
                    credit_dec = val_dec
            else:
                if hasattr(ls, "debit") and getattr(ls, "debit") is not None:
                    debit_dec = to_decimal_exact(getattr(ls, "debit") or 0)
                if hasattr(ls, "credit") and getattr(ls, "credit") is not None:
                    credit_dec = to_decimal_exact(getattr(ls, "credit") or 0)
                if hasattr(ls, "amount") and getattr(ls, "amount") is not None and side:
                    val_dec = to_decimal_exact(getattr(ls, "amount") or 0)
                    if side == "debit":
                        debit_dec = val_dec
                    else:
                        credit_dec = val_dec
        except Exception:
            LOG.debug("Error computing line amounts for ls=%r", ls, exc_info=True)

        # accumulate precise totals
        total_debit_dec += debit_dec
        total_credit_dec += credit_dec

        # store rounded floats for display in preview lines (quantize to 2 decimals)
        debit_display = float(debit_dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        credit_display = float(credit_dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

        lines_preview.append({
            "account_code": resolved_code,
            "account_id": resolved_id,
            "account_name": getattr(accounts_map.get(resolved_code), "name", None) if resolved_code else None,
            "debit": debit_display,
            "credit": credit_display,
            # P0-2: Store exact values for persistence (not display)
            "_debit_exact": str(debit_dec),
            "_credit_exact": str(credit_dec),
            "description": getattr(ls, "description", "") or "",
            "_declared": declared,
        })

    # decide balanced by comparing totals rounded to 2 decimals (quantize)
    total_debit_q = total_debit_dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    total_credit_q = total_credit_dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    balanced = (total_debit_q == total_credit_q)

    total_debit_out = float(total_debit_q)
    total_credit_out = float(total_credit_q)

    # For preview we only mark missing when template didn't declare anything resolvable.
    if missing_accounts:
        seen = set()
        missing_filtered: List[str] = []
        for c in missing_accounts:
            if c not in seen:
                seen.add(c)
                missing_filtered.append(c)
        return {
            "template": template_key,
            "description": getattr(tpl, "description", None),
            "date": datetime.datetime.now(datetime.timezone.utc).date(),
            "lines": lines_preview,
            "total_debit": total_debit_out,
            "total_credit": total_credit_out,
            "balanced": False,
            "missing_accounts": missing_filtered,
        }

    return {
        "template": template_key,
        "description": getattr(tpl, "description", None),
        "date": datetime.datetime.now(datetime.timezone.utc).date(),
        "lines": lines_preview,
        "total_debit": total_debit_out,
        "total_credit": total_credit_out,
        "balanced": bool(balanced),
        "missing_accounts": [],
    }


# -------------------------
# Trial balance computation
# -------------------------
def _balances_from_sqlite(db_path: Optional[Path], as_of: Optional[str] = None) -> Dict[str, Decimal]:
    """
    Aggregate journalline (debit - credit) grouped by account code (or account_id joined to account.code).
    Supports as_of parameter to filter by date: includes only JournalEntry with date <= as_of.
    
    P0-2 CHANGE: Sums are now calculated in Python using Decimal arithmetic (not SQLite SUM)
    to preserve exact monetary values. Values are read as-is (strings or floats) and converted
    to Decimal before aggregation.
    """
    if db_path is None:
        raise RuntimeError("No sqlite DB path found for fallback")
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info('journalline')")
        cols = [r[1] for r in cur.fetchall()]
        # detect available account columns
        has_account_code = "account_code" in cols
        has_account_id = "account_id" in cols

        debit_col = next((c for c in cols if c.lower() in ("debit", "debe", "cargo")), None)
        credit_col = next((c for c in cols if c.lower() in ("credit", "haber", "abono")), None)

        q_debit = debit_col if debit_col else "0"
        q_credit = credit_col if credit_col else "0"

        balances: Dict[str, Decimal] = {}
        
        # P0-3: Construir condición WHERE para as_of
        # Semántica: as_of="2026-03-31" debe incluir TODO el 31 de marzo (hasta 23:59:59)
        # Implementar como límite exclusivo del día siguiente
        where_clause = ""
        params = []
        if as_of is not None:
            # P0-3: as_of format must be ISO YYYY-MM-DD; no fallback on parsing failure
            try:
                if isinstance(as_of, str):
                    # Parse string "2026-03-31" to date (ISO format required)
                    as_of_date = __import__('datetime').datetime.strptime(as_of[:10], "%Y-%m-%d").date()
                else:
                    as_of_date = as_of if isinstance(as_of, __import__('datetime').date) else as_of.date()
                
                # Next day for exclusive boundary
                next_day = as_of_date + __import__('datetime').timedelta(days=1)
                
                # Use DATE(je.date) < DATE(next_day) for robust date comparison
                where_clause = " WHERE DATE(je.date) < ?"
                params.append(str(next_day))
            except ValueError as e:
                # Explicit failure: as_of must be ISO YYYY-MM-DD
                raise ValueError(
                    f"as_of must be ISO format YYYY-MM-DD (e.g., '2026-03-31'), "
                    f"got: {as_of!r}"
                ) from e
            except Exception as e:
                # Unexpected error: re-raise
                raise ValueError(f"Invalid as_of value: {as_of!r}") from e

        # P0-2: Aggregate in Python with Decimal arithmetic instead of SQLite SUM
        # Read individual lines and sum in Python to preserve exact Decimal values
        
        # Si ambas columnas existen
        if has_account_code and has_account_id:
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='account'")
            has_account_table = bool(cur.fetchone())
            if has_account_table:
                sql = f"""
                    SELECT COALESCE(jl.account_code, a.code, CAST(jl.account_id AS TEXT)) as acct_code,
                           jl.{q_debit}, jl.{q_credit}
                    FROM journalline jl
                    LEFT JOIN account a ON jl.account_id = a.id
                    LEFT JOIN journalentry je ON jl.entry_id = je.id
                    {where_clause}
                    ORDER BY acct_code
                """
                cur.execute(sql, params)
                rows = cur.fetchall()
                
                # Aggregate in Python with Decimal
                current_code = None
                current_sum = Decimal("0")
                for acct_code, debit_val, credit_val in rows:
                    if acct_code is None or acct_code == "":
                        continue
                    # Convert to Decimal (handles both str and float from DB)
                    d = Decimal(str(debit_val or 0))
                    c = Decimal(str(credit_val or 0))
                    line_balance = d - c
                    
                    if acct_code != current_code:
                        if current_code is not None:
                            balances[str(current_code)] = current_sum
                        current_code = acct_code
                        current_sum = line_balance
                    else:
                        current_sum += line_balance
                
                if current_code is not None:
                    balances[str(current_code)] = current_sum
                return balances
            else:
                # Sin tabla account: coalesce account_code o account_id
                sql = f"""
                    SELECT COALESCE(jl.account_code, CAST(jl.account_id AS TEXT)) as acct_code,
                           jl.{q_debit}, jl.{q_credit}
                    FROM journalline jl
                    LEFT JOIN journalentry je ON jl.entry_id = je.id
                    {where_clause}
                    ORDER BY acct_code
                """
                cur.execute(sql, params)
                rows = cur.fetchall()
                
                current_code = None
                current_sum = Decimal("0")
                for acct_code, debit_val, credit_val in rows:
                    if acct_code is None or acct_code == "":
                        continue
                    d = Decimal(str(debit_val or 0))
                    c = Decimal(str(credit_val or 0))
                    line_balance = d - c
                    
                    if acct_code != current_code:
                        if current_code is not None:
                            balances[str(current_code)] = current_sum
                        current_code = acct_code
                        current_sum = line_balance
                    else:
                        current_sum += line_balance
                
                if current_code is not None:
                    balances[str(current_code)] = current_sum
                return balances

        # Si solo account_id existe
        if has_account_id and not has_account_code:
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='account'")
            if cur.fetchone():
                sql = f"""
                    SELECT COALESCE(a.code, CAST(jl.account_id AS TEXT)) as acct_code,
                           jl.{q_debit}, jl.{q_credit}
                    FROM journalline jl
                    LEFT JOIN account a ON jl.account_id = a.id
                    LEFT JOIN journalentry je ON jl.entry_id = je.id
                    {where_clause}
                    ORDER BY acct_code
                """
                cur.execute(sql, params)
                rows = cur.fetchall()
                
                current_code = None
                current_sum = Decimal("0")
                for acct_code, debit_val, credit_val in rows:
                    if acct_code is None or acct_code == "":
                        continue
                    d = Decimal(str(debit_val or 0))
                    c = Decimal(str(credit_val or 0))
                    line_balance = d - c
                    
                    if acct_code != current_code:
                        if current_code is not None:
                            balances[str(current_code)] = current_sum
                        current_code = acct_code
                        current_sum = line_balance
                    else:
                        current_sum += line_balance
                
                if current_code is not None:
                    balances[str(current_code)] = current_sum
                return balances
            else:
                sql = f"""
                    SELECT CAST(jl.account_id AS TEXT) as acct_code,
                           jl.{q_debit}, jl.{q_credit}
                    FROM journalline jl
                    LEFT JOIN journalentry je ON jl.entry_id = je.id
                    {where_clause}
                    ORDER BY acct_code
                """
                cur.execute(sql, params)
                rows = cur.fetchall()
                
                current_code = None
                current_sum = Decimal("0")
                for acct_code, debit_val, credit_val in rows:
                    d = Decimal(str(debit_val or 0))
                    c = Decimal(str(credit_val or 0))
                    line_balance = d - c
                    
                    if acct_code != current_code:
                        if current_code is not None:
                            balances[str(current_code)] = current_sum
                        current_code = acct_code
                        current_sum = line_balance
                    else:
                        current_sum += line_balance
                
                if current_code is not None:
                    balances[str(current_code)] = current_sum
                return balances

        # Si solo account_code existe
        if has_account_code and not has_account_id:
            sql = f"""
                SELECT COALESCE(jl.account_code, '') as acct_code,
                       jl.{q_debit}, jl.{q_credit}
                FROM journalline jl
                LEFT JOIN journalentry je ON jl.entry_id = je.id
                {where_clause}
                ORDER BY acct_code
            """
            cur.execute(sql, params)
            rows = cur.fetchall()
            
            current_code = None
            current_sum = Decimal("0")
            for acct_code, debit_val, credit_val in rows:
                if acct_code is None or acct_code == "":
                    continue
                d = Decimal(str(debit_val or 0))
                c = Decimal(str(credit_val or 0))
                line_balance = d - c
                
                if acct_code != current_code:
                    if current_code is not None:
                        balances[str(current_code)] = current_sum
                    current_code = acct_code
                    current_sum = line_balance
                else:
                    current_sum += line_balance
            
            if current_code is not None:
                balances[str(current_code)] = current_sum
            return balances

        # Nada relevante
        return {}
    finally:
        conn.close()


def _balances_from_libro() -> Dict[str, Decimal]:
    """
    Compute balances using modelos.libro.Libro.compute_balance() if available.
    Defensive handling of DataFrame emptiness.
    """
    if Libro is None:
        return {}
    try:
        libro = Libro()
        df = libro.compute_balance()
    except Exception as e:
        LOG.debug("Libro compute_balance failed: %s", e)
        return {}

    try:
        if df is None:
            return {}
        if hasattr(df, "empty") and df.empty:
            return {}
    except Exception:
        LOG.debug("modelos.libro.compute_balance() returned unexpected type")
        return {}

    balances: Dict[str, Decimal] = {}
    try:
        for idx, row in df.iterrows():
            code = None
            for cand in ("code", "Codigo", "Cuenta", "codigo", "account", "cuenta"):
                try:
                    if hasattr(row, "get"):
                        code = row.get(cand)
                    else:
                        code = getattr(row, cand, None)
                except Exception:
                    code = None
                if code:
                    break
            if not code:
                code = idx

            saldo = None
            for cand in ("saldo", "Saldo", "balance", "saldo_final", "saldo_actual", "amount"):
                try:
                    if hasattr(row, "get"):
                        saldo = row.get(cand)
                    else:
                        saldo = getattr(row, cand, None)
                except Exception:
                    saldo = None
                if saldo is not None:
                    break

            if saldo is None:
                try:
                    items = dict(row) if hasattr(row, "__iter__") else {}
                    for k, v in items.items():
                        if isinstance(v, (int, float, Decimal)):
                            saldo = v
                            break
                except Exception:
                    saldo = 0
            try:
                balances[str(code)] = Decimal(str(saldo or 0))
            except Exception:
                balances[str(code)] = Decimal(0)
    except Exception as e:
        LOG.exception("Error extracting balances from modelos.libro: %s", e)
        return {}
    return balances


def trial_balance(as_of: Optional[str] = None) -> Dict[str, Decimal]:
    """
    P1-4: Return mapping account_code -> Decimal(saldo).
    SQLite is the sole authority. No Libro fallback.
    
    Strategy:
      1) Get balances from SQLite (aggregation).
      2) If SQLite valid but empty: fill with account catalog codes at zero.
      3) If SQLite fails: propagate error (do NOT fallback to Libro).
    """
    db_path = _find_db_path()
    
    # P1-4: SQLite aggregation is the sole source
    balances_sqlite = _balances_from_sqlite(db_path, as_of=as_of)
    
    # Merge account catalog codes with zero saldo for any missing codes
    if db_path:
        try:
            conn = sqlite3.connect(str(db_path))
            try:
                cur = conn.cursor()
                cur.execute("SELECT code FROM account")
                for (code,) in cur.fetchall():
                    if code is None:
                        continue
                    key = str(code)
                    if key not in balances_sqlite:
                        balances_sqlite[key] = Decimal("0")
            finally:
                conn.close()
        except Exception as e:
            LOG.debug("trial_balance: failed to merge account catalog codes: %s", e)
    
    return balances_sqlite


# -------------------------
# Persistence: low-level and wrapper
# -------------------------
def _persist_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Persist an entry dict via ORM only.
    ORM (SQLModel) is the sole persistence authority.
    No raw SQLite fallback.

    entry = {
      "description": str,
      "date": datetime | str | None,
      "doc_ref": str | None,
      "period_id": int | None,
      "posted_by": str | None,
      "state": str,
      "lines": [{"account_code":..., "account_id":..., "debit":..., "credit":...}, ...]
    }

    Returns {"ok": True, "entry_id": id} or {"ok": False, "error": msg}.
    """
    desc = entry.get("description", "") or ""
    lines = entry.get("lines", []) or []

    # P1-1: ORM as sole persistence authority
    if JournalEntry is None or JournalLine is None or get_session is None:
        return {"ok": False, "error": "ORM infrastructure (JournalEntry/JournalLine/get_session) not available"}

    try:
        with get_session() as s:
            # Resolve and validate accounts within same session
            resolved_accounts: Dict[int, Account] = {}  # line_idx -> Account

            for ln_idx, ln in enumerate(lines):
                account_id = ln.get("account_id")
                account_code = ln.get("account_code")

                # Both missing: invalid
                if not account_id and not account_code:
                    return {"ok": False, "error": f"Línea {ln_idx}: ni account_id ni account_code proporcionados"}

                # Resolve account_id (if provided)
                account = None
                if account_id:
                    try:
                        account = s.get(Account, int(account_id))
                    except Exception:
                        account = None
                    if not account:
                        return {"ok": False, "error": f"Línea {ln_idx}: account_id {account_id} no existe"}

                # Resolve account_code (if provided)
                if account_code:
                    from sqlmodel import select
                    try:
                        sel = select(Account).where(Account.code == str(account_code))
                        acc_by_code = s.exec(sel).one_or_none()
                    except Exception:
                        acc_by_code = None
                    if not acc_by_code:
                        return {"ok": False, "error": f"Línea {ln_idx}: account_code '{account_code}' no existe"}

                    # If both provided: verify same account
                    if account and acc_by_code.id != account.id:
                        return {"ok": False, "error": f"Línea {ln_idx}: account_id {account_id} y account_code '{account_code}' refieren cuentas distintas"}

                    account = acc_by_code

                if not account:
                    return {"ok": False, "error": f"Línea {ln_idx}: no se pudo resolver cuenta"}

                resolved_accounts[ln_idx] = account

            # Build JournalEntry with correct fields
            resolved_date = entry.get("date")
            if resolved_date is None:
                resolved_date = datetime.datetime.now(datetime.timezone.utc)
            elif isinstance(resolved_date, str):
                try:
                    # Parse ISO format strictly
                    resolved_date = datetime.datetime.fromisoformat(resolved_date.replace("Z", "+00:00"))
                except Exception:
                    return {"ok": False, "error": f"Invalid date format: {resolved_date}"}
            elif isinstance(resolved_date, datetime.date) and not isinstance(resolved_date, datetime.datetime):
                # Convert date to datetime
                resolved_date = datetime.datetime.combine(resolved_date, datetime.time.min, tzinfo=datetime.timezone.utc)

            # P1-1: ONE TRANSACTION for JournalEntry + JournalLines
            je = JournalEntry(
                date=resolved_date,
                concept=desc,
                doc_ref=entry.get("doc_ref"),
                period_id=entry.get("period_id"),
                posted_by=entry.get("posted_by"),
                state=entry.get("state", "draft"),
            )
            s.add(je)
            s.flush()  # Get je.id without commit

            # Add all JournalLines
            for ln_idx, ln in enumerate(lines):
                account = resolved_accounts[ln_idx]
                # P0-2: Use to_decimal_exact for safe monetary conversion
                jl = JournalLine(
                    entry_id=je.id,
                    account_id=account.id,
                    account_code=account.code,
                    debit=str(to_decimal_exact(ln.get("debit") or 0)),
                    credit=str(to_decimal_exact(ln.get("credit") or 0)),
                    description=ln.get("description"),
                )
                s.add(jl)

            # SINGLE COMMIT for entire transaction
            s.commit()
            return {"ok": True, "entry_id": je.id}

    except Exception as e:
        LOG.debug("ORM persistence failed: %s", exc_info=True)
        return {"ok": False, "error": f"Error persisting entry: {str(e)}"}


# -------------------------
# P0-2: Exact monetary conversion utility
# -------------------------


# -------------------------
# Public wrapper: post_entry
# -------------------------
def post_entry(first: Any, amount: Optional[float] = None, ctx: Optional[Dict[str, Any]] = None, user: Optional[str] = None) -> Any:
    """
    Two usages supported:
    - post_entry(template_key: str, amount: float, ctx: dict, user: Optional[str]) -> entry_id (int)
    - post_entry(entry_dict: dict) -> result dict (delegates to _persist_entry)

    For template mode, it builds preview and persists generated lines.
    """
    # If first is dict-like, delegate to persistence
    if isinstance(first, dict):
        return _persist_entry(first)

    # template mode
    # P0-2: Convert amount to Decimal exacto for monetary calculations
    template_key = first
    amount_decimal = to_decimal_exact(amount or 0)
    ctx = ctx or {}

    # Pass Decimal directly to generate_preview (not float)
    preview = generate_preview(template_key, amount_decimal, ctx=ctx)
    if not isinstance(preview, dict):
        raise RuntimeError("generate_preview did not return a preview dict")

    if not preview.get("balanced", False):
        missing = preview.get("missing_accounts", [])
        if missing:
            raise RuntimeError(f"Generated preview not persisted: missing accounts: {missing}")
        raise RuntimeError("Generated preview is not balanced; aborting post")

    # build entry dict
    entry = {
        "description": preview.get("description") or f"{template_key} {ctx.get('desc') or ''}".strip(),
        "lines": [],
    }
    for ln in preview.get("lines", []):
        # P0-2: Use exact values (_debit_exact, _credit_exact) if available, not display floats
        debit_val = ln.get("_debit_exact") or ln.get("debit")
        credit_val = ln.get("_credit_exact") or ln.get("credit")
        entry["lines"].append({
            "account_code": ln.get("account_code"),
            "account_id": ln.get("account_id"),
            "debit": debit_val,
            "credit": credit_val,
            "description": ln.get("description"),
        })

    res = _persist_entry(entry)
    if not res.get("ok"):
        raise RuntimeError(f"Failed to persist entry: {res.get('error')}")
    return res.get("entry_id")