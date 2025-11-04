"""
Dialogo de bienvenida para seleccionar el tipo de contabilidad.

Behaviour:
- Muestra 2 botones: Comercial / Sin fines de lucro
- Persiste la elección (intenta AppConfig DB; si falla, usa ~/.local/share/aqorath/config.json)
- Una vez elegido, el modelo es INMUTABLE - no se puede cambiar desde el diálogo
- Abre la MainWindow al confirmar la opción
"""
import logging

try:
    from PySide6.QtWidgets import (
        QApplication,
        QDialog,
        QVBoxLayout,
        QLabel,
        QPushButton,
        QMessageBox,
    )
except Exception as exc:
    # We'll handle missing Qt in caller
    QApplication = None  # type: ignore

from aqorath.config import get_accounting_model, set_accounting_model, is_accounting_model_set

logger = logging.getLogger(__name__)


class WelcomeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Bienvenido")
        self.resize(420, 200)
        layout = QVBoxLayout(self)
        
        # Check if accounting model is already set
        existing_model = get_accounting_model()
        
        if existing_model:
            # Model already set - show informational message and make immutable
            logger.info(f"Accounting model already set to: {existing_model}")
            model_name = "Comercial" if existing_model == "comercial" else "Sin fines de lucro"
            label = QLabel(
                f"El modelo de contabilidad ya está configurado como:\n\n"
                f"<b>{model_name}</b>\n\n"
                f"Esta configuración no puede ser cambiada."
            )
            label.setWordWrap(True)
            layout.addWidget(label)
            
            btn_ok = QPushButton("Aceptar")
            btn_ok.clicked.connect(self.accept)
            layout.addWidget(btn_ok)
            
            self.chosen = existing_model
        else:
            # No model set yet - allow selection
            label = QLabel("Bienvenido. Por favor selecciona el tipo de contabilidad que deseas registrar.")
            label.setWordWrap(True)
            layout.addWidget(label)

            btn_comercial = QPushButton("Comercial")
            btn_osc = QPushButton("Sin fines de lucro")

            btn_comercial.clicked.connect(lambda: self._choose("comercial"))
            btn_osc.clicked.connect(lambda: self._choose("sin_fines"))

            layout.addWidget(btn_comercial)
            layout.addWidget(btn_osc)

            self.chosen = None

    def _choose(self, choice: str):
        """Save the accounting model choice. Once saved, it becomes immutable."""
        # Use the new config module to save
        saved = set_accounting_model(choice)
        
        if saved:
            logger.info(f"Accounting model set to: {choice}")
            self.chosen = choice
            self.accept()
        else:
            QMessageBox.critical(
                self, 
                "Error", 
                f"No se pudo guardar la elección. Por favor intente nuevamente."
            )


def get_current_choice():
    """
    Get the current accounting model choice.
    Deprecated: Use aqorath.config.get_accounting_model() instead.
    """
    return get_accounting_model()


if __name__ == "__main__":
    # pruebas locales rápidas
    if QApplication is None:
        print("PySide6 no está instalado. Instalar con: pip install PySide6")
    else:
        app = QApplication([])
        dlg = WelcomeDialog()
        if dlg.exec():
            print("Elegido:", dlg.chosen)
        app.exec()