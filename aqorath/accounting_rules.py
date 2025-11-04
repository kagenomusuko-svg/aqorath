from __future__ import annotations
from decimal import Decimal
from pathlib import Path
from typing import Dict, Tuple
import json
import logging

LOG = logging.getLogger(__name__)
CATALOG_PATH = Path("aqorath/data/catalogo_base.json")

def load_catalog(path: Path | None = None) -> Dict[str, dict]:
    p = path or CATALOG_PATH
    try:
        j = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        LOG.exception("No se pudo leer el catálogo en %s: %s", p, e)
        return {}
    accounts = j.get("accounts") if isinstance(j, dict) else {}
    if not isinstance(accounts, dict):
        LOG.warning("Formato inesperado del catálogo: se esperaba objeto 'accounts'")
        return {}
    return accounts

def compute_totals_by_tipo(balances: Dict[str, Decimal], catalog: Dict[str, dict]) -> Dict[str, Decimal]:
    totals: Dict[str, Decimal] = {
        "Ingreso": Decimal(0),
        "Gasto": Decimal(0),
        "Costo": Decimal(0),
        "Activo": Decimal(0),
        "Pasivo": Decimal(0),
        "Patrimonio": Decimal(0),
        "otros": Decimal(0),
    }
    for acct_key, saldo in balances.items():
        entry = catalog.get(str(acct_key))
        if not entry:
            totals["otros"] += saldo
            continue
        tipo = entry.get("tipo") or entry.get("Tipo") or entry.get("tipo_contable") or ""
        tipo_norm = str(tipo).strip().capitalize()
        if tipo_norm in totals:
            totals[tipo_norm] += saldo
        else:
            totals["otros"] += saldo
    return totals

def compute_resultado_ejercicio(balances: Dict[str, Decimal], catalog: Dict[str, dict]) -> Tuple[Decimal, Dict[str, Decimal]]:
    totals = compute_totals_by_tipo(balances, catalog)
    ingresos = totals.get("Ingreso", Decimal(0))
    costos = totals.get("Costo", Decimal(0))
    gastos = totals.get("Gasto", Decimal(0))
    resultado = ingresos - costos - gastos
    return resultado, totals