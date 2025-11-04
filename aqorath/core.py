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
from pathlib import Path
from typing import Any, Dict, Optional, List
from types import SimpleNamespace

LOG = logging.getLogger(__name__)
LOG.addHandler(logging.NullHandler())

# Defensive imports to avoid circular import problems and allow sqlite fallback
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
    Locate sqlite DB. Prefer env AQORATH_DB then common locations used in tests.
    """
    cand = os.environ.get("AQORATH_DB")
    if cand:
        p = Path(cand)
        if p.exists():
            return p
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
def generate_preview(template_key: str, amount: float, ctx: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Build a preview of the journal entry lines produced by a template.

    Resolves account roles via ctx.get('account_codes', {}) before returning the preview.
    If any account referenced by the template cannot be resolved to an existing account code
    (in the DB) the preview will include 'missing_accounts' and 'balanced' will be False.
    This prevents inventing accounts and avoids persisting invalid entries.
    """
    ctx = ctx or {}
    # If templates module not available, return safe minimal preview-like dict
    if get_template is None:
        return {
            "template": template_key,
            "description": None,
            "date": datetime.datetime.utcnow().date(),
            "lines": [],
            "total_debit": 0.0,
            "total_credit": 0.0,
            "balanced": True,
            "missing_accounts": [],
        }

    tpl = get_template(template_key)
    line_specs = tpl.create_lines(amount, ctx or {})

    accounts_map = _load_accounts_map()  # code -> obj
    # mapping provided by caller: role -> account_code strings
    try:
        role_map: Dict[str, str] = dict((k, str(v)) for k, v in (ctx.get("account_codes") or {}).items())
    except Exception:
        role_map = {}

    lines_preview: List[Dict[str, Any]] = []
    total_debit = 0.0
    total_credit = 0.0
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

        if declared:
            # If declared matches an account code present in DB, use it
            if declared in accounts_map:
                resolved_code = declared
                resolved_id = getattr(accounts_map[declared], "id", None)
            else:
                # If declared is a role mapping provided by ctx, resolve via role_map
                if declared in role_map:
                    candidate = role_map[declared]
                    if candidate in accounts_map:
                        resolved_code = candidate
                        resolved_id = getattr(accounts_map[candidate], "id", None)
                    else:
                        missing_accounts.append(candidate)
                else:
                    # Try numeric-looking declared code
                    if str(declared).isdigit() and str(declared) in accounts_map:
                        resolved_code = str(declared)
                        resolved_id = getattr(accounts_map[resolved_code], "id", None)
                    else:
                        # declared could be direct code not present in DB -> missing
                        missing_accounts.append(declared)
        else:
            missing_accounts.append("(sin cuenta en línea)")

        # Compute amounts defensively
        debit = 0.0
        credit = 0.0
        try:
            side = getattr(ls, "side", None)
            amount_expr = getattr(ls, "amount_expr", None)
            if callable(amount_expr) and (side == "debit" or side == "credit"):
                val = float(amount_expr(amount, ctx or {}))
                if side == "debit":
                    debit = val
                else:
                    credit = val
            else:
                if hasattr(ls, "debit") and getattr(ls, "debit") is not None:
                    debit = float(getattr(ls, "debit") or 0)
                if hasattr(ls, "credit") and getattr(ls, "credit") is not None:
                    credit = float(getattr(ls, "credit") or 0)
                if hasattr(ls, "amount") and getattr(ls, "amount") is not None and side:
                    val = float(getattr(ls, "amount") or 0)
                    if side == "debit":
                        debit = val
                    else:
                        credit = val
        except Exception:
            LOG.debug("Error computing line amounts for ls=%r", ls, exc_info=True)

        total_debit += round(debit, 2)
        total_credit += round(credit, 2)

        lines_preview.append({
            "account_code": resolved_code,
            "account_id": resolved_id,
            "account_name": getattr(accounts_map.get(resolved_code), "name", None) if resolved_code else None,
            "debit": round(debit, 2),
            "credit": round(credit, 2),
            "description": getattr(ls, "description", "") or "",
            "_declared": declared,
        })

    balance_ok = math.isclose(total_debit, total_credit, rel_tol=1e-6)

    # If missing accounts exist, flag them and avoid returning balanced preview.
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
            "date": datetime.datetime.utcnow().date(),
            "lines": lines_preview,
            "total_debit": round(total_debit, 2),
            "total_credit": round(total_credit, 2),
            "balanced": False,
            "missing_accounts": missing_filtered,
        }

    return {
        "template": template_key,
        "description": getattr(tpl, "description", None),
        "date": datetime.datetime.utcnow().date(),
        "lines": lines_preview,
        "total_debit": round(total_debit, 2),
        "total_credit": round(total_credit, 2),
        "balanced": bool(balance_ok),
        "missing_accounts": [],
    }


