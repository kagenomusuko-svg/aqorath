"""Explicit fiscal-rate applicability declarations.

This module records an explicit in-memory declaration that one rate-based fiscal
rule is intended to apply to one already-structured economic fact for an exact
fiscal context and date. It deliberately does not infer tax treatment from the
fact, resolve a rule, calculate an amount, round money, select accounts, persist,
or post.

Absence of a declaration means applicability is unknown; it never means
"not applicable" and never triggers a default fiscal rule.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .economic_facts import EconomicFact
from .fiscal_rules import FiscalContext


def _require_nonempty_string(value, name):
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if not value.strip():
        raise ValueError(f"{name} must not be empty")


def _validate_context(context):
    if not isinstance(context, FiscalContext):
        raise TypeError("context must be a FiscalContext")
    _require_nonempty_string(context.jurisdiction, "context.jurisdiction")
    _require_nonempty_string(context.regime, "context.regime")
    _require_nonempty_string(context.entity_type, "context.entity_type")


@dataclass(frozen=True)
class FiscalRateApplicabilityDeclaration:
    """Immutable explicit selection of one fiscal rate rule for one fact."""

    fact: EconomicFact
    effective_date: date
    context: FiscalContext
    rule_key: str
    base: Decimal

    def __post_init__(self):
        if not isinstance(self.fact, EconomicFact):
            raise TypeError("fact must be an EconomicFact")
        if type(self.effective_date) is not date:
            raise TypeError("effective_date must be a datetime.date")
        _validate_context(self.context)
        _require_nonempty_string(self.rule_key, "rule_key")

        if not isinstance(self.base, Decimal):
            raise TypeError("base must be Decimal")
        if not self.base.is_finite():
            raise ValueError("base must be finite")
        if self.base < 0:
            raise ValueError("base must be >= 0")


def declare_fiscal_rate_applicability(
    fact,
    effective_date,
    context,
    rule_key,
    base,
):
    """Create one explicit fiscal-rate applicability declaration.

    ``rule_key`` and ``base`` are caller-supplied facts of the fiscal treatment.
    They are never inferred from the economic fact and are not verified against
    the fiscal-rule registry here; resolution/calculation belong to later layers.
    """
    return FiscalRateApplicabilityDeclaration(
        fact=fact,
        effective_date=effective_date,
        context=context,
        rule_key=rule_key,
        base=base,
    )


__all__ = [
    "FiscalRateApplicabilityDeclaration",
    "declare_fiscal_rate_applicability",
]
