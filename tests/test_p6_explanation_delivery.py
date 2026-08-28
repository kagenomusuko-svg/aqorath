"""Phase 6Y.1 — frozen explanation delivery orchestration contracts.

Constitution anchors:
- R11 requires explanation to remain derived from deterministic accounting truth.
- R12 requires usable explanation delivery, including explicit on-demand explanation.
- R13 keeps presentation history separate from merely preparing something to show.

Phase 6Y freezes the Application-layer composition of already-existing explanation,
planning, and structured-view authorities. Presentation formatting remains outside this
boundary. Preparing a delivery package must not persist state, mark concepts presented,
mark topics learned, localize text, format money, or re-resolve accounting truth.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from decimal import Decimal
import importlib
import inspect

import pytest


PACKAGE_FIELDS = (
    "explanation",
    "presentation_plan",
    "presentation_view",
)


def _module():
    return importlib.import_module("aqorath.explanation_delivery")


def _resolution():
    from aqorath.economic_fact_accounting_provenance import (
        resolve_economic_fact_with_provenance,
    )
    from aqorath.economic_facts import EconomicFact

    fact = EconomicFact(
        type="sale",
        amount=Decimal("125.5000"),
        payment_method="cash",
    )
    return resolve_economic_fact_with_provenance(fact)


def _state(
    *,
    level="brief",
    concepts_seen=(),
    always_professional=False,
    ui_language="es-MX",
    decimal_separator=".",
    currency_symbol="MX$",
    preferred_report_format="xlsx",
    learned_topics=(),
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


def test_delivery_public_contract_is_exact_frozen_pure_and_unformatted():
    module = _module()

    assert tuple(field.name for field in fields(module.PreparedExplanationPresentation)) == (
        PACKAGE_FIELDS
    )
    assert str(inspect.signature(module.prepare_explanation_presentation)) == (
        "(accounting_resolution, user_state)"
    )
    assert str(inspect.signature(module.prepare_requested_explanation_presentation)) == (
        "(accounting_resolution, user_state)"
    )

    package = module.prepare_explanation_presentation(_resolution(), _state())
    with pytest.raises(FrozenInstanceError):
        package.presentation_view = object()

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


def test_standard_delivery_requires_nominal_accounting_resolution():
    module = _module()
    state = _state()

    for invalid in (None, object(), {"fact": object()}, "resolution"):
        with pytest.raises(TypeError):
            module.prepare_explanation_presentation(invalid, state)


def test_standard_delivery_requires_nominal_user_knowledge_state():
    module = _module()
    resolution = _resolution()

    for invalid in (None, object(), {"explanation_level": "brief"}, "state"):
        with pytest.raises(TypeError):
            module.prepare_explanation_presentation(resolution, invalid)


def test_requested_delivery_requires_same_nominal_inputs():
    module = _module()
    resolution = _resolution()
    state = _state()

    with pytest.raises(TypeError):
        module.prepare_requested_explanation_presentation(object(), state)
    with pytest.raises(TypeError):
        module.prepare_requested_explanation_presentation(resolution, object())


def test_standard_delivery_calls_build_then_adaptive_plan_then_view_in_order(monkeypatch):
    module = _module()
    resolution = _resolution()
    state = _state()
    explanation = object()
    plan = object()
    view = object()
    calls = []

    def fake_build(value):
        calls.append(("build", value))
        return explanation

    def fake_plan(value, supplied_state):
        calls.append(("plan", value, supplied_state))
        return plan

    def fake_view(value, supplied_plan):
        calls.append(("view", value, supplied_plan))
        return view

    monkeypatch.setattr(module._explanation, "build_economic_fact_explanation", fake_build)
    monkeypatch.setattr(
        module._explanation_presentation,
        "plan_explanation_presentation",
        fake_plan,
    )
    monkeypatch.setattr(
        module._explanation_view,
        "build_explanation_presentation_view",
        fake_view,
    )

    package = module.prepare_explanation_presentation(resolution, state)

    assert calls == [
        ("build", resolution),
        ("plan", explanation, state),
        ("view", explanation, plan),
    ]
    assert package.explanation is explanation
    assert package.presentation_plan is plan
    assert package.presentation_view is view


def test_requested_delivery_uses_requested_planner_not_adaptive_planner(monkeypatch):
    module = _module()
    resolution = _resolution()
    state = _state(level="none")
    explanation = object()
    plan = object()
    view = object()
    calls = []

    def fake_build(value):
        calls.append(("build", value))
        return explanation

    def forbidden_adaptive(*args, **kwargs):
        raise AssertionError("adaptive planner must not serve explicit request")

    def fake_requested(value, supplied_state):
        calls.append(("requested", value, supplied_state))
        return plan

    def fake_view(value, supplied_plan):
        calls.append(("view", value, supplied_plan))
        return view

    monkeypatch.setattr(module._explanation, "build_economic_fact_explanation", fake_build)
    monkeypatch.setattr(
        module._explanation_presentation,
        "plan_explanation_presentation",
        forbidden_adaptive,
    )
    monkeypatch.setattr(
        module._explanation_request,
        "plan_requested_explanation",
        fake_requested,
    )
    monkeypatch.setattr(
        module._explanation_view,
        "build_explanation_presentation_view",
        fake_view,
    )

    package = module.prepare_requested_explanation_presentation(resolution, state)

    assert calls == [
        ("build", resolution),
        ("requested", explanation, state),
        ("view", explanation, plan),
    ]
    assert package.explanation is explanation
    assert package.presentation_plan is plan
    assert package.presentation_view is view


def test_standard_none_preference_prepares_hidden_common_view_without_mutating_state():
    module = _module()
    state = _state(level="none")

    package = module.prepare_explanation_presentation(_resolution(), state)

    assert package.presentation_plan.explanation_level == "none"
    assert package.presentation_view.fact_type is None
    assert package.presentation_view.payment_method is None
    assert package.presentation_view.amount is None
    assert package.presentation_view.effects == ()
    assert package.presentation_view.concepts == ()
    assert state.explanation_level == "none"


def test_standard_detailed_preference_preserves_exact_truth_and_seen_filtering():
    module = _module()
    state = _state(
        level="detailed",
        concepts_seen=("economic_fact",),
        always_professional=True,
    )

    package = module.prepare_explanation_presentation(_resolution(), state)

    assert package.presentation_plan.explanation_level == "detailed"
    assert package.presentation_plan.concepts_to_present == ("double_entry",)
    assert package.presentation_view.amount is package.explanation.amount
    assert package.presentation_view.effects is package.explanation.effects
    assert package.presentation_view.concepts == ("double_entry",)
    assert (
        package.presentation_view.professional_summary
        == package.explanation.professional_summary
    )


def test_requested_delivery_forces_detailed_view_without_rewriting_persisted_preference():
    module = _module()
    state = _state(level="none", concepts_seen=("economic_fact",))
    before_seen = state.concepts_seen

    package = module.prepare_requested_explanation_presentation(_resolution(), state)

    assert package.presentation_plan.explanation_level == "detailed"
    assert package.presentation_view.fact_type == "sale"
    assert package.presentation_view.amount == Decimal("125.5000")
    assert package.presentation_view.effects is package.explanation.effects
    assert package.presentation_view.concepts == ("double_entry",)
    assert state.explanation_level == "none"
    assert state.concepts_seen is before_seen


def test_delivery_package_preserves_exact_artifacts_for_later_presentation_recording():
    module = _module()
    package = module.prepare_explanation_presentation(
        _resolution(),
        _state(level="detailed"),
    )

    from aqorath.explanation import ExplanationData
    from aqorath.explanation_presentation import ExplanationPresentationPlan
    from aqorath.explanation_view import ExplanationPresentationView

    assert isinstance(package.explanation, ExplanationData)
    assert isinstance(package.presentation_plan, ExplanationPresentationPlan)
    assert isinstance(package.presentation_view, ExplanationPresentationView)
    assert package.presentation_view.effects is package.explanation.effects
    assert package.presentation_view.concepts is package.presentation_plan.concepts_to_present


def test_delivery_is_deterministic_for_same_resolution_and_state():
    module = _module()
    resolution = _resolution()
    state = _state(level="detailed", concepts_seen=("economic_fact",))

    first = module.prepare_explanation_presentation(resolution, state)
    second = module.prepare_explanation_presentation(resolution, state)
    requested_first = module.prepare_requested_explanation_presentation(resolution, state)
    requested_second = module.prepare_requested_explanation_presentation(resolution, state)

    assert first == second
    assert requested_first == requested_second
    assert not hasattr(first, "created_at")
    assert not hasattr(first, "generated_at")


def test_delivery_does_not_persist_progress_format_localize_or_reresolve_truth():
    module = _module()
    source = inspect.getsource(module).lower()

    for forbidden in (
        "resolve_economic_fact(",
        "record_presented_concepts",
        "record_learned_topic",
        "record_explanation_presentation",
        "record_user_topic_learning",
        "get_user_knowledge_state",
        "update_user_knowledge_state",
        "ui_language",
        "decimal_separator",
        "currency_symbol",
        "preferred_report_format",
        "locale",
        "gettext",
        "quantize",
        "float(",
        "format(",
        "render",
        "journalentry",
        "journalline",
        "post",
        "confirm",
    ):
        assert forbidden not in source


def test_standard_and_requested_delivery_share_same_explanation_truth():
    module = _module()
    resolution = _resolution()
    state = _state(level="none")

    standard = module.prepare_explanation_presentation(resolution, state)
    requested = module.prepare_requested_explanation_presentation(resolution, state)

    assert standard.explanation == requested.explanation
    assert standard.explanation.rule_key == requested.explanation.rule_key
    assert standard.explanation.effects == requested.explanation.effects
    assert standard.presentation_plan != requested.presentation_plan
    assert standard.presentation_view != requested.presentation_view


def test_application_exposes_exact_thin_standard_delivery_delegation(monkeypatch):
    application = importlib.import_module("aqorath.application")
    module = _module()

    assert hasattr(application, "prepare_explanation_presentation")
    assert str(inspect.signature(application.prepare_explanation_presentation)) == (
        "(accounting_resolution, user_state)"
    )

    resolution = object()
    state = object()
    sentinel = object()
    calls = []

    def fake_prepare(value, supplied_state):
        calls.append((value, supplied_state))
        return sentinel

    monkeypatch.setattr(module, "prepare_explanation_presentation", fake_prepare)

    result = application.prepare_explanation_presentation(resolution, state)
    assert result is sentinel
    assert calls == [(resolution, state)]


def test_application_exposes_exact_thin_requested_delivery_delegation(monkeypatch):
    application = importlib.import_module("aqorath.application")
    module = _module()

    assert hasattr(application, "prepare_requested_explanation_presentation")
    assert str(
        inspect.signature(application.prepare_requested_explanation_presentation)
    ) == "(accounting_resolution, user_state)"

    resolution = object()
    state = object()
    sentinel = object()
    calls = []

    def fake_prepare(value, supplied_state):
        calls.append((value, supplied_state))
        return sentinel

    monkeypatch.setattr(
        module,
        "prepare_requested_explanation_presentation",
        fake_prepare,
    )

    result = application.prepare_requested_explanation_presentation(resolution, state)
    assert result is sentinel
    assert calls == [(resolution, state)]


def test_application_delivery_boundaries_do_not_orchestrate_persist_or_format_themselves():
    application = importlib.import_module("aqorath.application")

    standard_source = inspect.getsource(application.prepare_explanation_presentation).lower()
    requested_source = inspect.getsource(
        application.prepare_requested_explanation_presentation
    ).lower()

    assert "_explanation_delivery.prepare_explanation_presentation" in standard_source
    assert (
        "_explanation_delivery.prepare_requested_explanation_presentation"
        in requested_source
    )

    for source in (standard_source, requested_source):
        for forbidden in (
            "session",
            "build_economic_fact_explanation",
            "plan_explanation_presentation",
            "plan_requested_explanation",
            "build_explanation_presentation_view",
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
