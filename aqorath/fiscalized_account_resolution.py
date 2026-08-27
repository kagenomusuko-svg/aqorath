"""Concrete account resolution for fiscalized semantic accounting proposals.

This module is a distinct nominal boundary from the historical two-line account
resolution flow. It resolves every semantic role in one FiscalizedAccountingProposal
through caller-supplied bindings and the canonical catalog, while preserving the
exact fiscalized proposal provenance, line order, Decimal amounts, and explicit
zero fiscal lines.

It does not load persistent bindings, confirm, persist, or post.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Tuple

from . import catalog as _catalog
from . import fiscalized_accounting_proposal as _fiscalized


@dataclass(frozen=True)
class ResolvedFiscalizedProposalLine:
    account_role: str
    account_id: int
    account_code: str
    account_name: str
    side: str
    amount: Decimal

    def __post_init__(self):
        if not isinstance(self.account_role, str):
            raise TypeError("account_role must be a string")
        if not self.account_role.strip():
            raise ValueError("account_role must not be empty")
        if not isinstance(self.account_id, int) or isinstance(self.account_id, bool):
            raise TypeError("account_id must be an integer")
        if not isinstance(self.account_code, str):
            raise TypeError("account_code must be a string")
        if not self.account_code.strip():
            raise ValueError("account_code must not be empty")
        if not isinstance(self.account_name, str):
            raise TypeError("account_name must be a string")
        if not self.account_name.strip():
            raise ValueError("account_name must not be empty")
        if self.side not in ("debit", "credit"):
            raise ValueError("side must be 'debit' or 'credit'")
        if not isinstance(self.amount, Decimal):
            raise TypeError("amount must be Decimal")
        if not self.amount.is_finite():
            raise ValueError("amount must be finite")
        if self.amount < Decimal("0"):
            raise ValueError("amount must not be negative")


@dataclass(frozen=True)
class ResolvedFiscalizedAccountingProposal:
    fiscalized_proposal: _fiscalized.FiscalizedAccountingProposal
    lines: Tuple[ResolvedFiscalizedProposalLine, ...]
    explanation: str

    def __post_init__(self):
        if not isinstance(
            self.fiscalized_proposal,
            _fiscalized.FiscalizedAccountingProposal,
        ):
            raise TypeError(
                "fiscalized_proposal must be FiscalizedAccountingProposal"
            )
        if not isinstance(self.lines, tuple):
            raise TypeError("lines must be a tuple")
        if not all(
            isinstance(line, ResolvedFiscalizedProposalLine)
            for line in self.lines
        ):
            raise TypeError("all lines must be ResolvedFiscalizedProposalLine")

        source_lines = self.fiscalized_proposal.lines
        if len(self.lines) != len(source_lines):
            raise ValueError("resolved lines must preserve fiscalized line count")

        for source, resolved in zip(source_lines, self.lines):
            if resolved.account_role != source.account_role:
                raise ValueError("resolved account_role order must match source")
            if resolved.side != source.side:
                raise ValueError("resolved side must match source")
            if resolved.amount.as_tuple() != source.amount.as_tuple():
                raise ValueError("resolved amount must match source exactly")

        if self.explanation != self.fiscalized_proposal.explanation:
            raise ValueError("explanation must match fiscalized proposal exactly")


def _validate_binding_code(role, code):
    if not isinstance(code, str):
        raise TypeError(f"account binding for role '{role}' must be a string")
    if not code or code.strip() != code:
        raise ValueError(
            f"account binding for role '{role}' must be non-empty and contain no surrounding whitespace"
        )


def _validated_account(account, bound_code, role):
    if account is None:
        raise ValueError(
            f"Account '{bound_code}' configured for role '{role}' does not exist"
        )

    account_id = getattr(account, "id", None)
    account_code = getattr(account, "code", None)
    account_name = getattr(account, "name", None)

    if not isinstance(account_id, int) or isinstance(account_id, bool):
        raise ValueError(
            f"Account '{bound_code}' configured for role '{role}' has no valid persistent id"
        )
    if account_code != bound_code:
        raise ValueError(
            f"Catalog returned account code '{account_code}' for bound code '{bound_code}'"
        )
    if not isinstance(account_name, str) or not account_name.strip():
        raise ValueError(
            f"Account '{bound_code}' configured for role '{role}' has no valid name"
        )

    return account_id, account_code, account_name


def resolve_fiscalized_proposal_accounts(
    session,
    fiscalized_proposal,
    account_bindings,
):
    """Resolve every fiscalized semantic line to one concrete catalog account."""
    if not isinstance(
        fiscalized_proposal,
        _fiscalized.FiscalizedAccountingProposal,
    ):
        raise TypeError(
            "resolve_fiscalized_proposal_accounts requires FiscalizedAccountingProposal"
        )
    if not isinstance(account_bindings, Mapping):
        raise TypeError("account_bindings must be a mapping of role to account code")

    resolved_lines = []
    for line in fiscalized_proposal.lines:
        role = line.account_role
        if role not in account_bindings:
            raise ValueError(f"No account binding configured for role '{role}'")

        bound_code = account_bindings[role]
        _validate_binding_code(role, bound_code)
        account = _catalog.resolve_account_by_code(session, bound_code)
        account_id, account_code, account_name = _validated_account(
            account,
            bound_code,
            role,
        )

        resolved_lines.append(
            ResolvedFiscalizedProposalLine(
                account_role=role,
                account_id=account_id,
                account_code=account_code,
                account_name=account_name,
                side=line.side,
                amount=line.amount,
            )
        )

    return ResolvedFiscalizedAccountingProposal(
        fiscalized_proposal=fiscalized_proposal,
        lines=tuple(resolved_lines),
        explanation=fiscalized_proposal.explanation,
    )


__all__ = [
    "ResolvedFiscalizedProposalLine",
    "ResolvedFiscalizedAccountingProposal",
    "resolve_fiscalized_proposal_accounts",
]
