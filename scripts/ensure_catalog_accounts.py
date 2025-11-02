#!/usr/bin/env python3
"""
Asegura que todos los códigos del catálogo embebido (aqorath/data/catalogo_base.json)
existan en la tabla `account`. Inserta solo los códigos faltantes.

Uso:
  1) Haz backup de la DB:
       DB="$HOME/.local/share/aqorath/aqorath.db"
       cp -v "$DB" "${DB}.bak.$(date +%F_%H%M%S)"
  2) Ejecuta:
       python scripts/ensure_catalog_accounts.py --dry-run   # para ver lo que haría
       python scripts/ensure_catalog_accounts.py            # para aplicar
"""
from pathlib import Path
import json
import argparse
from sqlmodel import select
from aqorath.storage import get_session
from aqorath.models import Account

CAT_PATH = Path("aqorath/data/catalogo_base.json")

def load_catalog():
    if not CAT_PATH.exists():
        raise FileNotFoundError(f"Catálogo no encontrado: {CAT_PATH}")
    data = json.loads(CAT_PATH.read_text(encoding="utf-8"))
    return data.get("accounts", {})

def find_missing_codes():
    accounts = load_catalog()
    with get_session() as s:
        rows = s.exec(select(Account.code)).all()
        db_codes = set(str(r[0]) for r in rows) if rows else set()
    cat_codes = set(accounts.keys())
    missing = sorted(list(cat_codes - db_codes))
    return missing, accounts

def apply_inserts(missing, accounts):
    inserted = []
    with get_session() as s:
        for code in missing:
            meta = accounts.get(code, {})
            name = meta.get("name_comercial") or meta.get("name_osc") or f"Cuenta {code}"
            naturaleza = meta.get("naturaleza") or None
            a = Account(code=str(code), name=name, nature=naturaleza)
            s.add(a)
            inserted.append((code, name))
        if inserted:
            s.commit()
    return inserted

def main(dry_run=False):
    missing, accounts = find_missing_codes()
    if not missing:
        print("No hay códigos faltantes. Nada que hacer.")
        return 0
    print(f"Códigos faltantes ({len(missing)}): {missing}")
    if dry_run:
        print("Dry-run: no se insertará nada.")
        return 0
    # solicitar confirmación por si acaso
    print("Se insertarán las cuentas faltantes. Revisa que hayas hecho backup de la DB.")
    resp = input("Continuar? [y/N]: ").strip().lower()
    if resp != "y":
        print("Cancelado por el usuario.")
        return 1
    inserted = apply_inserts(missing, accounts)
    print(f"Insertadas {len(inserted)} cuentas:")
    for code, name in inserted:
        print("  ", code, "->", name)
    return 0

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="Mostrar lo que se haría sin aplicar.")
    args = p.parse_args()
    raise SystemExit(main(dry_run=args.dry_run))