"""Fiscal accounting effect boundary.

Transforms one explicit fiscal accounting treatment declaration into one
standalone semantic effect line using exactly the already-confirmed rounded
fiscal monetary amount.

The result is intentionally not a balanced AccountingProposal, not account-
resolved, and not postable. Economic/fiscal composition is a later explicit
boundary.
"""

from dataclasses import dataclass
from decimal import Decimal

from . import fiscal_accounting_treatment as _treatment


def _require_nonempty_text(value, field_name):
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _require_amount(value):
    if not isinstance(value, Decimal):
        raise TypeError("amount must be Decimal")
    if not value.is_finite():
        raise ValueError("amount must be finite")
    if value < 0:
        raise ValueError("amount must be >= 0")


@dataclass(frozen=True)
class FiscalAccountingEffectLine:
    """One semantic fiscal accounting direction before composition/resolution."""

    account_role: str
    side: str
    amount: Decimal

    def __post_init__(self):
        _require_nonempty_text(self.account_role, "account_role")
        if not isinstance(self.side, str):
            raise TypeError("side must be a string")
        if self.side not in ("debit", "credit"):
            raise ValueError("side must be 'debit' or 'credit'")
        _require_amount(self.amount)


@dataclass(frozen=True)
class FiscalAccountingEffect:
    """One explicit, unbalanced and non-postable fiscal semantic effect."""

    declaration: _treatment.FiscalAccountingTreatmentDeclaration
    line: FiscalAccountingEffectLine

    def __post_init__(self):
        if not isinstance(
            self.declaration,
            _treatment.FiscalAccountingTreatmentDeclaration,
        ):
            raise TypeError(
                "declaration must be FiscalAccountingTreatmentDeclaration"
            )
        if not isinstance(self.line, FiscalAccountingEffectLine):
            raise TypeError("line must be FiscalAccountingEffectLine")

        if self.line.account_role != self.declaration.account_role:
            raise ValueError("line account_role must match declaration")
        if self.line.side != self.declaration.side:
            raise ValueError("line side must match declaration")

        source_amount = (
            self.declaration.confirmed_monetary_amount.snapshot.rounded_amount
        )
        _require_amount(source_amount)
        if self.line.amount.as_tuple() != source_amount.as_tuple():
            raise ValueError(
                "line amount must exactly match confirmed rounded fiscal amount"
            )


def build_fiscal_accounting_effect(declaration):
    """Build one semantic fiscal effect from one explicit treatment declaration."""
    if not isinstance(
        declaration,
        _treatment.FiscalAccountingTreatmentDeclaration,
    ):
        raise TypeError(
            "build_fiscal_accounting_effect requires "
            "FiscalAccountingTreatmentDeclaration"
        )

    amount = declaration.confirmed_monetary_amount.snapshot.rounded_amount
    line = FiscalAccountingEffectLine(
        account_role=declaration.account_role,
        side=declaration.side,
        amount=amount,
    )
    return FiscalAccountingEffect(
        declaration=declaration,
        line=line,
    )


__all__ = [
    "FiscalAccountingEffectLine",
    "FiscalAccountingEffect",
    "build_fiscal_accounting_effect",
]
