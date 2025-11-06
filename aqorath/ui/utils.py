"""
UI utilities for loading catalog codes and app config.
"""
from pathlib import Path
import json
from typing import Dict, Set, Optional, Any


def load_catalog_codes() -> Set[str]:
    """
    Load account codes from the catalog JSON file.
    Returns a set of account code strings.
    """
    from aqorath.catalog import load_catalog_codes as _load_catalog_codes
    return _load_catalog_codes()


def load_app_config() -> Dict[str, Any]:
    """
    Load application configuration from local config file.
    Returns empty dict if config doesn't exist.
    """
    config_path = Path.home() / ".local" / "share" / "aqorath" / "config.json"
    if not config_path.exists():
        return {}
    
    try:
        with config_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_app_config(config: Dict[str, Any]) -> bool:
    """
    Save application configuration to local config file.
    Returns True on success, False on failure.
    """
    config_path = Path.home() / ".local" / "share" / "aqorath" / "config.json"
    
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with config_path.open("w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False
