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
        
        # Add "Cierre del ejercicio" menu item
        close_exercise_action = QAction("Cierre del ejercicio", self)
        close_exercise_action.triggered.connect(self.handle_close_exercise)
        menu_conf.addAction(close_exercise_action)

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
    
    def handle_close_exercise(self):
        """
        Handle the "Cierre del ejercicio" menu action.
        Shows warning dialog and, if confirmed, performs the exercise close operation.
        """
        try:
            # Show warning message
            warning_text = (
                "⚠️ ADVERTENCIA: El cierre del ejercicio es una operación IRREVERSIBLE.\n\n"
                "Esta operación realizará las siguientes acciones:\n"
                "1. Transferirá el saldo de la cuenta 3103 (Resultado del ejercicio) a la cuenta 3104\n"
                "2. Creará un respaldo de la base de datos\n"
                "3. Generará los asientos contables correspondientes\n\n"
                "Una vez confirmado, NO será posible deshacer esta operación.\n\n"
                "¿Está seguro de que desea continuar con el cierre del ejercicio?"
            )
            
            reply = QMessageBox.warning(
                self,
                "Cierre del ejercicio - Confirmación",
                warning_text,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.No:
                return
            
            # Try to import and execute close_exercise
            try:
                from aqorath.exercise import close_exercise
                from aqorath.core import trial_balance
                
                # Get trial balance to check 3103
                balance = trial_balance()
                
                if "3103" not in balance or balance.get("3103") == 0:
                    QMessageBox.warning(
                        self,
                        "Error",
                        "No se encontró saldo en la cuenta 3103 (Resultado del ejercicio).\n"
                        "No es necesario realizar el cierre del ejercicio."
                    )
                    return
                
                # Execute close_exercise
                result = close_exercise()
                
                if result.get("status") == "success":
                    QMessageBox.information(
                        self,
                        "Cierre del ejercicio completado",
                        f"El cierre del ejercicio se ha completado exitosamente.\n\n"
                        f"Respaldo creado en: {result.get('backup_path', 'N/A')}\n"
                        f"Saldo transferido: {result.get('amount_transferred', 0)}\n"
                        f"Asiento creado: ID {result.get('entry_id', 'N/A')}"
                    )
                else:
                    QMessageBox.critical(
                        self,
                        "Error",
                        f"Error al realizar el cierre del ejercicio:\n{result.get('message', 'Error desconocido')}"
                    )
            
            except ImportError:
                # If aqorath.exercise doesn't exist, show message
                QMessageBox.information(
                    self,
                    "Funcionalidad no disponible",
                    "La funcionalidad de cierre del ejercicio no está disponible en esta versión.\n"
                    "Por favor, ejecute manualmente el script de cierre o contacte al administrador."
                )
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Error",
                    f"Error al realizar el cierre del ejercicio:\n{str(e)}"
                )
        
        except Exception as e:
            # Catch-all for any unexpected errors
            QMessageBox.critical(
                self,
                "Error",
                f"Error inesperado:\n{str(e)}"
            )


if __name__ == "__main__":
    if QApplication is None:
        print("PySide6 no instalado. Ejecuta: pip install PySide6")
    else:
        app = QApplication([])
        w = MainWindow()
        w.show()
        app.exec()