"""Pure EconomicEvent entrypoint into existing fiscalized accounting composition."""

from . import economic_event_fiscal_composition as _event_fiscal_composition
from . import fiscalized_accounting_proposal as _fiscalized


def compose_fiscal_economic_accounting_from_event(
    event,
    fiscal_effect,
    amount_basis,
    adjustment_role,
):
    """Declare explicit event/fiscal composition, then materialize it."""
    declaration = (
        _event_fiscal_composition.declare_fiscal_economic_composition_from_event(
            event,
            fiscal_effect,
            amount_basis,
            adjustment_role,
        )
    )
    return _fiscalized.compose_fiscal_economic_accounting(declaration)
