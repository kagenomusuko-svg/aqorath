# NOTE: Reemplaza o añade estas funciones en aqorath/core.py
from __future__ import annotations
from decimal import Decimal
from typing import Dict, Optional, Any, List
from pathlib import Path
import json
import logging
import os
import sqlite3
import datetime

# --- IMPORTS requeridos por el parche ---
from sqlmodel import select, Session
from aqorath.accounting_rules import load_catalog, compute_resultado_ejercicio
from decimal import Decimal
# ------------------------------------------------------------------------------

LOG = logging.getLogger(__name__)
LOG.addHandler(logging.NullHandler())

# Defensive imports to avoid circular imports and to allow sqlite fallback
try:
    from aqorath.storage import get_session
except Exception:
    get_session = None

try:
    from aqorath.models import Account, JournalEntry, JournalLine  # type: ignore
except Exception:
    Account = None
    JournalEntry = None
    JournalLine = None


# -----------------------------------------------------------------------------
# generate_preview: compatibilidad con llamadas de tests (amount posicional + ctx=...)
# -----------------------------------------------------------------------------
def generate_preview(template_name: str, *args, ctx: Optional[Dict[str, Any]] = None, **kwargs) -> str:
    context: Dict[str, Any] = {}
    if args:
        context["amount"] = args[0]
    if ctx and isinstance(ctx, dict):
        context.update(ctx)
    context.update(kwargs)

    try:
        from jinja2 import Environment, FileSystemLoader, select_autoescape
    except Exception:
        try:
            return f"Preview {template_name} - context: {json.dumps(context, default=str)}"
        except Exception:
            return f"Preview {template_name} - context unavailable"

    templates_dir = Path("templates")
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape(["html", "xml"]),
    )

    candidates = [template_name, f"{template_name}.html"]
    tmpl = None
    for name in candidates:
        try:
            tmpl = env.get_template(name)
            break
        except Exception:
            tmpl = None

    if tmpl is None:
        return f"Template {template_name} not found."

    try:
        return tmpl.render(**context)
    except Exception as e:
        LOG.exception("Error rendering template %s: %s", template_name, e)
        return f"Error rendering template {template_name}: {e}"

# -----------------------------------------------------------------------------
# trial_balance: prefer sqlite aggregation (determinista para tests)
# -----------------------------------------------------------------------------
def _find_db_path() -> Optional[Path]:
    cand = os.environ.get("AQORATH_DB")
    if cand and Path(cand).exists():
        return Path(cand)
    for p in ("tests/test.db", "datos/aqorath.db", "aqorath.db", "test.db"):
        if Path(p).exists():
            return Path(p)
    return None

def _balances_from_sqlite(db_path: Optional[Path]) -> Dict[str, Decimal]:
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
            raise RuntimeError(f"Could not detect account column in journalline (checked: {cols})")

        balances: Dict[str, Decimal] = {}
        if acct_col == "account_id":
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='account'")
            if cur.fetchone():
                q_debit = debit_col if debit_col else "0"
                q_credit = credit_col if credit_col else "0"
                sql = f"""
                    SELECT COALESCE(a.code, CAST(jl.account_id AS TEXT)) as acct_code,
                           SUM(COALESCE(jl.{q_debit},0) - COALESCE(jl.{q_credit},0)) as saldo
                    FROM journalline jl
                    LEFT JOIN account a ON jl.account_id = a.id
                    GROUP BY acct_code
                """
                cur.execute(sql)
                for acct_code, saldo in cur.fetchall():
                    balances[str(acct_code)] = Decimal(str(saldo or 0))
                return balances
            else:
                q_debit = debit_col if debit_col else "0"
                q_credit = credit_col if credit_col else "0"
                sql = f"""
                    SELECT CAST(account_id AS TEXT) as acct_code,
                           SUM(COALESCE({q_debit},0) - COALESCE({q_credit},0)) as saldo
                    FROM journalline
                    GROUP BY acct_code
                """
                cur.execute(sql)
                for acct_code, saldo in cur.fetchall():
                    balances[str(acct_code)] = Decimal(str(saldo or 0))
                return balances
        else:
            q_debit = debit_col if debit_col else "0"
            q_credit = credit_col if credit_col else "0"
            sql = f"""
                SELECT COALESCE({acct_col}, '') as acct_code,
                       SUM(COALESCE({q_debit},0) - COALESCE({q_credit},0)) as saldo
                FROM journalline
                GROUP BY acct_code
            """
            cur.execute(sql)
            for acct_code, saldo in cur.fetchall():
                if acct_code:
                    balances[str(acct_code)] = Decimal(str(saldo or 0))
            return balances
    finally:
        conn.close()

try:
    from modelos.libro import Libro  # type: ignore
except Exception:
    Libro = None

