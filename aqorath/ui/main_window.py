"""
MainWindow refactored to use modular UI components.
Includes sidebar with Ingreso/Egreso/Cuentas propias and AsientoDialog integration.
"""
from pathlib import Path

from PySide6.QtGui import QPixmap, QAction
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QLabel,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QMessageBox,
)

from .sidebar import create_sidebar
from .asiento_dialog import AsientoDialog

ASSETS_LOGO = Path(__file__).resolve().parents[1] / "assets" / "sello_ac.png"


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AQORATH - Sistema contable")
        self.resize(1000, 700)

        # Menú superior
        menu = self.menuBar()
        menu_reportes = menu.addMenu("Reportes")
        menu_catalogo = menu.addMenu("Catálogo")
        menu_conf = menu.addMenu("Configuración")

        gen_report_action = QAction("Generar reporte", self)
        gen_report_action.triggered.connect(self.on_generate_report)
        menu_reportes.addAction(gen_report_action)

        catalog_action = QAction("Ver catálogo", self)
        catalog_action.triggered.connect(self.on_view_catalog)
        menu_catalogo.addAction(catalog_action)

        conf_action = QAction("Ajustes", self)
        conf_action.triggered.connect(self.on_settings)
        menu_conf.addAction(conf_action)

        # Layout central
        central = QWidget()
        h = QHBoxLayout(central)

        # Sidebar (left) with callbacks
        sidebar = create_sidebar(
            on_ingreso=self.on_ingreso,
            on_egreso=self.on_egreso,
            on_cuentas_propias=self.on_cuentas_propias
        )

        # Centro con logo
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        logo_label = QLabel()
        if ASSETS_LOGO.exists():
            pix = QPixmap(str(ASSETS_LOGO))
            logo_label.setPixmap(pix.scaledToWidth(380))
        else:
            logo_label.setText("Logo no encontrado: assets/sello_ac.png")
        center_layout.addStretch(1)
        center_layout.addWidget(logo_label, 0)
        center_layout.addStretch(1)

        # Right placeholder area (información / registros)
        right_layout = QVBoxLayout()
        right_layout.addWidget(QLabel("Panel de registros (próximamente)"))
        right_layout.addStretch(1)

        h.addLayout(sidebar, 0)
        h.addWidget(center_widget, 1)
        h.addLayout(right_layout, 0)

        self.setCentralWidget(central)
    
    def on_ingreso(self):
        """Handle Ingreso button click - open AsientoDialog."""
        dialog = AsientoDialog(self)
        dialog.exec()
    
    def on_egreso(self):
        """Handle Egreso button click - open AsientoDialog."""
        dialog = AsientoDialog(self)
        dialog.exec()
    
    def on_cuentas_propias(self):
        """Handle Cuentas propias button click - open AsientoDialog."""
        dialog = AsientoDialog(self)
        dialog.exec()
    
    def on_generate_report(self):
        """Placeholder for report generation."""
        QMessageBox.information(self, "Reportes", "Generar reporte - pendiente")
    
    def on_view_catalog(self):
        """Placeholder for viewing catalog."""
        QMessageBox.information(self, "Catálogo", "Abrir catálogo - pendiente")
    
    def on_settings(self):
        """Placeholder for settings."""
        QMessageBox.information(self, "Configuración", "Configuración - pendiente")


if __name__ == "__main__":
    app = QApplication([])
    w = MainWindow()
    w.show()
    app.exec()