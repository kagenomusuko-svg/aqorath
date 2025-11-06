"""
Minimal desktop launcher for Aqorath.
Initializes DB with tables and shows accounting type selection if not set.
"""
from PySide6.QtWidgets import QApplication, QDialog
import sys

from aqorath.storage import init_db, get_db_path
from aqorath.ui.startup import AccountingTypeDialog
from aqorath.ui.main_window import MainWindow
from aqorath.ui.utils import is_accounting_type_set


def main():
    """Main entry point for desktop application."""
    # Create QApplication first
    app = QApplication(sys.argv)
    
    # Initialize database with table creation
    db_path = get_db_path()
    init_db(db_path=db_path, create_tables=True)
    
    # Check if accounting type is set; if not, show dialog
    if not is_accounting_type_set():
        dialog = AccountingTypeDialog()
        result = dialog.exec()
        if result != QDialog.Accepted:
            # User cancelled, exit application
            sys.exit(0)
    
    # Show main window
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
