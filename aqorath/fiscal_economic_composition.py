"""Explicit fiscal/economic composition declaration.

Binds one provenance-aware economic accounting resolution to one already
confirmed fiscal accounting effect and records the caller's explicit monetary
basis plus the existing semantic role that a later composition step may adjust.

This boundary validates cross-branch fact consistency and balance-direction
compatibility only. It does not change amounts, create accounting lines, resolve
accounts, confirm, persist, or post.
"""

from dataclasses import dataclass
from decimal import Decimal

from . import economic_fact_accounting_provenance as _provenance
from . import fiscal_accounting_effect as _fiscal_effect
from . import fiscal_monetary_confirmation as _monetary_confirmation


_ALLOWED_AMOUNT_BASES = (
    "net_before_fiscal",
    "gross_including_fiscal",
)


def _require_nonempty_text(value, field_name):
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


@dataclass(frozen=True)
class FiscalEconomicCompositionDeclaration:
    """Explicit, non-postable declaration for later economic/fiscal composition."""

    accounting_resolution: _provenance.EconomicFactAccountingResolution
    fiscal_effect: _fiscal_effect.FiscalAccountingEffect
    amount_basis: str
    adjustment_role: str

    def __post_init__(self):
        if not isinstance(
            self.accounting_resolution,
            _provenance.EconomicFactAccountingResolution,
        ):
            raise TypeError(
                "accounting_resolution must be EconomicFactAccountingResolution"
            )
        if not isinstance(self.fiscal_effect, _fiscal_effect.FiscalAccountingEffect):
            raise TypeError("fiscal_effect must be FiscalAccountingEffect")

        if not isinstance(self.amount_basis, str):
            raise TypeError("amount_basis must be a string")
        if self.amount_basis not in _ALLOWED_AMOUNT_BASES:
            raise ValueError(
                "amount_basis must be 'net_before_fiscal' or "
                "'gross_including_fiscal'"
            )
        _require_nonempty_text(self.adjustment_role, "adjustment_role")

        fact = self.accounting_resolution.fact
        monetary = self.fiscal_effect.declaration.confirmed_monetary_amount
        snapshot = monetary.snapshot
        if not isinstance(
            snapshot,
            _monetary_confirmation.FiscalMonetaryConfirmationSnapshot,
        ):
            raise TypeError(
                "fiscal effect must preserve FiscalMonetaryConfirmationSnapshot"
            )

        if fact.type != snapshot.fact_type:
            raise ValueError("economic and fiscal fact_type must match")
        if fact.payment_method != snapshot.payment_method:
            raise ValueError("economic and fiscal payment_method must match")
        if not isinstance(snapshot.fact_amount, Decimal):
            raise TypeError("fiscal fact_amount must be Decimal")
        if fact.amount.as_tuple() != snapshot.fact_amount.as_tuple():
            raise ValueError("economic and fiscal fact_amount must match exactly")

        matches = tuple(
            line
            for line in self.accounting_resolution.proposal.lines
            if line.account_role == self.adjustment_role
        )
        if len(matches) != 1:
            raise ValueError(
                "adjustment_role must identify exactly one existing proposal line"
            )

        adjustment_line = matches[0]
        fiscal_side = self.fiscal_effect.line.side
        if self.amount_basis == "net_before_fiscal":
            if adjustment_line.side == fiscal_side:
                raise ValueError(
                    "net_before_fiscal requires adjustment role on opposite side "
                    "from fiscal effect"
                )
        else:
            if adjustment_line.side != fiscal_side:
                raise ValueError(
                    "gross_including_fiscal requires adjustment role on same side "
                    "as fiscal effect"
                )


def declare_fiscal_economic_composition(
    accounting_resolution,
    fiscal_effect,
    amount_basis,
    adjustment_role,
):
    """Record explicit compatible economic/fiscal composition inputs."""
    return FiscalEconomicCompositionDeclaration(
        accounting_resolution=accounting_resolution,
        fiscal_effect=fiscal_effect,
        amount_basis=amount_basis,
        adjustment_role=adjustment_role,
    )


__all__ = [
    "FiscalEconomicCompositionDeclaration",
    "declare_fiscal_economic_composition",
]
