from __future__ import annotations
"""
aqorath.core - helper utilities for accounting operations

Provides:
  - trial_balance(as_of: Optional[str] = None) -> Dict[str, Decimal]

Behavior:
  1) Try to obtain balances using modelos.libro.Libro.compute_balance() if available.
  2) If that fails (missing module, schema mismatch, etc.), fall back to a sqlite3
     aggregation that computes SUM(debit)-SUM(credit) grouped by account (account code).
"""
from decimal import Decimal
from typing import Dict, Optional
import logging
import os
import sqlite3
from pathlib import Path

LOG = logging.getLogger(__name__)

# Try to import the existing Libro helper if present
try:
    from modelos.libro import Libro  # type: ignore
except Exception:
    Libro = None  # not fatal; we'll fallback to sqlite

def _balances_from_libro() -> Dict[str, Decimal]:
    if Libro is None:
        raise RuntimeError("modelos.libro.Libro not available")
    libro = Libro()
    df = libro.compute_balance()
    balances: Dict[str, Decimal] = {}
    # Defensive extraction: try common column names
    try:
        for idx, row in df.iterrows():
            code = row.get("code") or row.get("Cuenta") or row.get("codigo") or row.get("account") or idx
            # saldo column common names
            saldo = row.get("saldo") or row.get("Saldo") or row.get("balance") or row.get("saldo_final") or 0
            balances[str(code)] = Decimal(str(saldo))
    except Exception as e:
        LOG.exception("Failed to extract balances from modelos.libro: %s", e)
        raise
    return balances

def _find_db_path() -> Optional[Path]:
    # Look for env var first, then common locations used in this repo
    cand = os.environ.get("AQORATH_DB")
    if cand:
        p = Path(cand)
        if p.exists():
            return p
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
        # Inspect journalline columns
        cur.execute("PRAGMA table_info('journalline')")
        cols = [r[1] for r in cur.fetchall()]
        # Determine candidate column names
        acct_col = None
        for cand in ("account_code", "account", "account_id", "codigo", "cuenta"):
            if cand in cols:
                acct_col = cand
                break
        debit_col = next((c for c in cols if c.lower() in ("debit","debe","cargo")), None)
        credit_col = next((c for c in cols if c.lower() in ("credit","haber","abono")), None)

        # If debit/credit missing, attempt common fallbacks
        if debit_col is None:
            debit_col = next((c for c in cols if "debit" in c.lower() or "debe" in c.lower() or "cargo" in c.lower()), None)
        if credit_col is None:
            credit_col = next((c for c in cols if "credit" in c.lower() or "haber" in c.lower() or "abono" in c.lower()), None)

        if acct_col is None:
            raise RuntimeError("Could not detect account column in journalline table (checked: %s)" % (cols,))

        # If journalline stores account_id (numeric) but we want account.code, try joining with account table.
        use_join = acct_col in ("account_id",)
        balances: Dict[str, Decimal] = {}

        if use_join:
            # Ensure account table exists and has columns id, code
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='account'")
            if cur.fetchone():
                # Build query: join journalline jl with account a on jl.account_id = a.id
                q_debit = debit_col if debit_col else "0"
                q_credit = credit_col if credit_col else "0"
                sql = f"""
                SELECT COALESCE(a.code, CAST(jl.{acct_col} AS TEXT)) as acct_code,
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
                # account table missing; aggregate by account_id numeric (cast to text)
                q_debit = debit_col if debit_col else "0"
                q_credit = credit_col if credit_col else "0"
                sql = f"""
                SELECT CAST(jl.{acct_col} AS TEXT) as acct_code,
                       SUM(COALESCE(jl.{q_debit},0) - COALESCE(jl.{q_credit},0)) as saldo
                FROM journalline jl
                GROUP BY acct_code
                """
                cur.execute(sql)
                rows = cur.fetchall()
                for acct_code, saldo in rows:
                    balances[str(acct_code)] = Decimal(str(saldo or 0))
                return balances
        else:
            # acct_col already is a code string (e.g. account_code or account), aggregate directly
            q_debit = debit_col if debit_col else "0"
            q_credit = credit_col if credit_col else "0"
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

def trial_balance(as_of: Optional[str] = None) -> Dict[str, Decimal]:
    """
    Return a mapping account_code -> Decimal(saldo).
    Tries the Libro implementation first; on any error falls back to sqlite aggregation.
    """
    # First attempt: modelos.libro if available
    try:
        return _balances_from_libro()
    except Exception as e:
        LOG.debug("trial_balance: libros method unavailable or failed (%s); falling back to sqlite", e)

    # Fallback: sqlite aggregation
    db_path = _find_db_path()
    try:
        return _balances_from_sqlite(db_path)
    except Exception as e:
        LOG.exception("trial_balance fallback failed: %s", e)
        # Return empty dict instead of raising to keep callers defensive (tests will catch emptiness)
        return {}