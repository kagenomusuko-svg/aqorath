"""
Startup dialog for selecting accounting type.
"""
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QButtonGroup
from PySide6.QtCore import Qt


class AccountingTypeDialog(QDialog):
    """
    Dialog for selecting accounting model type (Comercial / Sin fines de lucro).
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Seleccionar tipo de contabilidad")
        self.resize(400, 200)
        self.setModal(True)
        
        self.selected_type = None
        
        layout = QVBoxLayout()
        
        # Title
        title = QLabel("Seleccione el tipo de contabilidad:")
        title.setStyleSheet("font-size: 14pt; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title)
        
        # Buttons
        btn_comercial = QPushButton("Comercial")
        btn_comercial.setMinimumHeight(50)
        btn_comercial.clicked.connect(lambda: self._select_type("comercial"))
        
        btn_sin_fines = QPushButton("Sin fines de lucro")
        btn_sin_fines.setMinimumHeight(50)
        btn_sin_fines.clicked.connect(lambda: self._select_type("sin_fines"))
        
        layout.addWidget(btn_comercial)
        layout.addWidget(btn_sin_fines)
        layout.addStretch()
        
        self.setLayout(layout)
    
    def _select_type(self, type_str: str):
        """Set the selected type and accept dialog."""
        self.selected_type = type_str
        self.accept()
    
    def get_selected_type(self) -> str:
        """Return the selected accounting type."""
        return self.selected_type
