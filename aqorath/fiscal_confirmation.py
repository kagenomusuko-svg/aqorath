"""Informed fiscal confirmation boundary.

Creates an immutable value snapshot from one already-resolved fiscal treatment
and represents the explicit in-memory act of confirming exactly that snapshot.
The historical declared-rate path delegates to the same value authority.

This module is deliberately downstream of fiscal applicability/calculation and
upstream of accounting or persistence effects. It does not infer fiscal
applicability, resolve rules, calculate or round amounts, select accounts, open a
session, install rules, persist, or post.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from . import fiscal_declaration_runtime as _declaration_runtime
from . import fiscal_rules as _fiscal_rules
from .economic_facts import EconomicFact


@dataclass(frozen=True)
class FiscalConfirmationSnapshot:
    """Deeply immutable value copy of the fiscal truth presented to the user."""

    fact_type: str
    fact_amount: Decimal
    payment_method: str
    effective_date: date
    jurisdiction: str
    regime: str
    entity_type: str
    rule_key: str
    base: Decimal
    rate: Decimal
    unit: str
    rule_effective_from: date
    rule_effective_to: Optional[date]
    source_ref: str
    calculated_amount: Decimal


@dataclass(frozen=True)
class ConfirmedFiscalTreatment:
    """Represents explicit confirmation of one exact fiscal snapshot."""

    snapshot: FiscalConfirmationSnapshot


def _require_exact_nonnegative_decimal(value, field_name):
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be Decimal")
    if not value.is_finite():
        raise ValueError(f"{field_name} must be finite")
    if value < Decimal("0"):
        raise ValueError(f"{field_name} must not be negative")


def create_resolved_fiscal_confirmation_snapshot(
    fact,
    effective_date,
    rule,
    base,
    calculated_amount,
):
    """Freeze already-resolved fiscal truth without assuming a rate formula.

    AQR-011 uses this same confirmation boundary for both finite rate rules and
    the exact statutory ``2/3`` IVA-retention formula. Calculation remains owned
    upstream; this function only validates and copies resolved truth by value.
    """
    if not isinstance(fact, EconomicFact):
        raise TypeError("fact must be EconomicFact")
    if type(effective_date) is not date:
        raise TypeError("effective_date must be datetime.date")
    if not isinstance(rule, _fiscal_rules.ResolvedFiscalRule):
        raise TypeError("rule must be ResolvedFiscalRule")
    _require_exact_nonnegative_decimal(base, "base")
    _require_exact_nonnegative_decimal(calculated_amount, "calculated_amount")
    _require_exact_nonnegative_decimal(rule.value, "rule.value")
    if effective_date < rule.effective_from:
        raise ValueError("effective_date precedes resolved fiscal-rule version")
    if rule.effective_to is not None and effective_date > rule.effective_to:
        raise ValueError("effective_date follows resolved fiscal-rule version")

    return FiscalConfirmationSnapshot(
        fact_type=fact.type,
        fact_amount=fact.amount,
        payment_method=fact.payment_method,
        effective_date=effective_date,
        jurisdiction=rule.jurisdiction,
        regime=rule.regime,
        entity_type=rule.entity_type,
        rule_key=rule.rule_key,
        base=base,
        rate=rule.value,
        unit=rule.unit,
        rule_effective_from=rule.effective_from,
        rule_effective_to=rule.effective_to,
        source_ref=rule.source_ref,
        calculated_amount=calculated_amount,
    )


def create_fiscal_confirmation_snapshot(declared_calculation):
    """Freeze one historical declared-rate calculation into the same snapshot."""
    if not isinstance(
        declared_calculation,
        _declaration_runtime.DeclaredFiscalRateCalculation,
    ):
        raise TypeError(
            "create_fiscal_confirmation_snapshot requires "
            "DeclaredFiscalRateCalculation"
        )

    declaration = declared_calculation.declaration
    calculation = declared_calculation.calculation
    rule = calculation.rule
    if declaration.rule_key != rule.rule_key:
        raise ValueError("declared rule_key must match resolved rule")
    context = declaration.context
    if (
        context.jurisdiction != rule.jurisdiction
        or context.regime != rule.regime
        or context.entity_type != rule.entity_type
    ):
        raise ValueError("declared fiscal context must match resolved rule")
    if declaration.base.as_tuple() != calculation.base.as_tuple():
        raise ValueError("declared base must match calculated base exactly")

    return create_resolved_fiscal_confirmation_snapshot(
        declaration.fact,
        declaration.effective_date,
        rule,
        declaration.base,
        calculation.amount,
    )


def confirm_fiscal_snapshot(snapshot):
    """Confirm exactly one immutable fiscal snapshot without recomputation."""
    if not isinstance(snapshot, FiscalConfirmationSnapshot):
        raise TypeError("confirm_fiscal_snapshot requires FiscalConfirmationSnapshot")

    return ConfirmedFiscalTreatment(snapshot=snapshot)


__all__ = [
    "FiscalConfirmationSnapshot",
    "ConfirmedFiscalTreatment",
    "create_fiscal_confirmation_snapshot",
    "create_resolved_fiscal_confirmation_snapshot",
    "confirm_fiscal_snapshot",
]
