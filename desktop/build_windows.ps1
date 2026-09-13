$ErrorActionPreference = "Stop"

python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

pyinstaller desktop/aqorath.spec

Write-Host "Aqorath Windows build generated in dist/"
