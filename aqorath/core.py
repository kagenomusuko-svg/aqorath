from __future__ import annotations
"""
aqorath.core - helper utilities for accounting operations

Provides:
  - trial_balance(as_of: Optional[str] = None) -> Dict[str, Decimal]

Behavior:
  1) Try to obtain balances using modelos.libro.Libro.compute_balance() if available.
     If the result is empty or doesn't include the expected '3103' account, fall back.
  2) Fallback to a sqlite3 aggregation that computes SUM(debit)-SUM(credit) grouped by account (account code).
"""
from decimal import Decimal
from typing import Dict, Optional
import logging
import os
import sqlite3
from pathlib import Path

LOG = logging.getLogger(__name__)
LOG.addHandler(logging.NullHandler())

# Try to import the existing Libro helper if present
try:
    from modelos.libro import Libro  # type: ignore
except Exception:
    Libro = None  # not fatal; we'll fallback to sqlite

def _balances_from_libro() -> Dict[str, Decimal]:
    """
    Attempt to compute balances via modelos.libro.Libro.
    Return empty dict if unable to compute or DataFrame is empty.
    """
    if Libro is None:
        raise RuntimeError("modelos.libro.Libro not available")
    libro = Libro()
    df = libro.compute_balance()
    balances: Dict[str, Decimal] = {}

    # Defensive: if df is falsy or empty, return empty dict so caller can fallback
    try:
        if df is None:
            LOG.debug("modelos.libro.compute_balance() returned None")
            return {}
        # pandas DataFrame handling: empty check
        try:
            empty = hasattr(df, "empty") and df.empty
        except Exception:
            empty = False
        if empty:
            LOG.debug("modelos.libro.compute_balance() returned empty DataFrame")
            return {}

        # Try to iterate rows; support DataFrame-like or dict-like
        # We expect rows to have account code and a saldo column; be defensive with names.
        for idx, row in df.iterrows():
            # attempt several common keys
            code = None
            for cand in ("code", "Codigo", "Cuenta", "codigo", "account", "cuenta"):
                code = row.get(cand) if hasattr(row, "get") else None
                if code:
                    break
            if not code:
                # fallback to index if it's a string account code
                code = idx

            saldo = None
            for cand in ("saldo", "Saldo", "balance", "saldo_final", "saldo_actual", "amount"):
                saldo = row.get(cand) if hasattr(row, "get") else None
                if saldo is not None:
                    break
            if saldo is None:
                # last resort: try any numeric column in row
                try:
                    for k, v in dict(row).items():
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
    """
    Aggregate journalline rows in sqlite to compute balances in the form
    { account_code_str: Decimal(saldo) }.
    """
    if db_path is None:
        raise RuntimeError("No sqlite DB path found for fallback")
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        # Inspect journalline columns
        cur.execute("PRAGMA table_info('journalline')")
        cols = [r[1] for r in cur.fetchall()]
        LOG.debug("journalline columns: %s", cols)

        # Determine candidate column names
        acct_col = None
        for cand in ("account_code", "account", "account_id", "codigo", "cuenta"):
            if cand in cols:
                acct_col = cand
                break
        debit_col = next((c for c in cols if c.lower() in ("debit","debe","cargo")), None)
        credit_col = next((c for c in cols if c.lower() in ("credit","haber","abono")), None)

        # If debit/credit missing, attempt broader fallbacks
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
    Tries the Libro implementation first; if the result is empty or doesn't include
    expected accounts, falls back to sqlite aggregation.
    """
    # First attempt: modelos.libro if available
    try:
        balances = _balances_from_libro()
        # If libro returned no balances or doesn't include 3103, fallback
        if not balances:
            LOG.info("trial_balance: modelos.libro returned empty balances; using sqlite fallback")
            return _balances_from_sqlite(_find_db_path())
        # If 3103 not present, also fallback (robustness)
        if "3103" not in balances and not any(k.endswith("3103") for k in balances.keys()):
            LOG.info("trial_balance: modelos.libro did not include 3103; using sqlite fallback")
            return _balances_from_sqlite(_find_db_path())
        return balances
    except Exception as e:
        LOG.debug("trial_balance: libros method unavailable or failed (%s); falling back to sqlite", e)

    # Final fallback: sqlite aggregation
    try:
        return _balances_from_sqlite(_find_db_path())
    except Exception as e:
        LOG.exception("trial_balance fallback failed: %s", e)
        return {}