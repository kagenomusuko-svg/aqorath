"""Phase 6AL.1 — frozen CustomReportPackage domain contracts.

R19 separates an official ReportPackage preset from a user's saved personalized
selection. The architecture gives CustomReportPackage a concrete owner-scoped shape and
an explicit created_at value. This phase freezes only that pure immutable domain value.
It does not derive ownership from installation state, generate timestamps, mutate an
official package, persist selections, generate reports, or enter Application.
"""

from dataclasses import FrozenInstanceError, fields
from datetime import date, datetime, timezone
import inspect

import pytest


CUSTOM_REPORT_PACKAGE_FIELDS = (
    "id",
    "owner_entity_id",
    "name",
    "included_reports",
    "created_at",
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


def _custom_package(**patch):
    from aqorath.custom_report_package import CustomReportPackage

    values = dict(
        id=None,
        owner_entity_id=1,
        name="Mi paquete",
        included_reports=(_definition(),),
        created_at=datetime(2026, 8, 27, 23, 30, 15),
    )
    values.update(patch)
    return CustomReportPackage(**values)


def test_custom_report_package_is_pure_frozen_and_has_exact_architecture_fields():
    import aqorath.custom_report_package as domain
    from aqorath.custom_report_package import CustomReportPackage

    package = _custom_package()
    assert tuple(field.name for field in fields(CustomReportPackage)) == (
        CUSTOM_REPORT_PACKAGE_FIELDS
    )

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


def test_custom_report_package_id_is_none_before_identity_or_exact_positive_int():
    assert _custom_package(id=None).id is None
    assert _custom_package(id=7).id == 7

    for invalid in (0, -1, True, 1.0, "1"):
        with pytest.raises((TypeError, ValueError)):
            _custom_package(id=invalid)


def test_owner_entity_id_is_exact_positive_int_without_boolean_coercion():
    assert _custom_package(owner_entity_id=999_999).owner_entity_id == 999_999

    for invalid in (0, -1, True, False, 1.0, "1", None):
        with pytest.raises((TypeError, ValueError)):
            _custom_package(owner_entity_id=invalid)


def test_custom_report_package_name_is_exact_nonblank_text_without_normalization():
    for invalid in (None, 7, "", " Mi paquete", "Mi paquete ", "   "):
        with pytest.raises((TypeError, ValueError)):
            _custom_package(name=invalid)

    package = _custom_package(name="Asamblea + Bancos")
    assert package.name == "Asamblea + Bancos"


def test_included_reports_must_be_exact_immutable_tuple():
    for invalid in ([], set(), {}, "Balanza", None):
        with pytest.raises(TypeError):
            _custom_package(included_reports=invalid)


def test_included_reports_items_must_be_nominal_report_definitions():
    valid = _definition()
    for invalid in (
        (object(),),
        ({"name": "Balanza"},),
        (valid, object()),
    ):
        with pytest.raises(TypeError):
            _custom_package(included_reports=invalid)


def test_included_reports_may_be_empty_and_preserve_exact_order_and_identity():
    empty = _custom_package(included_reports=())
    assert empty.included_reports == ()

    first = _definition(id=1, name="Primero")
    second = _definition(id=2, name="Segundo")
    reports = (second, first)
    package = _custom_package(included_reports=reports)

    assert package.included_reports is reports
    assert package.included_reports == (second, first)
    assert package.included_reports[0] is second
    assert package.included_reports[1] is first


def test_custom_package_does_not_require_persisted_report_definition_identity_or_resolve_reports():
    transient = _definition(
        id=None,
        renderer_id="future.renderer",
        query_template_id="future.query",
    )
    package = _custom_package(included_reports=(transient,))

    assert package.included_reports[0] is transient
    assert package.included_reports[0].id is None


def test_created_at_must_be_exact_explicit_datetime_not_date_text_or_none():
    explicit = datetime(2026, 8, 27, 23, 45, 1, 123456)
    assert _custom_package(created_at=explicit).created_at is explicit

    for invalid in (
        date(2026, 8, 27),
        "2026-08-27T23:45:01",
        0,
        None,
    ):
        with pytest.raises(TypeError):
            _custom_package(created_at=invalid)


def test_created_at_preserves_supplied_timezone_microseconds_and_exact_value():
    aware = datetime(2026, 8, 27, 23, 50, 2, 654321, tzinfo=timezone.utc)
    package = _custom_package(created_at=aware)

    assert package.created_at is aware
    assert package.created_at == aware
    assert package.created_at.tzinfo is timezone.utc
    assert package.created_at.microsecond == 654321


def test_custom_package_does_not_derive_owner_or_created_at_from_environment_or_active_entity():
    import aqorath.custom_report_package as domain

    package = _custom_package(
        owner_entity_id=777,
        created_at=datetime(2001, 2, 3, 4, 5, 6),
    )
    assert package.owner_entity_id == 777
    assert package.created_at == datetime(2001, 2, 3, 4, 5, 6)

    source = inspect.getsource(domain).lower()
    for forbidden in (
        "load_active_entity",
        "entity_repository",
        "date.today",
        "datetime.now",
        "datetime.utcnow",
        "time.time",
    ):
        assert forbidden not in source


def test_custom_package_is_independent_from_official_report_package_truth():
    from aqorath.custom_report_package import CustomReportPackage
    from aqorath.report_package import ReportPackage

    assert not issubclass(CustomReportPackage, ReportPackage)

    field_names = {field.name for field in fields(CustomReportPackage)}
    assert "is_official" not in field_names
    assert "suggested_parameters" not in field_names


def test_custom_package_fields_do_not_embed_concrete_generation_request_truth():
    from aqorath.custom_report_package import CustomReportPackage

    field_names = {field.name for field in fields(CustomReportPackage)}
    request_only = {
        "report_definition_id",
        "entity_id",
        "from_date",
        "to_date",
        "as_of_date",
        "filters",
        "dimensions_to_group",
        "format",
        "output_path",
    }
    assert field_names.isdisjoint(request_only)


def test_custom_package_is_a_saved_selection_not_a_locked_container_or_mutation_api():
    import aqorath.custom_report_package as domain

    for forbidden_name in (
        "add_report",
        "remove_report",
        "lock_package",
        "is_report_allowed",
        "is_report_forbidden",
        "apply_official_package",
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


def test_custom_report_package_is_deterministic_value_truth_without_random_or_environment():
    import aqorath.custom_report_package as domain

    first = _custom_package(id=4)
    second = _custom_package(id=4)
    assert first == second
    assert hash(first) == hash(second)

    source = inspect.getsource(domain).lower()
    for forbidden in (
        "random",
        "uuid",
        "os.environ",
    ):
        assert forbidden not in source


def test_custom_report_package_foundation_does_not_persist_generate_or_enter_runtime_application_preferences():
    import aqorath.application as application
    import aqorath.custom_report_package as domain

    source = inspect.getsource(domain).lower()
    for forbidden in (
        "report_request",
        "reporting_runtime",
        "reporting_export",
        "storage",
        "get_session",
        "models",
        "user_knowledge_state",
        "preferred_report_format",
        "create_custom_report_package",
        "save_custom_report_package",
        "execute_report",
        "render_report",
    ):
        assert forbidden not in source

    application_source = inspect.getsource(application).lower()
    assert "custom_report_package" not in application_source
    assert "create_custom_report_package" not in application_source
