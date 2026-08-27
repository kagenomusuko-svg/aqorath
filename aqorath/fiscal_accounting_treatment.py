"""Explicit fiscal accounting treatment declaration boundary.

This module records only an explicit semantic accounting direction for one
already-confirmed fiscal monetary amount. It does not infer treatment from the
fiscal rule or economic fact, resolve concrete accounts, balance an entry,
construct a proposal, persist, or post.
"""

from dataclasses import dataclass

from . import fiscal_monetary_confirmation as _monetary


def _require_nonempty_text(value, field_name):
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


@dataclass(frozen=True)
class FiscalAccountingTreatmentDeclaration:
    """Explicit semantic account role/side for confirmed fiscal money."""

    confirmed_monetary_amount: _monetary.ConfirmedFiscalMonetaryAmount
    account_role: str
    side: str

    def __post_init__(self):
        if not isinstance(
            self.confirmed_monetary_amount,
            _monetary.ConfirmedFiscalMonetaryAmount,
        ):
            raise TypeError(
                "confirmed_monetary_amount must be ConfirmedFiscalMonetaryAmount"
            )
        _require_nonempty_text(self.account_role, "account_role")
        if not isinstance(self.side, str):
            raise TypeError("side must be a string")
        if self.side not in ("debit", "credit"):
            raise ValueError("side must be 'debit' or 'credit'")


def declare_fiscal_accounting_treatment(
    confirmed_monetary_amount,
    account_role,
    side,
):
    """Declare one explicit semantic fiscal accounting role and side."""
    return FiscalAccountingTreatmentDeclaration(
        confirmed_monetary_amount=confirmed_monetary_amount,
        account_role=account_role,
        side=side,
    )


__all__ = [
    "FiscalAccountingTreatmentDeclaration",
    "declare_fiscal_accounting_treatment",
]
