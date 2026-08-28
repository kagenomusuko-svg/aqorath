"""Pure composition from EconomicEvent through existing accounting provenance."""

from . import economic_event_fact_adapter as _event_adapter
from . import economic_fact_accounting_provenance as _provenance


def resolve_economic_event_with_provenance(event):
    """Resolve one event through the frozen adapter and provenance authority."""
    fact = _event_adapter.economic_fact_from_event(event)
    return _provenance.resolve_economic_fact_with_provenance(fact)
