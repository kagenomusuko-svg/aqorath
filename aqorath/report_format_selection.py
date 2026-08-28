"""Pure selection of one explicit report-format capability."""

from .user_knowledge_state import UserKnowledgeState


def _validate_available_formats(available_formats):
    if type(available_formats) is not tuple:
        raise TypeError("available_formats must be tuple")
    if not available_formats:
        raise ValueError("available_formats must not be empty")

    seen = set()
    for value in available_formats:
        if type(value) is not str:
            raise TypeError("available format must be str")
        if not value or value.strip() != value:
            raise ValueError(
                "available format must be nonblank without surrounding whitespace"
            )
        if value in seen:
            raise ValueError("available_formats must be unique")
        seen.add(value)


def select_preferred_report_format(user_state, available_formats):
    """Return the exact available capability matching the explicit preference."""
    if not isinstance(user_state, UserKnowledgeState):
        raise TypeError("user_state must be UserKnowledgeState")

    _validate_available_formats(available_formats)

    preferred = user_state.preferred_report_format
    for capability in available_formats:
        if capability == preferred:
            return capability

    raise ValueError("preferred report format is not available")
