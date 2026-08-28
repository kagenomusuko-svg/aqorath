"""Pure explanation delivery assembly from existing authorities."""

from dataclasses import dataclass

from . import economic_fact_accounting_provenance as _accounting_provenance
from . import explanation as _explanation
from . import explanation_presentation as _explanation_presentation
from . import explanation_request as _explanation_request
from . import explanation_view as _explanation_view
from .user_knowledge_state import UserKnowledgeState


@dataclass(frozen=True)
class PreparedExplanationPresentation:
    """Immutable explanation, directives, and selected view prepared together."""

    explanation: _explanation.ExplanationData
    presentation_plan: _explanation_presentation.ExplanationPresentationPlan
    presentation_view: _explanation_view.ExplanationPresentationView


def _prepare(accounting_resolution, user_state, planner):
    if not isinstance(
        accounting_resolution,
        _accounting_provenance.EconomicFactAccountingResolution,
    ):
        raise TypeError(
            "accounting_resolution must be EconomicFactAccountingResolution"
        )
    if not isinstance(user_state, UserKnowledgeState):
        raise TypeError("user_state must be UserKnowledgeState")

    explanation = _explanation.build_economic_fact_explanation(accounting_resolution)
    presentation_plan = planner(explanation, user_state)
    presentation_view = _explanation_view.build_explanation_presentation_view(
        explanation,
        presentation_plan,
    )
    return PreparedExplanationPresentation(
        explanation=explanation,
        presentation_plan=presentation_plan,
        presentation_view=presentation_view,
    )


def prepare_explanation_presentation(accounting_resolution, user_state):
    """Prepare adaptive explanation artifacts from one existing resolution."""
    return _prepare(
        accounting_resolution,
        user_state,
        _explanation_presentation.plan_explanation_presentation,
    )


def prepare_requested_explanation_presentation(accounting_resolution, user_state):
    """Prepare explicitly requested explanation artifacts from one resolution."""
    return _prepare(
        accounting_resolution,
        user_state,
        _explanation_request.plan_requested_explanation,
    )
