"""Aqorath Economic Fact Application Layer.

Supported deterministic verticals:
- cash sale: debit ``cash``, credit ``sales_revenue``;
- credit sale: debit ``accounts_receivable``, credit ``sales_revenue``;
- utility expense paid by bank: debit ``utilities_expense``, credit ``bank``;
- utility expense incurred on credit: debit ``utilities_expense``, credit ``accounts_payable``;
- receivable collection by bank: debit ``bank``, credit ``accounts_receivable``;
- supplier payment by bank: debit ``accounts_payable``, credit ``bank``.

This module is pure domain logic: no catalog, storage, SQLite, journal execution, or external
services. It describes WHAT happened using semantic account roles only.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import List

from .account_balance import _exact_decimal_sum, ledger_signed_balance


@dataclass(frozen=True)
class EconomicFact:
    """Structured economic fact, not an accounting entry."""

    type: str
    amount: Decimal
    payment_method: str

    def __post_init__(self):
        valid_payment_methods = {
            "donation": ("bank",),
            "sale": ("cash", "credit"),
            "utility_expense": ("bank",),
            "utility_expense_incurred": ("credit",),
            "receivable_collection": ("bank",),
            "supplier_payment": ("bank",),
        }

        if self.type not in valid_payment_methods:
            raise ValueError(
                "type must be one of: 'sale', 'utility_expense', "
                "'utility_expense_incurred', 'receivable_collection', "
                "'supplier_payment'. "
                f"Got: {self.type}"
            )

        if not isinstance(self.amount, Decimal):
            raise TypeError(
                f"amount must be Decimal (exact monetary authority). "
                f"Got: {type(self.amount).__name__}."
            )
        if not self.amount.is_finite():
            raise ValueError("amount must be finite")

        if self.amount <= 0:
            raise ValueError(
                f"amount must be > 0 (positive transaction). Got: {self.amount}"
            )

        allowed = valid_payment_methods[self.type]
        if self.payment_method not in allowed:
            allowed_text = ", ".join(repr(value) for value in allowed)
            raise ValueError(
                f"payment_method for type={self.type!r} must be one of: "
                f"{allowed_text}. Got: {self.payment_method}"
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
        if not self.amount.is_finite():
            raise ValueError("amount must be finite")
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
                f"Supported proposals must have exactly 2 entries. Got {len(self.lines)}"
            )

        total_debit = _exact_decimal_sum(
            [line.amount for line in self.lines if line.side == "debit"]
        )
        total_credit = _exact_decimal_sum(
            [line.amount for line in self.lines if line.side == "credit"]
        )
        if ledger_signed_balance(total_debit, total_credit) != Decimal("0"):
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
    """Deterministically resolve a supported fact to semantic accounting roles."""
    if fact.type == "donation" and fact.payment_method == "bank":
        debit_role = "bank"
        credit_role = "donation_income"
        explanation = (
            f"Monetary donation: {fact.amount} received in bank. "
            "Bank resource increased and donation income recognized."
        )
    elif fact.type == "sale" and fact.payment_method == "cash":
        debit_role = "cash"
        credit_role = "sales_revenue"
        explanation = (
            f"Sale transaction: {fact.amount} received in cash. "
            "Cash account increased (debit), sales revenue recognized (credit)."
        )
    elif fact.type == "sale" and fact.payment_method == "credit":
        debit_role = "accounts_receivable"
        credit_role = "sales_revenue"
        explanation = (
            f"Sale transaction: {fact.amount} sold on credit. "
            "Accounts receivable increased (debit), sales revenue recognized (credit)."
        )
    elif fact.type == "utility_expense" and fact.payment_method == "bank":
        debit_role = "utilities_expense"
        credit_role = "bank"
        explanation = (
            f"Utility expense: {fact.amount} paid from bank. "
            "Utilities expense recognized (debit), bank balance decreased (credit)."
        )
    elif fact.type == "utility_expense_incurred" and fact.payment_method == "credit":
        debit_role = "utilities_expense"
        credit_role = "accounts_payable"
        explanation = (
            f"Utility expense: {fact.amount} incurred on credit. "
            "Utilities expense recognized (debit), accounts payable obligation increased (credit)."
        )
    elif fact.type == "receivable_collection" and fact.payment_method == "bank":
        debit_role = "bank"
        credit_role = "accounts_receivable"
        explanation = (
            f"Receivable collection: {fact.amount} collected into bank. "
            "Bank balance increased (debit), accounts receivable decreased (credit)."
        )
    elif fact.type == "supplier_payment" and fact.payment_method == "bank":
        debit_role = "accounts_payable"
        credit_role = "bank"
        explanation = (
            f"Supplier payment: {fact.amount} paid from bank. "
            "Accounts payable obligation decreased (debit), bank balance decreased (credit)."
        )
    else:
        raise ValueError(
            f"Unsupported economic fact combination: type={fact.type!r}, "
            f"payment_method={fact.payment_method!r}"
        )

    debit_line = ProposalLine(
        account_role=debit_role,
        side="debit",
        amount=fact.amount,
    )
    credit_line = ProposalLine(
        account_role=credit_role,
        side="credit",
        amount=fact.amount,
    )

    return AccountingProposal(
        lines=[debit_line, credit_line],
        explanation=explanation,
    )
