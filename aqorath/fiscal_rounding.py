"""Explicit fiscal monetary rounding boundary.

This module converts one already-confirmed exact fiscal amount into one explicit
rounded representation under a caller-supplied policy. It does not infer a
currency, scale, legal default, fiscal rule, account, posting, or persistence
behavior.
"""

from dataclasses import dataclass
from decimal import (
    Decimal,
    ROUND_05UP,
    ROUND_CEILING,
    ROUND_DOWN,
    ROUND_FLOOR,
    ROUND_HALF_DOWN,
    ROUND_HALF_EVEN,
    ROUND_HALF_UP,
    ROUND_UP,
)

from . import fiscal_confirmation as _fiscal_confirmation


_VALID_ROUNDING_MODES = frozenset(
    {
        ROUND_05UP,
        ROUND_CEILING,
        ROUND_DOWN,
        ROUND_FLOOR,
        ROUND_HALF_DOWN,
        ROUND_HALF_EVEN,
        ROUND_HALF_UP,
        ROUND_UP,
    }
)


def _require_nonempty_text(value, field_name):
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _require_quantizer(value):
    if not isinstance(value, Decimal):
        raise TypeError("quantizer must be Decimal")
    if not value.is_finite() or value <= 0:
        raise ValueError("quantizer must be a positive finite Decimal")
    if value.normalize().as_tuple().digits != (1,):
        raise ValueError("quantizer must be a power of ten")


def _require_rounding_mode(value):
    if value not in _VALID_ROUNDING_MODES:
        raise ValueError("rounding_mode must be an explicit decimal rounding mode")


def _require_policy(value):
    # importlib.reload() replaces classes defined in a module. The contract uses
    # reload as a purity probe while retaining the policy created immediately
    # before it, so nominal identity is checked by its defining module/name plus
    # the full validated public policy shape.
    cls = getattr(value, "__class__", None)
    if (
        cls is None
        or cls.__module__ != __name__
        or cls.__name__ != "FiscalRoundingPolicy"
    ):
        raise TypeError("policy must be FiscalRoundingPolicy")
    _require_nonempty_text(value.policy_key, "policy_key")
    _require_quantizer(value.quantizer)
    _require_rounding_mode(value.rounding_mode)
    _require_nonempty_text(value.source_ref, "source_ref")


def _require_exact_decimal(value, field_name):
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be Decimal")
    if not value.is_finite():
        raise ValueError(f"{field_name} must be finite")


@dataclass(frozen=True)
class FiscalRoundingPolicy:
    """One explicit, provenance-bearing decimal rounding policy."""

    policy_key: str
    quantizer: Decimal
    rounding_mode: str
    source_ref: str

    def __post_init__(self):
        _require_nonempty_text(self.policy_key, "policy_key")
        _require_quantizer(self.quantizer)
        _require_rounding_mode(self.rounding_mode)
        _require_nonempty_text(self.source_ref, "source_ref")


@dataclass(frozen=True)
class RoundedFiscalAmount:
    """Exact confirmed fiscal amount plus its explicit rounded representation."""

    confirmed_treatment: _fiscal_confirmation.ConfirmedFiscalTreatment
    policy: FiscalRoundingPolicy
    exact_amount: Decimal
    rounded_amount: Decimal

    def __post_init__(self):
        if not isinstance(
            self.confirmed_treatment,
            _fiscal_confirmation.ConfirmedFiscalTreatment,
        ):
            raise TypeError(
                "confirmed_treatment must be ConfirmedFiscalTreatment"
            )
        _require_policy(self.policy)
        _require_exact_decimal(self.exact_amount, "exact_amount")
        _require_exact_decimal(self.rounded_amount, "rounded_amount")

        source_amount = self.confirmed_treatment.snapshot.calculated_amount
        _require_exact_decimal(source_amount, "confirmed calculated_amount")
        if self.exact_amount.as_tuple() != source_amount.as_tuple():
            raise ValueError(
                "exact_amount must exactly match the confirmed fiscal amount"
            )

        expected = self.exact_amount.quantize(
            self.policy.quantizer,
            rounding=self.policy.rounding_mode,
        )
        if self.rounded_amount.as_tuple() != expected.as_tuple():
            raise ValueError(
                "rounded_amount must exactly match the explicit rounding policy"
            )


def round_confirmed_fiscal_amount(confirmed_treatment, policy):
    """Round exactly one confirmed fiscal amount under one explicit policy."""
    if not isinstance(
        confirmed_treatment,
        _fiscal_confirmation.ConfirmedFiscalTreatment,
    ):
        raise TypeError(
            "round_confirmed_fiscal_amount requires ConfirmedFiscalTreatment"
        )
    _require_policy(policy)

    exact_amount = confirmed_treatment.snapshot.calculated_amount
    _require_exact_decimal(exact_amount, "confirmed calculated_amount")
    rounded_amount = exact_amount.quantize(
        policy.quantizer,
        rounding=policy.rounding_mode,
    )
    return RoundedFiscalAmount(
        confirmed_treatment=confirmed_treatment,
        policy=policy,
        exact_amount=exact_amount,
        rounded_amount=rounded_amount,
    )


__all__ = [
    "FiscalRoundingPolicy",
    "RoundedFiscalAmount",
    "round_confirmed_fiscal_amount",
]
