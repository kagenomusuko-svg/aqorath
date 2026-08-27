"""Informed fiscal confirmation boundary.

Creates an immutable value snapshot from one already-declared, already-calculated
fiscal treatment and represents the explicit in-memory act of confirming exactly
that snapshot.

This module is deliberately downstream of fiscal declaration/calculation and
upstream of any accounting or persistence effect. It does not infer fiscal
applicability, resolve rules, calculate or round amounts, select accounts, open a
session, install rules, persist, or post.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from . import fiscal_declaration_runtime as _declaration_runtime


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


def create_fiscal_confirmation_snapshot(declared_calculation):
    """Freeze one declared fiscal calculation into a standalone value snapshot."""
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
    fact = declaration.fact
    context = declaration.context
    rule = calculation.rule

    return FiscalConfirmationSnapshot(
        fact_type=fact.type,
        fact_amount=fact.amount,
        payment_method=fact.payment_method,
        effective_date=declaration.effective_date,
        jurisdiction=context.jurisdiction,
        regime=context.regime,
        entity_type=context.entity_type,
        rule_key=declaration.rule_key,
        base=declaration.base,
        rate=rule.value,
        unit=rule.unit,
        rule_effective_from=rule.effective_from,
        rule_effective_to=rule.effective_to,
        source_ref=rule.source_ref,
        calculated_amount=calculation.amount,
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
    "confirm_fiscal_snapshot",
]
