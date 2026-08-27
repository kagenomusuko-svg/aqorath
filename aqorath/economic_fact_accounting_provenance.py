"""Economic-fact accounting provenance boundary.

Links one nominal EconomicFact to the exact AccountingProposal returned by the
existing deterministic economic-fact resolver. The link preserves both objects
by identity so later composition layers can distinguish the proposal's origin
from independently supplied accounting content.

This boundary does not infer fiscal treatment, resolve concrete accounts,
confirm, compose, persist, or post.
"""

from dataclasses import dataclass

from . import economic_facts as _economic_facts


@dataclass(frozen=True, init=False)
class EconomicFactAccountingResolution:
    """Unforgeable public provenance link created only by the canonical factory."""

    fact: _economic_facts.EconomicFact
    proposal: _economic_facts.AccountingProposal

    def __init__(self, *args, **kwargs):
        raise TypeError(
            "EconomicFactAccountingResolution must be created by "
            "resolve_economic_fact_with_provenance"
        )

    @classmethod
    def _create(cls, fact, proposal):
        instance = object.__new__(cls)
        object.__setattr__(instance, "fact", fact)
        object.__setattr__(instance, "proposal", proposal)
        return instance


def resolve_economic_fact_with_provenance(fact):
    """Resolve one economic fact once and preserve exact fact/proposal provenance."""
    if not isinstance(fact, _economic_facts.EconomicFact):
        raise TypeError(
            "resolve_economic_fact_with_provenance requires EconomicFact"
        )

    proposal = _economic_facts.resolve_economic_fact(fact)
    if not isinstance(proposal, _economic_facts.AccountingProposal):
        raise TypeError(
            "economic fact resolver must return AccountingProposal"
        )

    return EconomicFactAccountingResolution._create(fact, proposal)


__all__ = [
    "EconomicFactAccountingResolution",
    "resolve_economic_fact_with_provenance",
]
