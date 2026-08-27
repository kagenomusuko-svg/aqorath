"""Pure composition of one explicit fiscal/economic declaration.

Creates a new immutable semantic accounting proposal from the exact economic
proposal and confirmed fiscal effect already bound by Phase 5V. No concrete
accounts are resolved and no confirmation, persistence, or posting occurs here.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Tuple

from . import fiscal_economic_composition as _composition


@dataclass(frozen=True)
class FiscalizedProposalLine:
    account_role: str
    side: str
    amount: Decimal

    def __post_init__(self):
        if not isinstance(self.account_role, str):
            raise TypeError("account_role must be a string")
        if not self.account_role.strip():
            raise ValueError("account_role must not be empty")
        if self.side not in ("debit", "credit"):
            raise ValueError("side must be 'debit' or 'credit'")
        if not isinstance(self.amount, Decimal):
            raise TypeError("amount must be Decimal")
        if not self.amount.is_finite():
            raise ValueError("amount must be finite")
        if self.amount < Decimal("0"):
            raise ValueError("amount must not be negative")


def _explanation_for(declaration):
    fiscal_line = declaration.fiscal_effect.line
    return (
        "Fiscalized accounting composition: "
        f"amount_basis={declaration.amount_basis}; "
        f"adjustment_role={declaration.adjustment_role}; "
        f"fiscal_role={fiscal_line.account_role}; "
        f"fiscal_side={fiscal_line.side}; "
        f"fiscal_amount={fiscal_line.amount}."
    )


@dataclass(frozen=True)
class FiscalizedAccountingProposal:
    declaration: _composition.FiscalEconomicCompositionDeclaration
    lines: Tuple[FiscalizedProposalLine, ...]
    explanation: str

    def __post_init__(self):
        if not isinstance(
            self.declaration,
            _composition.FiscalEconomicCompositionDeclaration,
        ):
            raise TypeError(
                "declaration must be FiscalEconomicCompositionDeclaration"
            )
        if not isinstance(self.lines, tuple):
            raise TypeError("lines must be a tuple")
        if not all(isinstance(line, FiscalizedProposalLine) for line in self.lines):
            raise TypeError("all lines must be FiscalizedProposalLine")

        source_lines = tuple(self.declaration.accounting_resolution.proposal.lines)
        if len(self.lines) != len(source_lines) + 1:
            raise ValueError("fiscalized proposal must preserve source lines and append one fiscal line")

        fiscal_line = self.declaration.fiscal_effect.line
        for index, source in enumerate(source_lines):
            result = self.lines[index]
            expected_amount = source.amount
            if source.account_role == self.declaration.adjustment_role:
                if self.declaration.amount_basis == "net_before_fiscal":
                    expected_amount = source.amount + fiscal_line.amount
                else:
                    expected_amount = source.amount - fiscal_line.amount
                    if expected_amount <= Decimal("0"):
                        raise ValueError(
                            "gross fiscal composition must leave adjusted line amount > 0"
                        )

            if result.account_role != source.account_role:
                raise ValueError("source account_role order must be preserved")
            if result.side != source.side:
                raise ValueError("source line side must be preserved")
            if result.amount.as_tuple() != expected_amount.as_tuple():
                raise ValueError("source line amount does not match declared fiscal composition")

        appended = self.lines[-1]
        if appended.account_role != fiscal_line.account_role:
            raise ValueError("appended fiscal account_role must match fiscal effect")
        if appended.side != fiscal_line.side:
            raise ValueError("appended fiscal side must match fiscal effect")
        if appended.amount.as_tuple() != fiscal_line.amount.as_tuple():
            raise ValueError("appended fiscal amount must match fiscal effect exactly")

        total_debit = sum(
            (line.amount for line in self.lines if line.side == "debit"),
            Decimal("0"),
        )
        total_credit = sum(
            (line.amount for line in self.lines if line.side == "credit"),
            Decimal("0"),
        )
        if total_debit != total_credit:
            raise ValueError(
                "fiscalized proposal must be balanced: "
                f"total_debit={total_debit}, total_credit={total_credit}"
            )

        expected_explanation = _explanation_for(self.declaration)
        if self.explanation != expected_explanation:
            raise ValueError("explanation must describe the exact declared composition")


def compose_fiscal_economic_accounting(declaration):
    """Materialize one explicit Phase 5V declaration as a balanced semantic proposal."""
    if not isinstance(declaration, _composition.FiscalEconomicCompositionDeclaration):
        raise TypeError(
            "compose_fiscal_economic_accounting requires "
            "FiscalEconomicCompositionDeclaration"
        )

    fiscal_line = declaration.fiscal_effect.line
    composed_lines = []
    for source in declaration.accounting_resolution.proposal.lines:
        amount = source.amount
        if source.account_role == declaration.adjustment_role:
            if declaration.amount_basis == "net_before_fiscal":
                amount = source.amount + fiscal_line.amount
            else:
                amount = source.amount - fiscal_line.amount
                if amount <= Decimal("0"):
                    raise ValueError(
                        "gross fiscal composition must leave adjusted line amount > 0"
                    )
        composed_lines.append(
            FiscalizedProposalLine(
                account_role=source.account_role,
                side=source.side,
                amount=amount,
            )
        )

    composed_lines.append(
        FiscalizedProposalLine(
            account_role=fiscal_line.account_role,
            side=fiscal_line.side,
            amount=fiscal_line.amount,
        )
    )

    return FiscalizedAccountingProposal(
        declaration=declaration,
        lines=tuple(composed_lines),
        explanation=_explanation_for(declaration),
    )


__all__ = [
    "FiscalizedProposalLine",
    "FiscalizedAccountingProposal",
    "compose_fiscal_economic_accounting",
]
