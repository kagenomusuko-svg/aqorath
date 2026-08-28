"""Phase 6AG.1 — frozen ReportDefinition/ReportRequest compatibility contracts.

R18 separates WHAT report exists from WHAT to generate this time. 6AG freezes only the
intrinsic bridge between those two already-frozen values: a concrete request must point
to the supplied persisted definition and request one of that definition's exact supported
format tokens. Entity applicability, effective fiscal requirements, required-data
availability, query execution, rendering, persistence, and report generation remain
outside this authority.
"""

from dataclasses import replace
from datetime import date
import importlib
import inspect

import pytest


def _definition(**patch):
    from aqorath.report_definition import ReportDefinition

    values = dict(
        id=3,
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


def _request(**patch):
    from aqorath.report_request import ReportRequest

    values = dict(
        id=None,
        report_definition_id=3,
        entity_id=1,
        from_date=date(2026, 1, 1),
        to_date=date(2026, 12, 31),
        as_of_date=None,
        filters=(("state", "posted"),),
        dimensions_to_group=("program",),
        format="pdf",
    )
    values.update(patch)
    return ReportRequest(**values)


def _module():
    return importlib.import_module("aqorath.report_request_compatibility")


def test_compatibility_public_contract_is_exact_and_pure():
    module = _module()

    assert str(inspect.signature(module.validate_report_request_against_definition)) == (
        "(definition, request)"
    )

    source = inspect.getsource(module).lower()
    for forbidden in (
        "sqlmodel",
        "sqlalchemy",
        "sqlite3",
        "requests",
        "fastapi",
        "openai",
        "llm",
    ):
        assert forbidden not in source


def test_compatibility_requires_nominal_report_definition():
    module = _module()
    request = _request()

    for invalid in (None, object(), {"id": 3}, "report"):
        with pytest.raises(TypeError):
            module.validate_report_request_against_definition(invalid, request)


def test_compatibility_requires_definition_to_have_persisted_identity():
    module = _module()

    with pytest.raises(ValueError):
        module.validate_report_request_against_definition(
            _definition(id=None),
            _request(report_definition_id=3),
        )


def test_compatibility_requires_nominal_report_request():
    module = _module()
    definition = _definition()

    for invalid in (None, object(), {"report_definition_id": 3}, "pdf"):
        with pytest.raises(TypeError):
            module.validate_report_request_against_definition(definition, invalid)


def test_request_must_reference_exact_supplied_definition_identity():
    module = _module()

    with pytest.raises(ValueError):
        module.validate_report_request_against_definition(
            _definition(id=3),
            _request(report_definition_id=4),
        )

    request = _request(report_definition_id=3)
    assert module.validate_report_request_against_definition(
        _definition(id=3),
        request,
    ) is request


def test_exact_supported_format_returns_the_exact_request_object():
    module = _module()
    request = _request(format="xlsx")

    validated = module.validate_report_request_against_definition(
        _definition(supported_formats=("pdf", "xlsx")),
        request,
    )

    assert validated is request
    assert validated.format == "xlsx"


def test_format_compatibility_depends_on_membership_not_supported_format_order():
    module = _module()
    request = _request(format="pdf")

    first = module.validate_report_request_against_definition(
        _definition(supported_formats=("pdf", "xlsx", "csv")),
        request,
    )
    second = module.validate_report_request_against_definition(
        _definition(supported_formats=("csv", "xlsx", "pdf")),
        request,
    )

    assert first is request
    assert second is request


def test_unsupported_requested_format_fails_closed_without_fallback():
    module = _module()

    with pytest.raises(ValueError):
        module.validate_report_request_against_definition(
            _definition(supported_formats=("xlsx", "csv")),
            _request(format="pdf"),
        )


def test_compatibility_never_normalizes_format_case_whitespace_or_aliases():
    module = _module()

    cases = (
        ("PDF", ("pdf",)),
        ("pdf", ("PDF",)),
        ("excel", ("xlsx",)),
        ("xlsx", ("excel",)),
        ("structured-json", ("structured_json",)),
    )
    for requested_format, supported_formats in cases:
        with pytest.raises(ValueError):
            module.validate_report_request_against_definition(
                _definition(supported_formats=supported_formats),
                _request(format=requested_format),
            )


def test_extensible_future_format_is_compatible_when_explicitly_supported():
    module = _module()
    request = _request(format="future-open-format")

    assert module.validate_report_request_against_definition(
        _definition(supported_formats=("pdf", "future-open-format")),
        request,
    ) is request


def test_compatibility_does_not_mutate_definition_or_request():
    module = _module()
    definition = _definition()
    request = _request()

    before_definition = definition
    before_request = request
    validated = module.validate_report_request_against_definition(
        definition,
        request,
    )

    assert definition is before_definition
    assert request is before_request
    assert validated is before_request
    assert definition.supported_formats == ("pdf", "xlsx")
    assert request.report_definition_id == 3
    assert request.format == "pdf"


def test_non_compatibility_definition_metadata_does_not_change_result():
    module = _module()
    base = _definition()
    changed = replace(
        base,
        name="Otro nombre",
        description="Otra descripción",
        required_data=("future-data",),
        requires_capabilities=("osc",),
        forbidden_capabilities=("payroll",),
        required_fiscal_features=("requires_cfdi",),
        renderer_id="future.renderer",
        query_template_id="future.query",
    )
    request = _request()

    assert module.validate_report_request_against_definition(base, request) is request
    assert module.validate_report_request_against_definition(changed, request) is request


def test_request_generation_parameters_do_not_change_intrinsic_compatibility():
    module = _module()
    definition = _definition()
    base = _request()
    changed = replace(
        base,
        entity_id=999_999,
        from_date=date(2025, 1, 1),
        to_date=date(2027, 12, 31),
        as_of_date=date(2028, 1, 15),
        filters=(("opaque", object()),),
        dimensions_to_group=("FutureDimension",),
    )

    assert module.validate_report_request_against_definition(definition, base) is base
    assert module.validate_report_request_against_definition(definition, changed) is changed


def test_compatibility_does_not_evaluate_entity_fiscal_capability_or_required_data_availability():
    module = _module()
    definition = _definition(
        required_data=("not-yet-available-data",),
        requires_capabilities=("future-capability",),
        forbidden_capabilities=("another-capability",),
        required_fiscal_features=("future-fiscal-feature",),
    )
    request = _request(entity_id=777_777)

    assert module.validate_report_request_against_definition(
        definition,
        request,
    ) is request

    source = inspect.getsource(module).lower()
    for forbidden in (
        "entity_repository",
        "resolve_fiscal_profile",
        "fiscal_profile",
        "fiscal_rule",
        "load_active_entity",
        "required_data_available",
    ):
        assert forbidden not in source


def test_compatibility_is_deterministic_and_does_not_touch_runtime_exporters_storage_or_preferences():
    module = _module()
    definition = _definition()
    request = _request()

    first = module.validate_report_request_against_definition(definition, request)
    second = module.validate_report_request_against_definition(definition, request)
    assert first is second is request

    source = inspect.getsource(module).lower()
    for forbidden in (
        "reporting_runtime",
        "reporting_export",
        "reporting_csv",
        "reporting_xlsx",
        "financial_statements_pdf",
        "financial_statements_xlsx",
        "storage",
        "get_session",
        "user_knowledge_state",
        "preferred_report_format",
        "datetime.now",
        "datetime.utcnow",
        "time.time",
        "random",
        "uuid",
        "os.environ",
    ):
        assert forbidden not in source


def test_compatibility_does_not_generate_render_persist_or_enter_application_layer():
    module = _module()
    application = importlib.import_module("aqorath.application")

    for forbidden_name in (
        "generate_report",
        "render_report",
        "execute_report",
        "create_report_request",
        "save_report_request",
        "is_report_available",
    ):
        assert not hasattr(module, forbidden_name)

    application_source = inspect.getsource(application).lower()
    assert "report_request_compatibility" not in application_source
    assert "validate_report_request_against_definition" not in application_source
