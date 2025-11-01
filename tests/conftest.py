import os
import subprocess
from pathlib import Path

def pytest_sessionstart(session):
    """
    Antes de ejecutar tests, fijar AQORATH_DB a tests/test.db y ejecutar el script
    init_catalog_db.py para poblar la DB con el catálogo embebido.
    """
    test_db = Path.cwd() / "tests" / "test.db"
    os.environ.setdefault("AQORATH_DB", str(test_db))
    # Asegurar carpeta tests/ existe
    test_db.parent.mkdir(parents=True, exist_ok=True)
    # Ejecutar el init (no fallará si ya está poblada)
    subprocess.run(["python", "scripts/init_catalog_db.py"], check=True)