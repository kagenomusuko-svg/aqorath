"""
AsientoDialog for journal entry creation with catalog validation.
"""
from decimal import Decimal
from datetime import datetime
from typing import List, Dict, Any, Set

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QPushButton, QDateEdit, QLineEdit, QComboBox,
    QTableWidget, QTableWidgetItem, QMessageBox, QListWidget
)
from PySide6.QtCore import Qt, QDate

from .utils import load_catalog_codes


class AsientoDialog(QDialog):
    """
    Dialog for creating journal entries (asientos) with strict catalog validation.
    
    Features:
    - Left list showing visual cuenta list
    - Right form with fecha, importe, cuenta-select (combo with catalog codes only)
    - Buttons: Balancear, Guardar, Factura, Limpiar
    - Bottom table showing Monto/Cuenta/Cargo/Abono
    - Balance label showing current balance
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nuevo Asiento")
        self.resize(900, 600)
        
        # Load catalog codes
        self.catalog_codes: Set[str] = load_catalog_codes()
        
        # Entry lines storage
        self.entry_lines: List[Dict[str, Any]] = []
        
        # Main layout
        main_layout = QHBoxLayout()
        
        # Left side - visual cuenta list
        left_layout = QVBoxLayout()
        left_label = QLabel("Cuentas del catálogo:")
        left_label.setStyleSheet("font-weight: bold;")
        self.cuenta_list = QListWidget()
        self.cuenta_list.addItems(sorted(self.catalog_codes))
        left_layout.addWidget(left_label)
        left_layout.addWidget(self.cuenta_list)
        
        # Right side - form and table
        right_layout = QVBoxLayout()
        
        # Form for input
        form_layout = QFormLayout()
        
        self.fecha_input = QDateEdit()
        self.fecha_input.setDate(QDate.currentDate())
        self.fecha_input.setCalendarPopup(True)
        
        self.importe_input = QLineEdit()
        self.importe_input.setPlaceholderText("0.00")
        
        self.cuenta_combo = QComboBox()
        self.cuenta_combo.setEditable(False)  # Strict: no free text allowed
        self.cuenta_combo.addItem("-- Seleccione cuenta --")
        self.cuenta_combo.addItems(sorted(self.catalog_codes))
        
        self.tipo_combo = QComboBox()
        self.tipo_combo.addItems(["Cargo", "Abono"])
        
        self.descripcion_input = QLineEdit()
        self.descripcion_input.setPlaceholderText("Descripción de la línea")
        
        form_layout.addRow("Fecha:", self.fecha_input)
        form_layout.addRow("Importe:", self.importe_input)
        form_layout.addRow("Cuenta:", self.cuenta_combo)
        form_layout.addRow("Tipo:", self.tipo_combo)
        form_layout.addRow("Descripción:", self.descripcion_input)
        
        # Add line button
        btn_add_line = QPushButton("Agregar línea")
        btn_add_line.clicked.connect(self.on_add_line)
        form_layout.addRow("", btn_add_line)
        
        right_layout.addLayout(form_layout)
        
        # Action buttons
        btn_layout = QHBoxLayout()
        self.btn_balancear = QPushButton("Balancear")
        self.btn_guardar = QPushButton("Guardar")
        self.btn_factura = QPushButton("Factura")
        self.btn_limpiar = QPushButton("Limpiar")
        
        self.btn_balancear.clicked.connect(self.on_balancear)
        self.btn_guardar.clicked.connect(self.on_guardar)
        self.btn_factura.clicked.connect(self.on_factura)
        self.btn_limpiar.clicked.connect(self.on_limpiar)
        
        btn_layout.addWidget(self.btn_balancear)
        btn_layout.addWidget(self.btn_guardar)
        btn_layout.addWidget(self.btn_factura)
        btn_layout.addWidget(self.btn_limpiar)
        
        right_layout.addLayout(btn_layout)
        
        # Table for entry lines
        table_label = QLabel("Líneas del asiento:")
        table_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        right_layout.addWidget(table_label)
        
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Monto", "Cuenta", "Cargo", "Abono"])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        right_layout.addWidget(self.table)
        
        # Balance label
        self.balance_label = QLabel("Balance: 0.00")
        self.balance_label.setStyleSheet("font-size: 12pt; font-weight: bold; color: #333;")
        self.balance_label.setAlignment(Qt.AlignRight)
        right_layout.addWidget(self.balance_label)
        
        # Combine left and right
        main_layout.addLayout(left_layout, 1)
        main_layout.addLayout(right_layout, 2)
        
        self.setLayout(main_layout)
    
    def on_add_line(self):
        """Add a line to the entry."""
        # Validate inputs
        importe_text = self.importe_input.text().strip()
        if not importe_text:
            QMessageBox.warning(self, "Error", "Debe ingresar un importe.")
            return
        
        try:
            importe = Decimal(importe_text)
        except Exception:
            QMessageBox.warning(self, "Error", "El importe debe ser un número válido.")
            return
        
        cuenta = self.cuenta_combo.currentText()
        if cuenta == "-- Seleccione cuenta --":
            QMessageBox.warning(self, "Error", "Debe seleccionar una cuenta.")
            return
        
        # Verify cuenta is in catalog
        if cuenta not in self.catalog_codes:
            QMessageBox.critical(self, "Error", f"La cuenta '{cuenta}' no está en el catálogo.")
            return
        
        tipo = self.tipo_combo.currentText()
        descripcion = self.descripcion_input.text().strip()
        
        # Determine cargo/abono
        cargo = importe if tipo == "Cargo" else Decimal("0")
        abono = importe if tipo == "Abono" else Decimal("0")
        
        # Add to entry lines
        line = {
            "account_code": cuenta,
            "debit": float(cargo),
            "credit": float(abono),
            "description": descripcion
        }
        self.entry_lines.append(line)
        
        # Update table
        self._update_table()
        
        # Clear inputs
        self.importe_input.clear()
        self.descripcion_input.clear()
        self.cuenta_combo.setCurrentIndex(0)
    
    def _update_table(self):
        """Update the table with current entry lines."""
        self.table.setRowCount(len(self.entry_lines))
        
        for i, line in enumerate(self.entry_lines):
            monto = max(line["debit"], line["credit"])
            self.table.setItem(i, 0, QTableWidgetItem(f"{monto:.2f}"))
            self.table.setItem(i, 1, QTableWidgetItem(line["account_code"]))
            self.table.setItem(i, 2, QTableWidgetItem(f"{line['debit']:.2f}"))
            self.table.setItem(i, 3, QTableWidgetItem(f"{line['credit']:.2f}"))
        
        # Update balance
        self._update_balance()
    
    def _update_balance(self):
        """Update the balance label."""
        total_cargo = sum(Decimal(str(line["debit"])) for line in self.entry_lines)
        total_abono = sum(Decimal(str(line["credit"])) for line in self.entry_lines)
        balance = total_cargo - total_abono
        
        self.balance_label.setText(f"Balance: {balance:.2f}")
        
        if balance == Decimal("0") and len(self.entry_lines) > 0:
            self.balance_label.setStyleSheet("font-size: 12pt; font-weight: bold; color: green;")
        else:
            self.balance_label.setStyleSheet("font-size: 12pt; font-weight: bold; color: red;")
    
    def on_balancear(self):
        """
        Sum cargo/abono decimals and update balance label.
        When balanced and non-zero, clear inputs.
        """
        if not self.entry_lines:
            QMessageBox.information(self, "Balancear", "No hay líneas para balancear.")
            return
        
        self._update_balance()
        
        total_cargo = sum(Decimal(str(line["debit"])) for line in self.entry_lines)
        total_abono = sum(Decimal(str(line["credit"])) for line in self.entry_lines)
        balance = total_cargo - total_abono
        
        if balance == Decimal("0") and total_cargo > 0:
            QMessageBox.information(
                self, 
                "Balanceado", 
                f"El asiento está balanceado.\nCargo: {total_cargo:.2f}\nAbono: {total_abono:.2f}"
            )
            # Clear inputs when balanced
            self.importe_input.clear()
            self.descripcion_input.clear()
            self.cuenta_combo.setCurrentIndex(0)
        else:
            QMessageBox.warning(
                self,
                "No balanceado",
                f"El asiento NO está balanceado.\nCargo: {total_cargo:.2f}\nAbono: {total_abono:.2f}\nDiferencia: {balance:.2f}"
            )
    
    def on_guardar(self):
        """
        Validate all account codes in table are in catalog.
        Validate balance.
        Construct entry dict and call post_entry or _persist_entry.
        Show error dialog on failure.
        Accept dialog on success.
        """
        if not self.entry_lines:
            QMessageBox.warning(self, "Error", "No hay líneas para guardar.")
            return
        
        # Validate all account codes are in catalog
        for line in self.entry_lines:
            account_code = line.get("account_code")
            if account_code not in self.catalog_codes:
                QMessageBox.critical(
                    self,
                    "Error de validación",
                    f"La cuenta '{account_code}' no está en el catálogo.\n"
                    "Solo se permiten cuentas del catálogo base."
                )
                return
        
        # Validate balance
        total_cargo = sum(Decimal(str(line["debit"])) for line in self.entry_lines)
        total_abono = sum(Decimal(str(line["credit"])) for line in self.entry_lines)
        balance = total_cargo - total_abono
        
        if balance != Decimal("0"):
            QMessageBox.critical(
                self,
                "Error de balance",
                f"El asiento no está balanceado.\nDiferencia: {balance:.2f}\n\n"
                "Use el botón 'Balancear' para verificar."
            )
            return
        
        if total_cargo == Decimal("0"):
            QMessageBox.warning(self, "Error", "El asiento no puede tener monto cero.")
            return
        
        # Construct entry dict
        entry = {
            "description": f"Asiento {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "lines": self.entry_lines
        }
        
        # Persist entry
        try:
            from aqorath.core import post_entry
            result = post_entry(entry)
            
            if isinstance(result, dict):
                if result.get("ok"):
                    QMessageBox.information(
                        self,
                        "Éxito",
                        f"Asiento guardado correctamente.\nID: {result.get('entry_id')}"
                    )
                    self.accept()
                else:
                    QMessageBox.critical(
                        self,
                        "Error al guardar",
                        f"Error al guardar el asiento:\n{result.get('error')}"
                    )
            else:
                # post_entry returned entry_id directly
                QMessageBox.information(
                    self,
                    "Éxito",
                    f"Asiento guardado correctamente.\nID: {result}"
                )
                self.accept()
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Error al guardar el asiento:\n{str(e)}"
            )
    
    def on_factura(self):
        """Placeholder for factura functionality."""
        QMessageBox.information(self, "Factura", "Funcionalidad de factura pendiente de implementar.")
    
    def on_limpiar(self):
        """Clear all entry lines and reset form."""
        reply = QMessageBox.question(
            self,
            "Limpiar",
            "¿Está seguro que desea limpiar todas las líneas?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.entry_lines.clear()
            self._update_table()
            self.importe_input.clear()
            self.descripcion_input.clear()
            self.cuenta_combo.setCurrentIndex(0)
