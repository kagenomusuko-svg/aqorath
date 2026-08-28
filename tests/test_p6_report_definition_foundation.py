"""Phase 6AE.1 — frozen ReportDefinition domain contracts.

R18 requires a report definition to describe WHAT document exists independently from
one concrete generation request. This phase freezes only the immutable definition value.
It does not decide applicability for one Entity/FiscalProfile, select a user-preferred
format, execute queries, render output, persist definitions, or generate reports.
"""

from dataclasses import FrozenInstanceError, fields
import inspect

import pytest


REPORT_DEFINITION_FIELDS = (
    "id",
    "name",
    "description",
    "required_data",
    "supported_formats",
    "requires_capabilities",
    "forbidden_capabilities",
    "required_fiscal_features",
    "renderer_id",
    "query_template_id",
)


def _definition(**patch):
    from aqorath.report_definition import ReportDefinition

    values = dict(
        id=None,
        name="Estado financiero",
        description="Documento financiero formal",
        required_data=("accounts", "journal_entries"),
        supported_formats=("pdf", "xlsx"),
        requires_capabilities=(),
        forbidden_capabilities=(),
        required_fiscal_features=(),
        renderer_id="financial_statements",
        query_template_id="financial_snapshot",
    )
    values.update(patch)
    return ReportDefinition(**values)


def test_report_definition_is_pure_frozen_and_has_exact_architecture_fields():
    import aqorath.report_definition as domain
    from aqorath.report_definition import ReportDefinition

    definition = _definition()
    assert tuple(field.name for field in fields(ReportDefinition)) == REPORT_DEFINITION_FIELDS

    with pytest.raises(FrozenInstanceError):
        definition.name = "Cambiado"

    source = inspect.getsource(domain).lower()
    for forbidden in (
        "sqlmodel",
        "sqlalchemy",
        "sqlite3",
        "requests",
        "openai",
        "llm",
    ):
        assert forbidden not in source


def test_report_definition_id_is_none_before_identity_or_exact_positive_int():
    assert _definition(id=None).id is None
    assert _definition(id=7).id == 7

    for invalid in (0, -1, True, 1.0, "1"):
        with pytest.raises((TypeError, ValueError)):
            _definition(id=invalid)


def test_report_definition_requires_explicit_nonblank_text_fields_without_normalization():
    for field_name in (
        "name",
        "description",
        "renderer_id",
        "query_template_id",
    ):
        for invalid in (None, 7, "", " value", "value ", "   "):
            with pytest.raises((TypeError, ValueError)):
                _definition(**{field_name: invalid})

    exact = _definition(
        name="Balanza de comprobación",
        description="Vista profesional exacta",
        renderer_id="renderer.v2",
        query_template_id="query-template.v3",
    )
    assert exact.name == "Balanza de comprobación"
    assert exact.description == "Vista profesional exacta"
    assert exact.renderer_id == "renderer.v2"
    assert exact.query_template_id == "query-template.v3"


def test_report_definition_collection_fields_must_be_exact_immutable_tuples():
    for field_name in (
        "required_data",
        "supported_formats",
        "requires_capabilities",
        "forbidden_capabilities",
        "required_fiscal_features",
    ):
        for invalid in ([], set(), {}, "pdf", None):
            with pytest.raises(TypeError):
                _definition(**{field_name: invalid})


def test_report_definition_requires_at_least_one_supported_format():
    with pytest.raises(ValueError):
        _definition(supported_formats=())

    assert _definition(supported_formats=("pdf",)).supported_formats == ("pdf",)


def test_report_definition_allows_empty_data_and_applicability_requirements():
    definition = _definition(
        required_data=(),
        requires_capabilities=(),
        forbidden_capabilities=(),
        required_fiscal_features=(),
    )
    assert definition.required_data == ()
    assert definition.requires_capabilities == ()
    assert definition.forbidden_capabilities == ()
    assert definition.required_fiscal_features == ()


