"""Phase 6AA.1 — frozen preferred report-format selection contracts.

Architecture anchors:
- UserKnowledgeState keeps preferred_report_format as explicit extensible local truth.
- Presentation may offer different concrete export capabilities for different reports.
- Existing reporting exports include overlapping format names with different semantics,
  so a preference alone must never guess which exporter or report product is intended.

Phase 6AA freezes only deterministic capability selection: choose the user's exact
preferred format from an explicit set of formats available for the current presentation
context. It must not generate a report, invoke exporters, persist preferences, normalize
aliases, or silently fall back when the preference is unavailable.
"""

from __future__ import annotations

from dataclasses import replace
import importlib
import inspect

import pytest


def _module():
    return importlib.import_module("aqorath.report_format_selection")


def _state(*, preferred="xlsx", language="es", separator=".", symbol="MX$"):
    from aqorath.user_knowledge_state import UserKnowledgeState

    return UserKnowledgeState(
        id=1,
        explanation_level="brief",
        concepts_seen=("economic_fact",),
        ui_language=language,
        decimal_separator=separator,
        currency_symbol=symbol,
        preferred_report_format=preferred,
        always_show_professional_view=False,
        learned_topics=(),
    )


def test_selection_public_contract_is_exact_pure_and_capability_only():
    module = _module()

    assert str(inspect.signature(module.select_preferred_report_format)) == (
        "(user_state, available_formats)"
    )

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


def test_selection_requires_nominal_user_knowledge_state():
    module = _module()

    for invalid in (None, object(), {"preferred_report_format": "xlsx"}, "xlsx"):
        with pytest.raises(TypeError):
            module.select_preferred_report_format(invalid, ("xlsx", "pdf"))


def test_available_formats_must_be_exact_tuple():
    module = _module()
    state = _state()

    for invalid in (["xlsx"], {"xlsx"}, "xlsx", None, object()):
        with pytest.raises(TypeError):
            module.select_preferred_report_format(state, invalid)


def test_available_formats_must_not_be_empty():
    module = _module()

    with pytest.raises(ValueError):
        module.select_preferred_report_format(_state(), ())


def test_available_format_items_must_be_explicit_nonblank_text_without_whitespace_normalization():
    module = _module()
    state = _state()

    for invalid in (
        ("xlsx", None),
        ("xlsx", 1),
        ("xlsx", ""),
        ("xlsx", " pdf"),
        ("xlsx", "pdf "),
        ("xlsx", "   "),
    ):
        with pytest.raises((TypeError, ValueError)):
            module.select_preferred_report_format(state, invalid)


def test_available_formats_must_be_unique():
    module = _module()

    with pytest.raises(ValueError):
        module.select_preferred_report_format(
            _state(preferred="xlsx"),
            ("xlsx", "pdf", "xlsx"),
        )


def test_exact_preference_selects_exact_matching_capability_token():
    module = _module()

    preferred = "".join(("structured", "-json"))
    capability = bytearray(b"structured-json").decode()
    assert preferred == capability
    assert preferred is not capability

    selected = module.select_preferred_report_format(
        _state(preferred=preferred),
        ("pdf", capability, "xlsx"),
    )

    assert selected is capability


def test_selection_depends_on_membership_not_available_order():
    module = _module()
    state = _state(preferred="pdf")

    first = module.select_preferred_report_format(
        state,
        ("pdf", "xlsx", "csv"),
    )
    second = module.select_preferred_report_format(
        state,
        ("csv", "xlsx", "pdf"),
    )

    assert first == "pdf"
    assert second == "pdf"


def test_unavailable_preference_fails_closed_without_fallback_to_first_or_any_other_format():
    module = _module()

    with pytest.raises(ValueError):
        module.select_preferred_report_format(
            _state(preferred="pdf"),
            ("xlsx", "csv"),
        )


def test_selection_never_normalizes_case_whitespace_or_format_aliases():
    module = _module()

    cases = (
        ("PDF", ("pdf",)),
        ("pdf", ("PDF",)),
        ("excel", ("xlsx",)),
        ("xlsx", ("excel",)),
        ("structured-json", ("structured_json",)),
    )
    for preferred, available in cases:
        with pytest.raises(ValueError):
            module.select_preferred_report_format(
                _state(preferred=preferred),
                available,
            )


def test_extensible_future_format_is_valid_when_explicitly_available():
    module = _module()
    state = _state(preferred="structured-json")

    assert module.select_preferred_report_format(
        state,
        ("pdf", "xlsx", "structured-json"),
    ) == "structured-json"


def test_selection_does_not_mutate_persisted_preference_or_available_capabilities():
    module = _module()
    state = _state(preferred="xlsx")
    available = ("pdf", "xlsx", "csv")
    before_state = state
    before_available = available

    selected = module.select_preferred_report_format(state, available)

    assert selected == "xlsx"
    assert state is before_state
    assert state.preferred_report_format == "xlsx"
    assert available is before_available
    assert available == ("pdf", "xlsx", "csv")


def test_non_report_user_state_fields_do_not_influence_selection():
    module = _module()
    base = _state(preferred="pdf")
    changed = replace(
        base,
        explanation_level="detailed",
        concepts_seen=("double_entry",),
        ui_language="pt-BR",
        decimal_separator=",",
        currency_symbol="R$",
        always_show_professional_view=True,
    )

    available = ("xlsx", "pdf")
    assert module.select_preferred_report_format(base, available) == "pdf"
    assert module.select_preferred_report_format(changed, available) == "pdf"


def test_selection_is_deterministic_for_same_state_and_capabilities():
    module = _module()
    state = _state(preferred="csv")
    available = ("pdf", "csv", "xlsx")

    first = module.select_preferred_report_format(state, available)
    second = module.select_preferred_report_format(state, available)

    assert first == second == "csv"


def test_selection_does_not_generate_render_or_route_any_report_product_itself():
    module = _module()
    source = inspect.getsource(module).lower()

    for forbidden in (
        "reporting_export",
        "reporting_runtime",
        "reporting_csv",
        "reporting_xlsx",
        "financial_statements_pdf",
        "financial_statements_xlsx",
        "get_financial_report",
        "get_financial_statements",
        "render_",
        "write(",
        "open(",
        "pathlib",
        "storage",
    ):
        assert forbidden not in source


def test_selection_is_presentation_side_and_application_remains_unaware_of_this_authority():
    module = _module()
    application = importlib.import_module("aqorath.application")

    assert module.select_preferred_report_format(
        _state(preferred="pdf"),
        ("xlsx", "pdf"),
    ) == "pdf"

    application_source = inspect.getsource(application).lower()
    assert "report_format_selection" not in application_source
    assert "select_preferred_report_format" not in application_source
