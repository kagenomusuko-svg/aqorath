"""Phase 6T.1 — frozen adaptive explanation-presentation contracts.

This phase composes two already-authoritative value objects:
- Phase 6S ExplanationData: the structured deterministic explanation truth.
- Phase 6R UserKnowledgeState: the local owner's explicit pedagogical preferences.

6T may decide which presentation layers are due. It may not rebuild accounting,
rewrite explanation truth, render localized prose, or mutate learning state merely
because an explanation was planned for presentation.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace
from datetime import datetime
from decimal import Decimal
import importlib
import inspect

import pytest


PLAN_FIELDS = (
    "explanation_level",
    "show_common_explanation",
    "show_structured_effects",
    "concepts_to_present",
    "show_professional_view",
)


def _module():
    return importlib.import_module("aqorath.explanation_presentation")


def _explanation(*, concepts=("economic_fact", "double_entry")):
    from aqorath.explanation import ExplanationData, ExplanationEffect

    return ExplanationData(
        fact_type="sale",
        payment_method="cash",
        amount=Decimal("123.4500"),
        rule_key="economic_fact:sale:cash",
        effects=(
            ExplanationEffect("cash", "debit", Decimal("123.4500")),
            ExplanationEffect("sales_revenue", "credit", Decimal("123.4500")),
        ),
        concepts=concepts,
        professional_summary="Venta de contado por 123.4500.",
    )


def _state(
    *,
    level="brief",
    concepts_seen=(),
    always_professional=False,
    learned_topics=(),
    ui_language="es",
    decimal_separator=".",
    currency_symbol="$",
    preferred_report_format="pdf",
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


def test_presentation_plan_public_contract_is_exact_frozen_and_pure():
    module = _module()

    assert tuple(field.name for field in fields(module.ExplanationPresentationPlan)) == PLAN_FIELDS
    assert str(inspect.signature(module.plan_explanation_presentation)) == "(explanation, user_state)"

    source = inspect.getsource(module).lower()
    for forbidden in (
        "sqlmodel",
        "sqlalchemy",
        "sqlite3",
        "requests",
        "fastapi",
        "get_session",
        "user_knowledge_state_repository",
        "appconfig",
        "journalentry",
        "journalline",
        "datetime.now",
        "random",
        "openai",
    ):
        assert forbidden not in source


def test_presentation_plan_is_deeply_immutable_and_uses_tuple_concepts():
    module = _module()
    plan = module.plan_explanation_presentation(_explanation(), _state())

    with pytest.raises(FrozenInstanceError):
        plan.explanation_level = "detailed"
    assert type(plan.concepts_to_present) is tuple


def test_public_plan_validates_level_boolean_and_concept_shapes_fail_closed():
    module = _module()
    valid = module.ExplanationPresentationPlan(
        explanation_level="brief",
        show_common_explanation=True,
        show_structured_effects=False,
        concepts_to_present=("economic_fact",),
        show_professional_view=False,
    )

    for invalid_level in ("", "Brief", " brief ", "verbose", None, 1):
        with pytest.raises((TypeError, ValueError)):
            replace(valid, explanation_level=invalid_level)

    for field_name in (
        "show_common_explanation",
        "show_structured_effects",
        "show_professional_view",
    ):
        for invalid in (0, 1, None, "true"):
            with pytest.raises((TypeError, ValueError)):
                replace(valid, **{field_name: invalid})

    with pytest.raises((TypeError, ValueError)):
        replace(valid, concepts_to_present=["economic_fact"])
    with pytest.raises((TypeError, ValueError)):
        replace(valid, concepts_to_present=("economic_fact", "economic_fact"))
    with pytest.raises((TypeError, ValueError)):
        replace(valid, concepts_to_present=(" spaced ",))


def test_planner_requires_nominal_explanation_data_before_using_user_state():
    module = _module()
    state = _state()

    for invalid in (None, object(), {"fact_type": "sale"}, "summary"):
        with pytest.raises(TypeError):
            module.plan_explanation_presentation(invalid, state)


def test_planner_requires_nominal_user_knowledge_state():
    module = _module()
    explanation = _explanation()

    for invalid in (None, object(), {"explanation_level": "brief"}, "brief"):
        with pytest.raises(TypeError):
            module.plan_explanation_presentation(explanation, invalid)


def test_none_level_omits_common_effect_and_concept_layers_without_hiding_explicit_professional_preference():
    module = _module()

    hidden = module.plan_explanation_presentation(
        _explanation(),
        _state(level="none", always_professional=False),
    )
    assert hidden == module.ExplanationPresentationPlan(
        explanation_level="none",
        show_common_explanation=False,
        show_structured_effects=False,
        concepts_to_present=(),
        show_professional_view=False,
    )

    professional = module.plan_explanation_presentation(
        _explanation(),
        _state(level="none", always_professional=True),
    )
    assert professional.show_common_explanation is False
    assert professional.show_structured_effects is False
    assert professional.concepts_to_present == ()
    assert professional.show_professional_view is True


def test_brief_level_shows_common_explanation_but_not_structured_effects():
    module = _module()
    plan = module.plan_explanation_presentation(
        _explanation(),
        _state(level="brief"),
    )

    assert plan.explanation_level == "brief"
    assert plan.show_common_explanation is True
    assert plan.show_structured_effects is False
    assert plan.concepts_to_present == ("economic_fact", "double_entry")
    assert plan.show_professional_view is False


def test_detailed_level_shows_common_and_structured_effect_layers():
    module = _module()
    plan = module.plan_explanation_presentation(
        _explanation(),
        _state(level="detailed"),
    )

    assert plan.explanation_level == "detailed"
    assert plan.show_common_explanation is True
    assert plan.show_structured_effects is True
    assert plan.concepts_to_present == ("economic_fact", "double_entry")


def test_seen_concepts_are_filtered_without_reordering_or_rewriting_remaining_concepts():
    module = _module()
    explanation = _explanation(concepts=("economic_fact", "double_entry", "accrual"))
    state = _state(level="detailed", concepts_seen=("double_entry", "other_concept"))

    plan = module.plan_explanation_presentation(explanation, state)
    assert plan.concepts_to_present == ("economic_fact", "accrual")


def test_all_seen_concepts_leave_empty_introduction_tuple_without_changing_level_directives():
    module = _module()
    explanation = _explanation()

    brief = module.plan_explanation_presentation(
        explanation,
        _state(level="brief", concepts_seen=("economic_fact", "double_entry")),
    )
    detailed = module.plan_explanation_presentation(
        explanation,
        _state(level="detailed", concepts_seen=("economic_fact", "double_entry")),
    )

    assert brief.concepts_to_present == ()
    assert brief.show_common_explanation is True
    assert brief.show_structured_effects is False
    assert detailed.concepts_to_present == ()
    assert detailed.show_common_explanation is True
    assert detailed.show_structured_effects is True


def test_learned_topics_do_not_imply_concepts_seen_or_suppress_presentations():
    module = _module()
    from aqorath.user_knowledge_state import LearnedTopic

    learned = LearnedTopic(
        topic="double_entry",
        learned_at=datetime(2026, 8, 27, 12, 0, 0),
    )
    plan = module.plan_explanation_presentation(
        _explanation(),
        _state(level="brief", learned_topics=(learned,)),
    )

    assert plan.concepts_to_present == ("economic_fact", "double_entry")


def test_nonpedagogical_locale_and_report_preferences_do_not_change_presentation_plan():
    module = _module()
    explanation = _explanation()

    baseline = module.plan_explanation_presentation(explanation, _state(level="detailed"))
    changed = module.plan_explanation_presentation(
        explanation,
        _state(
            level="detailed",
            ui_language="en",
            decimal_separator=",",
            currency_symbol="MX$",
            preferred_report_format="excel",
        ),
    )

    assert changed == baseline


def test_professional_view_preference_is_independent_from_explanation_level():
    module = _module()
    explanation = _explanation()

    for level in ("none", "brief", "detailed"):
        off = module.plan_explanation_presentation(
            explanation,
            _state(level=level, always_professional=False),
        )
        on = module.plan_explanation_presentation(
            explanation,
            _state(level=level, always_professional=True),
        )
        assert off.show_professional_view is False
        assert on.show_professional_view is True
        assert replace(on, show_professional_view=False) == off


def test_plan_contains_only_presentation_directives_and_does_not_duplicate_explanation_or_accounting_truth():
    module = _module()
    plan = module.plan_explanation_presentation(_explanation(), _state())

    forbidden = {
        "amount",
        "fact_type",
        "payment_method",
        "rule_key",
        "effects",
        "professional_summary",
        "account_role",
        "account_id",
        "account_code",
        "side",
        "debit",
        "credit",
        "tax",
        "fiscal_effect",
        "journal_entry_id",
    }
    assert forbidden.isdisjoint(PLAN_FIELDS)
    for name in forbidden:
        assert not hasattr(plan, name)


def test_planning_never_mutates_explanation_concepts_seen_or_learned_topics():
    module = _module()
    from aqorath.user_knowledge_state import LearnedTopic

    explanation = _explanation(concepts=("economic_fact", "double_entry", "cash_basis"))
    state = _state(
        level="detailed",
        concepts_seen=("economic_fact",),
        learned_topics=(
            LearnedTopic(
                topic="double_entry",
                learned_at=datetime(2026, 8, 27, 12, 0, 0),
            ),
        ),
    )
    before_concepts = explanation.concepts
    before_seen = state.concepts_seen
    before_learned = state.learned_topics

    module.plan_explanation_presentation(explanation, state)

    assert explanation.concepts == before_concepts
    assert state.concepts_seen == before_seen
    assert state.learned_topics == before_learned


def test_planner_is_deterministic_and_uses_no_ambient_time_randomness_or_ai():
    module = _module()
    explanation = _explanation()
    state = _state(level="detailed", concepts_seen=("economic_fact",))

    first = module.plan_explanation_presentation(explanation, state)
    second = module.plan_explanation_presentation(explanation, state)
    assert first == second
    assert not hasattr(first, "created_at")
    assert not hasattr(first, "generated_at")

    source = inspect.getsource(module).lower()
    for forbidden in ("datetime.now", "time.time", "random", "openai", "llm"):
        assert forbidden not in source


def test_planner_never_reads_or_writes_repository_and_does_not_render_text():
    module = _module()
    source = inspect.getsource(module).lower()

    for forbidden in (
        "session",
        "repository",
        "commit(",
        "rollback(",
        "get_user_knowledge_state",
        "update_user_knowledge_state",
        "render_",
        "format(",
        "professional_summary.",
    ):
        assert forbidden not in source


def test_application_exposes_adaptive_plan_as_exact_thin_module_delegation(monkeypatch):
    application = importlib.import_module("aqorath.application")
    module = _module()

    assert hasattr(application, "plan_explanation_presentation")
    assert str(inspect.signature(application.plan_explanation_presentation)) == "(explanation, user_state)"

    sentinel_explanation = object()
    sentinel_state = object()
    sentinel_result = object()
    calls = []

    def fake_planner(explanation, user_state):
        calls.append((explanation, user_state))
        return sentinel_result

    monkeypatch.setattr(module, "plan_explanation_presentation", fake_planner)
    assert application.plan_explanation_presentation(sentinel_explanation, sentinel_state) is sentinel_result
    assert calls == [(sentinel_explanation, sentinel_state)]


def test_application_does_not_load_state_render_explanation_or_mutate_learning_itself():
    application = importlib.import_module("aqorath.application")
    source = inspect.getsource(application.plan_explanation_presentation).lower()

    assert "_explanation_presentation.plan_explanation_presentation" in source
    for forbidden in (
        "session",
        "get_user_knowledge_state",
        "update_user_knowledge_state",
        "concepts_seen",
        "learned_topics",
        "build_economic_fact_explanation",
        "render",
        "confirm",
        "post",
    ):
        assert forbidden not in source
