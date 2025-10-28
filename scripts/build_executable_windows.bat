@echo off
REM Uso: scripts\build_executable_windows.bat
SET VENV_DIR=.venv_build
python -m venv %VENV_DIR%
call %VENV_DIR%\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt

REM En Windows el formato de --add-data es "src;dest"
SET ADD_DATA=data\datos;datos

pyinstaller --noconfirm --onefile --name SistemaContable --add-data "datos;datos" main.py

echo Build finalizado. Ejecutable en dist\SistemaContable.exe