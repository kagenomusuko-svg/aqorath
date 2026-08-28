"""Phase 6AK.1 — frozen ReportPackage domain contracts.

R19 defines packages as official presets: initial report selections with suggested
parameters, never closed containers that limit what the user may ultimately generate.
The architecture gives ReportPackage a concrete shape, while required-data availability
still lacks enough semantics for a safe authority. This phase therefore freezes only the
pure immutable official ReportPackage value. It does not personalize selections, create a
CustomReportPackage, generate reports, persist packages, or enter Application.
"""

from dataclasses import FrozenInstanceError, fields
import inspect

import pytest


REPORT_PACKAGE_FIELDS = (
    "id",
    "name",
    "included_reports",
    "suggested_parameters",
    "is_official",
)


def _definition(**patch):
    from aqorath.report_definition import ReportDefinition

    values = dict(
        id=3,
        name="Balanza",
        description="Balanza profesional",
        required_data=("journal_entries",),
        supported_formats=("pdf", "xlsx"),
        requires_capabilities=(),
        forbidden_capabilities=(),
        required_fiscal_features=(),
        renderer_id="trial_balance",
        query_template_id="trial_balance_snapshot",
    )
    values.update(patch)
    return ReportDefinition(**values)


def _package(**patch):
    from aqorath.report_package import ReportPackage

    values = dict(
        id=None,
        name="Bancos",
        included_reports=(_definition(),),
        suggested_parameters=(("format", "pdf"),),
    )
    values.update(patch)
    return ReportPackage(**values)


def test_report_package_is_pure_frozen_and_has_exact_architecture_fields():
    import aqorath.report_package as domain
    from aqorath.report_package import ReportPackage

    package = _package()
    assert tuple(field.name for field in fields(ReportPackage)) == REPORT_PACKAGE_FIELDS

    with pytest.raises(FrozenInstanceError):
        package.name = "Cambiado"

    source = inspect.getsource(domain).lower()
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


def test_report_package_id_is_none_before_identity_or_exact_positive_int():
    assert _package(id=None).id is None
    assert _package(id=7).id == 7

    for invalid in (0, -1, True, 1.0, "1"):
        with pytest.raises((TypeError, ValueError)):
            _package(id=invalid)


def test_report_package_name_is_exact_nonblank_text_without_normalization():
    for invalid in (None, 7, "", " Bancos", "Bancos ", "   "):
        with pytest.raises((TypeError, ValueError)):
            _package(name=invalid)

    package = _package(name="Bancos y Tesorería")
    assert package.name == "Bancos y Tesorería"


def test_included_reports_must_be_exact_immutable_tuple():
    for invalid in ([], set(), {}, "Balanza", None):
        with pytest.raises(TypeError):
            _package(included_reports=invalid)


def test_included_reports_items_must_be_nominal_report_definitions():
    valid = _definition()
    for invalid in (
        (object(),),
        ({"name": "Balanza"},),
        (valid, object()),
    ):
        with pytest.raises(TypeError):
            _package(included_reports=invalid)


def test_included_reports_may_be_empty_and_preserve_exact_order_and_identity():
    empty = _package(included_reports=())
    assert empty.included_reports == ()

    first = _definition(id=1, name="Primero")
    second = _definition(id=2, name="Segundo")
    reports = (second, first)
    package = _package(included_reports=reports)

    assert package.included_reports is reports
    assert package.included_reports == (second, first)
    assert package.included_reports[0] is second
    assert package.included_reports[1] is first


def test_package_does_not_require_persisted_report_definition_identity_or_resolve_reports():
    transient = _definition(
        id=None,
        renderer_id="future.renderer",
        query_template_id="future.query",
    )
    package = _package(included_reports=(transient,))

    assert package.included_reports[0] is transient
    assert package.included_reports[0].id is None


def test_suggested_parameters_must_be_exact_tuple_of_exact_two_item_tuples():
    for invalid in ([], {}, set(), "format=pdf", None):
        with pytest.raises(TypeError):
            _package(suggested_parameters=invalid)

    for invalid in (
        (["format", "pdf"],),
        (("format",),),
        (("format", "pdf", "extra"),),
    ):
        with pytest.raises((TypeError, ValueError)):
            _package(suggested_parameters=invalid)


