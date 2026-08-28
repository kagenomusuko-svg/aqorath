"""Pure fail-closed adapter from EconomicEvent to legacy EconomicFact."""

from .economic_event import EconomicEvent
from . import economic_facts as _economic_facts


def economic_fact_from_event(event):
    """Adapt one explicit EconomicEvent to the narrower legacy EconomicFact."""
    if not isinstance(event, EconomicEvent):
        raise TypeError("event must be EconomicEvent")
    if "payment_method" not in event.context:
        raise ValueError("event context must include payment_method")

    return _economic_facts.EconomicFact(
        type=event.event_type,
        amount=event.amount,
        payment_method=event.context["payment_method"],
    )
