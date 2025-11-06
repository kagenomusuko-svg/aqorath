"""
Refactored MainWindow using modular UI structure with sidebar and asiento dialog.
Includes trial_balance and close_exercise logic from finish_exercise method.
"""
import os
from pathlib import Path
from typing import Optional

from PySide6.QtGui import QPixmap, QAction
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QLabel,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QPushButton,
    QMessageBox,
    QDialog,
)

from .sidebar import create_sidebar
from .asiento_dialog import AsientoDialog

ASSETS_LOGO = Path(__file__).resolve().parents[1] / "assets" / "sello_ac.png"


class MainWindow(QMainWindow):
    """Main window with modular UI structure."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AQORATH - Sistema contable")
        self.resize(1000, 700)

        # Menú superior
        menu = self.menuBar()
        menu_reportes = menu.addMenu("Reportes")
        menu_catalogo = menu.addMenu("Catálogo")
        menu_conf = menu.addMenu("Configuración")

        # Reports menu actions
        gen_report_action = QAction("Generar reporte", self)
        gen_report_action.triggered.connect(self.on_generate_report)
        menu_reportes.addAction(gen_report_action)
        
        trial_balance_action = QAction("Balance de comprobación", self)
        trial_balance_action.triggered.connect(self.on_trial_balance)
        menu_reportes.addAction(trial_balance_action)
        
        close_exercise_action = QAction("Cerrar ejercicio", self)
        close_exercise_action.triggered.connect(self.on_close_exercise)
        menu_reportes.addAction(close_exercise_action)

        # Catalog menu actions
        catalog_action = QAction("Ver catálogo", self)
        catalog_action.triggered.connect(self.on_view_catalog)
        menu_catalogo.addAction(catalog_action)

        # Config menu actions
        conf_action = QAction("Ajustes", self)
        conf_action.triggered.connect(self.on_settings)
        menu_conf.addAction(conf_action)

        # Layout central
        central = QWidget()
        h = QHBoxLayout(central)

        # Botones laterales (izquierda) using sidebar helper
        left = create_sidebar(
            on_ingreso=self.on_ingreso,
            on_egreso=self.on_egreso,
            on_diario=self.on_diario
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

        h.addLayout(left, 0)
        h.addWidget(center_widget, 1)
        h.addLayout(right_layout, 0)

        self.setCentralWidget(central)
    
    def on_ingreso(self):
        """Open AsientoDialog for income entry."""
        dialog = AsientoDialog(self)
        dialog.exec()
    
    def on_egreso(self):
        """Open AsientoDialog for expense entry."""
        dialog = AsientoDialog(self)
        dialog.exec()
    
    def on_diario(self):
        """Open AsientoDialog for general entry."""
        dialog = AsientoDialog(self)
        dialog.exec()
    
    def on_generate_report(self):
        """Generate report placeholder."""
        QMessageBox.information(self, "Reportes", "Generar reporte - pendiente")
    
    def on_trial_balance(self):
        """
        Generate trial balance report.
        Reuses logic from finish_exercise method.
        """
        try:
            from aqorath.core import trial_balance
            balances = trial_balance()
            
            if not balances:
                QMessageBox.information(self, "Balance de comprobación", "No hay saldos para mostrar.")
                return
            
            # Format balances for display
            text = "Balance de comprobación:\n\n"
            total_debit = 0.0
            total_credit = 0.0
            
            for account_code, balance in sorted(balances.items()):
                balance_float = float(balance)
                if balance_float >= 0:
                    text += f"{account_code}: ${balance_float:,.2f} (Débito)\n"
                    total_debit += balance_float
                else:
                    text += f"{account_code}: ${abs(balance_float):,.2f} (Crédito)\n"
                    total_credit += abs(balance_float)
            
            text += f"\nTotal Débito: ${total_debit:,.2f}\n"
            text += f"Total Crédito: ${total_credit:,.2f}\n"
            
            QMessageBox.information(self, "Balance de comprobación", text)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al generar balance:\n{str(e)}")
    
    def on_close_exercise(self):
        """
        Close accounting exercise.
        Reuses logic from finish_exercise method.
        """
        reply = QMessageBox.question(
            self,
            "Cerrar ejercicio",
            "¿Está seguro que desea cerrar el ejercicio contable?\n\n"
            "Esta operación creará un respaldo y trasladará los saldos.",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        try:
            from aqorath.exercise import close_exercise
            result = close_exercise(carry_over=True)
            
            if result.get("ok"):
                msg = f"Ejercicio cerrado exitosamente.\n\n"
                msg += f"Respaldo en: {result.get('path')}\n"
                if result.get('transferred'):
                    msg += f"Saldo trasladado: {result.get('transferred')}"
                elif result.get('note'):
                    msg += f"Nota: {result.get('note')}"
                
                QMessageBox.information(self, "Cierre de ejercicio", msg)
            else:
                QMessageBox.critical(
                    self,
                    "Error al cerrar ejercicio",
                    f"Error: {result.get('error')}"
                )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al cerrar ejercicio:\n{str(e)}")
    
    def on_view_catalog(self):
        """View catalog placeholder."""
        QMessageBox.information(self, "Catálogo", "Abrir catálogo - pendiente")
    
    def on_settings(self):
        """Settings placeholder."""
        QMessageBox.information(self, "Configuración", "Configuración - pendiente")


if __name__ == "__main__":
    app = QApplication([])
    w = MainWindow()
    w.show()
    app.exec()