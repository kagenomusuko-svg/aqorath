"""Explicit SQLite source adapter for immutable financial report snapshots.

The caller supplies the SQLite path and catalog classification.  Balances and account
identity are always read from that same database path; no hidden application DB path,
session, renderer, or alternate accounting authority is consulted.
"""

import os
import sqlite3
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from . import core as _core
from . import reporting as _reporting


def _explicit_existing_db_path(db_path) -> Path:
    if not isinstance(db_path, (str, os.PathLike)):
        raise TypeError("db_path must be a filesystem path")
    if isinstance(db_path, str) and not db_path.strip():
        raise ValueError("db_path must not be empty")

    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"SQLite reporting database does not exist: {path}")
    if not path.is_file():
        raise ValueError(f"SQLite reporting path is not a file: {path}")
    return path


def _load_account_identities_from_sqlite(db_path: Path):
    """Read account code/name/nature from exactly ``db_path`` in read-only mode."""
    uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        cur = conn.cursor()
        cur.execute("SELECT code, name, nature FROM account ORDER BY code")
        rows = cur.fetchall()
    finally:
        conn.close()

    accounts_by_code = {}
    for code, name, nature in rows:
        if code is None or not str(code).strip():
            raise ValueError("Account table contains an empty account code")
        code_str = str(code)
        if code_str in accounts_by_code:
            raise ValueError(f"Duplicate account code in SQLite: {code_str!r}")
        accounts_by_code[code_str] = SimpleNamespace(
            code=code_str,
            name=name,
            nature=nature,
        )
    return accounts_by_code


def build_financial_report_snapshot_from_sqlite(
    db_path,
    catalog,
    as_of=None,
):
    """Build a report snapshot using balances and account identity from one SQLite.

    Exact ledger aggregation is delegated to Aqorath's existing SQLite balance
    authority for the explicit path.  Account identities are then read from the same
    path.  Accounts with no movement are included at exact zero before the pure
    reporting snapshot builder is invoked.
    """
    path = _explicit_existing_db_path(db_path)

    balances = dict(_core._balances_from_sqlite(path, as_of=as_of))
    accounts_by_code = _load_account_identities_from_sqlite(path)

    for code in accounts_by_code:
        balances.setdefault(code, Decimal("0"))

    return _reporting.build_financial_report_snapshot(
        balances,
        accounts_by_code,
        catalog,
        as_of=as_of,
    )
