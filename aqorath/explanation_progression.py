"""Pure explicit progression of locally presented explanation concepts."""

from dataclasses import replace

from .explanation_presentation import ExplanationPresentationPlan
from .user_knowledge_state import UserKnowledgeState


def record_presented_concepts(user_state, presentation_plan):
    """Return state with concepts actually presented appended exactly once."""
    if not isinstance(user_state, UserKnowledgeState):
        raise TypeError("user_state must be UserKnowledgeState")
    if not isinstance(presentation_plan, ExplanationPresentationPlan):
        raise TypeError("presentation_plan must be ExplanationPresentationPlan")

    existing = set(user_state.concepts_seen)
    additions = tuple(
        concept
        for concept in presentation_plan.concepts_to_present
        if concept not in existing
    )
    if not additions:
        return user_state

    return replace(
        user_state,
        concepts_seen=user_state.concepts_seen + additions,
    )
