"""Pure adaptive directives for structured deterministic explanations."""

from dataclasses import dataclass

from .explanation import ExplanationData
from .user_knowledge_state import UserKnowledgeState


_LEVELS = frozenset({"none", "brief", "detailed"})


def _require_text(value, field_name):
    if type(value) is not str:
        raise TypeError(f"{field_name} must be str")
    if not value or value.strip() != value:
        raise ValueError(f"{field_name} must be nonblank without surrounding whitespace")
    return value


@dataclass(frozen=True)
class ExplanationPresentationPlan:
    """Immutable directives describing which explanation layers are due."""

    explanation_level: str
    show_common_explanation: bool
    show_structured_effects: bool
    concepts_to_present: tuple[str, ...]
    show_professional_view: bool

    def __post_init__(self):
        if type(self.explanation_level) is not str:
            raise TypeError("explanation_level must be str")
        if self.explanation_level not in _LEVELS:
            raise ValueError("explanation_level must be exactly none, brief, or detailed")

        for field_name, value in (
            ("show_common_explanation", self.show_common_explanation),
            ("show_structured_effects", self.show_structured_effects),
            ("show_professional_view", self.show_professional_view),
        ):
            if type(value) is not bool:
                raise TypeError(f"{field_name} must be bool")

        if type(self.concepts_to_present) is not tuple:
            raise TypeError("concepts_to_present must be tuple")
        for concept in self.concepts_to_present:
            _require_text(concept, "concept")
        if len(set(self.concepts_to_present)) != len(self.concepts_to_present):
            raise ValueError("concepts_to_present must be unique")


def plan_explanation_presentation(explanation, user_state):
    """Derive deterministic presentation directives from two explicit value inputs."""
    if not isinstance(explanation, ExplanationData):
        raise TypeError("explanation must be ExplanationData")
    if not isinstance(user_state, UserKnowledgeState):
        raise TypeError("user_state must be UserKnowledgeState")

    level = user_state.explanation_level
    show_common = level != "none"
    show_effects = level == "detailed"

    if level == "none":
        concepts = ()
    else:
        seen = frozenset(user_state.concepts_seen)
        concepts = tuple(
            concept
            for concept in explanation.concepts
            if concept not in seen
        )

    return ExplanationPresentationPlan(
        explanation_level=level,
        show_common_explanation=show_common,
        show_structured_effects=show_effects,
        concepts_to_present=concepts,
        show_professional_view=user_state.always_show_professional_view,
    )