def test_report_definition_tuple_items_are_explicit_nonblank_tokens():
    for field_name in (
        "required_data",
        "supported_formats",
        "requires_capabilities",
        "forbidden_capabilities",
        "required_fiscal_features",
    ):
        for invalid_item in (None, 7, "", " token", "token ", "   "):
            with pytest.raises((TypeError, ValueError)):
                _definition(**{field_name: (invalid_item,)})


def test_report_definition_rejects_duplicate_tokens_inside_each_collection():
    for field_name in (
        "required_data",
        "supported_formats",
        "requires_capabilities",
        "forbidden_capabilities",
        "required_fiscal_features",
    ):
        with pytest.raises(ValueError):
            _definition(**{field_name: ("same", "same")})


def test_report_definition_rejects_capability_that_is_both_required_and_forbidden():
    with pytest.raises(ValueError):
        _definition(
            requires_capabilities=("osc", "inventory"),
            forbidden_capabilities=("payroll", "osc"),
        )


def test_report_definition_tokens_are_open_and_extensible_not_closed_enums():
    definition = _definition(
        required_data=("future-ledger-projection",),
        supported_formats=("structured-json", "future-open-format"),
        requires_capabilities=("future-capability",),
        forbidden_capabilities=("future-conflict",),
        required_fiscal_features=("future-fiscal-feature",),
        renderer_id="future.renderer",
        query_template_id="future.query",
    )
    assert definition.supported_formats == (
        "structured-json",
        "future-open-format",
    )
    assert definition.requires_capabilities == ("future-capability",)


def test_report_definition_preserves_exact_token_case_order_and_spelling():
    definition = _definition(
        required_data=("JournalEntries", "accounts"),
        supported_formats=("PDF", "pdf", "xlsx"),
        requires_capabilities=("OSC", "osc"),
        forbidden_capabilities=("Payroll",),
        required_fiscal_features=("RequiresCFDI", "requires_cfdi"),
    )
    assert definition.required_data == ("JournalEntries", "accounts")
    assert definition.supported_formats == ("PDF", "pdf", "xlsx")
    assert definition.requires_capabilities == ("OSC", "osc")
    assert definition.required_fiscal_features == (
        "RequiresCFDI",
        "requires_cfdi",
    )


def test_report_definition_separates_document_identity_from_generation_request_fields():
    from aqorath.report_definition import ReportDefinition

    field_names = {field.name for field in fields(ReportDefinition)}
    request_only_fields = {
        "entity_id",
        "from_date",
        "to_date",
        "as_of_date",
        "filters",
        "dimensions_to_group",
        "format",
        "output_path",
    }
    assert field_names.isdisjoint(request_only_fields)


def test_report_definition_keeps_renderer_and_query_ids_opaque_and_does_not_resolve_them():
    definition = _definition(
        renderer_id="does.not.exist.renderer",
        query_template_id="does.not.exist.query",
    )
    assert definition.renderer_id == "does.not.exist.renderer"
    assert definition.query_template_id == "does.not.exist.query"


def test_report_definition_does_not_import_runtime_exporters_storage_or_user_preferences():
    import aqorath.report_definition as domain

    source = inspect.getsource(domain).lower()
    for forbidden in (
        "reporting_runtime",
        "reporting_export",
        "storage",
        "get_session",
        "models",
        "user_knowledge_state",
        "preferred_report_format",
        "format_explanation",
    ):
        assert forbidden not in source


def test_report_definition_is_deterministic_value_truth_without_time_random_or_environment():
    import aqorath.report_definition as domain

    one = _definition(id=3)
    two = _definition(id=3)
    assert one == two
    assert hash(one) == hash(two)

    source = inspect.getsource(domain).lower()
    for forbidden in (
        "datetime.now",
        "datetime.utcnow",
        "time.time",
        "random",
        "uuid",
        "os.environ",
    ):
        assert forbidden not in source


def test_report_definition_foundation_does_not_generate_render_select_or_persist_reports():
    import aqorath.report_definition as domain

    for forbidden_name in (
        "generate_report",
        "render_report",
        "execute_report",
        "select_report_format",
        "select_preferred_report_format",
        "create_report_definition",
        "save_report_definition",
        "is_report_available",
    ):
        assert not hasattr(domain, forbidden_name)
