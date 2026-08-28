"""Phase 6AF.1 — frozen ReportRequest domain contracts.

R18 separates WHAT report exists (ReportDefinition) from WHAT to generate this time
(ReportRequest). This phase freezes only the immutable concrete generation request value.
It does not resolve definitions/entities, evaluate applicability, select user preferences,
execute queries, render output, persist requests, or generate reports.
"""

from dataclasses import FrozenInstanceError, fields
from datetime import date, datetime
from decimal import Decimal
import inspect

import pytest


REPORT_REQUEST_FIELDS = (
    "id",
    "report_definition_id",
    "entity_id",
    "from_date",
    "to_date",
    "as_of_date",
    "filters",
    "dimensions_to_group",
    "format",
)


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


def test_report_request_is_pure_frozen_and_has_exact_architecture_fields():
    import aqorath.report_request as domain
    from aqorath.report_request import ReportRequest

    request = _request()
    assert tuple(field.name for field in fields(ReportRequest)) == REPORT_REQUEST_FIELDS

    with pytest.raises(FrozenInstanceError):
        request.format = "xlsx"

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


def test_report_request_id_is_none_before_identity_or_exact_positive_int():
    assert _request(id=None).id is None
    assert _request(id=8).id == 8

    for invalid in (0, -1, True, 1.0, "1"):
        with pytest.raises((TypeError, ValueError)):
            _request(id=invalid)


def test_report_request_requires_exact_positive_definition_and_entity_ids():
    assert _request(report_definition_id=9, entity_id=4).report_definition_id == 9

    for field_name in ("report_definition_id", "entity_id"):
        for invalid in (0, -1, True, 1.0, "1", None):
            with pytest.raises((TypeError, ValueError)):
                _request(**{field_name: invalid})


def test_report_request_requires_exact_date_period_boundaries_not_datetime_or_text():
    request = _request(
        from_date=date(2026, 2, 1),
        to_date=date(2026, 2, 28),
    )
    assert request.from_date == date(2026, 2, 1)
    assert request.to_date == date(2026, 2, 28)

    for field_name in ("from_date", "to_date"):
        for invalid in (
            None,
            "2026-02-01",
            datetime(2026, 2, 1),
            20260201,
        ):
            with pytest.raises((TypeError, ValueError)):
                _request(**{field_name: invalid})


def test_report_request_rejects_period_with_end_before_start():
    with pytest.raises(ValueError):
        _request(
            from_date=date(2026, 3, 2),
            to_date=date(2026, 3, 1),
        )

    same_day = _request(
        from_date=date(2026, 3, 1),
        to_date=date(2026, 3, 1),
    )
    assert same_day.from_date == same_day.to_date


def test_report_request_as_of_date_is_optional_exact_date_without_invented_range_relation():
    assert _request(as_of_date=None).as_of_date is None

    outside_period = _request(as_of_date=date(2027, 1, 15))
    assert outside_period.as_of_date == date(2027, 1, 15)

    for invalid in ("2026-12-31", datetime(2026, 12, 31), 20261231):
        with pytest.raises((TypeError, ValueError)):
            _request(as_of_date=invalid)


def test_report_request_filters_are_exact_immutable_tuple_of_two_item_tuples():
    filters = (("state", "posted"), ("minimum", Decimal("10.5000")))
    request = _request(filters=filters)
    assert request.filters is filters

    for invalid in (
        {},
        [],
        {"state", "posted"},
        "state=posted",
        (("state", "posted", "extra"),),
        (["state", "posted"],),
        (("state",),),
    ):
        with pytest.raises((TypeError, ValueError)):
            _request(filters=invalid)


def test_report_request_filter_keys_are_explicit_nonblank_unique_tokens():
    for invalid_key in (None, 7, "", " key", "key ", "   "):
        with pytest.raises((TypeError, ValueError)):
            _request(filters=((invalid_key, "value"),))

    with pytest.raises(ValueError):
        _request(filters=(("state", "posted"), ("state", "draft")))


def test_report_request_filter_values_are_opaque_and_preserved_without_coercion():
    marker = object()
    amount = Decimal("123.4500")
    request = _request(
        filters=(("opaque", marker), ("amount", amount), ("active", True)),
    )

    assert request.filters[0][1] is marker
    assert request.filters[1][1] is amount
    assert request.filters[2][1] is True


def test_report_request_dimensions_are_exact_tuple_and_empty_is_valid():
    assert _request(dimensions_to_group=()).dimensions_to_group == ()
    assert _request(dimensions_to_group=("program", "source")).dimensions_to_group == (
        "program",
        "source",
    )

    for invalid in ([], set(), {}, "program", None):
        with pytest.raises(TypeError):
            _request(dimensions_to_group=invalid)


def test_report_request_dimension_tokens_are_explicit_unique_and_preserve_order_case():
    request = _request(dimensions_to_group=("Program", "program", "FundingSource"))
    assert request.dimensions_to_group == ("Program", "program", "FundingSource")

    for invalid in (None, 7, "", " program", "program ", "   "):
        with pytest.raises((TypeError, ValueError)):
            _request(dimensions_to_group=(invalid,))

    with pytest.raises(ValueError):
        _request(dimensions_to_group=("program", "program"))


def test_report_request_format_is_explicit_open_token_with_no_normalization_or_closed_enum():
    for value in ("pdf", "PDF", "structured-json", "future-open-format"):
        request = _request(format=value)
        assert request.format == value

    for invalid in (None, 7, "", " pdf", "pdf ", "   "):
        with pytest.raises((TypeError, ValueError)):
            _request(format=invalid)


def test_report_request_separates_concrete_request_from_definition_metadata_fields():
    from aqorath.report_request import ReportRequest

    field_names = {field.name for field in fields(ReportRequest)}
    definition_only_fields = {
        "name",
        "description",
        "required_data",
        "supported_formats",
        "requires_capabilities",
        "forbidden_capabilities",
        "required_fiscal_features",
        "renderer_id",
        "query_template_id",
    }
    assert field_names.isdisjoint(definition_only_fields)


def test_report_request_keeps_foreign_identities_opaque_and_does_not_resolve_existence():
    request = _request(report_definition_id=999_999, entity_id=888_888)
    assert request.report_definition_id == 999_999
    assert request.entity_id == 888_888

    import aqorath.report_request as domain

    source = inspect.getsource(domain).lower()
    for forbidden in (
        "report_definition_repository",
        "entity_repository",
        "session.get",
        "select(",
    ):
        assert forbidden not in source


def test_report_request_does_not_import_runtime_exporters_storage_or_user_preferences():
    import aqorath.report_request as domain

    source = inspect.getsource(domain).lower()
    for forbidden in (
        "reporting_runtime",
        "reporting_export",
        "storage",
        "get_session",
        "models",
        "user_knowledge_state",
        "preferred_report_format",
        "select_preferred_report_format",
        "datetime.now",
        "datetime.utcnow",
        "time.time",
        "random",
        "uuid",
        "os.environ",
    ):
        assert forbidden not in source


def test_report_request_foundation_does_not_generate_render_resolve_select_or_persist_reports():
    import aqorath.report_request as domain

    one = _request(id=5)
    two = _request(id=5)
    assert one == two

    for forbidden_name in (
        "generate_report",
        "render_report",
        "execute_report",
        "resolve_report_definition",
        "resolve_report_request",
        "select_report_format",
        "select_preferred_report_format",
        "create_report_request",
        "save_report_request",
        "is_report_available",
    ):
        assert not hasattr(domain, forbidden_name)
