"""Fiscalized posting-instruction boundary — Phase 5Z.2.

Transforms one explicitly confirmed fiscalized accounting snapshot into an immutable
posting instruction without re-resolving, recalculating, reconfirming, opening a
session, or persisting.

A confirmed zero fiscal line requires an explicit caller policy. If omission is
chosen, only the already-confirmed final fiscal zero may be omitted, and an
immutable value copy remains attached to the instruction for auditability.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Tuple

from . import fiscalized_confirmation as _confirmation


_ALLOWED_ZERO_POLICIES = (
    "reject_zero_fiscal_line",
    "omit_confirmed_zero_fiscal_line",
)


@dataclass(frozen=True)
class FiscalizedPostingLine:
    """One immutable positive debit/credit line ready for persistence execution."""

    account_role: str
    account_id: int
    account_code: str
    account_name: str
    debit: Decimal
    credit: Decimal

    def __post_init__(self):
        if not isinstance(self.account_role, str) or not self.account_role.strip():
            raise ValueError("account_role must be non-empty text")
        if not isinstance(self.account_id, int) or isinstance(self.account_id, bool):
            raise TypeError("account_id must be an integer")
        if not isinstance(self.account_code, str) or not self.account_code.strip():
            raise ValueError("account_code must be non-empty text")
        if not isinstance(self.account_name, str) or not self.account_name.strip():
            raise ValueError("account_name must be non-empty text")

        for name in ("debit", "credit"):
            value = getattr(self, name)
            if not isinstance(value, Decimal):
                raise TypeError(f"{name} must be Decimal")
            if not value.is_finite() or value < Decimal("0"):
                raise ValueError(f"{name} must be finite and non-negative")

        if not ((self.debit > Decimal("0")) ^ (self.credit > Decimal("0"))):
            raise ValueError(
                "each posting line must contain exactly one positive debit or credit"
            )


def _copy_confirmation_line(line):
    return _confirmation.FiscalizedConfirmationLine(
        account_role=line.account_role,
        account_id=line.account_id,
        account_code=line.account_code,
        account_name=line.account_name,
        side=line.side,
        amount=line.amount,
    )


def _posting_line_from_confirmation(line):
    if not isinstance(line.amount, Decimal):
        raise TypeError("confirmed posting amount must be Decimal")
    if not line.amount.is_finite():
        raise ValueError("confirmed posting amount must be finite")
    if line.amount <= Decimal("0"):
        raise ValueError("posting line amount must be greater than zero")

    if line.side == "debit":
        debit = line.amount
        credit = Decimal("0")
    elif line.side == "credit":
        debit = Decimal("0")
        credit = line.amount
    else:
        raise ValueError(f"invalid confirmed posting side: {line.side!r}")

    return FiscalizedPostingLine(
        account_role=line.account_role,
        account_id=line.account_id,
        account_code=line.account_code,
        account_name=line.account_name,
        debit=debit,
        credit=credit,
    )


def _same_decimal(left, right):
    return isinstance(left, Decimal) and isinstance(right, Decimal) and (
        left.as_tuple() == right.as_tuple()
    )


def _posting_line_matches_source(posting_line, source_line):
    if (
        posting_line.account_role != source_line.account_role
        or posting_line.account_id != source_line.account_id
        or posting_line.account_code != source_line.account_code
        or posting_line.account_name != source_line.account_name
    ):
        return False

    if source_line.side == "debit":
        return _same_decimal(posting_line.debit, source_line.amount) and (
            posting_line.credit == Decimal("0")
        )
    if source_line.side == "credit":
        return (posting_line.debit == Decimal("0")) and _same_decimal(
            posting_line.credit,
            source_line.amount,
        )
    return False


def _confirmation_lines_equal(left, right):
    return (
        isinstance(left, _confirmation.FiscalizedConfirmationLine)
        and isinstance(right, _confirmation.FiscalizedConfirmationLine)
        and left.account_role == right.account_role
        and left.account_id == right.account_id
        and left.account_code == right.account_code
        and left.account_name == right.account_name
        and left.side == right.side
        and _same_decimal(left.amount, right.amount)
    )


@dataclass(frozen=True)
class FiscalizedPostingInstruction:
    """Immutable instruction derived exactly from one confirmed fiscalized snapshot."""

    confirmed_proposal: _confirmation.ConfirmedFiscalizedProposal
    lines: Tuple[FiscalizedPostingLine, ...]
    description: str
    zero_fiscal_line_policy: str
    omitted_zero_fiscal_line: Optional[_confirmation.FiscalizedConfirmationLine]

    def __post_init__(self):
        if not isinstance(
            self.confirmed_proposal,
            _confirmation.ConfirmedFiscalizedProposal,
        ):
            raise TypeError(
                "confirmed_proposal must be ConfirmedFiscalizedProposal"
            )
        if self.zero_fiscal_line_policy not in _ALLOWED_ZERO_POLICIES:
            raise ValueError("invalid zero fiscal line policy")
        if not isinstance(self.lines, tuple) or not self.lines:
            raise ValueError("lines must be a non-empty tuple")
        if not all(isinstance(line, FiscalizedPostingLine) for line in self.lines):
            raise TypeError("all lines must be FiscalizedPostingLine")

        snapshot = self.confirmed_proposal.snapshot
        if self.description != snapshot.explanation:
            raise ValueError("description must equal confirmed snapshot explanation")

        source_lines = snapshot.lines
        final_fiscal_line = source_lines[-1]
        non_fiscal_zero_lines = tuple(
            line for line in source_lines[:-1] if line.amount == Decimal("0")
        )
        if non_fiscal_zero_lines:
            raise ValueError("non-fiscal zero lines cannot be omitted or posted")

        fiscal_is_zero = final_fiscal_line.amount == Decimal("0")
        if (
            fiscal_is_zero
            and self.zero_fiscal_line_policy == "reject_zero_fiscal_line"
        ):
            raise ValueError("zero fiscal line rejected by explicit policy")

        if (
            fiscal_is_zero
            and self.zero_fiscal_line_policy == "omit_confirmed_zero_fiscal_line"
        ):
            expected_sources = source_lines[:-1]
            if self.omitted_zero_fiscal_line is None:
                raise ValueError("omitted confirmed zero fiscal line audit copy required")
            if not _confirmation_lines_equal(
                self.omitted_zero_fiscal_line,
                final_fiscal_line,
            ):
                raise ValueError(
                    "omitted zero fiscal line must equal confirmed final fiscal line"
                )
        else:
            expected_sources = source_lines
            if self.omitted_zero_fiscal_line is not None:
                raise ValueError(
                    "omitted zero fiscal line metadata is invalid when nothing is omitted"
                )

        if len(self.lines) != len(expected_sources):
            raise ValueError("posting lines do not match confirmed snapshot cardinality")

        for posting_line, source_line in zip(self.lines, expected_sources):
            if not _posting_line_matches_source(posting_line, source_line):
                raise ValueError(
                    "posting lines must preserve exact confirmed values and order"
                )

        total_debit = sum((line.debit for line in self.lines), Decimal("0"))
        total_credit = sum((line.credit for line in self.lines), Decimal("0"))
        if total_debit != total_credit:
            raise ValueError(
                "fiscalized posting instruction must remain balanced: "
                f"debit={total_debit} credit={total_credit}"
            )


def create_fiscalized_posting_instruction(
    confirmed_proposal,
    zero_fiscal_line_policy,
):
    """Create one immutable posting instruction from exact confirmed fiscalized truth."""
    if not isinstance(
        confirmed_proposal,
        _confirmation.ConfirmedFiscalizedProposal,
    ):
        raise TypeError(
            "create_fiscalized_posting_instruction requires "
            "ConfirmedFiscalizedProposal"
        )
    if zero_fiscal_line_policy not in _ALLOWED_ZERO_POLICIES:
        raise ValueError("invalid zero fiscal line policy")

    snapshot = confirmed_proposal.snapshot
    final_fiscal_line = snapshot.lines[-1]

    for line in snapshot.lines[:-1]:
        if line.amount == Decimal("0"):
            raise ValueError("non-fiscal zero line cannot be posted or omitted")

    fiscal_is_zero = final_fiscal_line.amount == Decimal("0")
    if fiscal_is_zero and zero_fiscal_line_policy == "reject_zero_fiscal_line":
        raise ValueError("zero fiscal line rejected by explicit policy")

    if fiscal_is_zero:
        source_lines = snapshot.lines[:-1]
        omitted_zero_fiscal_line = _copy_confirmation_line(final_fiscal_line)
    else:
        source_lines = snapshot.lines
        omitted_zero_fiscal_line = None

    lines = tuple(
        _posting_line_from_confirmation(line)
        for line in source_lines
    )

    return FiscalizedPostingInstruction(
        confirmed_proposal=confirmed_proposal,
        lines=lines,
        description=snapshot.explanation,
        zero_fiscal_line_policy=zero_fiscal_line_policy,
        omitted_zero_fiscal_line=omitted_zero_fiscal_line,
    )


__all__ = [
    "FiscalizedPostingLine",
    "FiscalizedPostingInstruction",
    "create_fiscalized_posting_instruction",
]
