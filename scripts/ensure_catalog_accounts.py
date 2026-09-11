#!/usr/bin/env python3
"""Inspect or materialize missing governed catalog Account rows.

This maintenance CLI delegates writes to aqorath.catalog_persistence, the same
persistence composition used by product onboarding. It is not a second catalog
or insertion authority.
"""

import argparse
from sqlmodel import select

from aqorath.catalog import load_catalog
from aqorath.catalog_persistence import ensure_canonical_accounts
from aqorath.models import Account
from aqorath.storage import get_session


def find_missing_codes():
    document = load_catalog()
    accounts = document.get("accounts", {})
    with get_session() as session:
        rows = session.exec(select(Account.code)).all()
        db_codes = {str(row) for row in rows}
    missing = sorted(set(accounts) - db_codes)
    return missing, accounts


def apply_inserts(_missing=None, _accounts=None):
    with get_session() as session:
        inserted_codes = ensure_canonical_accounts(session, "lucrativo")
        session.commit()
        rows = session.exec(
            select(Account).where(Account.code.in_(inserted_codes)).order_by(Account.code)
        ).all() if inserted_codes else []
        return [(row.code, row.name) for row in rows]


def main(dry_run=False):
    missing, _accounts = find_missing_codes()
    if not missing:
        print("No hay códigos faltantes. Nada que hacer.")
        return 0
    print(f"Códigos faltantes ({len(missing)}): {missing}")
    if dry_run:
        print("Dry-run: no se insertará nada.")
        return 0
    print("Se insertarán únicamente cuentas canónicas faltantes del catálogo gobernado.")
    response = input("Continuar? [y/N]: ").strip().lower()
    if response != "y":
        print("Cancelado por el usuario.")
        return 1
    inserted = apply_inserts()
    print(f"Insertadas {len(inserted)} cuentas:")
    for code, name in inserted:
        print("  ", code, "->", name)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Mostrar lo que se haría sin aplicar.")
    args = parser.parse_args()
    raise SystemExit(main(dry_run=args.dry_run))
