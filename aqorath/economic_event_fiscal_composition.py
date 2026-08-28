"""Pure EconomicEvent entrypoint into existing fiscal/economic composition."""

from . import economic_event_accounting_resolution as _event_resolution
from . import fiscal_economic_composition as _fiscal_composition


def declare_fiscal_economic_composition_from_event(
    event,
    fiscal_effect,
    amount_basis,
    adjustment_role,
):
    """Resolve one event, then delegate explicit fiscal composition inputs."""
    accounting_resolution = _event_resolution.resolve_economic_event_with_provenance(
        event
    )
    return _fiscal_composition.declare_fiscal_economic_composition(
        accounting_resolution,
        fiscal_effect,
        amount_basis,
        adjustment_role,
    )
