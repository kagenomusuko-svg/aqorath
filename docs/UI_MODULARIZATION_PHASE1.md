# UI Modularization - Phase 1

This document describes the Phase 1 implementation of UI modularization for Aqorath.

## Overview

Phase 1 implements:
- Modular UI package structure (`aqorath/ui/`)
- AsientoDialog with strict catalog validation
- Database initialization on startup
- AccountingTypeDialog for initial setup

## Components

### aqorath/ui/utils.py
Utility functions for loading catalog codes and app configuration.

### aqorath/ui/startup.py
AccountingTypeDialog for selecting accounting model (Comercial / Sin fines de lucro).

### aqorath/ui/sidebar.py
Helper function to create sidebar layout with Ingreso/Egreso/Cuentas propias buttons.

### aqorath/ui/asiento_dialog.py
Journal entry dialog with:
- Strict catalog validation (combo box, no free text)
- Balance validation
- Entry persistence via post_entry()

### aqorath/ui/main_window.py
Refactored main window using modular components.

## Testing

Run tests with:
```bash
python -m pytest tests/
```

Manual testing:
```bash
python -m aqorath.desktop
```

## Storage Validation

The storage layer prevents creation of non-catalog accounts through a SQLAlchemy event listener.
This provides defense-in-depth alongside UI validation.
