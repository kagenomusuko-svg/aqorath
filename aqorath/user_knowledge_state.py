"""Local monouser pedagogical and presentation preference truth — Phase 6R.2."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


_EXPLANATION_LEVELS = frozenset({"none", "brief", "detailed"})


def _require_explicit_text(name, value):
    if type(value) is not str or not value or value.strip() != value:
        raise ValueError(
            f"{name} must be a non-empty string without surrounding whitespace"
        )


@dataclass(frozen=True)
class LearnedTopic:
    """One explicitly learned topic at one explicitly supplied timestamp."""

    topic: str
    learned_at: datetime

    def __post_init__(self):
        _require_explicit_text("topic", self.topic)
        if type(self.learned_at) is not datetime:
            raise TypeError("learned_at must be an exact datetime")


@dataclass(frozen=True)
class UserKnowledgeState:
    """One local owner's explicit pedagogical and presentation preference state."""

    id: Optional[int]
    explanation_level: str
    concepts_seen: tuple
    ui_language: str
    decimal_separator: str
    currency_symbol: str
    preferred_report_format: str
    always_show_professional_view: bool
    learned_topics: tuple

    def __post_init__(self):
        if self.id is not None and (type(self.id) is not int or self.id != 1):
            raise ValueError("id must be None before persistence or exact singleton identity 1")

        if (
            type(self.explanation_level) is not str
            or self.explanation_level not in _EXPLANATION_LEVELS
        ):
            raise ValueError("explanation_level must be one of: none, brief, detailed")

        if type(self.concepts_seen) is not tuple:
            raise TypeError("concepts_seen must be an immutable tuple")
        seen = set()
        for concept in self.concepts_seen:
            _require_explicit_text("concepts_seen item", concept)
            if concept in seen:
                raise ValueError("concepts_seen cannot contain duplicates")
            seen.add(concept)

        _require_explicit_text("ui_language", self.ui_language)
        if self.decimal_separator not in (".", ",") or type(self.decimal_separator) is not str:
            raise ValueError("decimal_separator must be exactly '.' or ','")
        _require_explicit_text("currency_symbol", self.currency_symbol)
        _require_explicit_text("preferred_report_format", self.preferred_report_format)

        if type(self.always_show_professional_view) is not bool:
            raise TypeError("always_show_professional_view must be an exact bool")

        if type(self.learned_topics) is not tuple:
            raise TypeError("learned_topics must be an immutable tuple")
        learned_names = set()
        for learned in self.learned_topics:
            if not isinstance(learned, LearnedTopic):
                raise TypeError("learned_topics must contain only LearnedTopic values")
            if learned.topic in learned_names:
                raise ValueError("learned_topics cannot contain duplicate topics")
            learned_names.add(learned.topic)
