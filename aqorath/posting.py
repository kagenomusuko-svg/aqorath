"""Pure posting-instruction boundary — Phase 2C.4.

Transforms an already-confirmed immutable snapshot into an immutable posting
instruction. This module deliberately does NOT persist, open sessions, resolve
accounts, or construct JournalEntry/JournalLine objects.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Tuple

from . import confirmation as _confirmation
from .account_balance import _exact_decimal_sum, ledger_signed_balance


__all__ = [
    "PostingLine",
    "PostingInstruction",
    "create_posting_instruction",
]


@dataclass(frozen=True)
class PostingLine:
    """One immutable debit/credit line ready for a later persistence adapter."""

    account_role: str
    account_id: int
    account_code: str
    account_name: str
    debit: Decimal
    credit: Decimal


@dataclass(frozen=True)
class PostingInstruction:
    """Immutable, balanced instruction derived only from confirmed content."""

    lines: Tuple[PostingLine, ...]
    description: str


def create_posting_instruction(confirmed_proposal):
    """Create an exact balanced posting instruction from a ConfirmedProposal."""
    if not isinstance(confirmed_proposal, _confirmation.ConfirmedProposal):
        raise TypeError("create_posting_instruction requires ConfirmedProposal")

    snapshot = confirmed_proposal.snapshot
    posting_lines = []

    for line in snapshot.lines:
        amount = line.amount

        if not isinstance(amount, Decimal):
            raise TypeError("posting amounts must be Decimal")
        if not amount.is_finite():
            raise ValueError("posting amounts must be finite Decimal values")
        if amount <= Decimal("0"):
            raise ValueError("posting amounts must be greater than zero")

        if line.account_id is None:
            raise ValueError("posting line requires a concrete account_id")
        if not isinstance(line.account_code, str) or not line.account_code:
            raise ValueError("posting line requires a concrete account_code")

        if line.side == "debit":
            debit = amount
            credit = Decimal("0")
        elif line.side == "credit":
            debit = Decimal("0")
            credit = amount
        else:
            raise ValueError(f"invalid posting side: {line.side!r}")

        posting_lines.append(
            PostingLine(
                account_role=line.account_role,
                account_id=line.account_id,
                account_code=line.account_code,
                account_name=line.account_name,
                debit=debit,
                credit=credit,
            )
        )

    if not posting_lines:
        raise ValueError("posting instruction requires at least one line")

    lines = tuple(posting_lines)
    total_debit = _exact_decimal_sum([line.debit for line in lines])
    total_credit = _exact_decimal_sum([line.credit for line in lines])

    if ledger_signed_balance(total_debit, total_credit) != Decimal("0"):
        raise ValueError(
            f"posting instruction is unbalanced: debit={total_debit} credit={total_credit}"
        )

    return PostingInstruction(
        lines=lines,
        description=snapshot.explanation,
    )
