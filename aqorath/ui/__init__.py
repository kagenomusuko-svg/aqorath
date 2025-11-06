"""
UI package for Aqorath desktop application.

This package provides modular UI components for the accounting system:
- startup: AccountingTypeDialog for initial configuration
- main_window: MainWindow with sidebar and menu
- asiento_dialog: AsientoDialog for journal entry creation
- sidebar: Helper for creating sidebar layouts
- utils: Utility functions for catalog and config
"""

from .main_window import MainWindow
from .startup import AccountingTypeDialog
from .asiento_dialog import AsientoDialog
from .sidebar import create_sidebar
from .utils import load_catalog_codes, load_app_config, save_app_config

__all__ = [
    "MainWindow",
    "AccountingTypeDialog", 
    "AsientoDialog",
    "create_sidebar",
    "load_catalog_codes",
    "load_app_config",
    "save_app_config",
]