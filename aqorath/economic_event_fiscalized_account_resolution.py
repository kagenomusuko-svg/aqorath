"""Compose EconomicEvent fiscalized accounting with concrete account resolution."""

from . import economic_event_fiscalized_accounting as _event_fiscalized
from . import fiscalized_account_resolution as _account_resolution


def resolve_fiscalized_economic_event_accounts(
    session,
    event,
    fiscal_effect,
    amount_basis,
    adjustment_role,
    account_bindings,
):
    """Compose fiscalized event accounting, then resolve caller-supplied accounts."""
    fiscalized_proposal = (
        _event_fiscalized.compose_fiscal_economic_accounting_from_event(
            event,
            fiscal_effect,
            amount_basis,
            adjustment_role,
        )
    )
    return _account_resolution.resolve_fiscalized_proposal_accounts(
        session,
        fiscalized_proposal,
        account_bindings,
    )
