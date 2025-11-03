import os
import importlib
from pathlib import Path
import json

# Fijar la ruta de la DB de tests lo antes posible
TEST_DB = Path.cwd() / "tests" / "test.db"
os.environ["AQORATH_DB"] = str(TEST_DB.resolve())

# Borrar DB antigua para partir limpio
if TEST_DB.exists():
    try:
        TEST_DB.unlink()
    except Exception:
        pass

# Importar/recargar storage (usa AQORATH_DB que acabamos de fijar)
import aqorath.storage as storage
importlib.reload(storage)

# IMPORTAR MODELOS ANTES de crear tablas para que metadata incluya las definiciones
# Importar aqorath.models asegura que SQLModel.metadata conozca Account, AppConfig, etc.
import aqorath.models as _models  # noqa: F401

# Crear esquema en la test DB (ahora metadata ya contiene los modelos)
storage.init_db(str(TEST_DB), create_tables=True)

# Cargar catálogo embebido y asegurar cuentas en la DB antes de que los tests se importen
from sqlmodel import select, text
from aqorath.models import Account
from aqorath.storage import get_session

# --- NUEVO BLOQUE: generar catálogo mínimo si no existe ---
CAT_PATH = Path("aqorath/data/catalogo_base.json")
if not os.path.isfile(CAT_PATH):
    # Intentamos crear un JSON mínimo para permitir que CI ejecute tests
    os.makedirs(os.path.dirname(CAT_PATH), exist_ok=True)
    minimal = {
        "version": "generated-for-ci",
        "notes": "Auto-generated minimal catalog",
        "accounts": {}
    }
    with open(CAT_PATH, "w", encoding="utf-8") as f:
        json.dump(minimal, f, ensure_ascii=False, indent=2)
    # Opcional: emitir aviso en stdout para el log de CI
    print(f"[conftest] Catálogo no encontrado; creado archivo mínimo en {CAT_PATH}")
# --- FIN BLOQUE NUEVO ---

# Continúa la ejecución normal
catalog = json.loads(CAT_PATH.read_text(encoding="utf-8"))
accounts = catalog.get("accounts", {})

with get_session() as s:
    # Insertar solo los códigos que no existan (no modifica existentes)
    added = 0
    for code, meta in accounts.items():
        existing = s.exec(select(Account).where(Account.code == str(code))).one_or_none()
        if not existing:
            a = Account(
                code=str(code),
                name=meta.get("name_comercial") or meta.get("name_osc") or "",
                nature=meta.get("naturaleza") or None
            )
            s.add(a)
            added += 1
    if added:
        s.commit()

    # Deduplicar por si acaso (mantener la fila con menor id por code) usando SQL directo
    try:
        s.exec(text("DELETE FROM account WHERE id NOT IN (SELECT MIN(id) FROM account GROUP BY code);"))
        s.commit()
    except Exception:
        # Si falla la dedup, permitimos que los tests sigan y lo reporten
        pass
