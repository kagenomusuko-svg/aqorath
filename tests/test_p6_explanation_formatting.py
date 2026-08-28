"""Phase 6Z.1 — frozen presentation-side explanation-formatting contracts.

Constitution anchors:
- R11 keeps explanation derived from structured deterministic accounting truth.
- R12 requires explanation to remain usable while respecting explicit user preferences.
- Architecture assigns final formatting to Presentation after Application has prepared data.

Phase 6Z freezes deterministic display formatting of an already-prepared explanation
package. Formatting may translate known semantic labels and format visible Decimal amounts
from explicit UI preferences, but it must never re-plan, persist, infer, re-resolve, or
resurrect fields hidden by the prepared presentation view.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from decimal import Decimal
import importlib
import inspect

import pytest


EFFECT_FIELDS = (
    "account_label",
    "side_label",
    "amount_text",
)

DISPLAY_FIELDS = (
    "ui_language",
    "fact_type_label",
    "payment_method_label",
    "amount_text",
    "effects",
    "concept_labels",
    "professional_summary",
)


def _module():
    return importlib.import_module("aqorath.explanation_formatting")


def _state(
    *,
    language="es",
    decimal_separator=",",
    currency_symbol="MX$",
    explanation_level="detailed",
    concepts_seen=(),
    always_professional=True,
    preferred_report_format="xlsx",
    learned_topics=(),
):
    from aqorath.user_knowledge_state import UserKnowledgeState

    return UserKnowledgeState(
        id=1,
        explanation_level=explanation_level,
        concepts_seen=concepts_seen,
        ui_language=language,
        decimal_separator=decimal_separator,
        currency_symbol=currency_symbol,
        preferred_report_format=preferred_report_format,
        always_show_professional_view=always_professional,
        learned_topics=learned_topics,
    )


def _prepared(
    *,
    fact_type="sale",
    payment_method="cash",
    amount=Decimal("125.5000"),
    effects=None,
    concepts=("economic_fact", "double_entry"),
    professional_summary="Sale transaction: 125.5000 received in cash.",
    visible_fact_type=None,
    visible_payment_method=None,
    visible_amount=None,
    visible_effects=None,
    visible_concepts=None,
    visible_professional_summary=None,
):
    from aqorath.explanation import ExplanationData, ExplanationEffect
    from aqorath.explanation_delivery import PreparedExplanationPresentation
    from aqorath.explanation_presentation import ExplanationPresentationPlan
    from aqorath.explanation_view import ExplanationPresentationView

    if effects is None:
        effects = (
            ExplanationEffect("cash", "debit", amount),
            ExplanationEffect("sales_revenue", "credit", amount),
        )

    explanation = ExplanationData(
        fact_type=fact_type,
        payment_method=payment_method,
        amount=amount,
        rule_key=f"economic_fact:{fact_type}:{payment_method}",
        effects=effects,
        concepts=concepts,
        professional_summary=professional_summary,
    )

    if visible_fact_type is None:
        visible_fact_type = fact_type
    if visible_payment_method is None:
        visible_payment_method = payment_method
    if visible_amount is None:
        visible_amount = amount
    if visible_effects is None:
        visible_effects = effects
    if visible_concepts is None:
        visible_concepts = concepts
    if visible_professional_summary is None:
        visible_professional_summary = professional_summary

    plan = ExplanationPresentationPlan(
        explanation_level="detailed",
        show_common_explanation=visible_fact_type is not None,
        show_structured_effects=bool(visible_effects),
        concepts_to_present=visible_concepts,
        show_professional_view=visible_professional_summary is not None,
    )
    view = ExplanationPresentationView(
        fact_type=visible_fact_type,
        payment_method=visible_payment_method,
        amount=visible_amount,
        effects=visible_effects,
        concepts=visible_concepts,
        professional_summary=visible_professional_summary,
    )
    return PreparedExplanationPresentation(
        explanation=explanation,
        presentation_plan=plan,
        presentation_view=view,
    )


def _hidden_prepared():
    from aqorath.explanation import ExplanationData, ExplanationEffect
    from aqorath.explanation_delivery import PreparedExplanationPresentation
    from aqorath.explanation_presentation import ExplanationPresentationPlan
    from aqorath.explanation_view import ExplanationPresentationView

    amount = Decimal("777.2500")
    explanation = ExplanationData(
        fact_type="sale",
        payment_method="cash",
        amount=amount,
        rule_key="economic_fact:sale:cash",
        effects=(
            ExplanationEffect("cash", "debit", amount),
            ExplanationEffect("sales_revenue", "credit", amount),
        ),
        concepts=("economic_fact", "double_entry"),
        professional_summary="This underlying truth must remain hidden.",
    )
    plan = ExplanationPresentationPlan(
        explanation_level="none",
        show_common_explanation=False,
        show_structured_effects=False,
        concepts_to_present=(),
        show_professional_view=False,
    )
    view = ExplanationPresentationView(
        fact_type=None,
        payment_method=None,
        amount=None,
        effects=(),
        concepts=(),
        professional_summary=None,
    )
    return PreparedExplanationPresentation(explanation, plan, view)


def test_formatting_public_contract_is_exact_frozen_pure_and_presentation_side():
    module = _module()

    assert tuple(field.name for field in fields(module.FormattedExplanationEffect)) == (
        EFFECT_FIELDS
    )
    assert tuple(
        field.name for field in fields(module.FormattedExplanationPresentation)
    ) == DISPLAY_FIELDS
    assert str(inspect.signature(module.format_explanation_presentation)) == (
        "(prepared, user_state)"
    )

    formatted = module.format_explanation_presentation(_prepared(), _state())
    with pytest.raises(FrozenInstanceError):
        formatted.amount_text = "changed"
    with pytest.raises(FrozenInstanceError):
        formatted.effects[0].amount_text = "changed"

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
    ):
        assert forbidden not in source


def test_formatting_requires_nominal_prepared_explanation_presentation():
    module = _module()
    state = _state()

    for invalid in (None, object(), {"presentation_view": object()}, "prepared"):
        with pytest.raises(TypeError):
            module.format_explanation_presentation(invalid, state)


def test_formatting_requires_nominal_user_knowledge_state():
    module = _module()
    prepared = _prepared()

    for invalid in (None, object(), {"ui_language": "es"}, "state"):
        with pytest.raises(TypeError):
            module.format_explanation_presentation(prepared, invalid)


def test_ui_language_is_explicit_exact_es_or_en_without_normalization():
    module = _module()
    prepared = _prepared()

    assert module.format_explanation_presentation(
        prepared,
        _state(language="es"),
    ).ui_language == "es"
    assert module.format_explanation_presentation(
        prepared,
        _state(language="en"),
    ).ui_language == "en"

    for unsupported in ("ES", "EN", "es-MX", "en-US", " es", "es ", "fr"):
        with pytest.raises(ValueError):
            module.format_explanation_presentation(
                prepared,
                _state(language=unsupported),
            )


def test_hidden_view_stays_hidden_and_never_resurrects_underlying_truth():
    module = _module()

    formatted = module.format_explanation_presentation(
        _hidden_prepared(),
        _state(language="es", decimal_separator=",", currency_symbol="MX$"),
    )

    assert formatted == module.FormattedExplanationPresentation(
        ui_language="es",
        fact_type_label=None,
        payment_method_label=None,
        amount_text=None,
        effects=(),
        concept_labels=(),
        professional_summary=None,
    )


def test_dot_decimal_separator_and_currency_symbol_format_visible_money_exactly():
    module = _module()

    formatted = module.format_explanation_presentation(
        _prepared(amount=Decimal("125.5000")),
        _state(language="en", decimal_separator=".", currency_symbol="$"),
    )

    assert formatted.amount_text == "$ 125.5000"
    assert tuple(effect.amount_text for effect in formatted.effects) == (
        "$ 125.5000",
        "$ 125.5000",
    )


def test_comma_decimal_separator_and_currency_symbol_format_visible_money_exactly():
    module = _module()

    formatted = module.format_explanation_presentation(
        _prepared(amount=Decimal("125.5000")),
        _state(language="es", decimal_separator=",", currency_symbol="MX$"),
    )

    assert formatted.amount_text == "MX$ 125,5000"
    assert tuple(effect.amount_text for effect in formatted.effects) == (
        "MX$ 125,5000",
        "MX$ 125,5000",
    )


def test_money_formatting_preserves_decimal_scale_without_rounding_or_grouping():
    module = _module()

    cases = (
        (Decimal("1.2300"), ".", "USD", "USD 1.2300"),
        (Decimal("1234567.890100"), ".", "$", "$ 1234567.890100"),
        (Decimal("1234567.890100"), ",", "€", "€ 1234567,890100"),
    )
    for amount, separator, symbol, expected in cases:
        formatted = module.format_explanation_presentation(
            _prepared(amount=amount),
            _state(
                language="en",
                decimal_separator=separator,
                currency_symbol=symbol,
            ),
        )
        assert formatted.amount_text == expected

    source = inspect.getsource(module).lower()
    for forbidden in ("quantize", "float(", "round(", "locale", "babel"):
        assert forbidden not in source


def test_english_labels_cover_current_visible_semantic_vocabulary():
    module = _module()
    state = _state(language="en", decimal_separator=".", currency_symbol="$" )

    fact_labels = {
        "sale": "Sale",
        "utility_expense": "Utility expense",
        "utility_expense_incurred": "Utility expense incurred",
        "receivable_collection": "Receivable collection",
        "supplier_payment": "Supplier payment",
    }
    payment_labels = {
        "cash": "Cash",
        "credit": "Credit",
        "bank": "Bank",
    }
    account_labels = {
        "cash": "Cash",
        "sales_revenue": "Sales revenue",
        "accounts_receivable": "Accounts receivable",
        "utilities_expense": "Utilities expense",
        "bank": "Bank",
        "accounts_payable": "Accounts payable",
    }

    from aqorath.explanation import ExplanationEffect

    for code, label in fact_labels.items():
        formatted = module.format_explanation_presentation(
            _prepared(fact_type=code),
            state,
        )
        assert formatted.fact_type_label == label

    for code, label in payment_labels.items():
        formatted = module.format_explanation_presentation(
            _prepared(payment_method=code),
            state,
        )
        assert formatted.payment_method_label == label

    for code, label in account_labels.items():
        amount = Decimal("9.00")
        formatted = module.format_explanation_presentation(
            _prepared(
                amount=amount,
                effects=(ExplanationEffect(code, "debit", amount),),
            ),
            state,
        )
        assert formatted.effects[0].account_label == label

    formatted = module.format_explanation_presentation(_prepared(), state)
    assert tuple(effect.side_label for effect in formatted.effects) == ("Debit", "Credit")
    assert formatted.concept_labels == ("Economic fact", "Double-entry accounting")


def test_spanish_labels_cover_current_visible_semantic_vocabulary():
    module = _module()
    state = _state(language="es", decimal_separator=",", currency_symbol="MX$")

    fact_labels = {
        "sale": "Venta",
        "utility_expense": "Gasto de servicios",
        "utility_expense_incurred": "Gasto de servicios devengado",
        "receivable_collection": "Cobro de cuenta por cobrar",
        "supplier_payment": "Pago a proveedor",
    }
    payment_labels = {
        "cash": "Efectivo",
        "credit": "Crédito",
        "bank": "Banco",
    }
    account_labels = {
        "cash": "Efectivo",
        "sales_revenue": "Ingresos por ventas",
        "accounts_receivable": "Cuentas por cobrar",
        "utilities_expense": "Gastos de servicios",
        "bank": "Banco",
        "accounts_payable": "Cuentas por pagar",
    }

    from aqorath.explanation import ExplanationEffect

    for code, label in fact_labels.items():
        formatted = module.format_explanation_presentation(
            _prepared(fact_type=code),
            state,
        )
        assert formatted.fact_type_label == label

    for code, label in payment_labels.items():
        formatted = module.format_explanation_presentation(
            _prepared(payment_method=code),
            state,
        )
        assert formatted.payment_method_label == label

    for code, label in account_labels.items():
        amount = Decimal("9.00")
        formatted = module.format_explanation_presentation(
            _prepared(
                amount=amount,
                effects=(ExplanationEffect(code, "debit", amount),),
            ),
            state,
        )
        assert formatted.effects[0].account_label == label

    formatted = module.format_explanation_presentation(_prepared(), state)
    assert tuple(effect.side_label for effect in formatted.effects) == ("Debe", "Haber")
    assert formatted.concept_labels == ("Hecho económico", "Partida doble")


def test_formatted_effects_preserve_visible_order_and_use_each_exact_visible_amount():
    module = _module()
    from aqorath.explanation import ExplanationEffect

    effects = (
        ExplanationEffect("accounts_receivable", "debit", Decimal("10.100")),
        ExplanationEffect("sales_revenue", "credit", Decimal("20.2000")),
        ExplanationEffect("bank", "debit", Decimal("30.30000")),
    )
    formatted = module.format_explanation_presentation(
        _prepared(amount=Decimal("1.0"), effects=effects),
        _state(language="en", decimal_separator=".", currency_symbol="$"),
    )

    assert tuple(effect.account_label for effect in formatted.effects) == (
        "Accounts receivable",
        "Sales revenue",
        "Bank",
    )
    assert tuple(effect.side_label for effect in formatted.effects) == (
        "Debit",
        "Credit",
        "Debit",
    )
    assert tuple(effect.amount_text for effect in formatted.effects) == (
        "$ 10.100",
        "$ 20.2000",
        "$ 30.30000",
    )


def test_concept_labels_preserve_exact_visible_order_and_do_not_add_hidden_concepts():
    module = _module()
    from aqorath.explanation import ExplanationData, ExplanationEffect
    from aqorath.explanation_delivery import PreparedExplanationPresentation
    from aqorath.explanation_presentation import ExplanationPresentationPlan
    from aqorath.explanation_view import ExplanationPresentationView

    amount = Decimal("25.00")
    explanation = ExplanationData(
        fact_type="sale",
        payment_method="cash",
        amount=amount,
        rule_key="economic_fact:sale:cash",
        effects=(ExplanationEffect("cash", "debit", amount),),
        concepts=("economic_fact", "double_entry"),
        professional_summary="Professional truth.",
    )
    plan = ExplanationPresentationPlan(
        explanation_level="brief",
        show_common_explanation=True,
        show_structured_effects=False,
        concepts_to_present=("double_entry",),
        show_professional_view=False,
    )
    view = ExplanationPresentationView(
        fact_type="sale",
        payment_method="cash",
        amount=amount,
        effects=(),
        concepts=("double_entry",),
        professional_summary=None,
    )
    prepared = PreparedExplanationPresentation(explanation, plan, view)

    formatted = module.format_explanation_presentation(
        prepared,
        _state(language="es"),
    )

    assert formatted.concept_labels == ("Partida doble",)
    assert "Hecho económico" not in formatted.concept_labels


def test_professional_summary_is_passed_through_exactly_without_translation_or_rewriting():
    module = _module()
    summary = "Exact professional summary — 125.5000; DR cash / CR revenue."
    prepared = _prepared(professional_summary=summary)

    spanish = module.format_explanation_presentation(prepared, _state(language="es"))
    english = module.format_explanation_presentation(prepared, _state(language="en"))

    assert spanish.professional_summary is summary
    assert english.professional_summary is summary


def test_unknown_visible_semantic_codes_fail_closed_instead_of_leaking_internal_keys():
    module = _module()
    from aqorath.explanation import ExplanationData, ExplanationEffect
    from aqorath.explanation_delivery import PreparedExplanationPresentation
    from aqorath.explanation_presentation import ExplanationPresentationPlan
    from aqorath.explanation_view import ExplanationPresentationView

    state = _state(language="en")
    amount = Decimal("1.00")

    cases = (
        ExplanationPresentationView(
            fact_type="unknown_fact",
            payment_method="cash",
            amount=amount,
            effects=(),
            concepts=(),
            professional_summary=None,
        ),
        ExplanationPresentationView(
            fact_type="sale",
            payment_method="unknown_method",
            amount=amount,
            effects=(),
            concepts=(),
            professional_summary=None,
        ),
        ExplanationPresentationView(
            fact_type="sale",
            payment_method="cash",
            amount=amount,
            effects=(ExplanationEffect("unknown_role", "debit", amount),),
            concepts=(),
            professional_summary=None,
        ),
        ExplanationPresentationView(
            fact_type="sale",
            payment_method="cash",
            amount=amount,
            effects=(),
            concepts=("unknown_concept",),
            professional_summary=None,
        ),
    )

    explanation = ExplanationData(
        fact_type="sale",
        payment_method="cash",
        amount=amount,
        rule_key="economic_fact:sale:cash",
        effects=(ExplanationEffect("cash", "debit", amount),),
        concepts=("economic_fact",),
        professional_summary="Truth.",
    )

    for view in cases:
        plan = ExplanationPresentationPlan(
            explanation_level="detailed",
            show_common_explanation=view.fact_type is not None,
            show_structured_effects=bool(view.effects),
            concepts_to_present=view.concepts,
            show_professional_view=False,
        )
        prepared = PreparedExplanationPresentation(explanation, plan, view)
        with pytest.raises(ValueError):
            module.format_explanation_presentation(prepared, state)


def test_formatting_is_deterministic_and_never_mutates_prepared_package_or_user_state():
    module = _module()
    prepared = _prepared()
    state = _state(language="es", decimal_separator=",", currency_symbol="MX$")
    before_view = prepared.presentation_view
    before_effects = prepared.presentation_view.effects
    before_concepts = prepared.presentation_view.concepts
    before_state = state

    first = module.format_explanation_presentation(prepared, state)
    second = module.format_explanation_presentation(prepared, state)

    assert first == second
    assert prepared.presentation_view is before_view
    assert prepared.presentation_view.effects is before_effects
    assert prepared.presentation_view.concepts is before_concepts
    assert state is before_state
    assert not hasattr(first, "created_at")
    assert not hasattr(first, "generated_at")


def test_formatting_uses_only_visible_view_and_explicit_display_preferences_not_application_logic():
    module = _module()
    source = inspect.getsource(module).lower()

    for required in ("ui_language", "decimal_separator", "currency_symbol"):
        assert required in source

    for forbidden in (
        "preferred_report_format",
        "explanation_level",
        "concepts_seen",
        "always_show_professional_view",
        "learned_topics",
        "build_economic_fact_explanation",
        "plan_explanation_presentation",
        "plan_requested_explanation",
        "build_explanation_presentation_view",
        "prepare_explanation_presentation",
        "prepare_requested_explanation_presentation",
        "record_presented_concepts",
        "record_learned_topic",
        "record_explanation_presentation",
        "record_user_topic_learning",
        "resolve_economic_fact(",
        "journalentry",
        "journalline",
        "post",
        "confirm",
    ):
        assert forbidden not in source

    application = importlib.import_module("aqorath.application")
    application_source = inspect.getsource(application).lower()
    assert "explanation_formatting" not in application_source
    assert "formatexplanationpresentation" not in application_source
