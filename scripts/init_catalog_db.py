#!/usr/bin/env python3
"""
Inicializa la tabla `account` a partir de aqorath/data/catalogo_base.json.

Comportamiento:
 - Crea las tablas que falten (SQLModel.metadata.create_all).
 - Deduplica (opcional, mantiene MIN(id) por code).
 - Inserta filas faltantes del catálogo (no modifica filas existentes).
 - Registra la versión del catálogo en AppConfig.
"""
from pathlib import Path
import os
import json
from datetime import datetime
from sqlmodel import SQLModel, create_engine, Session, select, text

from aqorath.models import Account, AppConfig
from aqorath.config import get_accounting_model

# ruta por defecto (igual que en storage.py)
DEFAULT_DB = Path.home() / ".local" / "share" / "aqorath" / "aqorath.db"
CATALOG_PATH = Path("aqorath/data/catalogo_base.json")


def get_db_path() -> str:
    env = os.environ.get("AQORATH_DB")
    if env:
        return str(Path(env).resolve())
    return str(DEFAULT_DB)


def load_catalog():
    if not CATALOG_PATH.exists():
        raise FileNotFoundError(f"Catálogo base no encontrado: {CATALOG_PATH}")
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def _row_name_for_model(row):
    model = get_accounting_model()
    if model == "sin_fines":
        return row.get("name_osc") or row.get("B") or row.get(1) or ""
    return row.get("name_comercial") or row.get("C") or row.get(2) or ""


def main():
    db_path = get_db_path()
    print("init_catalog_db: usando AQORATH_DB =", db_path)

    # crear engine propio y asegurarnos de que el esquema existe
    url = f"sqlite:///{db_path}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    # crear todas las tablas definidas por los modelos (si no existen)
    SQLModel.metadata.create_all(engine)

    data = load_catalog()
    version = data.get("version", "")
    accounts = data.get("accounts", {})

    with Session(engine) as s:
        # deduplicar: mantener la fila con MIN(id) por code si hay duplicados
        try:
            s.exec(text("DELETE FROM account WHERE id NOT IN (SELECT MIN(id) FROM account GROUP BY code);"))
            s.commit()
        except Exception:
            # si no existe la tabla o algo falla, continuar (ya hicimos create_all)
            pass

        added = 0
        for code, meta in accounts.items():
            rows = s.exec(select(Account).where(Account.code == str(code))).all()
            if len(rows) == 0:
                a = Account(
                    code=str(code),
                    name=_row_name_for_model(meta),
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
