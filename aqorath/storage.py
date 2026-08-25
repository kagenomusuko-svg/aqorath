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


def _migrate_account_extension_schema(engine):
    """
    P1-3: Migración determinística de schema legacy.
    
    Añade origin y parent_id a tabla Account existente.
    Idempotente: seguro de ejecutar multiple veces.
    NO modifica datos existentes.
    """
    from sqlalchemy import inspect, text
    
    try:
        # Obtener inspector de SQLAlchemy
        insp = inspect(engine)
        
        # ¿Existe tabla account?
        if "account" not in insp.get_table_names():
            # DB nueva: create_all la creará con schema completo
            return
        
        # Obtener columnas existentes
        columns = {c["name"] for c in insp.get_columns("account")}
        
        # Conectar directamente para migraciones ALTER TABLE
        with engine.begin() as conn:
            # Añadir origin si no existe
            if "origin" not in columns:
                conn.execute(text("ALTER TABLE account ADD COLUMN origin VARCHAR NOT NULL DEFAULT 'canonical'"))
            
            # Añadir parent_id si no existe
            if "parent_id" not in columns:
                conn.execute(text("ALTER TABLE account ADD COLUMN parent_id INTEGER NULL"))
            
            # Crear índice si no existe
            try:
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_account_parent_id ON account(parent_id)"))
            except Exception:
                pass  # índice puede ya existir
        
    except Exception as e:
        # Errores de migración son críticos
        raise RuntimeError(f"Migración de schema account falló: {e}")


def _register_account_listener():
    """
    P1-3: Registra listeners que gobiernan cuentas canónicas y de entidad.
    
    Reglas:
    - Canonical: origin="canonical", parent_id=None, code en JSON
    - Entity: origin="entity", parent_id=parent canonical id, code=parent.NNN
    - Invariantes estructurales: no pueden modificarse
    """
    global _account_listener_registered
    if _account_listener_registered:
        return

    try:
        from aqorath.models import Account
        from aqorath.catalog import load_catalog_codes
        import re
    except Exception:
        return

    @event.listens_for(Account, "before_insert")
    def _govern_account_insert(mapper, connection: Connection, target):
        """Validar inserción según origin"""
        try:
            catalog_codes = load_catalog_codes()
        except Exception:
            raise RuntimeError("No se pudo cargar el catálogo para validar códigos de cuenta.")
        
        code_str = str(getattr(target, "code", "")).strip()
        origin = str(getattr(target, "origin", "canonical")).strip().lower()
        parent_id = getattr(target, "parent_id", None)
        name = str(getattr(target, "name", "")).strip()
        nature = str(getattr(target, "nature", "")).strip()
        
        if not code_str:
            raise ValueError("Inserción denegada: código de cuenta vacío.")
        if not name:
            raise ValueError("Inserción denegada: nombre de cuenta vacío.")
        
        # CANONICAL
        if origin == "canonical":
            if parent_id is not None:
                raise ValueError(
                    f"Cuenta canónica '{code_str}' no puede tener parent_id."
                )
            if code_str not in catalog_codes:
                raise ValueError(
                    f"Inserción denegada: la cuenta canónica '{code_str}' no existe en el catálogo."
                )
        
        # ENTITY
        elif origin == "entity":
            if parent_id is None:
                raise ValueError(
                    f"Cuenta de entidad '{code_str}' debe tener parent_id."
                )
            
            # Validar formato código: parent_code.NNN
            if "." not in code_str:
                raise ValueError(
                    f"Código de entidad '{code_str}' debe tener formato parent_code.NNN"
                )
            
            parts = code_str.rsplit(".", 1)
            if len(parts) != 2 or not parts[1].isdigit() or len(parts[1]) != 3:
                raise ValueError(
                    f"Código de entidad '{code_str}' debe tener formato parent_code.NNN (3 dígitos)"
                )
            
            parent_code_expected = parts[0]
            
            # Verificar que parent existe y es canónico
            try:
                from sqlalchemy import text
                
                parent_result = connection.execute(
                    text("SELECT id, code, origin, nature FROM account WHERE id = :pid"),
                    {"pid": parent_id}
                ).fetchone()
                
                if not parent_result:
                    raise ValueError(
                        f"Parent account con id {parent_id} no existe."
                    )
                
                parent_id_db, parent_code_db, parent_origin, parent_nature = parent_result
                
                if parent_origin != "canonical":
                    raise ValueError(
                        f"Parent debe ser canónico, no entidad. Parent code: {parent_code_db}"
                    )
                
                if parent_code_db != parent_code_expected:
                    raise ValueError(
                        f"Código entity '{code_str}' refiere parent '{parent_code_expected}' pero parent actual es '{parent_code_db}'"
                    )
                
                if parent_code_db not in catalog_codes:
                    raise ValueError(
                        f"Parent canónico '{parent_code_db}' no está en catálogo."
                    )
                
                # Naturaleza debe heredarse
                if nature != parent_nature:
                    raise ValueError(
                        f"Entidad hereda naturaleza '{parent_nature}' del padre, no puede ser '{nature}'"
                    )
            
            except Exception as e:
                if "no existe" in str(e) or "refiere" in str(e) or "hereda" in str(e):
                    raise
                raise ValueError(f"Error validando parent: {e}")
        
        else:
            raise ValueError(f"origin inválido: {origin}. Debe ser 'canonical' o 'entity'.")
    
    @event.listens_for(Account, "before_update")
    def _prevent_structural_changes(mapper, connection: Connection, target):
        """Prevenir cambios de estructura: code, origin, parent_id"""
        # Obtener estado anterior
        insp = object.__getattribute__(target, "_sa_instance_state")
        if not insp.has_identity:
            return  # Inserción, no actualización
        
        old_code = insp.committed_state.get("code")
        old_origin = insp.committed_state.get("origin", "canonical")
        old_parent_id = insp.committed_state.get("parent_id")
        
        new_code = target.code
        new_origin = target.origin
        new_parent_id = target.parent_id
        
        if new_code != old_code:
            raise ValueError(f"No se puede modificar code de cuenta: {old_code} → {new_code}")
        
        if new_origin != old_origin:
            raise ValueError(f"No se puede modificar origin de cuenta: {old_origin} → {new_origin}")
        
        if new_parent_id != old_parent_id:
            raise ValueError(f"No se puede modificar parent_id de cuenta: {old_parent_id} → {new_parent_id}")
        
        # Validación adicional para entity: naturaleza debe mantenerse igual a padre
        if new_origin == "entity" and new_parent_id:
            try:
                from sqlalchemy import text
                
                parent_nature = connection.execute(
                    text("SELECT nature FROM account WHERE id = :pid"),
                    {"pid": new_parent_id}
                ).scalar()
                
                if parent_nature and target.nature != parent_nature:
                    raise ValueError(
                        f"Naturaleza de entidad debe heredarse del padre. "
                        f"Padre: {parent_nature}, Intento: {target.nature}"
                    )
            except ValueError:
                raise
            except Exception as e:
                raise ValueError(f"Error validating entity nature: {e}")

    _account_listener_registered = True



def _create_engine(db_path: str):
    """
    P1-1: Crea y devuelve un engine SQLModel/SQLAlchemy para la ruta dada.
    P1-3: Ejecuta migración de schema si es necesario.
    Registra listeners necesarios.
    """
    url = f"sqlite:///{db_path}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    
    # P1-3: Migrar schema si es necesario (legacy DB)
    _migrate_account_extension_schema(engine)
    
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