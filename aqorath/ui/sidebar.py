"""
Sidebar helper for the main window.
"""
from PySide6.QtWidgets import QVBoxLayout, QPushButton
from typing import Callable, Optional


def create_sidebar(
    on_ingreso: Optional[Callable] = None,
    on_egreso: Optional[Callable] = None,
    on_diario: Optional[Callable] = None
) -> QVBoxLayout:
    """
    Create sidebar layout with (I) Ingreso, (E) Egreso, (D) Cuentas propias buttons.
    
    Args:
        on_ingreso: Callback for Ingreso button
        on_egreso: Callback for Egreso button
        on_diario: Callback for Cuentas propias button
    
    Returns:
        QVBoxLayout with sidebar buttons
    """
    layout = QVBoxLayout()
    
    btn_ingreso = QPushButton("[I] Ingreso")
    btn_egreso = QPushButton("[E] Egreso")
    btn_diario = QPushButton("[D] Cuentas propias")
    
    if on_ingreso:
        btn_ingreso.clicked.connect(on_ingreso)
    if on_egreso:
        btn_egreso.clicked.connect(on_egreso)
    if on_diario:
        btn_diario.clicked.connect(on_diario)
    
    layout.addWidget(btn_ingreso)
    layout.addWidget(btn_egreso)
    layout.addWidget(btn_diario)
    layout.addStretch(1)
    
    return layout
