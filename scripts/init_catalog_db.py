#!/usr/bin/env python3
"""
Inicializa la tabla `account` a partir de aqorath/data/catalogo_base.json.

Comportamiento:
 - Crea las tablas que falten (SQLModel.metadata.create_all).
 - Deduplica (opcional, mantiene MIN(id) por code).
 - Inserta filas faltantes del catálogo (no modifica filas existentes).
 - Registra la versión del catálogo en AppConfig.
 - Respeta la selección del modelo de contabilidad al elegir nombres de cuentas.
"""
from pathlib import Path
import os
import sys
import json
import logging
from datetime import datetime
from sqlmodel import SQLModel, create_engine, Session, select, text

# Add parent directory to path so we can import aqorath.config
sys.path.insert(0, str(Path(__file__).parent.parent))

from aqorath.models import Account, AppConfig

# Import config helpers with fallback
try:
    from aqorath.config import get_accounting_model
except ImportError:
    # Fallback if config module doesn't exist yet
    def get_accounting_model():
        return None

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

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

    # Get saved accounting model preference
    saved_model = get_accounting_model()
    if saved_model:
        if saved_model == "sin_fines":
            logger.info("Using saved accounting model preference: sin_fines (OSC)")
            name_preference = "osc"
        elif saved_model == "comercial":
            logger.info("Using saved accounting model preference: comercial")
            name_preference = "comercial"
        else:
            logger.warning(f"Unknown accounting model '{saved_model}', using comercial as default")
            name_preference = "comercial"
    else:
        logger.info("No saved accounting model, using comercial as default")
        name_preference = "comercial"

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
                # Choose name based on accounting model preference
                if name_preference == "osc":
                    chosen_name = meta.get("name_osc") or meta.get("name_comercial") or ""
                else:  # comercial
                    chosen_name = meta.get("name_comercial") or meta.get("name_osc") or ""
                
                a = Account(
                    code=str(code),
                    name=chosen_name,
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