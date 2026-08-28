"""Phase 6AI.1 — frozen report fiscal applicability contracts.

ReportDefinition declares required fiscal features, while FiscalProfile carries explicit
effective-dated tax characteristics. This phase freezes only the pure point-in-time
applicability of one definition against one explicit FiscalProfile on one explicit date.
It deliberately does not select fiscal history for a ReportRequest period, infer features
from regime codes, execute queries, render output, persist anything, or enter Application.
"""

from dataclasses import replace
from datetime import date, datetime
import importlib
import inspect

import pytest


def _definition(**patch):
    from aqorath.report_definition import ReportDefinition

    values = dict(
        id=3,
        name="Declaración informativa",
        description="Documento fiscal formal",
        required_data=("journal_entries",),
        supported_formats=("pdf",),
        requires_capabilities=(),
        forbidden_capabilities=(),
        required_fiscal_features=("requires_cfdi",),
        renderer_id="fiscal_statement",
        query_template_id="fiscal_snapshot",
    )
    values.update(patch)
    return ReportDefinition(**values)


def _profile(**patch):
    from aqorath.entity import FiscalProfile

    values = dict(
        id=11,
        entity_id=1,
        jurisdiction="MX",
        fiscal_regime_code="EXPLICIT-REGIME",
        tax_characteristics=("requires_cfdi", "iva"),
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
    )
    values.update(patch)
    return FiscalProfile(**values)


def _module():
    return importlib.import_module("aqorath.report_fiscal_applicability")


