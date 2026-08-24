from pathlib import Path
import os
from typing import Optional

from sqlmodel import Session, create_engine
from sqlalchemy import event
from sqlalchemy.engine import Connection

# DEFAULT DB location (user local data dir)
DEFAULT_DB = Path.home() / ".local" / "share" / "aqorath" / "aqorath.db"

# Module-level state
_DB_PATH: Optional[str] = None
_engine = None
_account_listener_registered = False

def get_db_path() -> str:
    """
    Devuelve la ruta absoluta del DB usado por la aplicación.
    Priorizamos la variable de entorno AQORATH_DB si está establecida.
    """
    env = os.environ.get("AQORATH_DB")
    if env:
        return str(Path(env).resolve())
    return str(DEFAULT_DB)


# Provide DB_PATH at import time (tests expect this name)
DB_PATH = get_db_path()


def _register_account_listener():
    """
    Registra un listener que impide la inserción de Accounts cuyo código
    no esté presente en el catálogo JSON. Se registra sólo si los imports
    necesarios están disponibles (evita import cycles).
    """
    global _account_listener_registered
    if _account_listener_registered:
        return

    try:
        # import aquí para evitar problemas de import circular durante import time
        from aqorath.models import Account
        from aqorath.catalog import load_catalog_codes
    except Exception:
        # si no podemos importar (modelos no listos aún), no registramos ahora
        return

    @event.listens_for(Account, "before_insert")
    def _prevent_non_catalog_account(mapper, connection: Connection, target):
        try:
            catalog_codes = load_catalog_codes()
        except Exception:
            # si no podemos leer catálogo, fallamos con mensaje claro
            raise RuntimeError("No se pudo cargar el catálogo para validar códigos de cuenta.")
        code_str = str(getattr(target, "code", "")).strip()
        if not code_str:
            raise ValueError("Inserción denegada: código de cuenta vacío.")
        if code_str not in catalog_codes:
            raise ValueError(
                f"Inserción denegada: la cuenta '{code_str}' no existe en el catálogo. "
                "Solo se permiten cuentas definidas en aqorath/data/catalogo_base.json."
            )

    _account_listener_registered = True


def _create_engine(db_path: str):
    """
    P1-1: Crea y devuelve un engine SQLModel/SQLAlchemy para la ruta dada.
    Registra listeners necesarios.
    """
    url = f"sqlite:///{db_path}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    # intentar registrar listener ahora que imports deberían resolverse
    _register_account_listener()
    return engine


def get_engine():
    """
    P1-1: Obtener (y crear si hace falta) el engine usando AQORATH_DB o DEFAULT_DB.
    Path-aware: Si AQORATH_DB cambió, recrea el engine.
    """
    global _engine, _DB_PATH, DB_PATH
    desired_path = get_db_path()
    
    # Si engine no existe o la ruta ha cambiado: recrear
    if _engine is None or _DB_PATH != desired_path:
        # Disponer del engine anterior si existe
        if _engine is not None:
            try:
                _engine.dispose()
            except Exception:
                pass
        _engine = _create_engine(desired_path)
        _DB_PATH = desired_path
        DB_PATH = desired_path
    
    return _engine


def get_session() -> Session:
    """
    Devuelve una instancia de Session. Puede usarse como "with get_session() as s:".
    """
    eng = get_engine()
    return Session(eng)


def init_db(db_path: Optional[str] = None, create_tables: bool = False):
    """
    Inicializa la conexión a la base de datos. Si create_tables=True creará
    las tablas definidas en SQLModel.metadata.create_all(engine).
    - db_path: ruta absoluta o relativa al fichero SQLite. Si no se pasa, usa AQORATH_DB o DEFAULT_DB.
    """
    global _engine, _DB_PATH, DB_PATH
    if db_path:
        os.environ["AQORATH_DB"] = str(Path(db_path).resolve())
    _DB_PATH = get_db_path()
    DB_PATH = _DB_PATH
    _engine = _create_engine(_DB_PATH)

    if create_tables:
        # importamos SQLModel aquí para evitar import circular
        from sqlmodel import SQLModel
        SQLModel.metadata.create_all(_engine)

    # asegurar el listener quedó registrado si antes no fue posible
    _register_account_listener()

    return _engine