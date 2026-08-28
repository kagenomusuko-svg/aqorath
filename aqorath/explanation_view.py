"""Pure structured selection of explanation fields for a presentation plan."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from .explanation import ExplanationData, ExplanationEffect
from .explanation_presentation import ExplanationPresentationPlan


@dataclass(frozen=True)
class ExplanationPresentationView:
    """Immutable selected explanation fields for an interface boundary."""

    fact_type: Optional[str]
    payment_method: Optional[str]
    amount: Optional[Decimal]
    effects: tuple[ExplanationEffect, ...]
    concepts: tuple[str, ...]
    professional_summary: Optional[str]


def build_explanation_presentation_view(explanation, presentation_plan):
    """Select authoritative explanation fields according to supplied directives."""
    if not isinstance(explanation, ExplanationData):
        raise TypeError("explanation must be ExplanationData")
    if not isinstance(presentation_plan, ExplanationPresentationPlan):
        raise TypeError("presentation_plan must be ExplanationPresentationPlan")

    if any(
        concept not in explanation.concepts
        for concept in presentation_plan.concepts_to_present
    ):
        raise ValueError("presentation_plan concepts must exist in explanation")

    show_common = presentation_plan.show_common_explanation
    return ExplanationPresentationView(
        fact_type=explanation.fact_type if show_common else None,
        payment_method=explanation.payment_method if show_common else None,
        amount=explanation.amount if show_common else None,
        effects=(
            explanation.effects
            if presentation_plan.show_structured_effects
            else ()
        ),
        concepts=presentation_plan.concepts_to_present,
        professional_summary=(
            explanation.professional_summary
            if presentation_plan.show_professional_view
            else None
        ),
    )
