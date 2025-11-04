"""
Simple tax engine.

Exposes:
  - calculate_taxes(line_items: List[Dict]) -> Dict

line_items: cada ítem debe ser dict con:
  - amount: Decimal or number (base)
  - iva_rate: Decimal (e.g. 0.16) or string 'exento' or 0
  - iva_retained: Decimal (porcentaje retenido sobre IVA) opcional
  - isr_retained: Decimal (porcentaje retenido sobre base) opcional

Return:
  {
    "lines": [...],
    "totals": {"subtotal": Decimal, "iva": Decimal, "iva_retained": Decimal, "isr_retained": Decimal, "total": Decimal}
  }
"""
from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Any

ROUND = Decimal("0.01")

def _round(v: Decimal) -> Decimal:
    return v.quantize(ROUND, rounding=ROUND_HALF_UP)

def calculate_taxes(line_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    subtotal = Decimal(0)
    iva_total = Decimal(0)
    iva_ret_total = Decimal(0)
    isr_ret_total = Decimal(0)
    lines_out = []
    for li in line_items:
        amt = Decimal(str(li.get("amount", 0)))
        iva_rate = li.get("iva_rate", 0)
        if iva_rate == "exento":
            iva = Decimal(0)
        else:
            iva_rate = Decimal(str(iva_rate or 0))
            iva = (amt * iva_rate)
        iva = _round(iva)
        iva_ret = Decimal(0)
        if li.get("iva_retained"):
            iva_ret = _round(iva * Decimal(str(li["iva_retained"])))
        isr_ret = Decimal(0)
        if li.get("isr_retained"):
            isr_ret = _round(amt * Decimal(str(li["isr_retained"])))
        line_total = amt + iva - iva_ret - isr_ret
        subtotal += amt
        iva_total += iva
        iva_ret_total += iva_ret
        isr_ret_total += isr_ret
        lines_out.append({
            "amount": _round(amt),
            "iva": iva,
            "iva_retained": iva_ret,
            "isr_retained": isr_ret,
            "line_total": _round(line_total)
        })
    total = subtotal + iva_total - iva_ret_total - isr_ret_total
    return {
        "lines": lines_out,
        "totals": {
            "subtotal": _round(subtotal),
            "iva": _round(iva_total),
            "iva_retained": _round(iva_ret_total),
            "isr_retained": _round(isr_ret_total),
            "total": _round(total)
        }
    }