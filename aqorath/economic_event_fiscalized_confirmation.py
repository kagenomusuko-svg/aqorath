"""Prepare informed fiscalized confirmation content from one EconomicEvent."""

from . import economic_event_fiscalized_account_resolution as _event_resolution
from . import fiscalized_confirmation as _confirmation


def prepare_fiscalized_economic_event_confirmation(
    session,
    event,
    fiscal_effect,
    amount_basis,
    adjustment_role,
    account_bindings,
):
    """Resolve event accounts, then prepare the exact confirmation snapshot."""
    resolved_proposal = _event_resolution.resolve_fiscalized_economic_event_accounts(
        session,
        event,
        fiscal_effect,
        amount_basis,
        adjustment_role,
        account_bindings,
    )
    return _confirmation.create_fiscalized_confirmation_snapshot(resolved_proposal)
