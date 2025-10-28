import sys
from pathlib import Path

# Añade la raíz del proyecto al PYTHONPATH para que 'modelos' sea importable durante los tests.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))