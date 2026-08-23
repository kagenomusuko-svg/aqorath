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


# ============================================================================
# FIXTURES PARA TESTS P0 (REGRESSION TESTS)
# ============================================================================

import pytest
import tempfile
import sqlite3
from decimal import Decimal
from datetime import datetime, timezone
from sqlmodel import Session, create_engine, SQLModel

@pytest.fixture
def temp_db_with_accounts():
    """
    Crea SQLite temporal AISLADA para tests P0.
    Evita listeners de storage.py usando sqlite3 directo para setup.
    Retorna (db_path, engine, session_factory).
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_p0.db"
        
        # 1) Crear schema con sqlite3 directo (evita listeners)
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        
        # Crear tablas mínimas
        cur.execute("""
            CREATE TABLE account (
                id INTEGER PRIMARY KEY,
                code TEXT UNIQUE,
                name TEXT,
                nature TEXT,
                vat_flag BOOLEAN DEFAULT 0,
                created_at TIMESTAMP
            )
        """)
        
        cur.execute("""
            CREATE TABLE journalentry (
                id INTEGER PRIMARY KEY,
                date TIMESTAMP,
                concept TEXT,
                doc_ref TEXT,
                period_id INTEGER,
                posted_by TEXT,
                state TEXT,
                created_at TIMESTAMP
            )
        """)
        
        cur.execute("""
            CREATE TABLE journalline (
                id INTEGER PRIMARY KEY,
                entry_id INTEGER,
                account_code TEXT,
                account_id INTEGER,
                debit FLOAT,
                credit FLOAT,
                description TEXT,
                created_at TIMESTAMP
            )
        """)
        
        # 2) Insertar cuentas base con sqlite3 (directo, sin listeners)
        now = datetime.now(timezone.utc).isoformat()
        accounts = [
            ("1000", "Bancos", "debit"),
            ("3000", "Ventas", "credit"),
            ("3100", "Costos", "debit"),
            ("4000", "Gastos", "debit"),
            ("3103", "Resultado", "credit"),
        ]
        for code, name, nature in accounts:
            cur.execute(
                "INSERT INTO account (code, name, nature, created_at) VALUES (?, ?, ?, ?)",
                (code, name, nature, now)
            )
        
        conn.commit()
        conn.close()
        
        # 3) Crear engine y session para lectura/escritura test
        engine = create_engine(f"sqlite:///{db_path}", echo=False)
        
        # Cargar modelos para que SQLAlchemy los conozca
        from aqorath.models import Account, JournalEntry, JournalLine
        
        yield db_path, engine
        
        # Cleanup automático


@pytest.fixture
def session_from_temp_db(temp_db_with_accounts):
    """Sesión contra DB P0 temporal."""
    db_path, engine = temp_db_with_accounts
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def minimal_catalog():
    """Catálogo mínimo para tests P0."""
    return {
        "accounts": {
            "1000": {"name_comercial": "Bancos", "tipo": "Activo", "naturaleza": "debit"},
            "3000": {"name_comercial": "Ventas", "tipo": "Ingreso", "naturaleza": "credit"},
            "3100": {"name_comercial": "Costos", "tipo": "Costo", "naturaleza": "debit"},
            "4000": {"name_comercial": "Gastos", "tipo": "Gasto", "naturaleza": "debit"},
            "3103": {"name_comercial": "Resultado del Ejercicio", "tipo": "Patrimonio", "naturaleza": "credit"},
        }
    }


@pytest.fixture
def setup_accounts_in_session(session_from_temp_db):
    """
    Retorna la sesión (cuentas ya están en la BD temporal).
    No necesita insertar porque ya están creadas en temp_db_with_accounts.
    """
    return session_from_temp_db


@pytest.fixture
def env_with_temp_db(temp_db_with_accounts):
    """Configura AQORATH_DB para apuntar a DB temporal."""
    db_path, engine = temp_db_with_accounts
    old_db = os.environ.get("AQORATH_DB")
    os.environ["AQORATH_DB"] = str(db_path)
    
    yield db_path
    
    if old_db is not None:
        os.environ["AQORATH_DB"] = old_db
    elif "AQORATH_DB" in os.environ:
        del os.environ["AQORATH_DB"]
