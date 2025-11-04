"""
Tax calculation engine for Mexican tax system (IVA, ISR).

Provides functions to calculate taxes on line items including:
- IVA trasladado (16%, 0%, exento)
- IVA retenido
- ISR retenido
- Rounding to 2 decimals
- Support for multiple lines
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Any, Optional


def calculate_taxes(line_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calculate taxes for a list of line items.
    
    Each line item should be a dict with keys:
    - amount: Decimal or float, the base amount
    - iva_rate: Optional[float], IVA rate (16, 0, or None for exempt)
    - iva_retencion_rate: Optional[float], IVA retention rate (usually 10.67 for 2/3 of 16%)
    - isr_retencion_rate: Optional[float], ISR retention rate (varies by concept)
    
    Returns a dict with:
    - subtotal: Sum of all line item amounts
    - iva_trasladado: Total IVA charged (16% or 0%)
    - iva_retenido: Total IVA retained
    - isr_retenido: Total ISR retained
    - total: Final total (subtotal + IVA trasladado - retentions)
    - lines: List of processed lines with calculated taxes
    
    Example:
        line_items = [
            {"amount": 1000, "iva_rate": 16},
            {"amount": 500, "iva_rate": 0},
        ]
        result = calculate_taxes(line_items)
        # result["iva_trasladado"] == Decimal("160.00")
        # result["total"] == Decimal("1660.00")
    """
    # Ensure precision
    subtotal = Decimal("0.00")
    iva_trasladado_total = Decimal("0.00")
    iva_retenido_total = Decimal("0.00")
    isr_retenido_total = Decimal("0.00")
    
    processed_lines = []
    
    for idx, item in enumerate(line_items):
        # Parse amount
        try:
            amount = Decimal(str(item.get("amount", 0))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except Exception:
            amount = Decimal("0.00")
        
        subtotal += amount
        
        # Calculate IVA trasladado
        iva_rate = item.get("iva_rate")
        iva_trasladado = Decimal("0.00")
        if iva_rate is not None and iva_rate > 0:
            try:
                rate_dec = Decimal(str(iva_rate))
                iva_trasladado = (amount * rate_dec / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                iva_trasladado_total += iva_trasladado
            except Exception:
                pass
        
        # Calculate IVA retenido
        iva_retencion_rate = item.get("iva_retencion_rate")
        iva_retenido = Decimal("0.00")
        if iva_retencion_rate is not None and iva_retencion_rate > 0:
            try:
                ret_rate_dec = Decimal(str(iva_retencion_rate))
                iva_retenido = (amount * ret_rate_dec / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                iva_retenido_total += iva_retenido
            except Exception:
                pass
        
        # Calculate ISR retenido
        isr_retencion_rate = item.get("isr_retencion_rate")
        isr_retenido = Decimal("0.00")
        if isr_retencion_rate is not None and isr_retencion_rate > 0:
            try:
                isr_rate_dec = Decimal(str(isr_retencion_rate))
                isr_retenido = (amount * isr_rate_dec / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                isr_retenido_total += isr_retenido
            except Exception:
                pass
        
        # Store processed line
        processed_lines.append({
            "line_number": idx + 1,
            "amount": float(amount),
            "iva_trasladado": float(iva_trasladado),
            "iva_retenido": float(iva_retenido),
            "isr_retenido": float(isr_retenido),
            "iva_rate": iva_rate,
            "description": item.get("description", f"Line {idx + 1}")
        })
    
    # Calculate total
    # Total = Subtotal + IVA trasladado - IVA retenido - ISR retenido
    total = subtotal + iva_trasladado_total - iva_retenido_total - isr_retenido_total
    total = total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    
    return {
        "subtotal": float(subtotal),
        "iva_trasladado": float(iva_trasladado_total),
        "iva_retenido": float(iva_retenido_total),
        "isr_retenido": float(isr_retenido_total),
        "total": float(total),
        "lines": processed_lines
    }


def calculate_iva_16(amount: float) -> Decimal:
    """
    Calculate IVA at 16% for a given amount.
    
    Args:
        amount: Base amount
    
    Returns:
        IVA amount rounded to 2 decimals
    """
    amt_dec = Decimal(str(amount))
    iva = (amt_dec * Decimal("16") / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return iva


def calculate_iva_retencion(amount: float, rate: float = 10.67) -> Decimal:
    """
    Calculate IVA retention (retencion) at given rate.
    Default rate is 10.67% (2/3 of 16%).
    
    Args:
        amount: Base amount
        rate: Retention rate (default 10.67)
    
    Returns:
        IVA retention amount rounded to 2 decimals
    """
    amt_dec = Decimal(str(amount))
    rate_dec = Decimal(str(rate))
    retencion = (amt_dec * rate_dec / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return retencion


def calculate_isr_retencion(amount: float, rate: float) -> Decimal:
    """
    Calculate ISR retention at given rate.
    Common rates: 10% for professional services, 1.25% for rent.
    
    Args:
        amount: Base amount
        rate: ISR retention rate
    
    Returns:
        ISR retention amount rounded to 2 decimals
    """
    amt_dec = Decimal(str(amount))
    rate_dec = Decimal(str(rate))
    retencion = (amt_dec * rate_dec / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return retencion


def split_amount_with_iva(total_with_iva: float, iva_rate: float = 16.0) -> Dict[str, Decimal]:
    """
    Split a total amount that includes IVA into subtotal and IVA.
    
    Args:
        total_with_iva: Total amount including IVA
        iva_rate: IVA rate (default 16)
    
    Returns:
        Dict with 'subtotal' and 'iva' keys
    """
    total_dec = Decimal(str(total_with_iva))
    rate_dec = Decimal(str(iva_rate))
    
    # Subtotal = Total / (1 + rate/100)
    divisor = Decimal("1") + (rate_dec / Decimal("100"))
    subtotal = (total_dec / divisor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    iva = total_dec - subtotal
    iva = iva.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    
    return {
        "subtotal": subtotal,
        "iva": iva,
        "total": total_dec
    }


def validate_tax_calculation(subtotal: float, iva: float, total: float, tolerance: float = 0.02) -> bool:
    """
    Validate that subtotal + iva = total (within tolerance).
    
    Args:
        subtotal: Subtotal amount
        iva: IVA amount
        total: Total amount
        tolerance: Maximum acceptable difference (default 0.02 = 2 cents)
    
    Returns:
        True if calculation is valid, False otherwise
    """
    subtotal_dec = Decimal(str(subtotal))
    iva_dec = Decimal(str(iva))
    total_dec = Decimal(str(total))
    calculated_total = subtotal_dec + iva_dec
    diff = abs(calculated_total - total_dec)
    
    return diff <= Decimal(str(tolerance))
