"""
Startup dialogs for UI initialization.
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPushButton, QButtonGroup, QRadioButton, QHBoxLayout
)
from PySide6.QtCore import Qt

from .utils import set_accounting_type


class AccountingTypeDialog(QDialog):
    """
    Dialog to select accounting type: Comercial or Sin fines de lucro.
    This should be shown once on first startup.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Seleccionar tipo de contabilidad")
        self.resize(400, 200)
        self.selected_type = None
        
        layout = QVBoxLayout()
        
        # Title
        title = QLabel("Seleccione el tipo de contabilidad para su organización:")
        title.setStyleSheet("font-size: 14px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title)
        
        # Radio buttons
        self.radio_comercial = QRadioButton("Comercial")
        self.radio_sin_fines = QRadioButton("Sin fines de lucro")
        
        self.button_group = QButtonGroup()
        self.button_group.addButton(self.radio_comercial)
        self.button_group.addButton(self.radio_sin_fines)
        
        layout.addWidget(self.radio_comercial)
        layout.addWidget(self.radio_sin_fines)
        layout.addStretch()
        
        # Buttons
        button_layout = QHBoxLayout()
        self.btn_ok = QPushButton("Aceptar")
        self.btn_cancel = QPushButton("Cancelar")
        
        self.btn_ok.clicked.connect(self.accept_selection)
        self.btn_cancel.clicked.connect(self.reject)
        
        button_layout.addStretch()
        button_layout.addWidget(self.btn_ok)
        button_layout.addWidget(self.btn_cancel)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
        
        # Set default selection
        self.radio_comercial.setChecked(True)
    
    def accept_selection(self):
        """Accept and save the selected accounting type."""
        if self.radio_comercial.isChecked():
            self.selected_type = "comercial"
        elif self.radio_sin_fines.isChecked():
            self.selected_type = "sin_fines"
        else:
            # No selection, shouldn't happen but handle it
            return
        
        # Save the selection
        if set_accounting_type(self.selected_type):
            self.accept()
        else:
            # TODO: Show error dialog if save fails
            self.reject()
    
    def get_selected_type(self) -> str:
        """Return the selected accounting type."""
        return self.selected_type
