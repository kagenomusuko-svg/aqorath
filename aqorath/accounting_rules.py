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

def normal_balance_amount(ledger_signed_balance: Decimal, naturaleza: str | None) -> Decimal:
    """
    Convierte LedgerSignedBalance a magnitud según naturaleza de la cuenta.
    
    LedgerSignedBalance = Debe - Haber (forma algebraica)
    
    Naturalezas válidas reconocidas:
      - debit / DEBIT (English)
      - credit / CREDIT (English)
      - Deudora / deudora (Spanish)
      - Acreedora / acreedora (Spanish)
    
    Para naturaleza deudora (debit-like): NormalBalance = LedgerSignedBalance (sin cambio)
    Para naturaleza acreedora (credit-like): NormalBalance = -LedgerSignedBalance (negación)
    
    Ejemplo:
      Ingreso (Acreedora): LedgerSignedBalance = -100 → NormalBalance = +100
      Gasto (Deudora): LedgerSignedBalance = +40 → NormalBalance = +40
      Resultado normalizado: 100 - 40 = +60
      
    IMPORTANTE: Una naturaleza desconocida o None lanza ValueError.
    No es aceptable retornar saldo algebraico sin confirmar naturaleza.
    """
    # Validar que naturaleza sea conocida
    if naturaleza is None or naturaleza.strip() == "":
        raise ValueError(
            "Naturaleza de cuenta no puede ser None o vacía. "
            "Se requiere un valor válido: debit, credit, Deudora, o Acreedora."
        )
    
    naturaleza_lower = naturaleza.lower().strip()
    
    # Vocabulario English (debit/credit)
    if naturaleza_lower in ("debit",):
        return ledger_signed_balance
    elif naturaleza_lower in ("credit",):
        return -ledger_signed_balance
    
    # Vocabulario Spanish (Deudora/Acreedora)
    elif naturaleza_lower in ("deudora",):
        return ledger_signed_balance
    elif naturaleza_lower in ("acreedora",):
        return -ledger_signed_balance
    
    else:
        # Naturaleza desconocida: FALLAR
        raise ValueError(
            f"Naturaleza de cuenta desconocida: '{naturaleza}'. "
            f"Valores válidos: debit, credit, Deudora, Acreedora."
        )


def resolve_catalog_entry_for_account_code(account_code: str, catalog: Dict[str, dict]) -> dict:
    """
    P1-3: Resolver entrada de catálogo para una cuenta (canónica o entidad).
    
    Si account_code es exacto en catálogo: retorna entrada.
    Si account_code es entidad (parent_code.NNN):
      - Extrae parent_code
      - Busca parent_code en catálogo
      - Retorna metadata del padre (entidad hereda clasificación)
    Si no encuentra: retorna None
    """
    import re
    
    # Intento 1: búsqueda exacta
    if account_code in catalog:
        return catalog[account_code]
    
    # Intento 2: patrón de entidad (XXXX.NNN)
    match = re.match(r"^([^.]+)\.(\d{3})$", str(account_code))
    if match:
        parent_code = match.group(1)
        if parent_code in catalog:
            return catalog[parent_code]
    
    return None


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
    for acct_key, saldo_algebraico in balances.items():
        # P1-3: Usar helper para resolver canónicas y entidades
        entry = resolve_catalog_entry_for_account_code(str(acct_key), catalog)
        if not entry:
            totals["otros"] += saldo_algebraico
            continue
        
        # Normalizar saldo según naturaleza
        naturaleza = entry.get("naturaleza")
        saldo_normalizado = normal_balance_amount(saldo_algebraico, naturaleza)
        
        tipo = entry.get("tipo") or entry.get("Tipo") or entry.get("tipo_contable") or ""
        tipo_norm = str(tipo).strip().capitalize()
        if tipo_norm in totals:
            totals[tipo_norm] += saldo_normalizado
        else:
            totals["otros"] += saldo_normalizado
    return totals

def compute_resultado_ejercicio(balances: Dict[str, Decimal], catalog: Dict[str, dict]) -> Tuple[Decimal, Dict[str, Decimal]]:
    totals = compute_totals_by_tipo(balances, catalog)
    ingresos = totals.get("Ingreso", Decimal(0))
    costos = totals.get("Costo", Decimal(0))
    gastos = totals.get("Gasto", Decimal(0))
    resultado = ingresos - costos - gastos
    return resultado, totals