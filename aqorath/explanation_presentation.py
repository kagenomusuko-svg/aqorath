"""Pure adaptive planning for structured explanation presentation."""

from dataclasses import dataclass

from .explanation import ExplanationData
from .user_knowledge_state import UserKnowledgeState


_EXPLANATION_LEVELS = frozenset({"none", "brief", "detailed"})


def _require_text(value, field_name):
    if type(value) is not str:
        raise TypeError(f"{field_name} must be str")
    if not value or value.strip() != value:
        raise ValueError(f"{field_name} must be nonblank without surrounding whitespace")


def _require_bool(value, field_name):
    if type(value) is not bool:
        raise TypeError(f"{field_name} must be bool")


@dataclass(frozen=True)
class ExplanationPresentationPlan:
    """Immutable directives for presenting already-structured explanation truth."""

    explanation_level: str
    show_common_explanation: bool
    show_structured_effects: bool
    concepts_to_present: tuple[str, ...]
    show_professional_view: bool

    def __post_init__(self):
        if type(self.explanation_level) is not str:
            raise TypeError("explanation_level must be str")
        if self.explanation_level not in _EXPLANATION_LEVELS:
            raise ValueError("explanation_level must be one of: none, brief, detailed")

        _require_bool(self.show_common_explanation, "show_common_explanation")
        _require_bool(self.show_structured_effects, "show_structured_effects")
        _require_bool(self.show_professional_view, "show_professional_view")

        if type(self.concepts_to_present) is not tuple:
            raise TypeError("concepts_to_present must be tuple")
        seen = set()
        for concept in self.concepts_to_present:
            _require_text(concept, "concept")
            if concept in seen:
                raise ValueError("concepts_to_present must be unique")
            seen.add(concept)


def plan_explanation_presentation(explanation, user_state):
    """Return deterministic directives from explanation truth and explicit preferences."""
    if not isinstance(explanation, ExplanationData):
        raise TypeError("explanation must be ExplanationData")
    if not isinstance(user_state, UserKnowledgeState):
        raise TypeError("user_state must be UserKnowledgeState")

    level = user_state.explanation_level
    show_common = level in {"brief", "detailed"}
    show_structured = level == "detailed"

    if level == "none":
        concepts = ()
    else:
        concepts_seen = set(user_state.concepts_seen)
        concepts = tuple(
            concept for concept in explanation.concepts if concept not in concepts_seen
        )

    return ExplanationPresentationPlan(
        explanation_level=level,
        show_common_explanation=show_common,
        show_structured_effects=show_structured,
        concepts_to_present=concepts,
        show_professional_view=user_state.always_show_professional_view,
    )
