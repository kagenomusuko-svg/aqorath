"""Phase 6AH.1 — frozen report capability applicability contracts.

ReportDefinition declares required/forbidden capabilities independently from fiscal
features, required-data availability, request compatibility, query execution, rendering,
persistence, or report generation. This phase freezes only the pure applicability of one
ReportDefinition against one explicit EntityProfile.special_capabilities tuple.
"""

from dataclasses import replace
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


def _profile(**patch):
    from aqorath.entity import EntityProfile

    values = dict(
        economic_purpose="no_lucrativo",
        is_donor_authorized=False,
        special_capabilities=("osc", "inventory_control"),
        modules_enabled=("osc", "inventory"),
    )
    values.update(patch)
    return EntityProfile(**values)


def _module():
    return importlib.import_module("aqorath.report_capability_applicability")


def test_capability_applicability_public_contract_is_exact_and_pure():
    module = _module()

    assert str(inspect.signature(module.is_report_definition_capability_applicable)) == (
        "(definition, entity_profile)"
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


def test_capability_applicability_requires_nominal_report_definition():
    module = _module()
    profile = _profile()

    for invalid in (None, object(), {"requires_capabilities": ()}, "report"):
        with pytest.raises(TypeError):
            module.is_report_definition_capability_applicable(invalid, profile)


def test_capability_applicability_requires_nominal_entity_profile():
    module = _module()
    definition = _definition()

    for invalid in (None, object(), {"special_capabilities": ()}, ("osc",)):
        with pytest.raises(TypeError):
            module.is_report_definition_capability_applicable(definition, invalid)


def test_definition_with_no_capability_requirements_is_applicable():
    module = _module()

    assert module.is_report_definition_capability_applicable(
        _definition(requires_capabilities=(), forbidden_capabilities=()),
        _profile(special_capabilities=()),
    ) is True


def test_all_required_capabilities_must_be_present():
    module = _module()

    definition = _definition(requires_capabilities=("osc", "inventory_control"))
    profile = _profile(special_capabilities=("osc", "inventory_control", "future"))

    assert module.is_report_definition_capability_applicable(definition, profile) is True


def test_missing_any_required_capability_makes_definition_not_applicable():
    module = _module()

    definition = _definition(requires_capabilities=("osc", "inventory_control"))
    profile = _profile(special_capabilities=("osc",))

    assert module.is_report_definition_capability_applicable(definition, profile) is False


def test_presence_of_any_forbidden_capability_makes_definition_not_applicable():
    module = _module()

    definition = _definition(forbidden_capabilities=("payroll", "inventory_control"))
    profile = _profile(special_capabilities=("osc", "inventory_control"))

    assert module.is_report_definition_capability_applicable(definition, profile) is False


def test_absent_forbidden_capabilities_leave_definition_applicable():
    module = _module()

    definition = _definition(
        requires_capabilities=("osc",),
        forbidden_capabilities=("payroll",),
    )
    profile = _profile(special_capabilities=("osc", "inventory_control"))

    assert module.is_report_definition_capability_applicable(definition, profile) is True


def test_capability_matching_is_exact_case_sensitive_and_has_no_aliases():
    module = _module()

    cases = (
        ("OSC", ("osc",)),
        ("inventory", ("inventory_control",)),
        ("payroll", ("payroll_reporting",)),
        ("future-capability", ("future_capability",)),
    )
    for required, present in cases:
        assert module.is_report_definition_capability_applicable(
            _definition(requires_capabilities=(required,)),
            _profile(special_capabilities=present),
        ) is False


def test_capability_membership_is_order_independent_and_extra_capabilities_are_allowed():
    module = _module()
    definition = _definition(requires_capabilities=("osc", "inventory_control"))

    first = _profile(
        special_capabilities=("osc", "inventory_control", "future-capability")
    )
    second = _profile(
        special_capabilities=("future-capability", "inventory_control", "osc")
    )

    assert module.is_report_definition_capability_applicable(definition, first) is True
    assert module.is_report_definition_capability_applicable(definition, second) is True


def test_modules_enabled_do_not_satisfy_required_special_capabilities():
    module = _module()

    definition = _definition(requires_capabilities=("inventory",))
    profile = _profile(
        special_capabilities=(),
        modules_enabled=("inventory",),
    )

    assert module.is_report_definition_capability_applicable(definition, profile) is False


def test_modules_enabled_do_not_trigger_forbidden_special_capabilities():
    module = _module()

    definition = _definition(forbidden_capabilities=("payroll",))
    profile = _profile(
        special_capabilities=(),
        modules_enabled=("payroll",),
    )

    assert module.is_report_definition_capability_applicable(definition, profile) is True


def test_economic_purpose_and_donor_authorization_do_not_change_capability_result():
    module = _module()
    definition = _definition(requires_capabilities=("osc",))

    nonprofit = _profile(
        economic_purpose="no_lucrativo",
        is_donor_authorized=False,
        special_capabilities=("osc",),
    )
    commercial = _profile(
        economic_purpose="lucrativo",
        is_donor_authorized=True,
        special_capabilities=("osc",),
    )

    assert module.is_report_definition_capability_applicable(definition, nonprofit) is True
    assert module.is_report_definition_capability_applicable(definition, commercial) is True


def test_non_capability_definition_metadata_does_not_change_capability_applicability():
    module = _module()
    base = _definition(requires_capabilities=("osc",))
    changed = replace(
        base,
        id=None,
        name="Otro nombre",
        description="Otra descripción",
        required_data=("future-data",),
        supported_formats=("future-open-format",),
        required_fiscal_features=("future-fiscal-feature",),
        renderer_id="future.renderer",
        query_template_id="future.query",
    )
    profile = _profile(special_capabilities=("osc",))

    assert module.is_report_definition_capability_applicable(base, profile) is True
    assert module.is_report_definition_capability_applicable(changed, profile) is True


def test_capability_applicability_does_not_evaluate_entity_fiscal_data_request_or_runtime_truth():
    module = _module()
    definition = _definition(requires_capabilities=("osc",))
    profile = _profile(special_capabilities=("osc",))

    assert module.is_report_definition_capability_applicable(definition, profile) is True

    source = inspect.getsource(module).lower()
    for forbidden in (
        "entity_repository",
        "load_active_entity",
        "resolve_fiscal_profile",
        "fiscal_profile",
        "fiscal_rule",
        "required_data_available",
        "report_request",
        "report_request_compatibility",
        "reporting_runtime",
        "reporting_export",
        "storage",
        "get_session",
        "user_knowledge_state",
        "preferred_report_format",
    ):
        assert forbidden not in source


def test_capability_applicability_is_deterministic_non_mutating_and_does_not_enter_application():
    module = _module()
    application = importlib.import_module("aqorath.application")
    definition = _definition(requires_capabilities=("osc",))
    profile = _profile(special_capabilities=("osc",))

    first = module.is_report_definition_capability_applicable(definition, profile)
    second = module.is_report_definition_capability_applicable(definition, profile)
    assert first is True
    assert second is True
    assert definition.requires_capabilities == ("osc",)
    assert profile.special_capabilities == ("osc",)

    source = inspect.getsource(module).lower()
    for forbidden in (
        "datetime.now",
        "datetime.utcnow",
        "time.time",
        "random",
        "uuid",
        "os.environ",
        "generate_report",
        "render_report",
        "execute_report",
        "save_report",
    ):
        assert forbidden not in source

    application_source = inspect.getsource(application).lower()
    assert "report_capability_applicability" not in application_source
    assert "is_report_definition_capability_applicable" not in application_source