def test_fiscal_applicability_public_contract_is_exact_and_pure():
    module = _module()

    assert str(inspect.signature(module.is_report_definition_fiscally_applicable_on)) == (
        "(definition, fiscal_profile, effective_date)"
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


def test_fiscal_applicability_requires_nominal_report_definition():
    module = _module()
    profile = _profile()

    for invalid in (None, object(), {"required_fiscal_features": ()}, "report"):
        with pytest.raises(TypeError):
            module.is_report_definition_fiscally_applicable_on(
                invalid,
                profile,
                date(2026, 6, 1),
            )


def test_fiscal_applicability_requires_nominal_fiscal_profile():
    module = _module()
    definition = _definition()

    for invalid in (None, object(), {"tax_characteristics": ()}, "profile"):
        with pytest.raises(TypeError):
            module.is_report_definition_fiscally_applicable_on(
                definition,
                invalid,
                date(2026, 6, 1),
            )


def test_effective_date_must_be_exact_date_not_datetime_text_or_none():
    module = _module()
    definition = _definition()
    profile = _profile()

    for invalid in (
        datetime(2026, 6, 1),
        "2026-06-01",
        20260601,
        None,
    ):
        with pytest.raises(TypeError):
            module.is_report_definition_fiscally_applicable_on(
                definition,
                profile,
                invalid,
            )


def test_fiscal_profile_effective_from_boundary_is_inclusive():
    module = _module()
    profile = _profile(effective_from=date(2026, 3, 1))

    assert module.is_report_definition_fiscally_applicable_on(
        _definition(),
        profile,
        date(2026, 3, 1),
    ) is True


def test_fiscal_profile_effective_to_boundary_is_inclusive_and_none_is_open_ended():
    module = _module()

    bounded = _profile(effective_to=date(2026, 7, 31))
    assert module.is_report_definition_fiscally_applicable_on(
        _definition(),
        bounded,
        date(2026, 7, 31),
    ) is True

    open_ended = _profile(effective_from=date(2026, 1, 1), effective_to=None)
    assert module.is_report_definition_fiscally_applicable_on(
        _definition(),
        open_ended,
        date(2099, 12, 31),
    ) is True


def test_date_outside_fiscal_profile_interval_is_not_applicable():
    module = _module()
    definition = _definition()
    profile = _profile(
        effective_from=date(2026, 3, 1),
        effective_to=date(2026, 9, 30),
    )

    assert module.is_report_definition_fiscally_applicable_on(
        definition,
        profile,
        date(2026, 2, 28),
    ) is False
    assert module.is_report_definition_fiscally_applicable_on(
        definition,
        profile,
        date(2026, 10, 1),
    ) is False


def test_definition_with_no_required_fiscal_features_is_applicable_when_profile_is_effective():
    module = _module()

    assert module.is_report_definition_fiscally_applicable_on(
        _definition(required_fiscal_features=()),
        _profile(tax_characteristics=()),
        date(2026, 6, 1),
    ) is True


def test_all_required_fiscal_features_must_be_present():
    module = _module()

    definition = _definition(
        required_fiscal_features=("requires_cfdi", "requires_monthly_vat"),
    )
    profile = _profile(
        tax_characteristics=(
            "requires_cfdi",
            "requires_monthly_vat",
            "future-feature",
        )
    )

    assert module.is_report_definition_fiscally_applicable_on(
        definition,
        profile,
        date(2026, 6, 1),
    ) is True


def test_missing_any_required_fiscal_feature_makes_definition_not_applicable():
    module = _module()

    definition = _definition(
        required_fiscal_features=("requires_cfdi", "requires_monthly_vat"),
    )
    profile = _profile(tax_characteristics=("requires_cfdi",))

    assert module.is_report_definition_fiscally_applicable_on(
        definition,
        profile,
        date(2026, 6, 1),
    ) is False


def test_fiscal_feature_matching_is_exact_case_sensitive_and_has_no_aliases():
    module = _module()

    cases = (
        ("requires_cfdi", ("cfdi",)),
        ("requires_cfdi", ("REQUIRES_CFDI",)),
        ("requires_monthly_vat", ("iva",)),
        ("future-feature", ("future_feature",)),
    )
    for required, present in cases:
        assert module.is_report_definition_fiscally_applicable_on(
            _definition(required_fiscal_features=(required,)),
            _profile(tax_characteristics=present),
            date(2026, 6, 1),
        ) is False


def test_fiscal_feature_membership_is_order_independent_and_extra_characteristics_are_allowed():
    module = _module()
    definition = _definition(
        required_fiscal_features=("requires_cfdi", "requires_monthly_vat"),
    )

    first = _profile(
        tax_characteristics=(
            "requires_cfdi",
            "requires_monthly_vat",
            "future-feature",
        )
    )
    second = _profile(
        tax_characteristics=(
            "future-feature",
            "requires_monthly_vat",
            "requires_cfdi",
        )
    )

    assert module.is_report_definition_fiscally_applicable_on(
        definition,
        first,
        date(2026, 6, 1),
    ) is True
    assert module.is_report_definition_fiscally_applicable_on(
        definition,
        second,
        date(2026, 6, 1),
    ) is True


def test_fiscal_regime_code_never_infers_missing_required_feature():
    module = _module()

    profile = _profile(
        fiscal_regime_code="REQUIRES-CFDI-BY-NAME",
        tax_characteristics=(),
    )

    assert module.is_report_definition_fiscally_applicable_on(
        _definition(required_fiscal_features=("requires_cfdi",)),
        profile,
        date(2026, 6, 1),
    ) is False


def test_non_fiscal_definition_metadata_does_not_change_fiscal_applicability():
    module = _module()
    base = _definition(required_fiscal_features=("requires_cfdi",))
    changed = replace(
        base,
        id=None,
        name="Otro nombre",
        description="Otra descripción",
        required_data=("future-data",),
        supported_formats=("future-open-format",),
        requires_capabilities=("future-capability",),
        forbidden_capabilities=("another-capability",),
        renderer_id="future.renderer",
        query_template_id="future.query",
    )
    profile = _profile(tax_characteristics=("requires_cfdi",))

    assert module.is_report_definition_fiscally_applicable_on(
        base,
        profile,
        date(2026, 6, 1),
    ) is True
    assert module.is_report_definition_fiscally_applicable_on(
        changed,
        profile,
        date(2026, 6, 1),
    ) is True


def test_fiscal_profile_identity_entity_jurisdiction_and_regime_do_not_change_feature_result():
    module = _module()
    definition = _definition(required_fiscal_features=("requires_cfdi",))
    base = _profile(tax_characteristics=("requires_cfdi",))
    changed = replace(
        base,
        id=None,
        entity_id=999_999,
        jurisdiction="FUTURE-JURISDICTION",
        fiscal_regime_code="FUTURE-REGIME",
    )

    assert module.is_report_definition_fiscally_applicable_on(
        definition,
        base,
        date(2026, 6, 1),
    ) is True
    assert module.is_report_definition_fiscally_applicable_on(
        definition,
        changed,
        date(2026, 6, 1),
    ) is True


def test_fiscal_applicability_is_deterministic_non_mutating_and_does_not_select_history_or_enter_application():
    module = _module()
    application = importlib.import_module("aqorath.application")
    definition = _definition(required_fiscal_features=("requires_cfdi",))
    profile = _profile(tax_characteristics=("requires_cfdi",))
    effective_date = date(2026, 6, 1)

    first = module.is_report_definition_fiscally_applicable_on(
        definition,
        profile,
        effective_date,
    )
    second = module.is_report_definition_fiscally_applicable_on(
        definition,
        profile,
        effective_date,
    )
    assert first is True
    assert second is True
    assert definition.required_fiscal_features == ("requires_cfdi",)
    assert profile.tax_characteristics == ("requires_cfdi",)

    source = inspect.getsource(module).lower()
    for forbidden in (
        "entity_repository",
        "resolve_fiscal_profile",
        "report_request",
        "report_request_compatibility",
        "report_capability_applicability",
        "reporting_runtime",
        "reporting_export",
        "storage",
        "get_session",
        "user_knowledge_state",
        "preferred_report_format",
        "date.today",
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
    assert "report_fiscal_applicability" not in application_source
    assert "is_report_definition_fiscally_applicable_on" not in application_source