def test_suggested_parameter_keys_are_exact_nonblank_unique_strings():
    for invalid_key in (None, 7, "", " format", "format ", "   "):
        with pytest.raises((TypeError, ValueError)):
            _package(suggested_parameters=((invalid_key, "value"),))

    with pytest.raises(ValueError):
        _package(
            suggested_parameters=(
                ("format", "pdf"),
                ("format", "xlsx"),
            )
        )

    package = _package(
        suggested_parameters=(
            ("Format", "PDF"),
            ("format", "pdf"),
        )
    )
    assert package.suggested_parameters[0][0] == "Format"
    assert package.suggested_parameters[1][0] == "format"


def test_suggested_parameter_values_are_opaque_and_preserve_identity():
    marker = object()
    mutable_value = {"future": [1, 2, 3]}
    parameters = (
        ("opaque", marker),
        ("future-structure", mutable_value),
        ("flag", True),
    )
    package = _package(suggested_parameters=parameters)

    assert package.suggested_parameters is parameters
    assert package.suggested_parameters[0][1] is marker
    assert package.suggested_parameters[1][1] is mutable_value
    assert package.suggested_parameters[2][1] is True


def test_report_package_is_always_official_and_rejects_non_boolean_or_false_flag():
    assert _package().is_official is True
    assert _package(is_official=True).is_official is True

    for invalid in (False, 1, 0, "true", None):
        with pytest.raises((TypeError, ValueError)):
            _package(is_official=invalid)


def test_suggested_parameters_are_only_suggestions_and_are_not_report_request_validation():
    marker = object()
    package = _package(
        suggested_parameters=(
            ("format", "not-supported-by-included-definition"),
            ("from_date", marker),
            ("future-parameter", "future-value"),
        )
    )

    assert package.suggested_parameters[0][1] == "not-supported-by-included-definition"
    assert package.suggested_parameters[1][1] is marker
    assert package.suggested_parameters[2] == ("future-parameter", "future-value")


def test_report_package_fields_do_not_embed_concrete_generation_request_or_custom_owner_truth():
    from aqorath.report_package import ReportPackage

    field_names = {field.name for field in fields(ReportPackage)}
    unrelated = {
        "entity_id",
        "owner_entity_id",
        "from_date",
        "to_date",
        "as_of_date",
        "filters",
        "dimensions_to_group",
        "format",
        "created_at",
        "output_path",
    }
    assert field_names.isdisjoint(unrelated)


def test_report_package_is_deterministic_value_truth_without_time_random_or_environment():
    import aqorath.report_package as domain

    first = _package(id=4)
    second = _package(id=4)
    assert first == second

    source = inspect.getsource(domain).lower()
    for forbidden in (
        "datetime.now",
        "datetime.utcnow",
        "date.today",
        "time.time",
        "random",
        "uuid",
        "os.environ",
    ):
        assert forbidden not in source


def test_report_package_is_a_preset_not_a_locked_container_or_mutation_api():
    import aqorath.report_package as domain

    for forbidden_name in (
        "add_report",
        "remove_report",
        "lock_package",
        "is_report_allowed",
        "is_report_forbidden",
        "personalize_package",
        "create_custom_report_package",
        "generate_report",
        "generate_package",
    ):
        assert not hasattr(domain, forbidden_name)

    source = inspect.getsource(domain).lower()
    for forbidden in (
        "allowed_reports",
        "forbidden_reports",
        "locked_reports",
        "exclusive_reports",
    ):
        assert forbidden not in source


def test_report_package_foundation_does_not_persist_generate_or_enter_runtime_application_preferences():
    import aqorath.application as application
    import aqorath.report_package as domain

    source = inspect.getsource(domain).lower()
    for forbidden in (
        "report_request",
        "custom_report_package",
        "reporting_runtime",
        "reporting_export",
        "storage",
        "get_session",
        "models",
        "user_knowledge_state",
        "preferred_report_format",
        "create_report_package",
        "save_report_package",
        "execute_report",
        "render_report",
    ):
        assert forbidden not in source

    application_source = inspect.getsource(application).lower()
    assert "report_package" not in application_source
    assert "create_report_package" not in application_source
