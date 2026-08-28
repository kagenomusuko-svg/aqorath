"""Phase 6X.1 — frozen structured explanation-view contracts.

Constitution anchors:
- R2 keeps common/professional interfaces over one accounting truth.
- R11 requires structured deterministic explainability derived from that truth.
- R12 lets presentation directives decide which explanation layers are visible.

Phase 6X freezes the interface-agnostic projection immediately before UI formatting.
It may select already-authoritative explanation fields according to an existing
ExplanationPresentationPlan, but may not generate new prose, localize, format money,
re-plan pedagogy, persist state, or rewrite accounting truth.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace
from decimal import Decimal
import importlib
import inspect

import pytest


VIEW_FIELDS = (
    "fact_type",
    "payment_method",
    "amount",
    "effects",
    "concepts",
    "professional_summary",
)


def _module():
    return importlib.import_module("aqorath.explanation_view")


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


def _plan(
    *,
    level="brief",
    show_common=True,
    show_effects=False,
    concepts=("economic_fact", "double_entry"),
    show_professional=False,
):
    from aqorath.explanation_presentation import ExplanationPresentationPlan

    return ExplanationPresentationPlan(
        explanation_level=level,
        show_common_explanation=show_common,
        show_structured_effects=show_effects,
        concepts_to_present=concepts,
        show_professional_view=show_professional,
    )


def test_view_public_contract_is_exact_frozen_pure_and_interface_agnostic():
    module = _module()

    assert tuple(field.name for field in fields(module.ExplanationPresentationView)) == VIEW_FIELDS
    assert str(inspect.signature(module.build_explanation_presentation_view)) == (
        "(explanation, presentation_plan)"
    )

    view = module.build_explanation_presentation_view(_explanation(), _plan())
    with pytest.raises(FrozenInstanceError):
        view.fact_type = "purchase"

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
        "time.time",
        "random",
        "openai",
        "llm",
    ):
        assert forbidden not in source


def test_view_requires_nominal_explanation_data():
    module = _module()
    plan = _plan()

    for invalid in (None, object(), {"fact_type": "sale"}, "explanation"):
        with pytest.raises(TypeError):
            module.build_explanation_presentation_view(invalid, plan)


def test_view_requires_nominal_explanation_presentation_plan():
    module = _module()
    explanation = _explanation()

    for invalid in (None, object(), {"show_common_explanation": True}, "brief"):
        with pytest.raises(TypeError):
            module.build_explanation_presentation_view(explanation, invalid)


def test_hidden_plan_projects_no_common_effect_concept_or_professional_layers():
    module = _module()
    plan = _plan(
        level="none",
        show_common=False,
        show_effects=False,
        concepts=(),
        show_professional=False,
    )

    view = module.build_explanation_presentation_view(_explanation(), plan)

    assert view == module.ExplanationPresentationView(
        fact_type=None,
        payment_method=None,
        amount=None,
        effects=(),
        concepts=(),
        professional_summary=None,
    )


def test_professional_view_can_be_visible_when_common_layers_are_hidden():
    module = _module()
    explanation = _explanation()
    plan = _plan(
        level="none",
        show_common=False,
        show_effects=False,
        concepts=(),
        show_professional=True,
    )

    view = module.build_explanation_presentation_view(explanation, plan)

    assert view.fact_type is None
    assert view.payment_method is None
    assert view.amount is None
    assert view.effects == ()
    assert view.concepts == ()
    assert view.professional_summary == explanation.professional_summary


def test_brief_projection_exposes_exact_common_truth_without_structured_effects():
    module = _module()
    explanation = _explanation()
    plan = _plan(
        level="brief",
        show_common=True,
        show_effects=False,
        concepts=("economic_fact", "double_entry"),
    )

    view = module.build_explanation_presentation_view(explanation, plan)

    assert view.fact_type == explanation.fact_type
    assert view.payment_method == explanation.payment_method
    assert view.amount is explanation.amount
    assert view.effects == ()
    assert view.concepts == plan.concepts_to_present
    assert view.professional_summary is None


def test_detailed_projection_reuses_exact_structured_effect_truth_without_rewriting():
    module = _module()
    explanation = _explanation()
    plan = _plan(
        level="detailed",
        show_common=True,
        show_effects=True,
        concepts=("economic_fact", "double_entry", "accrual"),
    )

    view = module.build_explanation_presentation_view(explanation, plan)

    assert view.effects is explanation.effects
    assert view.effects[0] is explanation.effects[0]
    assert view.effects[1] is explanation.effects[1]
    assert view.amount is explanation.amount


def test_projection_uses_exact_planned_concepts_not_all_explanation_concepts():
    module = _module()
    explanation = _explanation(
        concepts=("economic_fact", "double_entry", "accrual", "cash_basis")
    )
    plan = _plan(
        level="detailed",
        show_common=True,
        show_effects=True,
        concepts=("double_entry", "cash_basis"),
    )

    view = module.build_explanation_presentation_view(explanation, plan)

    assert view.concepts == ("double_entry", "cash_basis")
    assert "economic_fact" not in view.concepts
    assert "accrual" not in view.concepts


def test_projection_fails_closed_if_plan_invents_concept_absent_from_explanation_truth():
    module = _module()
    explanation = _explanation(concepts=("economic_fact", "double_entry"))
    plan = _plan(concepts=("economic_fact", "invented_concept"))

    with pytest.raises(ValueError):
        module.build_explanation_presentation_view(explanation, plan)


def test_professional_summary_visibility_is_controlled_only_by_plan_flag():
    module = _module()
    explanation = _explanation()

    hidden = module.build_explanation_presentation_view(
        explanation,
        _plan(show_professional=False),
    )
    visible = module.build_explanation_presentation_view(
        explanation,
        _plan(show_professional=True),
    )

    assert hidden.professional_summary is None
    assert visible.professional_summary == explanation.professional_summary
    assert replace(visible, professional_summary=None) == hidden


def test_projection_preserves_decimal_and_semantic_values_without_formatting_or_localization():
    module = _module()
    explanation = _explanation()
    view = module.build_explanation_presentation_view(
        explanation,
        _plan(level="detailed", show_effects=True),
    )

    assert type(view.amount) is Decimal
    assert view.amount == Decimal("125.5000")
    assert view.effects[0].amount == Decimal("125.5000")
    assert view.fact_type == "sale"
    assert view.payment_method == "cash"

    source = inspect.getsource(module).lower()
    for forbidden in (
        "ui_language",
        "decimal_separator",
        "currency_symbol",
        "preferred_report_format",
        "locale",
        "gettext",
        "quantize",
        "float(",
        "format(",
    ):
        assert forbidden not in source


def test_projection_never_mutates_explanation_or_presentation_plan():
    module = _module()
    explanation = _explanation()
    plan = _plan(level="detailed", show_effects=True)
    before_effects = explanation.effects
    before_concepts = plan.concepts_to_present

    module.build_explanation_presentation_view(explanation, plan)

    assert explanation.effects is before_effects
    assert plan.concepts_to_present is before_concepts


def test_projection_is_deterministic_and_uses_no_time_randomness_or_ai():
    module = _module()
    explanation = _explanation()
    plan = _plan(level="detailed", show_effects=True)

    first = module.build_explanation_presentation_view(explanation, plan)
    second = module.build_explanation_presentation_view(explanation, plan)

    assert first == second
    assert not hasattr(first, "created_at")
    assert not hasattr(first, "generated_at")

    source = inspect.getsource(module).lower()
    for forbidden in ("datetime", "time.time", "random", "openai", "llm"):
        assert forbidden not in source


def test_projection_does_not_replan_persist_render_or_rebuild_accounting_truth():
    module = _module()
    source = inspect.getsource(module).lower()

    for forbidden in (
        "plan_explanation_presentation",
        "plan_requested_explanation",
        "userknowledgestate",
        "get_user_knowledge_state",
        "update_user_knowledge_state",
        "record_presented_concepts",
        "record_learned_topic",
        "build_economic_fact_explanation",
        "resolve_economic_fact",
        "render",
        "journalentry",
        "journalline",
        "post",
        "confirm",
    ):
        assert forbidden not in source


def test_application_exposes_exact_thin_structured_view_delegation(monkeypatch):
    application = importlib.import_module("aqorath.application")
    module = _module()

    assert hasattr(application, "build_explanation_presentation_view")
    assert str(inspect.signature(application.build_explanation_presentation_view)) == (
        "(explanation, presentation_plan)"
    )

    sentinel_explanation = object()
    sentinel_plan = object()
    sentinel_result = object()
    calls = []

    def fake_builder(explanation, presentation_plan):
        calls.append((explanation, presentation_plan))
        return sentinel_result

    monkeypatch.setattr(module, "build_explanation_presentation_view", fake_builder)

    result = application.build_explanation_presentation_view(
        sentinel_explanation,
        sentinel_plan,
    )
    assert result is sentinel_result
    assert calls == [(sentinel_explanation, sentinel_plan)]


def test_application_view_boundary_does_not_plan_persist_format_or_mutate_itself():
    application = importlib.import_module("aqorath.application")
    source = inspect.getsource(application.build_explanation_presentation_view).lower()

    assert "_explanation_view.build_explanation_presentation_view" in source
    for forbidden in (
        "session",
        "plan_explanation_presentation",
        "plan_requested_explanation",
        "get_user_knowledge_state",
        "update_user_knowledge_state",
        "record_explanation_presentation",
        "record_user_topic_learning",
        "ui_language",
        "decimal_separator",
        "currency_symbol",
        "format(",
        "render",
        "post",
        "confirm",
    ):
        assert forbidden not in source
