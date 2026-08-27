"""Pure composition of one explicit fiscal/economic declaration.

Creates a new immutable semantic accounting proposal from the exact economic
proposal and all confirmed fiscal effects already bound by the composition
declaration. No concrete accounts are resolved and no confirmation, persistence,
or posting occurs here.
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


def _fiscal_delta(declaration):
    debit = sum(
        (
            effect.line.amount
            for effect in declaration.fiscal_effects
            if effect.line.side == "debit"
        ),
        Decimal("0"),
    )
    credit = sum(
        (
            effect.line.amount
            for effect in declaration.fiscal_effects
            if effect.line.side == "credit"
        ),
        Decimal("0"),
    )
    return credit - debit


def _adjusted_amount(source, declaration):
    if source.account_role != declaration.adjustment_role:
        return source.amount

    delta = _fiscal_delta(declaration)
    if source.side == "debit":
        result = source.amount + delta
    else:
        result = source.amount - delta

    if result < Decimal("0"):
        raise ValueError("fiscal composition cannot make an accounting line negative")
    if declaration.amount_basis == "gross_including_fiscal" and result <= Decimal("0"):
        raise ValueError(
            "gross fiscal composition must leave adjusted line amount > 0"
        )
    return result


def _explanation_for(declaration):
    effects = declaration.fiscal_effects
    if len(effects) == 1:
        fiscal_line = effects[0].line
        return (
            "Fiscalized accounting composition: "
            f"amount_basis={declaration.amount_basis}; "
            f"adjustment_role={declaration.adjustment_role}; "
            f"fiscal_role={fiscal_line.account_role}; "
            f"fiscal_side={fiscal_line.side}; "
            f"fiscal_amount={fiscal_line.amount}."
        )

    rendered = ", ".join(
        f"{effect.line.account_role}|{effect.line.side}|{effect.line.amount}"
        for effect in effects
    )
    return (
        "Fiscalized accounting composition: "
        f"amount_basis={declaration.amount_basis}; "
        f"adjustment_role={declaration.adjustment_role}; "
        f"fiscal_effects=[{rendered}]."
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
        effects = self.declaration.fiscal_effects
        if len(self.lines) != len(source_lines) + len(effects):
            raise ValueError(
                "fiscalized proposal must preserve source lines and append every fiscal line"
            )

        for index, source in enumerate(source_lines):
            result = self.lines[index]
            expected_amount = _adjusted_amount(source, self.declaration)
            if result.account_role != source.account_role:
                raise ValueError("source account_role order must be preserved")
            if result.side != source.side:
                raise ValueError("source line side must be preserved")
            if result.amount.as_tuple() != expected_amount.as_tuple():
                raise ValueError(
                    "source line amount does not match declared fiscal composition"
                )

        appended = self.lines[len(source_lines):]
        for result, effect in zip(appended, effects):
            fiscal_line = effect.line
            if result.account_role != fiscal_line.account_role:
                raise ValueError("appended fiscal account_role must match fiscal effect")
            if result.side != fiscal_line.side:
                raise ValueError("appended fiscal side must match fiscal effect")
            if result.amount.as_tuple() != fiscal_line.amount.as_tuple():
                raise ValueError(
                    "appended fiscal amount must match fiscal effect exactly"
                )

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
            raise ValueError(
                "explanation must describe the exact declared composition"
            )


def compose_fiscal_economic_accounting(declaration):
    """Materialize one explicit declaration as a balanced semantic proposal."""
    if not isinstance(declaration, _composition.FiscalEconomicCompositionDeclaration):
        raise TypeError(
            "compose_fiscal_economic_accounting requires "
            "FiscalEconomicCompositionDeclaration"
        )

    composed_lines = []
    for source in declaration.accounting_resolution.proposal.lines:
        composed_lines.append(
            FiscalizedProposalLine(
                account_role=source.account_role,
                side=source.side,
                amount=_adjusted_amount(source, declaration),
            )
        )

    for effect in declaration.fiscal_effects:
        fiscal_line = effect.line
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
