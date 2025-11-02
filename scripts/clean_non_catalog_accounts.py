#!/usr/bin/env python3
"""
Clean non-catalog accounts from a SQLite DB used by aqorath.

- Dry-run (default): lists accounts that would be removed.
- With --yes: performs backup, NULLs JournalLine.account_id for affected accounts,
  then deletes the Account rows whose code is NOT in the catalog.

Usage:
  # dry run (safe)
  .venv/bin/python scripts/clean_non_catalog_accounts.py

  # perform deletion (uses AQORATH_DB or tests/test.db by default)
  .venv/bin/python scripts/clean_non_catalog_accounts.py --yes

Options:
  --db PATH         Path to the sqlite file (default: $AQORATH_DB or tests/test.db)
  --catalog PATH    Path to catalog JSON (default: aqorath/data/catalogo_base.json)
  --yes             Execute changes (default: dry-run)
  --limit N         Only show first N accounts in the report (default 50)
"""
import argparse
import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_CATALOG = Path("aqorath/data/catalogo_base.json")
DEFAULT_TEST_DB = Path("tests/test.db")


def load_catalog_codes_from_json(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"Catálogo JSON no encontrado: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    accounts = data.get("accounts", {}) if isinstance(data, dict) else {}
    return {str(k).strip() for k in accounts.keys()}


def choose_db(db_arg):
    if db_arg:
        return Path(db_arg)
    env = Path(str((__import__("os")).environ.get("AQORATH_DB", ""))) if ( __import__("os")).environ.get("AQORATH_DB") else None
    if env and env.exists():
        return env
    # fallback to tests/test.db if exists, otherwise error
    if DEFAULT_TEST_DB.exists():
        return DEFAULT_TEST_DB
    raise FileNotFoundError("No DB found. Set --db PATH or export AQORATH_DB or ensure tests/test.db exists.")


def list_non_catalog_accounts(db_path: Path, catalog_codes: set):
    con = sqlite3.connect(str(db_path))
    cur = con.cursor()
    try:
        cur.execute("SELECT id, code, name FROM account ORDER BY id")
    except sqlite3.OperationalError as e:
        con.close()
        raise RuntimeError(f"La tabla account no existe en {db_path}: {e}")
    rows = cur.fetchall()
    noncat = [(rid, code, name) for (rid, code, name) in rows if str(code).strip() not in catalog_codes]
    con.close()
    return noncat


def apply_cleanup(db_path: Path, account_ids, account_codes):
    # backup
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup = db_path.with_suffix(db_path.suffix + f".bak.{ts}")
    shutil.copy2(db_path, backup)
    print(f"Backup creado: {backup}")

    con = sqlite3.connect(str(db_path))
    cur = con.cursor()
    try:
        # Nullify account_id where it references deleted accounts (by id)
        if account_ids:
            q_ids = ",".join(str(i) for i in account_ids)
            cur.execute(f"UPDATE journalline SET account_id = NULL WHERE account_id IN ({q_ids});")
        # Also if there are journallines that reference the deleted codes via account_code, keep account_code but ensure account_id NULL
        if account_codes:
            # use parameter substitution for safety
            for code in account_codes:
                cur.execute("UPDATE journalline SET account_id = NULL WHERE account_code = ?;", (code,))
        # delete accounts
        if account_ids:
            cur.execute(f"DELETE FROM account WHERE id IN ({','.join(str(i) for i in account_ids)});")
        con.commit()
    finally:
        con.close()
    print(f"Eliminadas {len(account_ids)} cuentas no-catalogadas y limpiadas referencias en journalline.")


def main():
    ap = argparse.ArgumentParser(description="Eliminar cuentas no presentes en el catálogo JSON.")
    ap.add_argument("--db", help="Ruta a la base de datos SQLite (por defecto AQORATH_DB o tests/test.db)")
    ap.add_argument("--catalog", help="Ruta al JSON del catálogo", default=str(DEFAULT_CATALOG))
    ap.add_argument("--yes", help="Aplicar cambios (por defecto dry-run)", action="store_true")
    ap.add_argument("--limit", type=int, default=50, help="Número de cuentas a listar en el reporte")
    args = ap.parse_args()

    db_path = choose_db(args.db)
    catalog_path = Path(args.catalog)
    try:
        catalog_codes = load_catalog_codes_from_json(catalog_path)
    except Exception as e:
        print("ERROR: no se pudo cargar el catálogo:", e, file=sys.stderr)
        sys.exit(2)

    print(f"Usando DB: {db_path}")
    print(f"Catálogo: {catalog_path} (codes: {len(catalog_codes)})")

    try:
        noncat = list_non_catalog_accounts(db_path, catalog_codes)
    except Exception as e:
        print("ERROR al listar cuentas:", e, file=sys.stderr)
        sys.exit(3)

    if not noncat:
        print("No se encontraron cuentas no presentes en el catálogo. Nada que hacer.")
        return

    print(f"Se encontraron {len(noncat)} cuentas que NO están en el catálogo.")
    for i, (rid, code, name) in enumerate(noncat[: args.limit]):
        print(f"  id={rid} code={code!r} name={name!r}")
    if len(noncat) > args.limit:
        print(f"  ... y {len(noncat) - args.limit} más (usa --limit para mostrar más)")

    if not args.yes:
        print("\nDRY-RUN: no se ha modificado la base de datos. Ejecuta con --yes para eliminar estas cuentas.")
        return

    # Prepare ids and codes
    account_ids = [rid for (rid, _, _) in noncat]
    account_codes = [str(code) for (_, code, _) in noncat]

    # Confirm again (no interactive prompt in scripts by default)
    print("\nSe va a proceder a eliminar las cuentas listadas. Se hará backup automático antes de modificar.")
    apply_cleanup(db_path, account_ids, account_codes)
    print("Operación completada.")

if __name__ == "__main__":
    main()