# -------------------------
# Trial balance computation
# -------------------------
def _balances_from_sqlite(db_path: Optional[Path]) -> Dict[str, Decimal]:
    """
    Aggregate journalline (debit - credit) grouped by account code (or account_id joined to account.code).
    """
    if db_path is None:
        raise RuntimeError("No sqlite DB path found for fallback")
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info('journalline')")
        cols = [r[1] for r in cur.fetchall()]
        acct_col = None
        for cand in ("account_code", "account", "account_id", "cuenta", "codigo"):
            if cand in cols:
                acct_col = cand
                break
        debit_col = next((c for c in cols if c.lower() in ("debit", "debe", "cargo")), None)
        credit_col = next((c for c in cols if c.lower() in ("credit", "haber", "abono")), None)
        if acct_col is None:
            return {}

        balances: Dict[str, Decimal] = {}
        q_debit = debit_col if debit_col else "0"
        q_credit = credit_col if credit_col else "0"

        if acct_col == "account_id":
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='account'")
            if cur.fetchone():
                sql = f"""
                    SELECT COALESCE(a.code, CAST(jl.account_id AS TEXT)) as acct_code,
                           SUM(COALESCE(jl.{q_debit},0) - COALESCE(jl.{q_credit},0)) as saldo
                    FROM journalline jl
                    LEFT JOIN account a ON jl.account_id = a.id
                    GROUP BY acct_code
                """
                cur.execute(sql)
                rows = cur.fetchall()
                for acct_code, saldo in rows:
                    balances[str(acct_code)] = Decimal(str(saldo or 0))
                return balances
            else:
                sql = f"""
                    SELECT CAST(account_id AS TEXT) as acct_code,
                           SUM(COALESCE({q_debit},0) - COALESCE({q_credit},0)) as saldo
                    FROM journalline
                    GROUP BY acct_code
                """
                cur.execute(sql)
                rows = cur.fetchall()
                for acct_code, saldo in rows:
                    balances[str(acct_code)] = Decimal(str(saldo or 0))
                return balances
        else:
            sql = f"""
                SELECT COALESCE({acct_col}, '') as acct_code,
                       SUM(COALESCE({q_debit},0) - COALESCE({q_credit},0)) as saldo
                FROM journalline
                GROUP BY acct_code
            """
            cur.execute(sql)
            rows = cur.fetchall()
            for acct_code, saldo in rows:
                if acct_code is None or acct_code == "":
                    continue
                balances[str(acct_code)] = Decimal(str(saldo or 0))
            return balances
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
    Return mapping account_code -> Decimal(saldo).
    Strategy:
      1) Try sqlite aggregation first.
      2) If sqlite returns empty, try modelos.libro.Libro.
      3) If both empty, return account codes with zero saldo (no creation).
    """
    # 1) sqlite
    try:
        db_path = _find_db_path()
        balances_sqlite = {}
        try:
            balances_sqlite = _balances_from_sqlite(db_path)
        except Exception as e:
            LOG.debug("trial_balance: sqlite aggregation failed: %s", e)
            balances_sqlite = {}

        if balances_sqlite:
            return balances_sqlite
    except Exception as e:
        LOG.debug("trial_balance sqlite attempt raised: %s", e)

    # 2) libro
    try:
        balances_libro = _balances_from_libro()
        if balances_libro:
            return balances_libro
    except Exception as e:
        LOG.debug("trial_balance: Libro fallback failed: %s", e)

    # 3) final fallback: return account codes with zero saldo (do not create accounts)
    try:
        db_path = _find_db_path()
        if db_path:
            conn = sqlite3.connect(str(db_path))
            try:
                cur = conn.cursor()
                cur.execute("SELECT code FROM account")
                rows = cur.fetchall()
                zeros: Dict[str, Decimal] = {}
                for (code,) in rows:
                    if code is None:
                        continue
                    zeros[str(code)] = Decimal("0")
                if zeros:
                    LOG.info("trial_balance: returning account codes with zero saldo as final fallback")
                    return zeros
            finally:
                conn.close()
    except Exception as e:
        LOG.debug("trial_balance final fallback failed: %s", e)

    return {}


# -------------------------
# Persistence: low-level and wrapper
# -------------------------
def _persist_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Persist an entry dict:
      entry = {"description": str, "lines": [ {"account_code":..., "account_id":..., "debit":..., "credit":..., "description":...}, ... ]}

    Validates accounts exist (sqlite check preferred), then inserts via ORM if available else sqlite.
    Returns {"ok": True, "entry_id": id} or {"ok": False, "error": msg}.
    """
    desc = entry.get("description", "") or ""
    lines = entry.get("lines", []) or []

    def _verify_accounts(lines_list: List[Dict[str, Any]]) -> List[str]:
        """
        Verify referenced accounts exist. Prefer sqlite direct check (deterministic for tests),
        fallback to ORM/SQLModel verification if sqlite not available.
        Returns list of missing identifiers (strings).
        """
        missing: List[str] = []
        # 1) sqlite check first
        try:
            db = _find_db_path()
            if db is not None and Path(db).exists():
                conn = sqlite3.connect(str(db))
                try:
                    cur = conn.cursor()
                    for ln in lines_list:
                        if ln.get("account_id"):
                            cur.execute("SELECT 1 FROM account WHERE id = ? LIMIT 1", (int(ln["account_id"]),))
                            if not cur.fetchone():
                                missing.append(str(ln.get("account_id")))
                        elif ln.get("account_code"):
                            cur.execute("SELECT 1 FROM account WHERE code = ? LIMIT 1", (str(ln["account_code"]),))
                            if not cur.fetchone():
                                missing.append(str(ln["account_code"]))
                        else:
                            missing.append("(sin cuenta en línea)")
                    return missing
                finally:
                    conn.close()
        except Exception:
            LOG.debug("sqlite account verification failed; will fallback to ORM check", exc_info=True)

        # 2) ORM fallback
        try:
            if Account is not None and get_session is not None:
                with get_session() as s:
                    for ln in lines_list:
                        if ln.get("account_id"):
                            try:
                                acc = s.get(Account, int(ln["account_id"]))
                            except Exception:
                                acc = None
                            if not acc:
                                missing.append(str(ln.get("account_id")))
                        elif ln.get("account_code"):
                            try:
                                sel = __import__("sqlmodel").sql.select(Account).where(Account.code == str(ln["account_code"]))
                                acc = s.exec(sel).one_or_none()
                            except Exception:
                                acc = None
                            if not acc:
                                missing.append(str(ln["account_code"]))
                        else:
                            missing.append("(sin cuenta en línea)")
                return missing
        except Exception:
            LOG.debug("ORM account verification failed as well", exc_info=True)

        # If neither method ran successfully, raise to signal verification cannot be done
        raise RuntimeError("No se pudo verificar la existencia de cuentas (ni sqlite ni ORM disponibles).")

    # perform verification
    try:
        missing = _verify_accounts(lines)
    except Exception as e:
        return {"ok": False, "error": f"Error verifying accounts: {e}"}
    if missing:
        return {"ok": False, "error": "Cuentas no encontradas: " + ", ".join(missing)}

    # ORM insertion if available
    if JournalEntry is not None and JournalLine is not None and get_session is not None:
        try:
            with get_session() as s:
                je = JournalEntry(description=desc, created_at=datetime.datetime.utcnow())
                s.add(je)
                s.commit()
                s.refresh(je)
                for ln in lines:
                    account_id = ln.get("account_id")
                    if not account_id and ln.get("account_code"):
                        try:
                            sel = __import__("sqlmodel").sql.select(Account).where(Account.code == str(ln["account_code"]))
                            acc = s.exec(sel).one_or_none()
                            if acc:
                                account_id = acc.id
                        except Exception:
                            account_id = None
                    if not account_id:
                        s.rollback()
                        return {"ok": False, "error": f"Cuenta no encontrada para línea: {ln}"}
                    jl = JournalLine(
                        entry_id=je.id,
                        account_id=int(account_id),
                        debit=float(ln.get("debit") or 0),
                        credit=float(ln.get("credit") or 0),
                        description=ln.get("description"),
                    )
                    s.add(jl)
                s.commit()
            return {"ok": True, "entry_id": je.id}
        except Exception:
            LOG.debug("ORM persist failed, falling back to sqlite", exc_info=True)

    # sqlite fallback insertion
    db = _find_db_path()
    if db is None:
        return {"ok": False, "error": "No se encontró base de datos para persistir entry."}
    conn = sqlite3.connect(str(db))
    try:
        cur = conn.cursor()
        # find entry table name
        entry_table = None
        for candidate in ("entry", "journalentry", "journal_entry"):
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?;", (candidate,))
            if cur.fetchone():
                entry_table = candidate
                break
        if not entry_table:
            return {"ok": False, "error": "No se encontró tabla de entries en la DB."}
        now = datetime.datetime.utcnow().isoformat()
        cur.execute(f"INSERT INTO {entry_table} (description, created_at) VALUES (?, ?)", (desc, now))
        entry_id = cur.lastrowid

        # find journalline table
        jl_table = None
        for candidate in ("journalline", "journal_line", "line", "journalentryline"):
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?;", (candidate,))
            if cur.fetchone():
                jl_table = candidate
                break
        if not jl_table:
            conn.rollback()
            return {"ok": False, "error": "No se encontró tabla journalline en la DB."}

        for ln in lines:
            acct_id = ln.get("account_id")
            if not acct_id and ln.get("account_code"):
                cur.execute("SELECT id FROM account WHERE code = ? LIMIT 1", (str(ln["account_code"]),))
                r = cur.fetchone()
                if r:
                    acct_id = r[0]
            if not acct_id:
                conn.rollback()
                return {"ok": False, "error": f"Cuenta no encontrada para línea: {ln}"}
            cur.execute(
                f"INSERT INTO {jl_table} (entry_id, account_id, debit, credit, description, created_at) VALUES (?,?,?,?,?,?)",
                (entry_id, int(acct_id), float(ln.get("debit") or 0), float(ln.get("credit") or 0), ln.get("description"), now),
            )
        conn.commit()
        return {"ok": True, "entry_id": entry_id}
    finally:
        conn.close()


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
    template_key = first
    amount = float(amount or 0)
    ctx = ctx or {}

    preview = generate_preview(template_key, amount, ctx=ctx)
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
        entry["lines"].append({
            "account_code": ln.get("account_code"),
            "account_id": ln.get("account_id"),
            "debit": ln.get("debit"),
            "credit": ln.get("credit"),
            "description": ln.get("description"),
        })

    res = _persist_entry(entry)
    if not res.get("ok"):
        raise RuntimeError(f"Failed to persist entry: {res.get('error')}")
    return res.get("entry_id")