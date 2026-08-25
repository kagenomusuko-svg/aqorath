"""
Módulo de catálogo para aqorath.

Provee funciones para leer el catálogo JSON embebido en:
  aqorath/data/catalogo_base.json

Ofrece una función resolve_account_by_code con dos comportamientos:
 - resolve_account_by_code(session, code, prefer=None) -> devuelve instancia Account o None (consulta BD)
 - resolve_account_by_code(code) -> devuelve metadata del catálogo JSON (sin tocar la BD)
"""

from __future__ import annotations
from pathlib import Path
import json
from typing import Dict, Optional, Set, Any

# Ruta por defecto al catálogo embebido
_DEFAULT_CATALOG_PATH = Path(__file__).resolve().parent / "data" / "catalogo_base.json"


def get_catalog_path() -> Path:
    """Devuelve la ruta al JSON del catálogo dentro del paquete."""
    return _DEFAULT_CATALOG_PATH


def load_catalog(path: Optional[Path] = None) -> Dict[str, Any]:
    """Carga y devuelve el dict del catálogo."""
    p = Path(path) if path else get_catalog_path()
    if not p.exists():
        raise FileNotFoundError(f"Catálogo no encontrado: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def load_catalog_codes(path: Optional[Path] = None) -> Set[str]:
    """Devuelve el conjunto de códigos definidos en el catálogo."""
    data = load_catalog(path)
    accounts = data.get("accounts", {}) if isinstance(data, dict) else {}
    return {str(k).strip() for k in accounts.keys()}


def _resolve_from_json(code: str, path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Resuelve metadata desde el JSON del catálogo; devuelve dict o None."""
    if code is None:
        return None
    code_str = str(code).strip()
    data = load_catalog(path)
    accounts = data.get("accounts") or {}
    return accounts.get(code_str)


def resolve_account_by_code(session_or_code, code: Optional[str] = None, prefer: Optional[str] = None):
    """
    Dual API:
    - Si se llama con (session, code), consulta la BD y devuelve Account o None.
    - Si se llama solo con (code), devuelve el dict del catálogo JSON.

    El parámetro 'prefer' (por ejemplo, 'osc' o 'comercial') se acepta
    para compatibilidad futura y puede usarse por el llamador
    para elegir qué nombre mostrar.
    """
    # Caso A: llamado como (session, code)
    if code is not None:
        session = session_or_code
        from sqlmodel import select
        from aqorath.models import Account  # Import interno para evitar ciclos
        code_str = str(code).strip()
        return session.exec(select(Account).where(Account.code == code_str)).one_or_none()

    # Caso B: llamado con solo el código
    return _resolve_from_json(str(session_or_code))


def create_entity_account(session, parent_code: str, name: str):
    """
    P1-3: Crear una cuenta de entidad bajo un padre canónico.
    
    Parámetros:
    - session: SQLModel Session
    - parent_code: código de cuenta canónica (ej. "1101")
    - name: nombre de la entidad (ej. "BBVA")
    
    Retorna: Account creada y persistida
    
    El código es generado automáticamente como: parent_code.NNN
    La naturaleza se hereda del padre.
    origin se establece como "entity".
    parent_id se establece al id del padre.
    
    Levanta ValueError si:
    - parent_code no existe
    - parent es entity (no canonical)
    - name vacío
    - error al generar código
    """
    from sqlmodel import select
    from aqorath.models import Account
    
    # Normalizar entrada
    parent_code = str(parent_code).strip()
    name = str(name).strip()
    
    if not name:
        raise ValueError("name no puede estar vacío")
    
    # Buscar padre
    parent = session.exec(
        select(Account).where(Account.code == parent_code)
    ).one_or_none()
    
    if not parent:
        raise ValueError(f"Parent account '{parent_code}' no existe")
    
    # Validar que padre es canónico
    if parent.origin != "canonical":
        raise ValueError(
            f"Parent debe ser canónico. '{parent_code}' tiene origin='{parent.origin}'"
        )
    
    # Validar que padre está en catálogo
    catalog_codes = load_catalog_codes()
    if parent_code not in catalog_codes:
        raise ValueError(
            f"Parent canónico '{parent_code}' no está en catálogo oficial"
        )
    
    # Generar código para la entidad
    import re
    
    existing_entity_codes = session.exec(
        select(Account).where(
            (Account.parent_id == parent.id) & 
            (Account.origin == "entity")
        )
    ).all()
    
    # Extraer números siguientes el patrón parent_code.NNN
    pattern = rf"^{re.escape(parent_code)}\.(\d{{3}})$"
    max_suffix = 0
    
    for entity in existing_entity_codes:
        match = re.match(pattern, entity.code)
        if match:
            suffix_num = int(match.group(1))
            max_suffix = max(max_suffix, suffix_num)
    
    next_suffix = max_suffix + 1
    if next_suffix > 999:
        raise ValueError(
            f"No se pueden crear más extensiones bajo '{parent_code}' "
            f"(máximo 999 alcanzado)"
        )
    
    entity_code = f"{parent_code}.{next_suffix:03d}"
    
    # Crear la entidad
    entity_account = Account(
        code=entity_code,
        name=name,
        nature=parent.nature,  # Hereda naturaleza
        origin="entity",
        parent_id=parent.id,
    )
    
    session.add(entity_account)
    session.commit()
    session.refresh(entity_account)
    
    return entity_account


__all__ = [
    "get_catalog_path",
    "load_catalog",
    "load_catalog_codes",
    "resolve_account_by_code",
    "create_entity_account",
]
