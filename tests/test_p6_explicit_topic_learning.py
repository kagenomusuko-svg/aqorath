"""Phase 6V.1 — frozen explicit topic-learning acknowledgement contracts.

Constitution anchors:
- R8 keeps pedagogical state local to the one installation owner.
- R12 requires explanation behavior to remain under explicit user control.
- R13 permits local learning history so pedagogy can progress without inference.

Phase 6U records only what Aqorath actually presented. Presentation is not evidence that
something was learned. 6V freezes the separate explicit acknowledgement boundary: a
caller may record one topic as learned at one caller-supplied timestamp. This phase must
not infer learning from presentation, usage, explanation level, elapsed time, or AI.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
import importlib
import inspect

import pytest


def _module():
    return importlib.import_module("aqorath.topic_learning")


def _state(*, concepts_seen=("economic_fact",), learned_topics=()):
    from aqorath.user_knowledge_state import UserKnowledgeState

    return UserKnowledgeState(
        id=1,
        explanation_level="brief",
        concepts_seen=concepts_seen,
        ui_language="es-MX",
        decimal_separator=".",
        currency_symbol="MX$",
        preferred_report_format="xlsx",
        always_show_professional_view=False,
        learned_topics=learned_topics,
    )


def _learned(topic="economic_fact", when=None):
    from aqorath.user_knowledge_state import LearnedTopic

    if when is None:
        when = datetime(2026, 8, 27, 18, 0, tzinfo=timezone.utc)
    return LearnedTopic(topic=topic, learned_at=when)


def test_topic_learning_public_contract_is_exact_pure_and_local_state_only():
    module = _module()

    assert str(inspect.signature(module.record_learned_topic)) == "(user_state, topic, learned_at)"

    source = inspect.getsource(module).lower()
    for forbidden in (
        "sqlmodel",
        "sqlalchemy",
        "sqlite3",
        "requests",
        "fastapi",
        "get_session",
        "repository",
        "datetime.now",
        "datetime.utcnow",
        "time.time",
        "random",
        "openai",
        "llm",
        "journalentry",
        "journalline",
    ):
        assert forbidden not in source


def test_topic_learning_requires_nominal_user_knowledge_state():
    module = _module()
    learned_at = datetime(2026, 8, 27, 19, 0, tzinfo=timezone.utc)

    for invalid in (None, object(), {"learned_topics": ()}, "state"):
        with pytest.raises(TypeError):
            module.record_learned_topic(invalid, "double_entry", learned_at)


def test_topic_is_explicit_nonblank_text_without_normalization():
    module = _module()
    learned_at = datetime(2026, 8, 27, 19, 0, tzinfo=timezone.utc)

    updated = module.record_learned_topic(_state(), "double_entry", learned_at)
    assert updated.learned_topics[-1].topic == "double_entry"

    for invalid in ("", " double_entry", "double_entry ", " double_entry ", None, 1):
        with pytest.raises((TypeError, ValueError)):
            module.record_learned_topic(_state(), invalid, learned_at)


def test_learning_timestamp_must_be_explicit_exact_datetime():
    module = _module()
    state = _state()

    timestamp = datetime(2026, 8, 27, 19, 0, 1, 123456, tzinfo=timezone.utc)
    updated = module.record_learned_topic(state, "double_entry", timestamp)
    assert updated.learned_topics[-1].learned_at is timestamp

    for invalid in (None, "2026-08-27T19:00:00Z", date(2026, 8, 27), 0):
        with pytest.raises((TypeError, ValueError)):
            module.record_learned_topic(state, "double_entry", invalid)


def test_new_learning_appends_exact_value_after_existing_history():
    module = _module()
    prior = _learned("economic_fact")
    timestamp = datetime(2026, 8, 27, 20, 15, tzinfo=timezone.utc)

    updated = module.record_learned_topic(
        _state(learned_topics=(prior,)),
        "double_entry",
        timestamp,
    )

    assert tuple(item.topic for item in updated.learned_topics) == (
        "economic_fact",
        "double_entry",
    )
    assert updated.learned_topics[0] is prior
    assert updated.learned_topics[1].learned_at is timestamp


def test_learning_does_not_require_prior_presentation_or_add_concepts_seen():
    module = _module()
    state = _state(concepts_seen=("economic_fact",))
    timestamp = datetime(2026, 8, 27, 20, 30, tzinfo=timezone.utc)

    updated = module.record_learned_topic(state, "accrual", timestamp)

    assert updated.concepts_seen == ("economic_fact",)
    assert updated.concepts_seen is state.concepts_seen
    assert updated.learned_topics[-1].topic == "accrual"


def test_exact_repeat_is_idempotent_and_preserves_original_object():
    module = _module()
    timestamp = datetime(2026, 8, 27, 21, 0, tzinfo=timezone.utc)
    state = _state(learned_topics=(_learned("double_entry", timestamp),))

    repeated = module.record_learned_topic(state, "double_entry", timestamp)

    assert repeated is state
    assert repeated.learned_topics == state.learned_topics


def test_conflicting_repeat_fails_closed_instead_of_rewriting_learning_history():
    module = _module()
    original_time = datetime(2026, 8, 27, 21, 0, tzinfo=timezone.utc)
    conflicting_time = datetime(2026, 8, 27, 22, 0, tzinfo=timezone.utc)
    state = _state(learned_topics=(_learned("double_entry", original_time),))

    with pytest.raises(ValueError):
        module.record_learned_topic(state, "double_entry", conflicting_time)

    assert state.learned_topics[0].learned_at is original_time


def test_existing_learning_order_is_never_sorted_rewritten_or_deduplicated_by_side_effect():
    module = _module()
    first = _learned(
        "cash_basis",
        datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc),
    )
    second = _learned(
        "economic_fact",
        datetime(2026, 8, 19, 10, 0, tzinfo=timezone.utc),
    )
    state = _state(learned_topics=(first, second))

    updated = module.record_learned_topic(
        state,
        "double_entry",
        datetime(2026, 8, 18, 10, 0, tzinfo=timezone.utc),
    )

    assert tuple(item.topic for item in updated.learned_topics) == (
        "cash_basis",
        "economic_fact",
        "double_entry",
    )
    assert updated.learned_topics[:2] == state.learned_topics


def test_topic_learning_preserves_every_non_learning_state_field_exactly():
    module = _module()
    state = replace(
        _state(concepts_seen=("economic_fact", "double_entry")),
        explanation_level="detailed",
        ui_language="pt-BR",
        decimal_separator=",",
        currency_symbol="R$",
        preferred_report_format="structured-json",
        always_show_professional_view=True,
    )

    updated = module.record_learned_topic(
        state,
        "accrual",
        datetime(2026, 8, 27, 23, 0, tzinfo=timezone.utc),
    )

    assert updated.id == state.id
    assert updated.explanation_level == state.explanation_level
    assert updated.concepts_seen is state.concepts_seen
    assert updated.ui_language == state.ui_language
    assert updated.decimal_separator == state.decimal_separator
    assert updated.currency_symbol == state.currency_symbol
    assert updated.preferred_report_format == state.preferred_report_format
    assert updated.always_show_professional_view is state.always_show_professional_view


def test_topic_learning_never_mutates_source_state_or_existing_learned_values():
    module = _module()
    prior = _learned("economic_fact")
    state = _state(learned_topics=(prior,))
    before_topics = state.learned_topics

    updated = module.record_learned_topic(
        state,
        "double_entry",
        datetime(2026, 8, 28, 0, 0, tzinfo=timezone.utc),
    )

    assert updated is not state
    assert state.learned_topics is before_topics
    assert state.learned_topics == (prior,)


def test_topic_learning_is_deterministic_and_uses_only_supplied_timestamp():
    module = _module()
    state = _state()
    timestamp = datetime(2026, 8, 28, 0, 15, 30, 654321, tzinfo=timezone.utc)

    first = module.record_learned_topic(state, "double_entry", timestamp)
    second = module.record_learned_topic(state, "double_entry", timestamp)

    assert first == second
    assert first.learned_topics[-1].learned_at is timestamp

    source = inspect.getsource(module).lower()
    for forbidden in ("now(", "utcnow(", "today(", "time.time", "random", "openai", "llm"):
        assert forbidden not in source


def test_topic_learning_does_not_plan_present_render_or_touch_accounting_truth():
    module = _module()
    source = inspect.getsource(module).lower()

    for forbidden in (
        "plan_explanation_presentation",
        "record_presented_concepts",
        "explanationpresentationplan",
        "build_economic_fact_explanation",
        "render",
        "professional_summary",
        "fact_type",
        "payment_method",
        "amount",
        "effects",
        "account",
        "debit",
        "credit",
        "fiscal",
        "post",
        "confirm",
    ):
        assert forbidden not in source


def test_application_exposes_exact_explicit_learning_persistence_signature():
    application = importlib.import_module("aqorath.application")

    assert hasattr(application, "record_user_topic_learning")
    assert str(inspect.signature(application.record_user_topic_learning)) == "(session, topic, learned_at)"


def test_application_loads_transitions_and_updates_singleton_with_same_session(monkeypatch):
    application = importlib.import_module("aqorath.application")
    repository = importlib.import_module("aqorath.user_knowledge_state_repository")
    learning = _module()

    session = object()
    state = _state()
    timestamp = datetime(2026, 8, 28, 0, 30, tzinfo=timezone.utc)
    transitioned = replace(
        state,
        learned_topics=(_learned("double_entry", timestamp),),
    )
    calls = []

    def fake_get(received_session):
        calls.append(("get", received_session))
        return state

    def fake_transition(received_state, received_topic, received_time):
        calls.append(("transition", received_state, received_topic, received_time))
        return transitioned

    def fake_update(received_session, received_state):
        calls.append(("update", received_session, received_state))
        return received_state

    monkeypatch.setattr(repository, "get_user_knowledge_state", fake_get)
    monkeypatch.setattr(learning, "record_learned_topic", fake_transition)
    monkeypatch.setattr(repository, "update_user_knowledge_state", fake_update)

    result = application.record_user_topic_learning(session, "double_entry", timestamp)

    assert result is transitioned
    assert calls == [
        ("get", session),
        ("transition", state, "double_entry", timestamp),
        ("update", session, transitioned),
    ]


def test_application_fails_closed_when_local_user_state_has_not_been_initialized(monkeypatch):
    application = importlib.import_module("aqorath.application")
    repository = importlib.import_module("aqorath.user_knowledge_state_repository")
    learning = _module()
    calls = []

    def fake_get(session):
        calls.append("get")
        return None

    def forbidden_transition(*args):
        raise AssertionError("learning transition must not run without state")

    def forbidden_update(*args):
        raise AssertionError("update must not run without state")

    monkeypatch.setattr(repository, "get_user_knowledge_state", fake_get)
    monkeypatch.setattr(learning, "record_learned_topic", forbidden_transition)
    monkeypatch.setattr(repository, "update_user_knowledge_state", forbidden_update)

    with pytest.raises(LookupError):
        application.record_user_topic_learning(
            object(),
            "double_entry",
            datetime(2026, 8, 28, 0, 45, tzinfo=timezone.utc),
        )
    assert calls == ["get"]


def test_application_is_thin_and_never_infers_learning_or_changes_presentation():
    application = importlib.import_module("aqorath.application")
    source = inspect.getsource(application.record_user_topic_learning).lower()

    assert "_user_knowledge_state_repository.get_user_knowledge_state" in source
    assert "_topic_learning.record_learned_topic" in source
    assert "_user_knowledge_state_repository.update_user_knowledge_state" in source

    for forbidden in (
        "datetime.now",
        "datetime.utcnow",
        "concepts_seen",
        "explanation_level",
        "plan_explanation_presentation",
        "record_explanation_presentation",
        "build_economic_fact_explanation",
        "render",
        "confirm",
        "post",
        "journal",
        "account",
        "fiscal",
        "openai",
        "llm",
    ):
        assert forbidden not in source
