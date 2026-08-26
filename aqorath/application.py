"""
Aqorath Application Boundary

Canonical interface-agnostic facade. Adapters call this module; accounting,
resolution, confirmation, binding and persistence rules remain in their specialized
authorities.

Public API includes the legacy template/trial-balance facade plus the economic-fact flow:
  - preview_economic_fact(fact)
  - prepare_economic_fact_confirmation(session, fact, account_bindings)
  - prepare_configured_economic_fact_confirmation(session, fact)
  - set_account_binding(session, role, account_code)
  - get_account_binding(session, role)
  - confirm_economic_fact(snapshot)
  - post_confirmed_economic_fact(confirmed_proposal)
"""

from . import core as _core
from . import economic_facts as _economic_facts
from . import account_resolution as _account_resolution
from . import account_bindings as _account_bindings
from . import confirmation as _confirmation
from . import posting as _posting
from . import posting_execution as _posting_execution


def list_templates():
    """Enumerate available contable templates."""
    return _core.list_templates()


def preview_template(template_key, amount, ctx=None):
    """Preview a template accounting entry without persistence."""
    return _core.generate_preview(template_key, amount, ctx=ctx)


def post_template(first, amount=None, ctx=None, user=None):
    """Persist a template/full entry through the canonical core authority."""
    return _core.post_entry(first, amount=amount, ctx=ctx, user=user)


def get_trial_balance(as_of=None):
    """Query the consolidated trial balance from the canonical SQLite authority."""
    return _core.trial_balance(as_of=as_of)


def preview_economic_fact(fact):
    """Resolve a structured EconomicFact to a semantic AccountingProposal."""
    return _economic_facts.resolve_economic_fact(fact)


def set_account_binding(session, role, account_code):
    """Persist or replace one semantic role binding using the supplied session."""
    return _account_bindings.set_account_binding(session, role, account_code)


def get_account_binding(session, role):
    """Return the configured concrete account code for one semantic role."""
    return _account_bindings.get_account_binding(session, role)


def prepare_economic_fact_confirmation(session, fact, account_bindings):
    """Resolve an economic fact through explicit concrete-account bindings."""
    proposal = _economic_facts.resolve_economic_fact(fact)
    resolved = _account_resolution.resolve_proposal_accounts(
        session,
        proposal,
        account_bindings,
    )
    return _confirmation.create_confirmation_snapshot(resolved)


def prepare_configured_economic_fact_confirmation(session, fact):
    """Resolve an economic fact using persistent SQLite account-role bindings."""
    proposal = _economic_facts.resolve_economic_fact(fact)
    roles = tuple(line.account_role for line in proposal.lines)
    account_bindings = _account_bindings.get_account_bindings(session, roles)
    resolved = _account_resolution.resolve_proposal_accounts(
        session,
        proposal,
        account_bindings,
    )
    return _confirmation.create_confirmation_snapshot(resolved)


def confirm_economic_fact(snapshot):
    """Record the explicit in-memory confirmation of exactly one snapshot."""
    return _confirmation.confirm_snapshot(snapshot)


def post_confirmed_economic_fact(confirmed_proposal):
    """Build and execute posting only from a previously confirmed proposal."""
    instruction = _posting.create_posting_instruction(confirmed_proposal)
    return _posting_execution.execute_posting_instruction(instruction)
