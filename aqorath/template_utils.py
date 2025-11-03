from typing import Optional, Dict
import json
from pathlib import Path
from aqorath.catalog import load_catalog, load_catalog_codes

# Ruta de mapping administrable (opcional)
TEMPLATE_MAPPING_PATH = Path("aqorath/data/template_account_mapping.json")


def load_template_mapping() -> Dict[str, str]:
    if TEMPLATE_MAPPING_PATH.exists():
        try:
            return json.loads(TEMPLATE_MAPPING_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def account_code_for(ctx: Optional[dict], logical_key: str) -> Optional[str]:
    """
    Resolve el código de cuenta a usar para la clave lógica:
     1) primero busca en ctx['account_codes'][logical_key]
     2) luego busca en mapping administrable (template_account_mapping.json)
     3) si no existe, devuelve None
    Esto evita fallbacks literales en templates y centraliza defaults.
    """
    if ctx:
        acct_map = ctx.get("account_codes", {})
        if acct_map and logical_key in acct_map:
            return str(acct_map[logical_key]).strip()

    mapping = load_template_mapping()
    code = mapping.get(logical_key)
    if code:
        return str(code).strip()

    return None