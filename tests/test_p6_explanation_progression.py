"""Phase 6U.1 — frozen explicit explanation-progression contracts.

Constitution anchors:
- R8 keeps pedagogical state local to the one installation owner.
- R12 keeps explanation behavior under explicit user preference.
- R13 permits recording concepts already presented so later explanations can progress.

Phase 6T only plans presentation and deliberately does not mutate learning state. 6U
freezes the next boundary: after a presentation has actually completed, the caller may
explicitly record the plan's presented concepts. Presentation is not proof of learning,
so learned_topics remains separate and unchanged here.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import importlib
import inspect

import pytest


def _module():
    return importlib.import_module("aqorath.explanation_progression")


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


def _plan(*, concepts=("double_entry",), level="brief"):
    from aqorath.explanation_presentation import ExplanationPresentationPlan

    return ExplanationPresentationPlan(
        explanation_level=level,
        show_common_explanation=level in {"brief", "detailed"},
        show_structured_effects=level == "detailed",
        concepts_to_present=concepts,
        show_professional_view=False,
    )


def test_progression_public_contract_is_exact_pure_and_interface_agnostic():
    module = _module()

    assert str(inspect.signature(module.record_presented_concepts)) == "(user_state, presentation_plan)"

    source = inspect.getsource(module).lower()
    for forbidden in (
        "sqlmodel",
        "sqlalchemy",
        "sqlite3",
        "requests",
        "fastapi",
        "get_session",
        "datetime.now",
        "time.time",
        "random",
        "openai",
        "llm",
        "journalentry",
        "journalline",
    ):
        assert forbidden not in source


def test_progression_requires_nominal_user_knowledge_state():
    module = _module()
    plan = _plan()

    for invalid in (None, object(), {"concepts_seen": ()}, "state"):
        with pytest.raises(TypeError):
            module.record_presented_concepts(invalid, plan)


def test_progression_requires_nominal_explanation_presentation_plan():
    module = _module()
    state = _state()

    for invalid in (None, object(), {"concepts_to_present": ()}, ("double_entry",)):
        with pytest.raises(TypeError):
            module.record_presented_concepts(state, invalid)


def test_empty_presented_concepts_are_an_exact_semantic_noop():
    module = _module()
    state = _state(concepts_seen=("economic_fact", "double_entry"))

    updated = module.record_presented_concepts(state, _plan(concepts=()))

    assert updated == state
    assert updated.concepts_seen == state.concepts_seen


def test_new_presented_concepts_append_in_plan_order_after_existing_history():
    module = _module()
    state = _state(concepts_seen=("economic_fact",))
    plan = _plan(concepts=("double_entry", "accrual", "cash_basis"), level="detailed")

    updated = module.record_presented_concepts(state, plan)

    assert updated.concepts_seen == (
        "economic_fact",
        "double_entry",
        "accrual",
        "cash_basis",
    )


def test_already_seen_concepts_are_not_duplicated_and_new_ones_keep_plan_order():
    module = _module()
    state = _state(concepts_seen=("economic_fact", "accrual"))
    plan = _plan(concepts=("accrual", "double_entry", "cash_basis"))

    updated = module.record_presented_concepts(state, plan)

    assert updated.concepts_seen == (
        "economic_fact",
        "accrual",
        "double_entry",
        "cash_basis",
    )


def test_reapplying_same_presentation_is_idempotent():
    module = _module()
    plan = _plan(concepts=("double_entry", "cash_basis"))

    once = module.record_presented_concepts(_state(), plan)
    twice = module.record_presented_concepts(once, plan)

    assert twice == once
    assert twice.concepts_seen == ("economic_fact", "double_entry", "cash_basis")


def test_presented_does_not_mean_learned_and_never_creates_timestamps():
    module = _module()
    from aqorath.user_knowledge_state import LearnedTopic

    learned = LearnedTopic(
        topic="economic_fact",
        learned_at=datetime(2026, 8, 27, 18, 0, tzinfo=timezone.utc),
    )
    state = _state(learned_topics=(learned,))

    updated = module.record_presented_concepts(
        state,
        _plan(concepts=("double_entry", "cash_basis")),
    )

    assert updated.learned_topics == (learned,)
    assert updated.learned_topics is state.learned_topics
    assert all(topic.topic != "double_entry" for topic in updated.learned_topics)

    source = inspect.getsource(module).lower()
    for forbidden in ("datetime.now", "datetime.utcnow", "time.time"):
        assert forbidden not in source


def test_learned_topic_does_not_suppress_recording_a_separately_presented_concept():
    module = _module()
    from aqorath.user_knowledge_state import LearnedTopic

    learned = LearnedTopic(
        topic="double_entry",
        learned_at=datetime(2026, 8, 27, 18, 0, tzinfo=timezone.utc),
    )
    state = _state(concepts_seen=("economic_fact",), learned_topics=(learned,))

    updated = module.record_presented_concepts(state, _plan(concepts=("double_entry",)))

    assert updated.concepts_seen == ("economic_fact", "double_entry")
    assert updated.learned_topics == (learned,)


def test_progression_preserves_all_non_seen_user_state_truth_exactly():
    module = _module()
    state = replace(
        _state(),
        explanation_level="detailed",
        ui_language="pt-BR",
        decimal_separator=",",
        currency_symbol="R$",
        preferred_report_format="structured-json",
        always_show_professional_view=True,
    )

    updated = module.record_presented_concepts(state, _plan(concepts=("double_entry",)))

    assert updated.id == state.id
    assert updated.explanation_level == state.explanation_level
    assert updated.ui_language == state.ui_language
    assert updated.decimal_separator == state.decimal_separator
    assert updated.currency_symbol == state.currency_symbol
    assert updated.preferred_report_format == state.preferred_report_format
    assert updated.always_show_professional_view is state.always_show_professional_view
    assert updated.learned_topics is state.learned_topics


def test_progression_never_mutates_source_state_or_plan():
    module = _module()
    state = _state(concepts_seen=("economic_fact",))
    plan = _plan(concepts=("double_entry", "cash_basis"))
    before_seen = state.concepts_seen
    before_plan_concepts = plan.concepts_to_present

    updated = module.record_presented_concepts(state, plan)

    assert updated is not state
    assert state.concepts_seen == before_seen
    assert plan.concepts_to_present == before_plan_concepts


def test_progression_is_deterministic_and_does_not_replan_or_render():
    module = _module()
    state = _state()
    plan = _plan(concepts=("double_entry", "cash_basis"), level="detailed")

    first = module.record_presented_concepts(state, plan)
    second = module.record_presented_concepts(state, plan)
    assert first == second

    source = inspect.getsource(module).lower()
    for forbidden in (
        "plan_explanation_presentation",
        "build_economic_fact_explanation",
        "render",
        "professional_summary",
        "effects",
        "amount",
        "fact_type",
        "payment_method",
    ):
        assert forbidden not in source


def test_application_exposes_exact_explicit_persistence_use_case_signature():
    application = importlib.import_module("aqorath.application")

    assert hasattr(application, "record_explanation_presentation")
    assert str(inspect.signature(application.record_explanation_presentation)) == "(session, presentation_plan)"


def test_application_loads_transitions_and_updates_singleton_with_same_session(monkeypatch):
    application = importlib.import_module("aqorath.application")
    repository = importlib.import_module("aqorath.user_knowledge_state_repository")
    progression = _module()

    session = object()
    state = _state()
    plan = _plan(concepts=("double_entry",))
    transitioned = replace(state, concepts_seen=("economic_fact", "double_entry"))
    calls = []

    def fake_get(received_session):
        calls.append(("get", received_session))
        return state

    def fake_transition(received_state, received_plan):
        calls.append(("transition", received_state, received_plan))
        return transitioned

    def fake_update(received_session, received_state):
        calls.append(("update", received_session, received_state))
        return received_state

    monkeypatch.setattr(repository, "get_user_knowledge_state", fake_get)
    monkeypatch.setattr(progression, "record_presented_concepts", fake_transition)
    monkeypatch.setattr(repository, "update_user_knowledge_state", fake_update)

    result = application.record_explanation_presentation(session, plan)

    assert result is transitioned
    assert calls == [
        ("get", session),
        ("transition", state, plan),
        ("update", session, transitioned),
    ]


def test_application_fails_closed_when_local_user_state_has_not_been_initialized(monkeypatch):
    application = importlib.import_module("aqorath.application")
    repository = importlib.import_module("aqorath.user_knowledge_state_repository")
    progression = _module()

    calls = []

    def fake_get(session):
        calls.append("get")
        return None

    def forbidden_transition(*args):
        raise AssertionError("transition must not run without state")

    def forbidden_update(*args):
        raise AssertionError("update must not run without state")

    monkeypatch.setattr(repository, "get_user_knowledge_state", fake_get)
    monkeypatch.setattr(progression, "record_presented_concepts", forbidden_transition)
    monkeypatch.setattr(repository, "update_user_knowledge_state", forbidden_update)

    with pytest.raises(LookupError):
        application.record_explanation_presentation(object(), _plan())
    assert calls == ["get"]


def test_application_is_thin_and_does_not_plan_render_mark_learned_or_touch_accounting():
    application = importlib.import_module("aqorath.application")
    source = inspect.getsource(application.record_explanation_presentation).lower()

    assert "_user_knowledge_state_repository.get_user_knowledge_state" in source
    assert "_explanation_progression.record_presented_concepts" in source
    assert "_user_knowledge_state_repository.update_user_knowledge_state" in source

    for forbidden in (
        "plan_explanation_presentation",
        "build_economic_fact_explanation",
        "learned_topics",
        "learnedtopic",
        "datetime",
        "render",
        "confirm",
        "post",
        "journal",
        "account",
        "fiscal",
    ):
        assert forbidden not in source
