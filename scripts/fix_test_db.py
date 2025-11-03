#!/usr/bin/env python3
"""
fix_test_db.py

Normaliza + deduplica la tabla `account` y asegura que estén insertadas
las cuentas del catálogo embebido (aqorath/data/catalogo_base.json).

Uso (ejemplo):
  export AQORATH_DB="$(pwd)/tests/test.db"
  python scripts/fix_test_db.py

El script:
 - realiza backup del archivo DB (tests/test.db.bak.TIMESTAMP)
 - normaliza Account.code -> str(code).strip()
 - elimina duplicados por code (mantiene la fila con menor id)
 - inserta códigos faltantes del catálogo embebido (solo insert)
 - imprime resumen
"""
import os
import shutil
from pathlib import Path
import json
from datetime import datetime

from sqlmodel import select
from aqorath.storage import get_session, get_db_path, init_db
from aqorath.models import Account

def backup_db(db_path: Path) -> Path:
    bak = db_path.with_name(db_path.name + f".bak.{datetime.utcnow().strftime('%Y%m%d%H%M%S')}")
    shutil.copy2(db_path, bak)
    return bak

def load_catalog_codes(cat_path: Path):
    d = json.loads(cat_path.read_text(encoding="utf-8"))
    return d.get("accounts", {})

def main():
    # Determine DB path (respect AQORATH_DB or default)
    db_path_str = os.environ.get("AQORATH_DB")
    if not db_path_str:
        db_path_str = get_db_path()
    db_path = Path(db_path_str).resolve()

    if not db_path.exists():
        print("DB file does not exist, creating and initializing schema:", db_path)
        # ensure DB+schema exist using storage.init_db
        init_db(str(db_path), create_tables=True)

    print("Using DB:", db_path)
    bak = backup_db(db_path)
    print("Backup created:", bak)

    # load catalog
    cat_path = Path("aqorath/data/catalogo_base.json")
    if not cat_path.exists():
        print("Catálogo no encontrado:", cat_path)
        return 1
    catalog = load_catalog_codes(cat_path)

    with get_session() as s:
        # 1) Normalize codes: strip whitespace and coerce to str
        rows = s.exec(select(Account)).all()
        changed = 0
        for r in rows:
            orig = r.code
            new = str(orig).strip() if orig is not None else ""
            if new != orig:
                r.code = new
                s.add(r)
                changed += 1
        if changed:
            s.commit()
        print(f"Normalized codes: {changed} rows updated")

        # 2) Deduplicate: for each code keep lowest id, delete the rest
        # gather codes with duplicates
        dup_codes = s.exec(
            select(Account.code).group_by(Account.code).having((Account.code != None) & (Account.code != "")).having((Account.code) != "").order_by(Account.code)
        ).all()  # we'll scan all codes below
        # Simpler: iterate over distinct codes in DB and check counts
        all_codes = [r[0] for r in s.exec(select(Account.code)).all()]
        distinct_codes = sorted(set(all_codes))
        deleted = 0
        for code in distinct_codes:
            if code is None or str(code).strip() == "":
                continue
            rows_for_code = s.exec(select(Account).where(Account.code == code).order_by(Account.id)).all()
            if len(rows_for_code) > 1:
                # keep first (lowest id), delete others
                for r in rows_for_code[1:]:
                    s.delete(r)
                    deleted += 1
        if deleted:
            s.commit()
        print(f"Deduplicated: deleted {deleted} rows (kept min id per code)")

        # 3) Insert missing codes from catalog
        cat_codes = set(str(k).strip() for k in catalog.keys())
        existing_rows = s.exec(select(Account.code)).all()
        existing_codes = set(str(r[0]) for r in existing_rows if r[0] is not None)
        missing = sorted(list(cat_codes - existing_codes))
        print("Missing codes to insert:", len(missing))
        inserted = 0
        for code in missing:
            meta = catalog.get(code, {})
            name = meta.get("name_comercial") or meta.get("name_osc") or f"Cuenta {code}"
            naturaleza = meta.get("naturaleza") or None
            a = Account(code=str(code), name=name, nature=naturaleza)
            s.add(a)
            inserted += 1
        if inserted:
            s.commit()
        print(f"Inserted {inserted} missing accounts from catalog")

        # 4) Final summary
        total_rows = s.exec(select(Account)).all()
        total_count = len(total_rows)
        distinct_after = set(str(r.code) for r in total_rows if r.code is not None)
        print("Final counts: rows:", total_count, "distinct codes:", len(distinct_after))

    print("Done. If anything unexpected, you can restore from backup:", bak)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())