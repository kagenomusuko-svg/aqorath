# PyInstaller build specification for Aqorath desktop package

# Generated as part of AQR-016.
# Usage:
# pyinstaller desktop/aqorath.spec

from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules("aqorath")


a = Analysis(
    ["aqorath_launcher.py"],
    pathex=["desktop"],
    hiddenimports=hiddenimports,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    name="Aqorath",
    console=False,
)
