"""Immutable application values for one prepared/confirmed accounting operation.

AQR-004 does not create a second accounting authority.  These values only preserve
provenance between the existing fact resolver, account resolver, explanation,
confirmation and posting authorities so the presentation layer can treat them as
one use case.
"""

from dataclasses import dataclass
from datetime import date

from . import account_resolution as _account_resolution
from . import confirmation as _confirmation
from . import economic_fact_accounting_provenance as _provenance
from . import economic_facts as _economic_facts
from . import explanation as _explanation


ECONOMIC_FACT_RULE_VERSION = "economic-fact-v1"


def _same_resolved_line(left, right):
    return (
        left.account_role == right.account_role
        and left.account_id == right.account_id
        and left.account_code == right.account_code
        and left.account_name == right.account_name
        and left.side == right.side
        and left.amount == right.amount
    )


@dataclass(frozen=True)
class AccountingDecision:
    """One prepared accounting decision before explicit user consent.

    ``fact`` remains the user's economic truth.  ``accounting_resolution`` and
    ``resolved_proposal`` are the existing deterministic authorities' outputs;
    this object does not calculate accounts or accounting semantics itself.
    """

    fact: _economic_facts.EconomicFact
    posting_date: date
    accounting_resolution: _provenance.EconomicFactAccountingResolution
    resolved_proposal: _account_resolution.ResolvedAccountingProposal
    explanation: _explanation.ExplanationData
    confirmation_snapshot: _confirmation.ConfirmationSnapshot
    rule_version: str = ECONOMIC_FACT_RULE_VERSION

    def __post_init__(self):
        if not isinstance(self.fact, _economic_facts.EconomicFact):
            raise TypeError("fact must be EconomicFact")
        if type(self.posting_date) is not date:
            raise TypeError("posting_date must be date")
        if not isinstance(
            self.accounting_resolution,
            _provenance.EconomicFactAccountingResolution,
        ):
            raise TypeError(
                "accounting_resolution must be EconomicFactAccountingResolution"
            )
        if self.accounting_resolution.fact is not self.fact:
            raise ValueError("accounting resolution must preserve exact fact provenance")
        if not isinstance(
            self.resolved_proposal,
            _account_resolution.ResolvedAccountingProposal,
        ):
            raise TypeError("resolved_proposal must be ResolvedAccountingProposal")
        if not isinstance(self.explanation, _explanation.ExplanationData):
            raise TypeError("explanation must be ExplanationData")
        if not isinstance(
            self.confirmation_snapshot,
            _confirmation.ConfirmationSnapshot,
        ):
            raise TypeError("confirmation_snapshot must be ConfirmationSnapshot")
        if type(self.rule_version) is not str or not self.rule_version:
            raise ValueError("rule_version must be nonblank text")

        semantic = self.accounting_resolution.proposal.lines
        resolved = self.resolved_proposal.lines
        snapshot = self.confirmation_snapshot.lines
        if len(semantic) != len(resolved) or len(resolved) != len(snapshot):
            raise ValueError("decision line cardinality must remain unchanged")

        for semantic_line, resolved_line, snapshot_line in zip(
            semantic,
            resolved,
            snapshot,
        ):
            if (
                semantic_line.account_role != resolved_line.account_role
                or semantic_line.side != resolved_line.side
                or semantic_line.amount != resolved_line.amount
            ):
                raise ValueError("resolved proposal changed semantic accounting truth")
            if not _same_resolved_line(resolved_line, snapshot_line):
                raise ValueError("confirmation snapshot changed resolved accounting truth")

        if (
            self.explanation.fact_type != self.fact.type
            or self.explanation.payment_method != self.fact.payment_method
            or self.explanation.amount != self.fact.amount
        ):
            raise ValueError("explanation must derive from the same economic fact")

    @property
    def rule_id(self):
        return self.explanation.rule_key


@dataclass(frozen=True)
class ConfirmedAccountingDecision:
    """Explicit consent to exactly one previously prepared decision."""

    decision: AccountingDecision
    confirmed_proposal: _confirmation.ConfirmedProposal

    def __post_init__(self):
        if not isinstance(self.decision, AccountingDecision):
            raise TypeError("decision must be AccountingDecision")
        if not isinstance(self.confirmed_proposal, _confirmation.ConfirmedProposal):
            raise TypeError("confirmed_proposal must be ConfirmedProposal")
        if self.confirmed_proposal.snapshot != self.decision.confirmation_snapshot:
            raise ValueError("confirmation must refer to the exact prepared snapshot")


@dataclass(frozen=True)
class AccountingOperationResult:
    """Recoverable identity of one atomically posted and audited decision."""

    entry_id: int
    audit_event_id: int
    state: str = "posted"

    def __post_init__(self):
        for name in ("entry_id", "audit_event_id"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if self.state != "posted":
            raise ValueError("completed accounting operation state must be posted")


__all__ = [
    "ECONOMIC_FACT_RULE_VERSION",
    "AccountingDecision",
    "ConfirmedAccountingDecision",
    "AccountingOperationResult",
]
