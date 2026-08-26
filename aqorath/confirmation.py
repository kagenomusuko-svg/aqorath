"""Confirmation boundary — Phase 2C.2.

Creates an immutable snapshot from a resolved accounting proposal and represents
the explicit in-memory act of confirming that exact snapshot.

This module is deliberately pre-posting:
- no database/session access;
- no account lookup or re-resolution;
- no JournalEntry/JournalLine construction;
- no persistence or posting.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Tuple

from . import account_resolution as _account_resolution


__all__ = [
    "ConfirmationLine",
    "ConfirmationSnapshot",
    "ConfirmedProposal",
    "create_confirmation_snapshot",
    "confirm_snapshot",
]


@dataclass(frozen=True)
class ConfirmationLine:
    """Immutable value copy of one resolved accounting line."""

    account_role: str
    account_id: int
    account_code: str
    account_name: str
    side: str
    amount: Decimal


@dataclass(frozen=True)
class ConfirmationSnapshot:
    """Deeply immutable snapshot of the proposal presented for confirmation."""

    lines: Tuple[ConfirmationLine, ...]
    explanation: str


@dataclass(frozen=True)
class ConfirmedProposal:
    """Represents explicit confirmation of one exact immutable snapshot."""

    snapshot: ConfirmationSnapshot


def create_confirmation_snapshot(resolved_proposal):
    """Copy a resolved proposal into a deeply immutable confirmation snapshot."""
    if not isinstance(
        resolved_proposal,
        _account_resolution.ResolvedAccountingProposal,
    ):
        raise TypeError(
            "create_confirmation_snapshot requires ResolvedAccountingProposal"
        )

    lines = tuple(
        ConfirmationLine(
            account_role=line.account_role,
            account_id=line.account_id,
            account_code=line.account_code,
            account_name=line.account_name,
            side=line.side,
            amount=line.amount,
        )
        for line in resolved_proposal.lines
    )

    return ConfirmationSnapshot(
        lines=lines,
        explanation=resolved_proposal.explanation,
    )


def confirm_snapshot(snapshot):
    """Confirm exactly one ConfirmationSnapshot without re-resolution or posting."""
    if not isinstance(snapshot, ConfirmationSnapshot):
        raise TypeError("confirm_snapshot requires ConfirmationSnapshot")

    return ConfirmedProposal(snapshot=snapshot)
