"""Aqorath Economic Fact Application Layer.

Supported sale verticals:
- cash sale: debit ``cash``, credit ``sales_revenue``;
- credit sale: debit ``accounts_receivable``, credit ``sales_revenue``.

This module is pure domain logic: no catalog, storage, SQLite, posting, or external
services. It describes WHAT happened using semantic account roles only.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import List


@dataclass(frozen=True)
class EconomicFact:
    """Structured economic fact, not an accounting entry."""

    type: str
    amount: Decimal
    payment_method: str

    def __post_init__(self):
        if self.type != "sale":
            raise ValueError(
                f"type must be 'sale'. Got: {self.type}"
            )

        if not isinstance(self.amount, Decimal):
            raise TypeError(
                f"amount must be Decimal (exact monetary authority). "
                f"Got: {type(self.amount).__name__}."
            )

        if self.amount <= 0:
            raise ValueError(
                f"amount must be > 0 (positive transaction). Got: {self.amount}"
            )

        if self.payment_method not in ("cash", "credit"):
            raise ValueError(
                "payment_method must be 'cash' or 'credit'. "
                f"Got: {self.payment_method}"
            )

    def __init__(self, type: str, amount, payment_method: str):
        if isinstance(amount, float):
            raise TypeError(
                "amount must be Decimal, not float. "
                "Float is not the monetary authority; use Decimal explicitly."
            )

        object.__setattr__(self, "type", type)
        object.__setattr__(self, "amount", amount)
        object.__setattr__(self, "payment_method", payment_method)
        self.__post_init__()


@dataclass(frozen=True)
class ProposalLine:
    """Semantic double-entry line before concrete account resolution."""

    account_role: str
    side: str
    amount: Decimal

    def __post_init__(self):
        if self.side not in ("debit", "credit"):
            raise ValueError(
                f"side must be 'debit' or 'credit'. Got: {self.side}"
            )
        if not isinstance(self.amount, Decimal):
            raise TypeError(
                f"amount must be Decimal. Got: {type(self.amount).__name__}"
            )
        if self.amount <= 0:
            raise ValueError(f"amount must be > 0. Got: {self.amount}")


@dataclass(frozen=True)
class AccountingProposal:
    """Balanced in-memory semantic proposal; never a persisted journal entry."""

    lines: List[ProposalLine]
    explanation: str

    def __post_init__(self):
        if not isinstance(self.lines, (list, tuple)):
            raise TypeError(
                f"lines must be list or tuple. Got: {type(self.lines).__name__}"
            )
        if len(self.lines) != 2:
            raise ValueError(
                f"Sale proposals must have exactly 2 entries. Got {len(self.lines)}"
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
                "Proposal must be balanced. "
                f"total_debit={total_debit}, total_credit={total_credit}"
            )

        if not isinstance(self.explanation, str):
            raise TypeError(
                f"explanation must be str. Got: {type(self.explanation).__name__}"
            )
        if not self.explanation.strip():
            raise ValueError("explanation must not be empty")


def resolve_economic_fact(fact: EconomicFact) -> AccountingProposal:
    """Deterministically resolve a supported sale fact to semantic accounting roles."""
    if fact.type != "sale":
        raise ValueError(
            f"resolve_economic_fact only supports type='sale'. Got: {fact.type}"
        )

    if fact.payment_method == "cash":
        debit_role = "cash"
        explanation = (
            f"Sale transaction: {fact.amount} received in cash. "
            "Cash account increased (debit), sales revenue recognized (credit)."
        )
    elif fact.payment_method == "credit":
        debit_role = "accounts_receivable"
        explanation = (
            f"Sale transaction: {fact.amount} sold on credit. "
            "Accounts receivable increased (debit), sales revenue recognized (credit)."
        )
    else:
        raise ValueError(
            "resolve_economic_fact only supports payment_method='cash' or 'credit'. "
            f"Got: {fact.payment_method}"
        )

    debit_line = ProposalLine(
        account_role=debit_role,
        side="debit",
        amount=fact.amount,
    )
    sales_credit = ProposalLine(
        account_role="sales_revenue",
        side="credit",
        amount=fact.amount,
    )

    return AccountingProposal(
        lines=[debit_line, sales_credit],
        explanation=explanation,
    )
