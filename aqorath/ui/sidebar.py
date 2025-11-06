"""
Sidebar helper for main window.
"""
from PySide6.QtWidgets import QVBoxLayout, QPushButton
from typing import Callable, Optional


def create_sidebar(
    on_ingreso: Optional[Callable] = None,
    on_egreso: Optional[Callable] = None,
    on_cuentas_propias: Optional[Callable] = None
) -> QVBoxLayout:
    """
    Create a sidebar layout with three main buttons:
    - [I] Ingreso
    - [E] Egreso
    - [D] Cuentas propias
    
    Each button calls the corresponding callback when clicked.
    Returns the QVBoxLayout containing the buttons.
    """
    sidebar = QVBoxLayout()
    
    btn_ingreso = QPushButton("[I] Ingreso")
    btn_egreso = QPushButton("[E] Egreso")
    btn_cuentas_propias = QPushButton("[D] Cuentas propias")
    
    if on_ingreso:
        btn_ingreso.clicked.connect(on_ingreso)
    if on_egreso:
        btn_egreso.clicked.connect(on_egreso)
    if on_cuentas_propias:
        btn_cuentas_propias.clicked.connect(on_cuentas_propias)
    
    sidebar.addWidget(btn_ingreso)
    sidebar.addWidget(btn_egreso)
    sidebar.addWidget(btn_cuentas_propias)
    sidebar.addStretch(1)
    
    return sidebar
