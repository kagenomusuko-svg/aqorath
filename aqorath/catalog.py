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


__all__ = [
    "get_catalog_path",
    "load_catalog",
    "load_catalog_codes",
    "resolve_account_by_code",
]
