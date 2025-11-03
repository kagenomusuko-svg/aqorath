"""
MainWindow esqueleto con logo central, botones laterales (Ingreso/Egreso/Cuentas propias)
y un menú superior con Reportes/Catálogo/Configuración.
"""
import os
from pathlib import Path

try:
    from PySide6.QtGui import QPixmap, QAction
    from PySide6.QtWidgets import (
        QApplication,
        QMainWindow,
        QLabel,
        QWidget,
        QHBoxLayout,
        QVBoxLayout,
        QPushButton,
        QMenuBar,
        QMessageBox,
    )
except Exception:
    QApplication = None  # type: ignore

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
        gen_report_action.triggered.connect(lambda: QMessageBox.information(self, "Reportes", "Generar reporte - pendiente"))
        menu_reportes.addAction(gen_report_action)

        catalog_action = QAction("Ver catálogo", self)
        catalog_action.triggered.connect(lambda: QMessageBox.information(self, "Catálogo", "Abrir catálogo - pendiente"))
        menu_catalogo.addAction(catalog_action)

        conf_action = QAction("Ajustes", self)
        conf_action.triggered.connect(lambda: QMessageBox.information(self, "Configuración", "Configuración - pendiente"))
        menu_conf.addAction(conf_action)

        # Layout central
        central = QWidget()
        h = QHBoxLayout(central)

        # Botones laterales (izquierda)
        left = QVBoxLayout()
        btn_ingreso = QPushButton("[I] Ingreso")
        btn_egreso = QPushButton("[E] Egreso")
        btn_diario = QPushButton("[D] Cuentas propias")
        btn_ingreso.clicked.connect(lambda: QMessageBox.information(self, "Ingreso", "Registrar Ingreso - pendiente"))
        btn_egreso.clicked.connect(lambda: QMessageBox.information(self, "Egreso", "Registrar Egreso - pendiente"))
        btn_diario.clicked.connect(lambda: QMessageBox.information(self, "Cuentas propias", "Registrar Cuentas propias - pendiente"))

        left.addWidget(btn_ingreso)
        left.addWidget(btn_egreso)
        left.addWidget(btn_diario)
        left.addStretch(1)

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

        h.addLayout(left, 0)
        h.addWidget(center_widget, 1)
        h.addLayout(right_layout, 0)

        self.setCentralWidget(central)


if __name__ == "__main__":
    if QApplication is None:
        print("PySide6 no instalado. Ejecuta: pip install PySide6")
    else:
        app = QApplication([])
        w = MainWindow()
        w.show()
        app.exec()