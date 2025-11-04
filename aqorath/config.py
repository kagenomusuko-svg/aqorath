"""
Configuration management for Aqorath.

Provides persistent storage for application configuration like accounting model selection.
Tries to use the database (AppConfig model) when available, otherwise falls back to
a JSON file at ~/.local/share/aqorath/config.json.
"""
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Fallback config file location
CONFIG_PATH = Path.home() / ".local" / "share" / "aqorath" / "config.json"


def get_accounting_model() -> Optional[str]:
    """
    Get the saved accounting model selection.
    
    Returns:
        "comercial", "sin_fines", or None if not set.
        
    First tries to read from AppConfig in the database if available.
    Falls back to reading from the JSON config file.
    """
    # Try database first
    try:
        from aqorath.models import AppConfig
        from aqorath.storage import get_session
        
        with get_session() as s:
            from sqlmodel import select
            row = s.exec(select(AppConfig).where(AppConfig.key == "accounting_model")).one_or_none()
            if row:
                value = getattr(row, "value", None)
                logger.debug(f"Retrieved accounting_model from DB: {value}")
                return value
    except Exception as e:
        logger.debug(f"Could not read accounting_model from DB: {e}")
    
    # Fallback to JSON file
    try:
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            value = cfg.get("accounting_model")
            logger.debug(f"Retrieved accounting_model from file: {value}")
            return value
    except Exception as e:
        logger.debug(f"Could not read accounting_model from file: {e}")
    
    logger.debug("No accounting_model found in DB or file")
    return None


def set_accounting_model(value: str) -> bool:
    """
    Save the accounting model selection.
    
    Args:
        value: Should be "comercial" or "sin_fines"
        
    Returns:
        True if successfully saved, False otherwise.
        
    First tries to save to AppConfig in the database if available.
    Falls back to saving to the JSON config file.
    """
    if not value:
        logger.error("Cannot set empty accounting_model")
        return False
    
    # Try database first
    try:
        from aqorath.models import AppConfig
        from aqorath.storage import get_session
        
        with get_session() as s:
            from sqlmodel import select
            existing = s.exec(select(AppConfig).where(AppConfig.key == "accounting_model")).one_or_none()
            if existing:
                existing.value = value
                s.add(existing)
            else:
                s.add(AppConfig(key="accounting_model", value=value))
            s.commit()
            logger.info(f"Saved accounting_model to DB: {value}")
            return True
    except Exception as e:
        logger.debug(f"Could not save accounting_model to DB: {e}, falling back to file")
    
    # Fallback to JSON file
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        cfg = {"accounting_model": value}
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved accounting_model to file: {value}")
        return True
    except Exception as e:
        logger.error(f"Failed to save accounting_model to file: {e}")
        return False


def is_accounting_model_set() -> bool:
    """
    Check if an accounting model has been set.
    
    Returns:
        True if a model is set, False otherwise.
    """
    return get_accounting_model() is not None
