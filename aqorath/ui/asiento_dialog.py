"""
AsientoDialog - Dialog for entering journal entries (asientos).
"""
from decimal import Decimal, InvalidOperation
from datetime import datetime
from typing import List, Dict, Any

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QTableWidget, QTableWidgetItem,
    QListWidget, QMessageBox, QDateEdit
)
from PySide6.QtCore import Qt, QDate

from .utils import load_catalog_codes, load_catalog_dict
from aqorath.core import post_entry


class AsientoDialog(QDialog):
    """
    Dialog for creating journal entries with:
    - Left: List of accounts (visual catalog)
    - Right: Form with date, amount, account selector
    - Buttons: Balancear, Guardar, Factura, Limpiar
    - Bottom: Table showing Monto/Cuenta/Cargo/Abono
    - Balance label showing current balance
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Asiento contable")
        self.resize(900, 600)
        
        # Load catalog
        self.catalog_codes = load_catalog_codes()
        self.catalog_dict = load_catalog_dict()
        
        # Data storage for entry lines
        self.entry_lines: List[Dict[str, Any]] = []
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup the UI components."""
        main_layout = QHBoxLayout()
        
        # Left: Account list (visual catalog)
        left_layout = QVBoxLayout()
        left_label = QLabel("Catálogo de cuentas:")
        left_label.setStyleSheet("font-weight: bold;")
        self.account_list = QListWidget()
        self._populate_account_list()
        left_layout.addWidget(left_label)
        left_layout.addWidget(self.account_list)
        
        # Right: Form and table
        right_layout = QVBoxLayout()
        
        # Form for input
        form_layout = QVBoxLayout()
        
        # Date
        date_row = QHBoxLayout()
        date_row.addWidget(QLabel("Fecha:"))
        self.date_edit = QDateEdit()
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        date_row.addWidget(self.date_edit)
        date_row.addStretch()
        form_layout.addLayout(date_row)
        
        # Amount
        amount_row = QHBoxLayout()
        amount_row.addWidget(QLabel("Importe:"))
        self.amount_edit = QLineEdit()
        self.amount_edit.setPlaceholderText("0.00")
        amount_row.addWidget(self.amount_edit)
        amount_row.addStretch()
        form_layout.addLayout(amount_row)
        
        # Account selector (combo box - strict, no free text)
        account_row = QHBoxLayout()
        account_row.addWidget(QLabel("Cuenta:"))
        self.account_combo = QComboBox()
        self.account_combo.setEditable(False)  # Strict: no free text allowed
        self._populate_account_combo()
        account_row.addWidget(self.account_combo)
        account_row.addStretch()
        form_layout.addLayout(account_row)
        
        # Cargo/Abono selector
        tipo_row = QHBoxLayout()
        tipo_row.addWidget(QLabel("Tipo:"))
        self.tipo_combo = QComboBox()
        self.tipo_combo.addItem("Cargo")
        self.tipo_combo.addItem("Abono")
        tipo_row.addWidget(self.tipo_combo)
        tipo_row.addStretch()
        form_layout.addLayout(tipo_row)
        
        # Add line button
        add_btn = QPushButton("Agregar línea")
        add_btn.clicked.connect(self.on_add_line)
        form_layout.addWidget(add_btn)
        
        right_layout.addLayout(form_layout)
        
        # Buttons: Balancear, Guardar, Factura, Limpiar
        button_row = QHBoxLayout()
        self.btn_balancear = QPushButton("Balancear")
        self.btn_guardar = QPushButton("Guardar")
        self.btn_factura = QPushButton("Factura")
        self.btn_limpiar = QPushButton("Limpiar")
        
        self.btn_balancear.clicked.connect(self.on_balancear)
        self.btn_guardar.clicked.connect(self.on_guardar)
        self.btn_factura.clicked.connect(self.on_factura)
        self.btn_limpiar.clicked.connect(self.on_limpiar)
        
        button_row.addWidget(self.btn_balancear)
        button_row.addWidget(self.btn_guardar)
        button_row.addWidget(self.btn_factura)
        button_row.addWidget(self.btn_limpiar)
        button_row.addStretch()
        right_layout.addLayout(button_row)
        
        # Table: Monto, Cuenta, Cargo, Abono
        table_label = QLabel("Líneas del asiento:")
        table_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Cuenta", "Descripción", "Cargo", "Abono"])
        self.table.setColumnWidth(0, 100)
        self.table.setColumnWidth(1, 250)
        self.table.setColumnWidth(2, 100)
        self.table.setColumnWidth(3, 100)
        right_layout.addWidget(table_label)
        right_layout.addWidget(self.table)
        
        # Balance label
        self.balance_label = QLabel("Balance: 0.00")
        self.balance_label.setStyleSheet("font-weight: bold; font-size: 14px; margin-top: 10px;")
        right_layout.addWidget(self.balance_label)
        
        # Assemble main layout
        main_layout.addLayout(left_layout, 1)
        main_layout.addLayout(right_layout, 2)
        
        self.setLayout(main_layout)
    
    def _populate_account_list(self):
        """Populate the visual account list from catalog."""
        accounts = self.catalog_dict.get("accounts", {})
        for code in sorted(accounts.keys()):
            account_info = accounts[code]
            name = account_info.get("name_comercial", account_info.get("name_osc", ""))
            self.account_list.addItem(f"{code} - {name}")
    
    def _populate_account_combo(self):
        """Populate the account combo box with catalog codes."""
        self.account_combo.clear()
        self.account_combo.addItem("-- Seleccionar cuenta --", "")
        
        accounts = self.catalog_dict.get("accounts", {})
        for code in sorted(accounts.keys()):
            account_info = accounts[code]
            name = account_info.get("name_comercial", account_info.get("name_osc", ""))
            self.account_combo.addItem(f"{code} - {name}", code)
    
    def on_add_line(self):
        """Add a line to the entry based on form inputs."""
        # Get values
        try:
            amount = Decimal(self.amount_edit.text().strip() or "0")
        except (InvalidOperation, ValueError):
            QMessageBox.warning(self, "Error", "Importe inválido")
            return
        
        if amount <= 0:
            QMessageBox.warning(self, "Error", "El importe debe ser mayor a cero")
            return
        
        account_code = self.account_combo.currentData()
        if not account_code:
            QMessageBox.warning(self, "Error", "Debe seleccionar una cuenta")
            return
        
        tipo = self.tipo_combo.currentText()
        
        # Get account name
        account_info = self.catalog_dict.get("accounts", {}).get(account_code, {})
        account_name = account_info.get("name_comercial", account_info.get("name_osc", ""))
        
        # Determine cargo/abono
        cargo = amount if tipo == "Cargo" else Decimal("0")
        abono = amount if tipo == "Abono" else Decimal("0")
        
        # Add to entry lines
        self.entry_lines.append({
            "account_code": account_code,
            "account_name": account_name,
            "debit": float(cargo),
            "credit": float(abono),
            "description": ""
        })
        
        # Update table
        self._update_table()
        
        # Clear form
        self.amount_edit.clear()
        self.account_combo.setCurrentIndex(0)
    
    def _update_table(self):
        """Update the table to show current entry lines."""
        self.table.setRowCount(len(self.entry_lines))
        
        for i, line in enumerate(self.entry_lines):
            self.table.setItem(i, 0, QTableWidgetItem(line["account_code"]))
            self.table.setItem(i, 1, QTableWidgetItem(line["account_name"]))
            self.table.setItem(i, 2, QTableWidgetItem(f"{line['debit']:.2f}"))
            self.table.setItem(i, 3, QTableWidgetItem(f"{line['credit']:.2f}"))
        
        # Update balance
        self._update_balance()
    
    def _update_balance(self):
        """Calculate and update the balance label."""
        total_debit = Decimal("0")
        total_credit = Decimal("0")
        
        for line in self.entry_lines:
            total_debit += Decimal(str(line["debit"]))
            total_credit += Decimal(str(line["credit"]))
        
        balance = total_debit - total_credit
        
        # Update label with color coding
        if balance == 0 and total_debit > 0:
            self.balance_label.setText(f"Balance: {balance:.2f} ✓")
            self.balance_label.setStyleSheet("font-weight: bold; font-size: 14px; margin-top: 10px; color: green;")
        elif balance == 0:
            self.balance_label.setText(f"Balance: {balance:.2f}")
            self.balance_label.setStyleSheet("font-weight: bold; font-size: 14px; margin-top: 10px;")
        else:
            self.balance_label.setText(f"Balance: {balance:.2f} ✗")
            self.balance_label.setStyleSheet("font-weight: bold; font-size: 14px; margin-top: 10px; color: red;")
    
    def on_balancear(self):
        """
        Balance check: sum cargo/abono and update balance label.
        If balanced and non-zero, clear inputs.
        """
        total_debit = Decimal("0")
        total_credit = Decimal("0")
        
        for line in self.entry_lines:
            total_debit += Decimal(str(line["debit"]))
            total_credit += Decimal(str(line["credit"]))
        
        balance = total_debit - total_credit
        
        if balance == 0 and total_debit > 0:
            QMessageBox.information(self, "Balance", "El asiento está balanceado correctamente")
            # Clear input fields
            self.amount_edit.clear()
            self.account_combo.setCurrentIndex(0)
        elif balance == 0:
            QMessageBox.warning(self, "Balance", "El asiento está vacío")
        else:
            QMessageBox.warning(
                self, 
                "Balance", 
                f"El asiento no está balanceado.\nCargo: {total_debit:.2f}\nAbono: {total_credit:.2f}\nDiferencia: {balance:.2f}"
            )
    
    def on_guardar(self):
        """
        Save the entry:
        1. Validate all account codes are in catalog
        2. Validate balance
        3. Construct entry dict
        4. Call post_entry
        5. Show error on failure or close dialog on success
        """
        # Validate we have lines
        if not self.entry_lines:
            QMessageBox.warning(self, "Error", "No hay líneas para guardar")
            return
        
        # Validate all accounts are in catalog
        for line in self.entry_lines:
            if line["account_code"] not in self.catalog_codes:
                QMessageBox.critical(
                    self,
                    "Error de validación",
                    f"La cuenta '{line['account_code']}' no existe en el catálogo.\n"
                    "Solo se permiten cuentas del catálogo."
                )
                return
        
        # Validate balance
        total_debit = Decimal("0")
        total_credit = Decimal("0")
        
        for line in self.entry_lines:
            total_debit += Decimal(str(line["debit"]))
            total_credit += Decimal(str(line["credit"]))
        
        if total_debit != total_credit:
            QMessageBox.warning(
                self,
                "Error de balance",
                f"El asiento no está balanceado.\nCargo: {total_debit:.2f}\nAbono: {total_credit:.2f}\nDiferencia: {total_debit - total_credit:.2f}"
            )
            return
        
        if total_debit == 0:
            QMessageBox.warning(self, "Error", "El asiento está vacío (sin movimientos)")
            return
        
        # Construct entry dict for post_entry
        entry = {
            "description": f"Asiento del {self.date_edit.date().toString('yyyy-MM-dd')}",
            "date": datetime.now(),
            "lines": []
        }
        
        for line in self.entry_lines:
            entry["lines"].append({
                "account_code": line["account_code"],
                "debit": line["debit"],
                "credit": line["credit"],
                "description": line.get("description", "")
            })
        
        # Try to persist
        try:
            result = post_entry(entry)
            
            # Check result format
            if isinstance(result, dict):
                if result.get("ok"):
                    QMessageBox.information(self, "Éxito", "Asiento guardado correctamente")
                    self.accept()
                else:
                    QMessageBox.critical(self, "Error", f"Error al guardar: {result.get('error', 'Unknown error')}")
            elif isinstance(result, int):
                # Entry ID returned (template mode, but we use dict mode)
                QMessageBox.information(self, "Éxito", f"Asiento guardado con ID: {result}")
                self.accept()
            else:
                QMessageBox.critical(self, "Error", f"Resultado inesperado: {result}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al guardar asiento:\n{str(e)}")
    
    def on_factura(self):
        """Placeholder for factura functionality."""
        QMessageBox.information(self, "Factura", "Funcionalidad de factura - pendiente")
    
    def on_limpiar(self):
        """Clear all entry lines and reset the form."""
        self.entry_lines.clear()
        self._update_table()
        self.amount_edit.clear()
        self.account_combo.setCurrentIndex(0)
