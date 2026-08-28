"""Persistence authority for the local singleton knowledge/preference state."""

from dataclasses import replace
from datetime import datetime
import json

from sqlmodel import select

from .models import UserKnowledgeStateRecord
from .user_knowledge_state import LearnedTopic, UserKnowledgeState


__all__ = [
    "create_user_knowledge_state",
    "get_user_knowledge_state",
    "update_user_knowledge_state",
]


def _dump_concepts(concepts):
    return json.dumps(
        list(concepts),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _dump_topics(topics):
    return json.dumps(
        [
            {"topic": item.topic, "learned_at": item.learned_at.isoformat()}
            for item in topics
        ],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _load_concepts(payload):
    values = json.loads(payload)
    if type(values) is not list:
        raise ValueError("concepts_seen_json must contain a JSON array")
    return tuple(values)


def _load_topics(payload):
    values = json.loads(payload)
    if type(values) is not list:
        raise ValueError("learned_topics_json must contain a JSON array")

    topics = []
    for item in values:
        if type(item) is not dict or set(item.keys()) != {"topic", "learned_at"}:
            raise ValueError("learned topic JSON must contain exact topic/timestamp fields")
        raw_time = item["learned_at"]
        if type(raw_time) is not str:
            raise TypeError("learned topic timestamp must be text")
        topics.append(
            LearnedTopic(
                topic=item["topic"],
                learned_at=datetime.fromisoformat(raw_time),
            )
        )
    return tuple(topics)


def _to_domain(record):
    return UserKnowledgeState(
        id=record.id,
        explanation_level=record.explanation_level,
        concepts_seen=_load_concepts(record.concepts_seen_json),
        ui_language=record.ui_language,
        decimal_separator=record.decimal_separator,
        currency_symbol=record.currency_symbol,
        preferred_report_format=record.preferred_report_format,
        always_show_professional_view=record.always_show_professional_view,
        learned_topics=_load_topics(record.learned_topics_json),
    )


def _require_nominal_state(state):
    if not isinstance(state, UserKnowledgeState):
        raise TypeError("state must be a UserKnowledgeState")


def create_user_knowledge_state(session, state):
    """Persist the one local owner's explicit state with singleton identity 1."""
    _require_nominal_state(state)
    if state.id is not None:
        raise ValueError("new user knowledge state must not already have an identity")

    existing = session.exec(select(UserKnowledgeStateRecord)).all()
    if existing:
        raise ValueError("user knowledge state already exists")

    record = UserKnowledgeStateRecord(
        id=1,
        explanation_level=state.explanation_level,
        concepts_seen_json=_dump_concepts(state.concepts_seen),
        ui_language=state.ui_language,
        decimal_separator=state.decimal_separator,
        currency_symbol=state.currency_symbol,
        preferred_report_format=state.preferred_report_format,
        always_show_professional_view=state.always_show_professional_view,
        learned_topics_json=_dump_topics(state.learned_topics),
    )
    try:
        session.add(record)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return replace(state, id=1)


def get_user_knowledge_state(session):
    """Load the singleton state, returning None only before first explicit setup."""
    records = session.exec(select(UserKnowledgeStateRecord)).all()
    if not records:
        return None
    if len(records) != 1:
        raise LookupError("ambiguous user knowledge state")
    return _to_domain(records[0])


def update_user_knowledge_state(session, state):
    """Replace the explicit singleton preference/learning truth in one commit."""
    _require_nominal_state(state)
    if type(state.id) is not int or state.id != 1:
        raise ValueError("persisted user knowledge state must have singleton identity 1")

    record = session.get(UserKnowledgeStateRecord, 1)
    if record is None:
        raise LookupError("user knowledge state does not exist")

    record.explanation_level = state.explanation_level
    record.concepts_seen_json = _dump_concepts(state.concepts_seen)
    record.ui_language = state.ui_language
    record.decimal_separator = state.decimal_separator
    record.currency_symbol = state.currency_symbol
    record.preferred_report_format = state.preferred_report_format
    record.always_show_professional_view = state.always_show_professional_view
    record.learned_topics_json = _dump_topics(state.learned_topics)

    try:
        session.add(record)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return state
