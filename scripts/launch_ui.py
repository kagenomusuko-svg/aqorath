#!/usr/bin/env python3
"""
Script de lanzamiento rápido para la UI:
- Si no hay elección guardada, abre el WelcomeDialog
- Luego abre la MainWindow
Uso:
  python scripts/launch_ui.py
Instalar dependencias:
  pip install PySide6
"""
import sys

def main():
    try:
        from PySide6.QtWidgets import QApplication
    except Exception:
        print("PySide6 no está instalado. Instala con: pip install PySide6")
        sys.exit(1)

    from aqorath.ui.welcome import get_current_choice, WelcomeDialog
    from aqorath.ui.main_window import MainWindow

    app = QApplication(sys.argv)

    current = get_current_choice()
    if not current:
        dlg = WelcomeDialog()
        if dlg.exec() != 1:
            print("No se seleccionó modelo. Saliendo.")
            sys.exit(0)
    # Al menos hay elección guardada ahora
    mw = MainWindow()
    mw.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()