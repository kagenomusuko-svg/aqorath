"""Rounded fiscal monetary confirmation boundary.

This module freezes one already-confirmed, already-rounded fiscal amount into a
standalone value snapshot and represents the explicit confirmation of exactly
that monetary presentation.

It does not resolve fiscal rules, calculate taxes, round amounts, select
accounts, open sessions, persist, or post.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from . import fiscal_rounding as _fiscal_rounding


@dataclass(frozen=True)
class FiscalMonetaryConfirmationSnapshot:
    """Immutable value copy of confirmed fiscal truth plus explicit rounding."""

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
    rule_source_ref: str
    exact_amount: Decimal
    rounding_policy_key: str
    rounding_quantizer: Decimal
    rounding_mode: str
    rounding_source_ref: str
    rounded_amount: Decimal


@dataclass(frozen=True)
class ConfirmedFiscalMonetaryAmount:
    """Represents explicit confirmation of one exact monetary snapshot."""

    snapshot: FiscalMonetaryConfirmationSnapshot


def create_fiscal_monetary_confirmation_snapshot(rounded_amount):
    """Copy one RoundedFiscalAmount into an immutable monetary snapshot."""
    if not isinstance(rounded_amount, _fiscal_rounding.RoundedFiscalAmount):
        raise TypeError(
            "create_fiscal_monetary_confirmation_snapshot requires "
            "RoundedFiscalAmount"
        )

    fiscal_snapshot = rounded_amount.confirmed_treatment.snapshot
    policy = rounded_amount.policy

    return FiscalMonetaryConfirmationSnapshot(
        fact_type=fiscal_snapshot.fact_type,
        fact_amount=fiscal_snapshot.fact_amount,
        payment_method=fiscal_snapshot.payment_method,
        effective_date=fiscal_snapshot.effective_date,
        jurisdiction=fiscal_snapshot.jurisdiction,
        regime=fiscal_snapshot.regime,
        entity_type=fiscal_snapshot.entity_type,
        rule_key=fiscal_snapshot.rule_key,
        base=fiscal_snapshot.base,
        rate=fiscal_snapshot.rate,
        unit=fiscal_snapshot.unit,
        rule_effective_from=fiscal_snapshot.rule_effective_from,
        rule_effective_to=fiscal_snapshot.rule_effective_to,
        rule_source_ref=fiscal_snapshot.source_ref,
        exact_amount=rounded_amount.exact_amount,
        rounding_policy_key=policy.policy_key,
        rounding_quantizer=policy.quantizer,
        rounding_mode=policy.rounding_mode,
        rounding_source_ref=policy.source_ref,
        rounded_amount=rounded_amount.rounded_amount,
    )


def confirm_fiscal_monetary_snapshot(snapshot):
    """Confirm exactly one immutable fiscal monetary snapshot."""
    if not isinstance(snapshot, FiscalMonetaryConfirmationSnapshot):
        raise TypeError(
            "confirm_fiscal_monetary_snapshot requires "
            "FiscalMonetaryConfirmationSnapshot"
        )

    return ConfirmedFiscalMonetaryAmount(snapshot=snapshot)


__all__ = [
    "FiscalMonetaryConfirmationSnapshot",
    "ConfirmedFiscalMonetaryAmount",
    "create_fiscal_monetary_confirmation_snapshot",
    "confirm_fiscal_monetary_snapshot",
]
