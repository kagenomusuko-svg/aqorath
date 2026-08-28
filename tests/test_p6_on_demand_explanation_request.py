"""Phase 6W.1 — frozen on-demand explanation request contracts.

Constitution anchors:
- R11 keeps explanation truth deterministic and derived from accounting truth.
- R12 requires an experienced user to be able to ask "Explícame esto" at any time.
- R13 keeps pedagogical progression explicit and separate from transient presentation.

Phase 6T plans presentation from the persisted preference. Phase 6W freezes a separate
one-shot override boundary: an explicit request must produce a detailed presentation for
this explanation without rewriting the user's persisted explanation level, presentation
history, or learning history.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
import importlib
import inspect

import pytest


def _module():
    return importlib.import_module("aqorath.explanation_request")


def _explanation(*, concepts=("economic_fact", "double_entry", "accrual")):
    from aqorath.explanation import ExplanationData, ExplanationEffect

    return ExplanationData(
        fact_type="sale",
        payment_method="cash",
        amount=Decimal("125.5000"),
        rule_key="economic_fact:sale:cash",
        effects=(
            ExplanationEffect("cash", "debit", Decimal("125.5000")),
            ExplanationEffect("sales_revenue", "credit", Decimal("125.5000")),
        ),
        concepts=concepts,
        professional_summary="Venta de contado por 125.5000.",
    )


def _state(
    *,
    level="none",
    concepts_seen=(),
    learned_topics=(),
    always_professional=False,
    ui_language="es-MX",
    decimal_separator=".",
    currency_symbol="MX$",
    preferred_report_format="xlsx",
):
    from aqorath.user_knowledge_state import UserKnowledgeState

    return UserKnowledgeState(
        id=1,
        explanation_level=level,
        concepts_seen=concepts_seen,
        ui_language=ui_language,
        decimal_separator=decimal_separator,
        currency_symbol=currency_symbol,
        preferred_report_format=preferred_report_format,
        always_show_professional_view=always_professional,
        learned_topics=learned_topics,
    )


def test_request_public_contract_is_exact_pure_and_nonpersistent():
    module = _module()

    assert str(inspect.signature(module.plan_requested_explanation)) == "(explanation, user_state)"

    source = inspect.getsource(module).lower()
    for forbidden in (
        "sqlmodel",
        "sqlalchemy",
        "sqlite3",
        "requests",
        "fastapi",
        "get_session",
        "repository",
        "commit(",
        "rollback(",
        "datetime.now",
        "datetime.utcnow",
        "time.time",
        "random",
        "openai",
        "llm",
    ):
        assert forbidden not in source


def test_request_requires_nominal_explanation_data():
    module = _module()
    state = _state()

    for invalid in (None, object(), {"fact_type": "sale"}, "explanation"):
        with pytest.raises(TypeError):
            module.plan_requested_explanation(invalid, state)


def test_request_requires_nominal_user_knowledge_state():
    module = _module()
    explanation = _explanation()

    for invalid in (None, object(), {"explanation_level": "none"}, "state"):
        with pytest.raises(TypeError):
            module.plan_requested_explanation(explanation, invalid)


def test_explicit_request_forces_detailed_presentation_even_when_preference_is_none():
    module = _module()

    plan = module.plan_requested_explanation(_explanation(), _state(level="none"))

    assert plan.explanation_level == "detailed"
    assert plan.show_common_explanation is True
    assert plan.show_structured_effects is True


def test_explicit_request_is_detailed_for_every_persisted_explanation_level():
    module = _module()
    explanation = _explanation()

    plans = [
        module.plan_requested_explanation(explanation, _state(level=level))
        for level in ("none", "brief", "detailed")
    ]

    assert all(plan.explanation_level == "detailed" for plan in plans)
    assert all(plan.show_common_explanation is True for plan in plans)
    assert all(plan.show_structured_effects is True for plan in plans)
    assert plans[0] == plans[1] == plans[2]


def test_request_returns_existing_explanation_presentation_plan_type():
    module = _module()
    from aqorath.explanation_presentation import ExplanationPresentationPlan

    plan = module.plan_requested_explanation(_explanation(), _state())
    assert isinstance(plan, ExplanationPresentationPlan)


def test_seen_concepts_remain_filtered_during_on_demand_explanation():
    module = _module()
    explanation = _explanation(
        concepts=("economic_fact", "double_entry", "accrual", "cash_basis")
    )
    state = _state(concepts_seen=("double_entry", "cash_basis"))

    plan = module.plan_requested_explanation(explanation, state)

    assert plan.concepts_to_present == ("economic_fact", "accrual")


def test_all_seen_concepts_do_not_block_requested_common_or_structured_explanation():
    module = _module()
    explanation = _explanation()
    state = _state(concepts_seen=explanation.concepts)

    plan = module.plan_requested_explanation(explanation, state)

    assert plan.concepts_to_present == ()
    assert plan.show_common_explanation is True
    assert plan.show_structured_effects is True
    assert plan.explanation_level == "detailed"


def test_learned_topics_do_not_suppress_concepts_that_were_never_presented():
    module = _module()
    from aqorath.user_knowledge_state import LearnedTopic

    learned = LearnedTopic(
        topic="double_entry",
        learned_at=datetime(2026, 8, 28, 1, 0, tzinfo=timezone.utc),
    )
    state = _state(concepts_seen=("economic_fact",), learned_topics=(learned,))

    plan = module.plan_requested_explanation(_explanation(), state)

    assert plan.concepts_to_present == ("double_entry", "accrual")


def test_professional_view_remains_an_independent_explicit_preference():
    module = _module()
    explanation = _explanation()

    off = module.plan_requested_explanation(
        explanation,
        _state(level="none", always_professional=False),
    )
    on = module.plan_requested_explanation(
        explanation,
        _state(level="none", always_professional=True),
    )

    assert off.show_professional_view is False
    assert on.show_professional_view is True
    assert replace(on, show_professional_view=False) == off


def test_request_does_not_rewrite_persisted_explanation_preference_or_other_state():
    module = _module()
    state = _state(
        level="none",
        concepts_seen=("economic_fact",),
        ui_language="pt-BR",
        decimal_separator=",",
        currency_symbol="R$",
        preferred_report_format="structured-json",
        always_professional=True,
    )
    before = state

    module.plan_requested_explanation(_explanation(), state)

    assert state is before
    assert state.explanation_level == "none"
    assert state.concepts_seen == ("economic_fact",)
    assert state.ui_language == "pt-BR"
    assert state.decimal_separator == ","
    assert state.currency_symbol == "R$"
    assert state.preferred_report_format == "structured-json"
    assert state.always_show_professional_view is True


def test_request_never_marks_concepts_presented_or_topics_learned():
    module = _module()
    from aqorath.user_knowledge_state import LearnedTopic

    learned = LearnedTopic(
        topic="economic_fact",
        learned_at=datetime(2026, 8, 28, 1, 15, tzinfo=timezone.utc),
    )
    state = _state(
        concepts_seen=("economic_fact",),
        learned_topics=(learned,),
    )
    before_seen = state.concepts_seen
    before_learned = state.learned_topics

    module.plan_requested_explanation(_explanation(), state)

    assert state.concepts_seen is before_seen
    assert state.learned_topics is before_learned

    source = inspect.getsource(module).lower()
    for forbidden in (
        "record_presented_concepts",
        "record_learned_topic",
        "record_explanation_presentation",
        "record_user_topic_learning",
        "update_user_knowledge_state",
    ):
        assert forbidden not in source


def test_locale_and_report_preferences_do_not_change_request_plan():
    module = _module()
    explanation = _explanation()

    baseline = module.plan_requested_explanation(explanation, _state())
    changed = module.plan_requested_explanation(
        explanation,
        _state(
            ui_language="en-US",
            decimal_separator=",",
            currency_symbol="USD",
            preferred_report_format="pdf",
        ),
    )

    assert changed == baseline


def test_request_is_deterministic_and_does_not_render_or_rebuild_accounting_truth():
    module = _module()
    explanation = _explanation()
    state = _state(concepts_seen=("economic_fact",))

    first = module.plan_requested_explanation(explanation, state)
    second = module.plan_requested_explanation(explanation, state)
    assert first == second

    source = inspect.getsource(module).lower()
    for forbidden in (
        "build_economic_fact_explanation",
        "resolve_economic_fact",
        "journalentry",
        "journalline",
        "render",
        "format(",
        "professional_summary.",
        "debit",
        "credit",
        "fiscal",
        "post",
        "confirm",
    ):
        assert forbidden not in source


def test_application_exposes_exact_thin_on_demand_request_delegation(monkeypatch):
    application = importlib.import_module("aqorath.application")
    module = _module()

    assert hasattr(application, "plan_requested_explanation")
    assert str(inspect.signature(application.plan_requested_explanation)) == "(explanation, user_state)"

    sentinel_explanation = object()
    sentinel_state = object()
    sentinel_result = object()
    calls = []

    def fake_request(explanation, user_state):
        calls.append((explanation, user_state))
        return sentinel_result

    monkeypatch.setattr(module, "plan_requested_explanation", fake_request)

    result = application.plan_requested_explanation(sentinel_explanation, sentinel_state)
    assert result is sentinel_result
    assert calls == [(sentinel_explanation, sentinel_state)]


def test_application_request_does_not_load_persist_or_mutate_user_state_itself():
    application = importlib.import_module("aqorath.application")
    source = inspect.getsource(application.plan_requested_explanation).lower()

    assert "_explanation_request.plan_requested_explanation" in source
    for forbidden in (
        "session",
        "get_user_knowledge_state",
        "update_user_knowledge_state",
        "record_explanation_presentation",
        "record_user_topic_learning",
        "concepts_seen",
        "learned_topics",
        "explanation_level =",
        "datetime",
        "render",
        "confirm",
        "post",
    ):
        assert forbidden not in source
