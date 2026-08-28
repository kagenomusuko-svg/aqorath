"""Phase 6AJ.1 — frozen report-period fiscal applicability contracts.

ReportRequest carries both a date range and an optional as_of_date, but the architecture
does not define a precedence between those concepts. This phase therefore freezes only
period applicability over the explicit inclusive [from_date, to_date] range. The supplied
FiscalProfile history is explicit input; matching-Entity profiles must cover the whole
range without ambiguity, and every relevant segment must satisfy the definition's fiscal
features through the already-frozen point-in-time authority from Phase 6AI.

as_of_date semantics, history loading, Definition/Request compatibility, capability
applicability, required-data availability, query execution, rendering, persistence, and
Application orchestration remain outside this authority.
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


def _profile(**patch):
    from aqorath.entity import FiscalProfile

    values = dict(
        id=11,
        entity_id=1,
        jurisdiction="MX",
        fiscal_regime_code="EXPLICIT-REGIME",
        tax_characteristics=("requires_cfdi",),
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
    )
    values.update(patch)
    return FiscalProfile(**values)


def _module():
    return importlib.import_module("aqorath.report_period_fiscal_applicability")


def test_period_fiscal_applicability_public_contract_is_exact_and_pure():
    module = _module()

    assert str(inspect.signature(module.is_report_request_period_fiscally_applicable)) == (
        "(definition, request, fiscal_profiles)"
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


def test_period_fiscal_applicability_requires_nominal_report_definition():
    module = _module()
    request = _request()

    for invalid in (None, object(), {"required_fiscal_features": ()}, "report"):
        with pytest.raises(TypeError):
            module.is_report_request_period_fiscally_applicable(
                invalid,
                request,
                (),
            )


def test_period_fiscal_applicability_requires_nominal_report_request():
    module = _module()
    definition = _definition()

    for invalid in (None, object(), {"from_date": date(2026, 1, 1)}, "request"):
        with pytest.raises(TypeError):
            module.is_report_request_period_fiscally_applicable(
                definition,
                invalid,
                (),
            )


def test_fiscal_profiles_must_be_exact_tuple_of_nominal_fiscal_profiles():
    module = _module()
    definition = _definition()
    request = _request()

    for invalid in (
        [],
        [_profile()],
        "history",
        None,
    ):
        with pytest.raises(TypeError):
            module.is_report_request_period_fiscally_applicable(
                definition,
                request,
                invalid,
            )

    for invalid_tuple in (
        (object(),),
        ({"entity_id": 1},),
        (_profile(), object()),
    ):
        with pytest.raises(TypeError):
            module.is_report_request_period_fiscally_applicable(
                definition,
                request,
                invalid_tuple,
            )


def test_definition_without_fiscal_requirements_needs_no_fiscal_history():
    module = _module()

    assert module.is_report_request_period_fiscally_applicable(
        _definition(required_fiscal_features=()),
        _request(),
        (),
    ) is True


def test_profiles_are_scoped_to_request_entity_and_foreign_profiles_never_satisfy_coverage():
    module = _module()
    definition = _definition()
    request = _request(entity_id=1)

    foreign = _profile(entity_id=2)
    assert module.is_report_request_period_fiscally_applicable(
        definition,
        request,
        (foreign,),
    ) is False

    matching = _profile(entity_id=1)
    assert module.is_report_request_period_fiscally_applicable(
        definition,
        request,
        (foreign, matching),
    ) is True


def test_single_matching_profile_covering_entire_period_is_applicable():
    module = _module()

    profile = _profile(
        effective_from=date(2025, 1, 1),
        effective_to=date(2027, 12, 31),
    )
    assert module.is_report_request_period_fiscally_applicable(
        _definition(),
        _request(),
        (profile,),
    ) is True


def test_period_boundaries_are_inclusive_and_open_ended_profile_can_cover_to_date():
    module = _module()

    exact = _profile(
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
    )
    assert module.is_report_request_period_fiscally_applicable(
        _definition(),
        _request(),
        (exact,),
    ) is True

    open_ended = _profile(
        effective_from=date(2026, 1, 1),
        effective_to=None,
    )
    assert module.is_report_request_period_fiscally_applicable(
        _definition(),
        _request(to_date=date(2099, 12, 31)),
        (open_ended,),
    ) is True


def test_required_fiscal_features_fail_closed_when_matching_history_is_empty():
    module = _module()

    assert module.is_report_request_period_fiscally_applicable(
        _definition(required_fiscal_features=("requires_cfdi",)),
        _request(),
        (),
    ) is False


def test_relevant_profile_must_satisfy_exact_required_features_without_aliases():
    module = _module()
    definition = _definition(required_fiscal_features=("requires_cfdi",))

    missing = _profile(tax_characteristics=())
    alias_only = _profile(tax_characteristics=("cfdi",))

    assert module.is_report_request_period_fiscally_applicable(
        definition,
        _request(),
        (missing,),
    ) is False
    assert module.is_report_request_period_fiscally_applicable(
        definition,
        _request(),
        (alias_only,),
    ) is False


def test_contiguous_multiple_profiles_can_cover_period_when_each_segment_is_applicable():
    module = _module()
    request = _request()

    first = _profile(
        id=11,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 6, 30),
    )
    second = _profile(
        id=12,
        effective_from=date(2026, 7, 1),
        effective_to=date(2026, 12, 31),
    )

    assert module.is_report_request_period_fiscally_applicable(
        _definition(),
        request,
        (first, second),
    ) is True


def test_any_relevant_segment_missing_required_feature_makes_period_not_applicable():
    module = _module()

    first = _profile(
        id=11,
        tax_characteristics=("requires_cfdi",),
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 6, 30),
    )
    second = _profile(
        id=12,
        tax_characteristics=(),
        effective_from=date(2026, 7, 1),
        effective_to=date(2026, 12, 31),
    )

    assert module.is_report_request_period_fiscally_applicable(
        _definition(),
        _request(),
        (first, second),
    ) is False


def test_gap_between_matching_profiles_makes_period_not_applicable():
    module = _module()

    first = _profile(
        id=11,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 6, 30),
    )
    second = _profile(
        id=12,
        effective_from=date(2026, 7, 2),
        effective_to=date(2026, 12, 31),
    )

    assert module.is_report_request_period_fiscally_applicable(
        _definition(),
        _request(),
        (first, second),
    ) is False


def test_overlapping_matching_profiles_inside_requested_period_are_rejected_as_ambiguous():
    module = _module()

    first = _profile(
        id=11,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 8, 31),
    )
    second = _profile(
        id=12,
        effective_from=date(2026, 8, 1),
        effective_to=date(2026, 12, 31),
    )

    with pytest.raises(ValueError):
        module.is_report_request_period_fiscally_applicable(
            _definition(),
            _request(),
            (first, second),
        )


def test_profile_input_order_and_profiles_outside_period_do_not_change_result():
    module = _module()
    definition = _definition()
    request = _request()

    before = _profile(
        id=9,
        tax_characteristics=(),
        effective_from=date(2024, 1, 1),
        effective_to=date(2025, 12, 31),
    )
    first = _profile(
        id=11,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 6, 30),
    )
    second = _profile(
        id=12,
        effective_from=date(2026, 7, 1),
        effective_to=date(2026, 12, 31),
    )
    after = _profile(
        id=13,
        tax_characteristics=(),
        effective_from=date(2027, 1, 1),
        effective_to=date(2027, 12, 31),
    )

    assert module.is_report_request_period_fiscally_applicable(
        definition,
        request,
        (before, first, second, after),
    ) is True
    assert module.is_report_request_period_fiscally_applicable(
        definition,
        request,
        (after, second, before, first),
    ) is True


def test_period_authority_reuses_point_truth_and_ignores_as_of_and_other_unrelated_report_truth():
    module = _module()
    application = importlib.import_module("aqorath.application")

    definition = _definition(required_fiscal_features=("requires_cfdi",))
    request = _request()
    changed_definition = replace(
        definition,
        id=None,
        required_data=("future-data",),
        supported_formats=("future-format",),
        requires_capabilities=("future-capability",),
        forbidden_capabilities=("another-capability",),
        renderer_id="future.renderer",
        query_template_id="future.query",
    )
    changed_request = replace(
        request,
        id=99,
        report_definition_id=999_999,
        as_of_date=date(2099, 1, 1),
        filters=(("opaque", object()),),
        dimensions_to_group=("FutureDimension",),
        format="future-format",
    )
    profiles = (_profile(),)

    assert module.is_report_request_period_fiscally_applicable(
        definition,
        request,
        profiles,
    ) is True
    assert module.is_report_request_period_fiscally_applicable(
        changed_definition,
        changed_request,
        profiles,
    ) is True

    source = inspect.getsource(module).lower()
    assert "report_fiscal_applicability" in source
    assert "is_report_definition_fiscally_applicable_on" in source
    for forbidden in (
        "entity_repository",
        "resolve_fiscal_profile",
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
    assert "report_period_fiscal_applicability" not in application_source
    assert "is_report_request_period_fiscally_applicable" not in application_source
