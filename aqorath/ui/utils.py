"""
UI utilities for loading catalog and app configuration.
"""
from pathlib import Path
from typing import Dict, Set, Any, Optional
import json
import logging

from aqorath.catalog import load_catalog, load_catalog_codes as _load_catalog_codes
from aqorath.config import get_accounting_model, set_accounting_model

LOG = logging.getLogger(__name__)

# App config path (local JSON file for UI preferences)
APP_CONFIG_PATH = Path.home() / ".local" / "share" / "aqorath" / "ui_config.json"


def load_catalog_codes() -> Set[str]:
    """
    Load and return the set of account codes from the catalog.
    Delegates to aqorath.catalog.load_catalog_codes.
    """
    return _load_catalog_codes()


def load_catalog_dict() -> Dict[str, Any]:
    """
    Load and return the full catalog dictionary.
    """
    return load_catalog()


def load_app_config() -> Dict[str, Any]:
    """
    Load UI-specific app configuration from local JSON file.
    Returns empty dict if file doesn't exist or can't be read.
    """
    if not APP_CONFIG_PATH.exists():
        return {}
    try:
        with APP_CONFIG_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        LOG.warning(f"Failed to load app config: {e}")
        return {}


def save_app_config(config: Dict[str, Any]) -> bool:
    """
    Save UI-specific app configuration to local JSON file.
    Returns True on success, False on failure.
    """
    try:
        APP_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with APP_CONFIG_PATH.open("w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        LOG.error(f"Failed to save app config: {e}")
        return False


def get_accounting_type() -> Optional[str]:
    """
    Get the accounting type (comercial / sin_fines).
    Delegates to aqorath.config.get_accounting_model.
    """
    return get_accounting_model()


def set_accounting_type(value: str) -> bool:
    """
    Set the accounting type (comercial / sin_fines).
    Delegates to aqorath.config.set_accounting_model.
    """
    return set_accounting_model(value)


def is_accounting_type_set() -> bool:
    """
    Check if accounting type has been set.
    """
    return get_accounting_type() is not None
