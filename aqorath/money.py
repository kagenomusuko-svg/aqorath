"""
P0-2: Exact monetary conversion utilities.

No imports from other aqorath modules to avoid circular dependencies.
Only standard library + Decimal.
"""

from decimal import Decimal
from typing import Any


def to_decimal_exact(value: Any) -> Decimal:
    """
    Convert any value to Decimal with exact representation.
    
    Contracts:
    - Decimal: returned as-is
    - int: converted to Decimal exactly
    - str: parsed as Decimal (exact)
    - float: LEGACY ONLY — converted via str() to recover lost precision
             (but cannot magically recover decimals already lost in binary representation)
    - None: raises ValueError
    
    NEVER: Decimal(float_value) because it incorporates float's binary expansion.
    """
    if isinstance(value, Decimal):
        return value
    elif isinstance(value, int):
        return Decimal(value)
    elif isinstance(value, str):
        return Decimal(value)
    elif isinstance(value, float):
        # Legacy float: convert via str to avoid binary expansion
        # But note: precision already lost in float is NOT recoverable
        return Decimal(str(value))
    elif value is None:
        raise ValueError("Cannot convert None to Decimal. Value is required.")
    else:
        # Try str() for other types
        return Decimal(str(value))
