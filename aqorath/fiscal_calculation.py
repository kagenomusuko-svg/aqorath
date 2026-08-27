"""Pure exact calculation for already-resolved rate-based fiscal rules.

This module does not resolve fiscal rules, determine applicability, round to a
currency scale, select accounts, build accounting proposals, post, or persist.
"""

from dataclasses import dataclass
from decimal import Decimal

from . import fiscal_rules as _fiscal_rules


@dataclass(frozen=True)
class FiscalRateCalculation:
    base: Decimal
    amount: Decimal
    rule: _fiscal_rules.ResolvedFiscalRule


def calculate_fiscal_rate_amount(base, rule):
    """Multiply an exact non-negative Decimal base by one resolved rate rule."""
    if not isinstance(base, Decimal):
        raise TypeError("base must be Decimal")
    if not base.is_finite():
        raise ValueError("base must be finite")
    if base < Decimal("0"):
        raise ValueError("base must not be negative")

    if not isinstance(rule, _fiscal_rules.ResolvedFiscalRule):
        raise TypeError("rule must be a ResolvedFiscalRule")
    if rule.unit != "rate":
        raise ValueError("rule.unit must be 'rate'")
    if not isinstance(rule.value, Decimal):
        raise TypeError("rule.value must be Decimal")
    if not rule.value.is_finite():
        raise ValueError("rule.value must be finite")
    if rule.value < Decimal("0"):
        raise ValueError("rule.value must not be negative")

    return FiscalRateCalculation(
        base=base,
        amount=base * rule.value,
        rule=rule,
    )


__all__ = [
    "FiscalRateCalculation",
    "calculate_fiscal_rate_amount",
]
