# PyInstaller build specification for Aqorath desktop package

from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

root = Path.cwd()
hiddenimports = collect_submodules("aqorath")


a = Analysis(
    [str(root / "desktop" / "aqorath_launcher.py")],
    pathex=[str(root), str(root / "desktop")],
    datas=[
        (str(root / "aqorath"), "aqorath"),
    ],
    hiddenimports=hiddenimports,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Aqorath",
    debug=False,
    strip=False,
    upx=True,
    console=False,
)
