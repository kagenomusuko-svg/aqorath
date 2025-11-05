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
                try:
                    val_dec = Decimal(str(raw))
                except (InvalidOperation, TypeError, ValueError):
                    val_dec = Decimal(float(raw or 0))
                if side == "debit":
                    debit_dec = val_dec
                else:
                    credit_dec = val_dec
            else:
                if hasattr(ls, "debit") and getattr(ls, "debit") is not None:
                    try:
                        debit_dec = Decimal(str(getattr(ls, "debit") or 0))
                    except Exception:
                        debit_dec = Decimal(float(getattr(ls, "debit") or 0))
                if hasattr(ls, "credit") and getattr(ls, "credit") is not None:
                    try:
                        credit_dec = Decimal(str(getattr(ls, "credit") or 0))
                    except Exception:
                        credit_dec = Decimal(float(getattr(ls, "credit") or 0))
                if hasattr(ls, "amount") and getattr(ls, "amount") is not None and side:
                    try:
                        val_dec = Decimal(str(getattr(ls, "amount") or 0))
                    except Exception:
                        val_dec = Decimal(float(getattr(ls, "amount") or 0))
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
def _balances_from_sqlite(db_path: Optional[Path]) -> Dict[str, Decimal]:
    """
    Aggregate journalline (debit - credit) grouped by account code (or account_id joined to account.code).
    Improved to handle cases where journalline has both account_code and account_id:
    it will prefer the explicit account_code when present, otherwise use the joined account.code,
    otherwise fallback to the textified account_id.
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

        # If both columns exist, use a COALESCE that prefers explicit account_code,
        # then joined account.code, then account_id as text.
        if has_account_code and has_account_id:
            # join to account to obtain a.code when account_code NULL
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='account'")
            has_account_table = bool(cur.fetchone())
            if has_account_table:
                sql = f"""
                    SELECT COALESCE(jl.account_code, a.code, CAST(jl.account_id AS TEXT)) as acct_code,
                           SUM(COALESCE(jl.{q_debit},0) - COALESCE(jl.{q_credit},0)) as saldo
                    FROM journalline jl
                    LEFT JOIN account a ON jl.account_id = a.id
                    GROUP BY acct_code
                """
                cur.execute(sql)
                rows = cur.fetchall()
                for acct_code, saldo in rows:
                    if acct_code is None or acct_code == "":
                        continue
                    balances[str(acct_code)] = Decimal(str(saldo or 0))
                return balances
            else:
                # no account table: fallback to coalesce account_code or account_id text
                sql = f"""
                    SELECT COALESCE(account_code, CAST(account_id AS TEXT)) as acct_code,
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

        # If only account_id exists (no account_code column), join to account to get code when possible
        if has_account_id and not has_account_code:
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='account'")
            if cur.fetchone():
                q = f"""
                    SELECT COALESCE(a.code, CAST(jl.account_id AS TEXT)) as acct_code,
                           SUM(COALESCE(jl.{q_debit},0) - COALESCE(jl.{q_credit},0)) as saldo
                    FROM journalline jl
                    LEFT JOIN account a ON jl.account_id = a.id
                    GROUP BY acct_code
                """
                cur.execute(q)
                rows = cur.fetchall()
                for acct_code, saldo in rows:
                    if acct_code is None or acct_code == "":
                        continue
                    balances[str(acct_code)] = Decimal(str(saldo or 0))
                return balances
            else:
                q = f"""
                    SELECT CAST(account_id AS TEXT) as acct_code,
                           SUM(COALESCE({q_debit},0) - COALESCE({q_credit},0)) as saldo
                    FROM journalline
                    GROUP BY acct_code
                """
                cur.execute(q)
                rows = cur.fetchall()
                for acct_code, saldo in rows:
                    balances[str(acct_code)] = Decimal(str(saldo or 0))
                return balances

        # If only account_code exists (no account_id), group by account_code directly
        if has_account_code and not has_account_id:
            sql = f"""
                SELECT COALESCE(account_code, '') as acct_code,
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

        # Nothing relevant found
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
    Return mapping account_code -> Decimal(saldo).
    Strategy:
      1) Try sqlite aggregation first.
      2) If sqlite returns empty, try modelos.libro.Libro.
      3) Always include account catalog codes with zero saldo if they are missing from aggregation.
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

        # Merge account catalog codes with zero saldo for any missing codes
        try:
            if db_path:
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

        if balances_sqlite:
            return balances_sqlite
    except Exception as e:
        LOG.debug("trial_balance sqlite attempt raised: %s", e)

    # 2) libro fallback
    try:
        balances_libro = _balances_from_libro()
        if balances_libro:
            # also merge catalog zeros if any missing
            try:
                db_path = _find_db_path()
                if db_path:
                    conn = sqlite3.connect(str(db_path))
                    try:
                        cur = conn.cursor()
                        cur.execute("SELECT code FROM account")
                        for (code,) in cur.fetchall():
                            if code is None:
                                continue
                            key = str(code)
                            if key not in balances_libro:
                                balances_libro[key] = Decimal("0")
                    finally:
                        conn.close()
            except Exception:
                pass
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

    Validates accounts exist (sqlite check preferred for account_id), then inserts via ORM if available else sqlite.
    Returns {"ok": True, "entry_id": id} or {"ok": False, "error": msg}.
    """
    desc = entry.get("description", "") or ""
    lines = entry.get("lines", []) or []

    def _verify_accounts(lines_list: List[Dict[str, Any]]) -> List[str]:
        """
        Verify referenced accounts exist where necessary.
        - If account_id provided -> verify that id exists (sqlite preferred).
        - If only account_code provided -> allow (we will persist account_code text).
        Returns list of missing identifiers (strings) for account_id checks only.
        """
        missing: List[str] = []
        # 1) sqlite check first for account_id
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
                        # if only account_code present, we accept it for persistence (no creation)
                    return missing
                finally:
                    conn.close()
        except Exception:
            LOG.debug("sqlite account-id verification failed; will fallback to ORM check", exc_info=True)

        # 2) ORM fallback for account_id
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
                return missing
        except Exception:
            LOG.debug("ORM account-id verification failed as well", exc_info=True)

        # If neither method ran successfully, raise to signal verification cannot be done
        raise RuntimeError("No se pudo verificar la existencia de cuentas por id (ni sqlite ni ORM disponibles).")

    # perform verification (only checks account_id existence)
    try:
        missing = _verify_accounts(lines)
    except Exception as e:
        return {"ok": False, "error": f"Error verifying accounts: {e}"}
    if missing:
        return {"ok": False, "error": "Cuentas no encontradas (por id): " + ", ".join(missing)}

    # ORM insertion if available: try to include account_code if account_id not present
    if JournalEntry is not None and JournalLine is not None and get_session is not None:
        try:
            with get_session() as s:
                je = JournalEntry(description=desc, created_at=datetime.datetime.now(datetime.timezone.utc))
                s.add(je)
                s.commit()
                s.refresh(je)
                for ln in lines:
                    account_id = ln.get("account_id")
                    account_code = ln.get("account_code")
                    if not account_id and account_code:
                        # try to resolve account_id by code; if not found, we'll set account_code on line
                        try:
                            sel = __import__("sqlmodel").sql.select(Account).where(Account.code == str(account_code))
                            acc = s.exec(sel).one_or_none()
                            if acc:
                                account_id = acc.id
                        except Exception:
                            account_id = None
                    # create JournalLine, prefer account_id but allow account_code property if model supports it
                    jl_kwargs: Dict[str, Any] = {
                        "entry_id": je.id,
                        "debit": float(ln.get("debit") or 0),
                        "credit": float(ln.get("credit") or 0),
                        "description": ln.get("description"),
                    }
                    if account_id:
                        jl_kwargs["account_id"] = int(account_id)
                    else:
                        # set account_code if model has field. We'll attempt to set attribute name 'account_code'
                        if hasattr(JournalLine, "account_code"):
                            jl_kwargs["account_code"] = str(account_code) if account_code is not None else None
                        else:
                            # If model doesn't have account_code, still proceed by leaving account_id None
                            jl_kwargs["account_id"] = None
                    jl = JournalLine(**jl_kwargs)
                    s.add(jl)
                s.commit()
            return {"ok": True, "entry_id": je.id}
        except Exception:
            LOG.debug("ORM persist failed, falling back to sqlite", exc_info=True)

    # sqlite fallback insertion (preferred in tests)
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

        # Inspect entry table columns dynamically and build insert columns accordingly.
        cur.execute(f"PRAGMA table_info('{entry_table}')")
        pragma_rows = cur.fetchall()  # rows: (cid, name, type, notnull, dflt_value, pk)

        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
        today_iso = datetime.datetime.now(datetime.timezone.utc).date().isoformat()

        insert_cols = []
        insert_vals = []

        # Build values for columns that are present and required.
        # We will fill known semantic columns first, then ensure any NOT NULL w/o default gets a sensible default.
        for cid, colname, coltype, notnull, dflt_value, pk in pragma_rows:
            # skip pk autoincrement (usually INTEGER PRIMARY KEY)
            if pk:
                continue
            lname = colname.lower()

            # Known semantic columns
            if lname in ("description", "name", "concept", "title", "label"):
                insert_cols.append(colname)
                insert_vals.append(desc)
                continue
            if lname == "date":
                insert_cols.append(colname)
                insert_vals.append(today_iso)
                continue
            if lname in ("created_at", "created", "timestamp", "ts"):
                insert_cols.append(colname)
                insert_vals.append(now_iso)
                continue

            # If column already has a default in schema, skip it (DB will use default)
            if dflt_value is not None:
                continue

            # If column is NOT NULL without default, supply a reasonable fallback based on declared type
            if notnull:
                ctype = (coltype or "").upper()
                if "CHAR" in ctype or "CLOB" in ctype or "TEXT" in ctype:
                    # likely a 'state' or status field
                    insert_cols.append(colname)
                    insert_vals.append("posted")
                elif "INT" in ctype or "NUM" in ctype:
                    insert_cols.append(colname)
                    insert_vals.append(0)
                elif "DATE" in ctype or "TIME" in ctype:
                    insert_cols.append(colname)
                    insert_vals.append(now_iso)
                else:
                    # generic fallback for unknown types
                    insert_cols.append(colname)
                    insert_vals.append("")

        # Perform insert: if we have columns to insert, insert them; else use DEFAULT VALUES
        if not insert_cols:
            try:
                cur.execute(f"INSERT INTO {entry_table} DEFAULT VALUES")
                entry_id = cur.lastrowid
            except Exception as e:
                conn.rollback()
                return {"ok": False, "error": f"No se pudo insertar en {entry_table}: {e}"}
        else:
            placeholders = ",".join("?" for _ in insert_cols)
            cols_sql = ",".join(insert_cols)
            try:
                cur.execute(f"INSERT INTO {entry_table} ({cols_sql}) VALUES ({placeholders})", tuple(insert_vals))
                entry_id = cur.lastrowid
            except Exception as e:
                conn.rollback()
                return {"ok": False, "error": f"Error inserting into {entry_table}: {e}"}

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

        # Inspect journalline columns to decide which columns to insert
        cur.execute(f"PRAGMA table_info('{jl_table}')")
        jl_cols = [r[1] for r in cur.fetchall()]
        has_account_code_col = "account_code" in jl_cols
        has_account_id_col = "account_id" in jl_cols

        for ln in lines:
            acct_id = ln.get("account_id")
            account_code = ln.get("account_code")
            if not acct_id and account_code:
                # try to resolve id by code; if not found, we will insert account_code text
                cur.execute("SELECT id FROM account WHERE code = ? LIMIT 1", (str(account_code),))
                r = cur.fetchone()
                if r:
                    acct_id = r[0]
            # Build insertion columns dynamically
            insert_cols = ["entry_id"]
            insert_vals = [entry_id]
            if has_account_id_col:
                insert_cols.append("account_id")
                insert_vals.append(int(acct_id) if acct_id is not None else None)
            if has_account_code_col:
                insert_cols.append("account_code")
                insert_vals.append(str(account_code) if account_code is not None else None)
            # add debit, credit, description, created_at when present in table
            if "debit" in jl_cols:
                insert_cols.append("debit"); insert_vals.append(float(ln.get("debit") or 0))
            if "credit" in jl_cols:
                insert_cols.append("credit"); insert_vals.append(float(ln.get("credit") or 0))
            if "description" in jl_cols:
                insert_cols.append("description"); insert_vals.append(ln.get("description"))
            if "created_at" in jl_cols:
                insert_cols.append("created_at"); insert_vals.append(now_iso)

            # If account_id is required and not provided (and account_code not present), abort
            if ("account_id" in jl_cols) and ("account_code" not in jl_cols) and not acct_id:
                conn.rollback()
                return {"ok": False, "error": f"Cuenta no encontrada para línea y no hay columna account_code para almacenar el code: {ln}"}

            placeholders = ",".join("?" for _ in insert_cols)
            cols_sql = ",".join(insert_cols)
            sql = f"INSERT INTO {jl_table} ({cols_sql}) VALUES ({placeholders})"
            cur.execute(sql, tuple(insert_vals))
        conn.commit()
        return {"ok": True, "entry_id": entry_id}
    finally:
        conn.close()


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