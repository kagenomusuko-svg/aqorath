from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel, QVBoxLayout,
                               QHBoxLayout, QStackedWidget, QPushButton, QFileDialog,
                               QDialog, QFormLayout, QLineEdit, QTextEdit)
from PySide6.QtGui import QPixmap, QPalette, QBrush, QLinearGradient, QColor
from PySide6.QtCore import Qt, QSize

import sys
from pathlib import Path
from typing import Optional

from .storage import get_session, init_db
from .company import Company
from .core import generate_preview
from .reports_jinja import generate_pdf_from_preview


STATIC_DIR = Path(__file__).resolve().parent / "static"
AC_SEAL = STATIC_DIR / "ac_seal.png"


class CompanyDialog(QDialog):
    def __init__(self, parent=None, company: Optional[Company] = None):
        super().__init__(parent)
        self.setWindowTitle("Crear / Editar Empresa")
        self.resize(420, 260)
        self.company = company

        layout = QFormLayout()
        self.name = QLineEdit()
        self.rfc = QLineEdit()
        self.denom = QLineEdit()
        self.phrase = QTextEdit()
        self.logo_btn = QPushButton("Subir logo")
        self.logo_btn.clicked.connect(self.upload_logo)
        layout.addRow("Nombre:", self.name)
        layout.addRow("RFC:", self.rfc)
        layout.addRow("Denominación:", self.denom)
        layout.addRow("Frase:", self.phrase)
        layout.addRow("Logo:", self.logo_btn)

        btns = QHBoxLayout()
        save = QPushButton("Guardar")
        cancel = QPushButton("Cancelar")
        save.clicked.connect(self.save)
        cancel.clicked.connect(self.reject)
        btns.addWidget(save)
        btns.addWidget(cancel)
        layout.addRow(btns)
        self.setLayout(layout)

        if company:
            self.name.setText(company.name)
            self.rfc.setText(company.rfc or "")
            self.denom.setText(company.denominacion or "")
            self.phrase.setPlainText(company.phrase or "")

    def upload_logo(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Seleccionar logo", "", "Images (*.png *.jpg *.jpeg)")
        if fn:
            # copy to data dir
            data_dir = Path(get_session().__enter__().bind.url.database).parent / "aqorath_data" / "company_logos"
            data_dir.mkdir(parents=True, exist_ok=True)
            target = data_dir / Path(fn).name
            Path(fn).replace(target) if False else Path(fn).absolute()  # noop to keep original -- just store path
            self._uploaded = str(fn)

    def save(self):
        with get_session() as s:
            if self.company:
                c = s.get(Company, self.company.id)
                if not c:
                    c = Company(name=self.name.text())
            else:
                c = Company(name=self.name.text())
            c.name = self.name.text()
            c.rfc = self.rfc.text() or None
            c.denominacion = self.denom.text() or None
            c.phrase = self.phrase.toPlainText() or None
            if getattr(self, '_uploaded', None):
                c.logo_path = self._uploaded
            s.add(c)
            s.commit()
            s.refresh(c)
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Aqorath — Escritorio")
        self.resize(1000, 700)

        # central widget
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout()
        central.setLayout(layout)

        # top menu (simple)
        menu = QHBoxLayout()
        btn_home = QPushButton("Inicio")
        btn_companies = QPushButton("Empresas")
        btn_entries = QPushButton("Asientos")
        btn_reports = QPushButton("Reportes")
        menu.addWidget(btn_home)
        menu.addWidget(btn_companies)
        menu.addWidget(btn_entries)
        menu.addWidget(btn_reports)
        menu.addStretch()
        layout.addLayout(menu)

        # stacked pages
        self.stack = QStackedWidget()
        layout.addWidget(self.stack)

        # pages
        self.page_home = QWidget()
        self.page_companies = QWidget()
        self.page_entries = QWidget()
        self.page_reports = QWidget()

        self._init_home()
        self._init_companies()
        self._init_entries()
        self._init_reports()

        self.stack.addWidget(self.page_home)
        self.stack.addWidget(self.page_companies)
        self.stack.addWidget(self.page_entries)
        self.stack.addWidget(self.page_reports)

        btn_home.clicked.connect(lambda: self.stack.setCurrentWidget(self.page_home))
        btn_companies.clicked.connect(lambda: self.stack.setCurrentWidget(self.page_companies))
        btn_entries.clicked.connect(lambda: self.stack.setCurrentWidget(self.page_entries))
        btn_reports.clicked.connect(lambda: self.stack.setCurrentWidget(self.page_reports))

        # apply gradient background
        self._apply_background()

    def _apply_background(self):
        # subtle gradient background via palette
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0.0, QColor('#f6fbff'))
        gradient.setColorAt(1.0, QColor('#e6f0ff'))
        pal = self.palette()
        pal.setBrush(QPalette.Window, QBrush(gradient))
        self.setPalette(pal)

    def _init_home(self):
        v = QVBoxLayout()
        lbl = QLabel()
        lbl.setAlignment(Qt.AlignCenter)
        if AC_SEAL.exists():
            pix = QPixmap(str(AC_SEAL))
            pix = pix.scaledToWidth(420, Qt.SmoothTransformation)
            lbl.setPixmap(pix)
        else:
            lbl.setText("[Sello AC no encontrado en static/ac_seal.png]")
        phrase = QLabel("La fuerza interior nos impulsa, un pequeño apoyo de los demás nos bendice")
        phrase.setStyleSheet("font-style: italic; color: #123; margin-left: 12px;")
        phrase.setAlignment(Qt.AlignLeft | Qt.AlignBottom)
        container = QWidget()
        container_layout = QVBoxLayout()
        container_layout.addWidget(lbl)
        container_layout.addWidget(phrase)
        container.setLayout(container_layout)
        self.page_home.setLayout(QVBoxLayout())
        self.page_home.layout().addWidget(container)

    def _init_companies(self):
        v = QVBoxLayout()
        btn_new = QPushButton("Nueva empresa")
        btn_new.clicked.connect(self._new_company)
        v.addWidget(btn_new)

        self.companies_list = QVBoxLayout()
        v.addLayout(self.companies_list)
        self.page_companies.setLayout(v)
        self.refresh_companies()

    def refresh_companies(self):
        # clear
        for i in reversed(range(self.companies_list.count())):
            w = self.companies_list.itemAt(i).widget()
            if w:
                w.deleteLater()
        with get_session() as s:
            rows = s.exec(select(Company)).scalars().all()
        for c in rows:
            row = QWidget()
            h = QHBoxLayout()
            lbl = QLabel(f"{c.id} - {c.name} ({c.rfc or ''})")
            edit = QPushButton("Editar")
            edit.clicked.connect(lambda checked, cc=c: self._edit_company(cc))
            h.addWidget(lbl)
            h.addWidget(edit)
            row.setLayout(h)
            self.companies_list.addWidget(row)

    def _new_company(self):
        dlg = CompanyDialog(self)
        if dlg.exec() == QDialog.Accepted:
            self.refresh_companies()

    def _edit_company(self, company: Company):
        dlg = CompanyDialog(self, company=company)
        if dlg.exec() == QDialog.Accepted:
            self.refresh_companies()

    def _init_entries(self):
        v = QVBoxLayout()
        lbl = QLabel("Lista de asientos — próximamente")
        v.addWidget(lbl)
        self.page_entries.setLayout(v)

    def _init_reports(self):
        v = QVBoxLayout()
        btn_preview = QPushButton("Generar PDF de prueba (preview)")
        btn_preview.clicked.connect(self._demo_report)
        v.addWidget(btn_preview)
        self.page_reports.setLayout(v)

    def _demo_report(self):
        try:
            preview = generate_preview("ingreso_venta", 1000.0, ctx={"account_codes": {"bank": "1000", "sales": "4000", "vat_tr": "2100"}, "vat_rate": 0.16, "desc": "Venta demo desde desktop"})
            # pick first company if exists
            company = None
            with get_session() as s:
                company = s.exec(select(Company)).scalars().first()
            out = generate_pdf_from_preview(preview, company=company)
            # open file externally
            import webbrowser
            webbrowser.open(str(out))
        except Exception as e:
            dlg = QDialog(self)
            dlg.setWindowTitle("Error")
            lbl = QLabel(str(e))
            lay = QVBoxLayout()
            lay.addWidget(lbl)
            dlg.setLayout(lay)
            dlg.exec()


def main():
    app = QApplication(sys.argv)
    init_db()
    win = MainWindow()
    win.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()