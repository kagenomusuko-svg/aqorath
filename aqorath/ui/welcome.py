"""
Dialogo de bienvenida para seleccionar el tipo de contabilidad.

Behaviour:
- Muestra 2 botones: Comercial / Sin fines de lucro
- Persiste la elección (intenta AppConfig DB; si falla, usa ~/.local/share/aqorath/config.json)
- Abre la MainWindow al confirmar la opción
"""
import json
import os
from pathlib import Path

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

CONFIG_PATH = Path.home() / ".local" / "share" / "aqorath" / "config.json"


def _save_choice_to_file(choice: str):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    cfg = {"accounting_model": choice}
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def _save_choice_to_db(choice: str):
    """
    Intenta persistir en AppConfig si el modelo existe.
    Si falla, lanza excepción para que el caller use el fallback a archivo.
    """
    try:
        from aqorath.models import AppConfig  # type: ignore
        from aqorath.storage import get_session  # type: ignore
    except Exception as exc:
        raise

    # usar get_session o crear una Session si tu proyecto expone otra API
    s = get_session()
    try:
        # buscar fila AppConfig (suponiendo una columna 'key' y 'value' o similar)
        appcfg = s.exec(AppConfig.select().where(AppConfig.key == "accounting_model")).one_or_none()
        if appcfg:
            appcfg.value = choice
            s.add(appcfg)
        else:
            # adaptar al schema real de AppConfig
            new = AppConfig(key="accounting_model", value=choice)
            s.add(new)
        s.commit()
    finally:
        s.close()


class WelcomeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Bienvenido")
        self.resize(420, 160)
        layout = QVBoxLayout(self)
        label = QLabel("Bienvenido. Por favor selecciona el tipo de contabilidad que deseas registrar.")
        layout.addWidget(label)

        btn_comercial = QPushButton("Comercial")
        btn_osc = QPushButton("Sin fines de lucro")

        btn_comercial.clicked.connect(lambda: self._choose("comercial"))
        btn_osc.clicked.connect(lambda: self._choose("sin_fines"))

        layout.addWidget(btn_comercial)
        layout.addWidget(btn_osc)

        self.chosen = None

    def _choose(self, choice: str):
        # intenta persistir en DB; si falla, guarda en archivo
        saved = False
        try:
            _save_choice_to_db(choice)
            saved = True
        except Exception:
            try:
                _save_choice_to_file(choice)
                saved = True
            except Exception as e:
                QMessageBox.critical(self, "Error", f"No se pudo guardar la elección: {e}")
                saved = False

        if saved:
            self.chosen = choice
            self.accept()


def get_current_choice():
    # Primero intentar leer DB AppConfig para ser consistente
    try:
        from aqorath.models import AppConfig  # type: ignore
        from aqorath.storage import get_session  # type: ignore
    except Exception:
        AppConfig = None  # type: ignore

    if "AppConfig" in globals() and AppConfig is not None:
        try:
            s = get_session()
            row = s.exec(AppConfig.select().where(AppConfig.key == "accounting_model")).one_or_none()
            s.close()
            if row:
                return getattr(row, "value", None)
        except Exception:
            pass

    # Fallback to file
    try:
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            return cfg.get("accounting_model")
    except Exception:
        return None


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