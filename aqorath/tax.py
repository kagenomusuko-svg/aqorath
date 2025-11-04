"""
Tax calculation engine for SAT (Mexican tax authority) compliance.
Handles IVA (VAT), retentions, and common fiscal scenarios.
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Any


def calculate_taxes(line_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calculate taxes for a list of line items following SAT rules.
    
    Supports:
    - IVA 16% (trasladado)
    - IVA 0% (tasa cero)
    - IVA exento (sin IVA)
    - IVA retenido (retención de IVA)
    - ISR retenido (retención de ISR)
    - Proper rounding to 2 decimals
    
    Args:
        line_items: List of dicts with keys:
            - amount (required): base amount (Decimal, float, or str)
            - iva_rate (optional): IVA rate in % (default 16)
            - iva_type (optional): 'trasladado', 'exento', 'tasa_cero' (default 'trasladado')
            - iva_retenido_rate (optional): IVA retention rate in % (default 0)
            - isr_retenido_rate (optional): ISR retention rate in % (default 0)
            - description (optional): line description
    
    Returns:
        Dict with:
            - subtotal: sum of all amounts before taxes
            - iva_trasladado: total IVA charged (16%, 0%, etc.)
            - iva_retenido: total IVA retained
            - isr_retenido: total ISR retained
            - total: final amount (subtotal + iva_trasladado - retentions)
            - breakdown: detailed breakdown per line
            - summary: summary by tax type
    """
    if not line_items:
        return {
            "subtotal": Decimal("0.00"),
            "iva_trasladado": Decimal("0.00"),
            "iva_retenido": Decimal("0.00"),
            "isr_retenido": Decimal("0.00"),
            "total": Decimal("0.00"),
            "breakdown": [],
            "summary": {}
        }
    
    subtotal = Decimal("0.00")
    iva_trasladado_total = Decimal("0.00")
    iva_retenido_total = Decimal("0.00")
    isr_retenido_total = Decimal("0.00")
    
    breakdown = []
    
    for idx, item in enumerate(line_items):
        # Parse amount
        try:
            amount = Decimal(str(item.get("amount", 0)))
        except Exception:
            amount = Decimal("0.00")
        
        # Round amount to 2 decimals
        amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        subtotal += amount
        
        # IVA trasladado (charged VAT)
        iva_type = str(item.get("iva_type", "trasladado")).lower()
        iva_rate = Decimal(str(item.get("iva_rate", 16)))
        
        iva_trasladado = Decimal("0.00")
        if iva_type == "trasladado" and iva_rate > 0:
            iva_trasladado = (amount * iva_rate / Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        elif iva_type == "tasa_cero":
            # IVA at 0% rate (still trasladado but 0 amount)
            iva_trasladado = Decimal("0.00")
        # else: exento, no IVA
        
        iva_trasladado_total += iva_trasladado
        
        # IVA retenido (withheld VAT)
        iva_retenido_rate = Decimal(str(item.get("iva_retenido_rate", 0)))
        iva_retenido = Decimal("0.00")
        if iva_retenido_rate > 0:
            iva_retenido = (amount * iva_retenido_rate / Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        iva_retenido_total += iva_retenido
        
        # ISR retenido (withheld income tax)
        isr_retenido_rate = Decimal(str(item.get("isr_retenido_rate", 0)))
        isr_retenido = Decimal("0.00")
        if isr_retenido_rate > 0:
            isr_retenido = (amount * isr_retenido_rate / Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        isr_retenido_total += isr_retenido
        
        # Build breakdown entry
        breakdown.append({
            "line": idx + 1,
            "description": item.get("description", f"Línea {idx + 1}"),
            "amount": float(amount),
            "iva_type": iva_type,
            "iva_rate": float(iva_rate),
            "iva_trasladado": float(iva_trasladado),
            "iva_retenido_rate": float(iva_retenido_rate),
            "iva_retenido": float(iva_retenido),
            "isr_retenido_rate": float(isr_retenido_rate),
            "isr_retenido": float(isr_retenido)
        })
    
    # Calculate total
    total = subtotal + iva_trasladado_total - iva_retenido_total - isr_retenido_total
    
    # Build summary
    summary = {
        "IVA_trasladado_16%": Decimal("0.00"),
        "IVA_trasladado_0%": Decimal("0.00"),
        "IVA_exento": Decimal("0.00"),
        "IVA_retenido": iva_retenido_total,
        "ISR_retenido": isr_retenido_total
    }
    
    # Aggregate IVA trasladado by rate
    for entry in breakdown:
        if entry["iva_type"] == "trasladado":
            rate = entry["iva_rate"]
            if rate == 16:
                summary["IVA_trasladado_16%"] += Decimal(str(entry["iva_trasladado"]))
            elif rate == 0:
                summary["IVA_trasladado_0%"] += Decimal(str(entry["iva_trasladado"]))
        elif entry["iva_type"] == "tasa_cero":
            summary["IVA_trasladado_0%"] += Decimal("0.00")  # Already 0
        elif entry["iva_type"] == "exento":
            summary["IVA_exento"] += Decimal(str(entry["amount"]))
    
    # Convert summary to float for JSON serialization
    summary_float = {k: float(v) for k, v in summary.items()}
    
    return {
        "subtotal": float(subtotal),
        "iva_trasladado": float(iva_trasladado_total),
        "iva_retenido": float(iva_retenido_total),
        "isr_retenido": float(isr_retenido_total),
        "total": float(total),
        "breakdown": breakdown,
        "summary": summary_float
    }


# Convenience functions for common scenarios

def calculate_simple_iva(amount: float, rate: float = 16.0) -> Dict[str, float]:
    """
    Calculate simple IVA (VAT) for a single amount.
    
    Args:
        amount: Base amount
        rate: IVA rate in % (default 16)
    
    Returns:
        Dict with subtotal, iva, and total
    """
    result = calculate_taxes([{"amount": amount, "iva_rate": rate}])
    return {
        "subtotal": result["subtotal"],
        "iva": result["iva_trasladado"],
        "total": result["total"]
    }


def calculate_with_retentions(
    amount: float, 
    iva_rate: float = 16.0,
    iva_retenido_rate: float = 0.0,
    isr_retenido_rate: float = 0.0
) -> Dict[str, float]:
    """
    Calculate taxes with retentions (common for professional services).
    
    Args:
        amount: Base amount
        iva_rate: IVA rate in % (default 16)
        iva_retenido_rate: IVA retention rate in % (default 0)
        isr_retenido_rate: ISR retention rate in % (default 0)
    
    Returns:
        Dict with subtotal, iva_trasladado, retentions, and total
    """
    result = calculate_taxes([{
        "amount": amount,
        "iva_rate": iva_rate,
        "iva_retenido_rate": iva_retenido_rate,
        "isr_retenido_rate": isr_retenido_rate
    }])
    return {
        "subtotal": result["subtotal"],
        "iva_trasladado": result["iva_trasladado"],
        "iva_retenido": result["iva_retenido"],
        "isr_retenido": result["isr_retenido"],
        "total": result["total"]
    }
