"""Pure one-shot planning for an explicitly requested detailed explanation."""

from dataclasses import replace

from .explanation import ExplanationData
from .explanation_presentation import plan_explanation_presentation
from .user_knowledge_state import UserKnowledgeState


def plan_requested_explanation(explanation, user_state):
    """Return a detailed presentation plan without changing persisted preference."""
    if not isinstance(explanation, ExplanationData):
        raise TypeError("explanation must be ExplanationData")
    if not isinstance(user_state, UserKnowledgeState):
        raise TypeError("user_state must be UserKnowledgeState")

    requested_state = replace(user_state, explanation_level="detailed")
    return plan_explanation_presentation(explanation, requested_state)
