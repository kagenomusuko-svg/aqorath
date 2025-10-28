#!/usr/bin/env bash
set -e
# Uso: ./scripts/build_executable.sh
# Crea un ejecutable standalone (Linux/macOS).
# Recomendación: ejecutar en cada plataforma por separado (PyInstaller no cross-compile).

APP_NAME="SistemaContable"
ENTRY="main.py"
VENV_DIR=".venv_build"

python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install -r requirements.txt

# Ajusta add-data: origen:dest (Unix)
# Incluye la carpeta datos dentro del ejecutable (en modo --onefile se extraerá a carpeta temporal en tiempo de ejecución)
ADD_DATA="datos:datos"

# Generar ejecutable
# --onefile crea un solo binario; --noconfirm para sobrescribir sin pedir
pyinstaller --noconfirm --onefile --name "$APP_NAME" --add-data "$ADD_DATA" "$ENTRY"

echo "Build finalizado. Ejecutable en dist/$APP_NAME (o dist/$APP_NAME.exe en Windows)."
deactivate