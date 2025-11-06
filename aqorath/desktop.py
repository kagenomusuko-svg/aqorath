"""
Desktop launcher for Aqorath accounting system.

This is a minimal launcher that:
1. Initializes the database with create_tables=True
2. Shows AccountingTypeDialog if config not set
3. Instantiates MainWindow and runs the app
"""
from PySide6.QtWidgets import QApplication
import sys
from pathlib import Path

from aqorath.storage import get_session, init_db, get_db_path
from aqorath.config import is_accounting_model_set, set_accounting_model
from aqorath.ui import MainWindow, AccountingTypeDialog


def main():
    """Main entry point for desktop application."""
    # Initialize QApplication
    app = QApplication(sys.argv)
    
    # Initialize database with create_tables=True
    db_path = get_db_path()
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    init_db(create_tables=True)
    
    # Check if accounting model is set
    if not is_accounting_model_set():
        dialog = AccountingTypeDialog()
        if dialog.exec():
            selected = dialog.get_selected_type()
            if selected:
                set_accounting_model(selected)
        else:
            # User cancelled, exit
            return 0
    
    # Show main window
    win = MainWindow()
    win.show()
    
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())