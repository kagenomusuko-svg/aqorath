"""AQR-004 unified Application use case.

The module composes existing authorities in one stable chain:

    economic fact -> accounting decision -> consent -> posting -> audit

It intentionally contains no debit/credit rules, account-code selection, period
arithmetic, fiscal calculation or SQLModel persistence rules.  Ordinary operations
use configured account bindings and the canonical posting staging authority.
Fiscalized confirmed truth is delegated unchanged to the existing fiscalized
posting + fiscal-audit authority.
"""

from . import account_bindings as _account_bindings
from . import account_resolution as _account_resolution
from . import accounting_decision as _decision
from . import accounting_operation_persistence as _persistence
from . import audit_event_repository as _audit_repository
from . import confirmation as _confirmation
from . import economic_fact_accounting_provenance as _provenance
from . import economic_facts as _economic_facts
from . import explanation as _explanation
from . import fiscalized_confirmation as _fiscalized_confirmation
from . import fiscalized_posting as _fiscalized_posting
from . import fiscalized_posting_persistence as _fiscalized_persistence
from . import posting as _posting


def _prepare_accounting_operation_with_binding_overrides(
    session,
    fact,
    posting_date,
    binding_overrides,
):
    """Prepare through the canonical chain while refining explicit semantic roles.

    Product compositions may already own a concrete resource identity (for example,
    a selected BankAccount).  This helper keeps account resolution before consent
    and lets that composition refine only the corresponding semantic role without
    creating a second accounting or posting authority.
    """
    if not isinstance(fact, _economic_facts.EconomicFact):
        raise TypeError("fact must be EconomicFact")
    if not isinstance(binding_overrides, dict):
        raise TypeError("binding_overrides must be dict")

    accounting_resolution = _provenance.resolve_economic_fact_with_provenance(fact)
    roles = tuple(line.account_role for line in accounting_resolution.proposal.lines)
    unexpected = set(binding_overrides) - set(roles)
    if unexpected:
        raise ValueError(
            "binding override does not belong to the economic fact: "
            + ", ".join(sorted(unexpected))
        )
    bindings = _account_bindings.get_account_bindings(session, roles)
    bindings.update(binding_overrides)
    resolved_proposal = _account_resolution.resolve_proposal_accounts(
        session,
        accounting_resolution.proposal,
        bindings,
    )
    explanation = _explanation.build_economic_fact_explanation(accounting_resolution)
    snapshot = _confirmation.create_confirmation_snapshot(resolved_proposal)

    return _decision.AccountingDecision(
        fact=fact,
        posting_date=posting_date,
        accounting_resolution=accounting_resolution,
        resolved_proposal=resolved_proposal,
        explanation=explanation,
        confirmation_snapshot=snapshot,
    )


def prepare_accounting_operation(session, fact, posting_date):
    """Prepare one ordinary fact without asking presentation for accounting internals."""
    return _prepare_accounting_operation_with_binding_overrides(
        session,
        fact,
        posting_date,
        {},
    )


def confirm_accounting_operation(decision):
    """Record explicit consent to exactly one prepared accounting decision."""
    if not isinstance(decision, _decision.AccountingDecision):
        raise TypeError("decision must be AccountingDecision")
    confirmed = _confirmation.confirm_snapshot(decision.confirmation_snapshot)
    return _decision.ConfirmedAccountingDecision(
        decision=decision,
        confirmed_proposal=confirmed,
    )


def execute_accounting_operation(confirmed_decision):
    """Post and audit one explicitly confirmed ordinary decision atomically."""
    if not isinstance(
        confirmed_decision,
        _decision.ConfirmedAccountingDecision,
    ):
        raise TypeError("confirmed_decision must be ConfirmedAccountingDecision")
    instruction = _posting.create_posting_instruction(
        confirmed_decision.confirmed_proposal
    )
    return _persistence.execute_posting_with_audit(
        instruction,
        confirmed_decision,
    )


def load_accounting_operation_audit(session, entity_id, entry_id):
    """Recover the unique general posting evidence for one ledger entry."""
    if type(entry_id) is not int or entry_id <= 0:
        raise ValueError("entry_id must be a positive integer")
    matches = tuple(
        event
        for event in _audit_repository.list_audit_events(session, entity_id)
        if event.event_type == "entry_posted"
        and event.details.get("entry_id") == entry_id
    )
    if not matches:
        raise LookupError("accounting operation audit not found")
    if len(matches) != 1:
        raise RuntimeError("multiple accounting operation audit events for entry")
    return matches[0]


def execute_fiscalized_accounting_operation(
    confirmed_proposal,
    zero_fiscal_line_policy,
):
    """Delegate confirmed fiscalized truth to the existing fiscal posting authority.

    Fiscal applicability/rule selection remains owned by the existing fiscal chain
    and by the later declared V1 coverage task; AQR-004 does not invent a rule from
    an ordinary fact.  Once fiscalized truth has been explicitly confirmed, this
    function provides the same application-use-case execution boundary without
    duplicating posting or fiscal audit persistence.
    """
    if not isinstance(
        confirmed_proposal,
        _fiscalized_confirmation.ConfirmedFiscalizedProposal,
    ):
        raise TypeError(
            "confirmed_proposal must be ConfirmedFiscalizedProposal"
        )
    instruction = _fiscalized_posting.create_fiscalized_posting_instruction(
        confirmed_proposal,
        zero_fiscal_line_policy,
    )
    return _fiscalized_persistence.execute_fiscalized_posting_with_audit(
        instruction
    )


__all__ = [
    "prepare_accounting_operation",
    "confirm_accounting_operation",
    "execute_accounting_operation",
    "load_accounting_operation_audit",
    "execute_fiscalized_accounting_operation",
]
