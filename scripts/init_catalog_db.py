#!/usr/bin/env python3
"""
Inicializa la tabla `account` a partir de aqorath/data/catalogo_base.json.

Uso:
    python scripts/init_catalog_db.py

Comportamiento:
 - Inserta filas para cada código que no exista todavía (no borra ni modifica existentes).
 - Registra en AppConfig la versión del catálogo importado.
"""
import json
from pathlib import Path
from datetime import datetime
from sqlmodel import select
from aqorath.storage import get_session
from aqorath.models import Account, AppConfig

BASE = Path("aqorath/data/catalogo_base.json")

def load_catalog():
    if not BASE.exists():
        raise FileNotFoundError(f"Catálogo base no encontrado: {BASE}")
    return json.loads(BASE.read_text(encoding="utf-8"))

def main():
    data = load_catalog()
    version = data.get("version", "")
    accounts = data.get("accounts", {})
    with get_session() as s:
        added = 0
        for code, meta in accounts.items():
            rows = s.exec(select(Account).where(Account.code == str(code))).all()
            if len(rows) == 0:
                a = Account(
                    code=str(code),
                    name=meta.get("name_comercial") or meta.get("name_osc") or "",
                    nature=meta.get("naturaleza") or None
                )
                s.add(a)
                added += 1
            elif len(rows) > 1:
                print(f"Advertencia: el código {code} tiene {len(rows)} filas en DB (no se insertó).")
        # registrar version del catálogo
        key = "catalog.base.version"
        existing = s.exec(select(AppConfig).where(AppConfig.key == key)).one_or_none()
        ts = f"{version} @ {datetime.utcnow().isoformat()}"
        if existing:
            existing.value = ts
            s.add(existing)
        else:
            s.add(AppConfig(key=key, value=ts))
        s.commit()
    print(f"Importación finalizada. Insertadas: {added}. Versión: {version}")

if __name__ == "__main__":
    main()