def _balances_from_libro() -> Dict[str, Decimal]:
    if Libro is None:
        return {}
    try:
        libro = Libro()
        df = libro.compute_balance()
    except Exception:
        return {}
    if not df:
        return {}
    balances: Dict[str, Decimal] = {}
    for idx, row in df.iterrows():
        code = None
        for cand in ("code", "Codigo", "Cuenta", "codigo", "account", "cuenta"):
            code = row.get(cand) if hasattr(row, "get") else None
            if code:
                break
        if not code:
            code = idx
        saldo = None
        for cand in ("saldo", "Saldo", "balance", "saldo_final", "amount"):
            saldo = row.get(cand) if hasattr(row, "get") else None
            if saldo is not None:
                break
        if saldo is None:
            for k, v in dict(row).items():
                if isinstance(v, (int, float, Decimal)):
                    saldo = v
                    break
        balances[str(code)] = Decimal(str(saldo or 0))
    return balances

def trial_balance(as_of: Optional[str] = None) -> Dict[str, Decimal]:
    try:
        db_path = _find_db_path()
        balances_sqlite = _balances_from_sqlite(db_path)
        if balances_sqlite:
            return balances_sqlite
    except Exception:
        pass
    try:
        balances_libro = _balances_from_libro()
        if balances_libro:
            return balances_libro
    except Exception:
        pass
    return {}

# -----------------------------------------------------------------------------
# post_entry actualizado (tu bloque de parche)
# -----------------------------------------------------------------------------
def post_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Persist a JournalEntry with JournalLines.
    """
    desc = entry.get("description", "") or ""
    lines = entry.get("lines", []) or []

    def _verify_accounts(lines):
        missing = []
        try:
            if "Account" in globals() and get_session is not None:
                with get_session() as s:
                    for ln in lines:
                        if ln.get("account_id"):
                            acc = s.get(Account, int(ln["account_id"]))
                            if not acc:
                                missing.append(str(ln.get("account_id")))
                        elif ln.get("account_code"):
                            acc = s.exec(select(Account).where(Account.code == str(ln["account_code"]))).one_or_none()
                            if not acc:
                                missing.append(str(ln.get("account_code")))
                        else:
                            missing.append("(sin cuenta en línea)")
                return missing
        except Exception:
            pass

        db = _find_db_path()
        if db is None:
            raise RuntimeError("No se encontró DB para verificar cuentas")
        conn = sqlite3.connect(str(db))
        try:
            cur = conn.cursor()
            for ln in lines:
                if ln.get("account_id"):
                    cur.execute("SELECT id FROM account WHERE id = ? LIMIT 1", (int(ln["account_id"]),))
                    if not cur.fetchone():
                        missing.append(str(ln.get("account_id")))
                elif ln.get("account_code"):
                    cur.execute("SELECT id FROM account WHERE code = ? LIMIT 1", (str(ln["account_code"]),))
                    if not cur.fetchone():
                        missing.append(str(ln.get("account_code")))
                else:
                    missing.append("(sin cuenta en línea)")
        finally:
            conn.close()
        return missing

    try:
        missing = _verify_accounts(lines)
    except Exception as e:
        return {"ok": False, "error": f"Error verificando cuentas: {e}"}
    if missing:
        return {"ok": False, "error": "Cuentas no encontradas: " + ", ".join(missing)}

    if "JournalEntry" in globals() and "JournalLine" in globals() and get_session is not None:
        try:
            with get_session() as s:
                je = JournalEntry(description=desc, created_at=datetime.datetime.utcnow())
                s.add(je)
                s.commit()
                s.refresh(je)
                for ln in lines:
                    account_id = ln.get("account_id")
                    if not account_id and ln.get("account_code"):
                        acc = s.exec(select(Account).where(Account.code == str(ln["account_code"]))).one_or_none()
                        if acc:
                            account_id = acc.id
                    if not account_id:
                        s.rollback()
                        return {"ok": False, "error": f"Cuenta no encontrada para línea: {ln}"}
                    jl = JournalLine(
                        entry_id=je.id,
                        account_id=int(account_id),
                        debit=float(ln.get("debit") or 0),
                        credit=float(ln.get("credit") or 0),
                        description=ln.get("description")
                    )
                    s.add(jl)
                s.commit()
            return {"ok": True, "entry_id": je.id}
        except Exception as e:
            LOG.debug("ORM post_entry failed, falling back to sqlite: %s", e)

    db = _find_db_path()
    if db is None:
        return {"ok": False, "error": "No se encontró base de datos para persistir entry."}
    conn = sqlite3.connect(str(db))
    try:
        cur = conn.cursor()
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
                (entry_id, int(acct_id), float(ln.get("debit") or 0), float(ln.get("credit") or 0), ln.get("description"), now)
            )
        conn.commit()
        return {"ok": True, "entry_id": entry_id}
    finally:
        conn.close()
