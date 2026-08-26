"""
Aqorath Application Boundary

Canonical application layer providing interface-agnostic facade over aqorath.core
and aqorath.economic_facts.

This module is the sole entry point for all adapters (web, desktop, CLI, etc).
It delegates all business logic to specialized authorities:
  - Template-based entries: aqorath.core
  - Economic fact resolution: aqorath.economic_facts
It contains no accounting rules, no persistence logic, no framework dependencies.

Public API:
  - list_templates(): enumerate available contable templates
  - preview_template(template_key, amount, ctx=None): preview template without persistence
  - post_template(first, amount=None, ctx=None, user=None): persist via core authority
  - get_trial_balance(as_of=None): query consolidated balances
  - preview_economic_fact(fact): resolve an EconomicFact to accounting proposal

Template and trial-balance methods delegate to aqorath.core.
Economic fact preview delegates to aqorath.economic_facts.
All methods return results unmodified.
"""

from . import core as _core
from . import economic_facts as _economic_facts


def list_templates():
    """
    Enumerate available contable templates.

    Returns:
        List[str]: Template identifiers available in the accounting system.
    """
    return _core.list_templates()


def preview_template(template_key, amount, ctx=None):
    """
    Preview a template accounting entry without persistence.

    Args:
        template_key (str): Template identifier
        amount (float | Decimal): Entry amount
        ctx (Dict[str, Any], optional): Template context/parameters. Default: None.

    Returns:
        Dict[str, Any]: Preview result containing computed entries and balances.
    """
    return _core.generate_preview(template_key, amount, ctx=ctx)


def post_template(first, amount=None, ctx=None, user=None):
    """
    Persist an accounting entry via the canonical SQLite authority.

    Args:
        first: Template key or full entry definition
        amount (float | None, optional): Entry amount. Default: None.
        ctx (Dict[str, Any], optional): Template context/parameters. Default: None.
        user (str, optional): User identifier for audit. Default: None.

    Returns:
        Any: Result of persistence operation (entry ID, confirmation, etc).
    """
    return _core.post_entry(first, amount=amount, ctx=ctx, user=user)


def get_trial_balance(as_of=None):
    """
    Query consolidated trial balance from SQLite authority.

    Args:
        as_of (str, optional): Date string for historical balance. Default: None (current).

    Returns:
        Dict[str, Decimal]: Trial balance with account codes as keys and Decimal amounts as values.
    """
    return _core.trial_balance(as_of=as_of)


def preview_economic_fact(fact):
    """
    Resolve an economic fact to an accounting proposal.

    Delegates to the economic facts domain resolver. Receives a structured EconomicFact
    and returns an AccountingProposal in memory without persistence.

    Args:
        fact (EconomicFact): Structured economic fact (type, amount, payment_method).

    Returns:
        AccountingProposal: In-memory proposal with lines and explanation, unmodified
                           from domain resolver.
    """
    return _economic_facts.resolve_economic_fact(fact)
