"""Phase 4Q.1 — canonical formal financial-statements XLSX export contracts."""

from inspect import signature

import pytest


def test_formal_xlsx_export_and_application_public_contracts_exist():
    import aqorath.application as application
    import aqorath.reporting_export as reporting_export

    assert callable(reporting_export.get_financial_statements_xlsx)
    assert callable(application.get_financial_statements_xlsx)

    export_params = signature(reporting_export.get_financial_statements_xlsx).parameters
    app_params = signature(application.get_financial_statements_xlsx).parameters
    assert list(export_params) == ["as_of"]
    assert list(app_params) == ["as_of"]
    assert export_params["as_of"].default is None
    assert app_params["as_of"].default is None


def test_formal_xlsx_export_builds_coherent_bundle_then_renders_exactly_once(monkeypatch):
    import aqorath.financial_statements_xlsx as formal_xlsx
    import aqorath.reporting_export as reporting_export
    import aqorath.reporting_runtime as reporting_runtime

    bundle = object()
    expected = b"FORMAL-XLSX"
    calls = []

    def fake_bundle(as_of=None):
        calls.append(("bundle", as_of))
        return bundle

    def fake_render(value):
        calls.append(("render", value))
        return expected

    monkeypatch.setattr(reporting_runtime, "get_financial_statements_bundle", fake_bundle)
    monkeypatch.setattr(formal_xlsx, "render_financial_statements_xlsx", fake_render)

    result = reporting_export.get_financial_statements_xlsx("2026-07-31")

    assert result is expected
    assert calls == [
        ("bundle", "2026-07-31"),
        ("render", bundle),
    ]


def test_formal_xlsx_export_passes_exact_none_as_of(monkeypatch):
    import aqorath.financial_statements_xlsx as formal_xlsx
    import aqorath.reporting_export as reporting_export
    import aqorath.reporting_runtime as reporting_runtime

    bundle = object()
    seen = []

    def fake_bundle(as_of=None):
        seen.append(as_of)
        return bundle

    monkeypatch.setattr(reporting_runtime, "get_financial_statements_bundle", fake_bundle)
    monkeypatch.setattr(formal_xlsx, "render_financial_statements_xlsx", lambda value: b"ok")

    assert reporting_export.get_financial_statements_xlsx() == b"ok"
    assert seen == [None]


def test_formal_xlsx_export_never_rebuilds_snapshot_or_independent_statements(monkeypatch):
    import aqorath.balance_sheet as balance_sheet
    import aqorath.financial_statements as financial_statements
    import aqorath.financial_statements_xlsx as formal_xlsx
    import aqorath.income_statement as income_statement
    import aqorath.reporting_export as reporting_export
    import aqorath.reporting_runtime as reporting_runtime

    bundle = object()

    def forbidden(*args, **kwargs):
        raise AssertionError("formal export must consume the coherent runtime bundle only")

    monkeypatch.setattr(reporting_runtime, "get_financial_report_snapshot", forbidden)
    monkeypatch.setattr(reporting_runtime, "get_income_statement_view", forbidden)
    monkeypatch.setattr(reporting_runtime, "get_balance_sheet_view", forbidden)
    monkeypatch.setattr(financial_statements, "build_financial_statements_bundle", forbidden)
    monkeypatch.setattr(income_statement, "build_income_statement_view", forbidden)
    monkeypatch.setattr(balance_sheet, "build_balance_sheet_view", forbidden)
    monkeypatch.setattr(reporting_runtime, "get_financial_statements_bundle", lambda as_of=None: bundle)
    monkeypatch.setattr(formal_xlsx, "render_financial_statements_xlsx", lambda value: b"formal")

    assert reporting_export.get_financial_statements_xlsx("2026-06-30") == b"formal"


def test_formal_xlsx_export_does_not_use_raw_xlsx_route_or_resolve_authorities_itself(monkeypatch):
    import aqorath.accounting_rules as accounting_rules
    import aqorath.financial_statements_xlsx as formal_xlsx
    import aqorath.reporting_export as reporting_export
    import aqorath.reporting_runtime as reporting_runtime
    import aqorath.reporting_source as reporting_source
    import aqorath.reporting_xlsx as raw_xlsx
    import aqorath.storage as storage

    bundle = object()

    def forbidden(*args, **kwargs):
        raise AssertionError("formal export must not use raw XLSX or resolve lower authorities")

    monkeypatch.setattr(storage, "get_db_path", forbidden)
    monkeypatch.setattr(accounting_rules, "load_catalog", forbidden)
    monkeypatch.setattr(reporting_source, "build_financial_report_snapshot_from_sqlite", forbidden)
    monkeypatch.setattr(raw_xlsx, "render_financial_report_xlsx", forbidden)
    monkeypatch.setattr(reporting_export, "get_financial_report_xlsx", forbidden)
    monkeypatch.setattr(reporting_runtime, "get_financial_statements_bundle", lambda as_of=None: bundle)
    monkeypatch.setattr(formal_xlsx, "render_financial_statements_xlsx", lambda value: b"formal")

    assert reporting_export.get_financial_statements_xlsx("2026-05-31") == b"formal"


def test_formal_xlsx_export_propagates_runtime_failure_without_render_or_retry(monkeypatch):
    import aqorath.financial_statements_xlsx as formal_xlsx
    import aqorath.reporting_export as reporting_export
    import aqorath.reporting_runtime as reporting_runtime

    failure = RuntimeError("bundle failure")
    calls = []

    def fail_bundle(as_of=None):
        calls.append(as_of)
        raise failure

    def forbidden_render(bundle):
        raise AssertionError("renderer must not run after bundle failure")

    monkeypatch.setattr(reporting_runtime, "get_financial_statements_bundle", fail_bundle)
    monkeypatch.setattr(formal_xlsx, "render_financial_statements_xlsx", forbidden_render)

    with pytest.raises(RuntimeError) as caught:
        reporting_export.get_financial_statements_xlsx("2026-04-30")

    assert caught.value is failure
    assert calls == ["2026-04-30"]


def test_formal_xlsx_export_propagates_renderer_failure_without_retry_or_rebuild(monkeypatch):
    import aqorath.financial_statements_xlsx as formal_xlsx
    import aqorath.reporting_export as reporting_export
    import aqorath.reporting_runtime as reporting_runtime

    bundle = object()
    failure = ValueError("formal render failure")
    calls = []

    def fake_bundle(as_of=None):
        calls.append(("bundle", as_of))
        return bundle

    def fail_render(value):
        calls.append(("render", value))
        raise failure

    monkeypatch.setattr(reporting_runtime, "get_financial_statements_bundle", fake_bundle)
    monkeypatch.setattr(formal_xlsx, "render_financial_statements_xlsx", fail_render)

    with pytest.raises(ValueError) as caught:
        reporting_export.get_financial_statements_xlsx("2026-03-31")

    assert caught.value is failure
    assert calls == [
        ("bundle", "2026-03-31"),
        ("render", bundle),
    ]


def test_application_delegates_formal_xlsx_export_exactly_once_and_does_not_build_itself(monkeypatch):
    import aqorath.application as application
    import aqorath.financial_statements_xlsx as formal_xlsx
    import aqorath.reporting_export as reporting_export
    import aqorath.reporting_runtime as reporting_runtime

    expected = b"APP-FORMAL-XLSX"
    calls = []

    def forbidden(*args, **kwargs):
        raise AssertionError("application must delegate formal XLSX export")

    def fake_export(as_of=None):
        calls.append(as_of)
        return expected

    monkeypatch.setattr(reporting_runtime, "get_financial_statements_bundle", forbidden)
    monkeypatch.setattr(formal_xlsx, "render_financial_statements_xlsx", forbidden)
    monkeypatch.setattr(reporting_export, "get_financial_statements_xlsx", fake_export)

    assert application.get_financial_statements_xlsx("2026-02-28") is expected
    assert calls == ["2026-02-28"]


def test_existing_raw_and_formal_reporting_api_remain_distinct_and_available():
    import aqorath.application as application

    assert callable(application.get_financial_report_snapshot)
    assert callable(application.get_income_statement_view)
    assert callable(application.get_balance_sheet_view)
    assert callable(application.get_financial_statements_bundle)
    assert callable(application.get_financial_report_csv)
    assert callable(application.get_financial_report_xlsx)
    assert callable(application.get_financial_statements_xlsx)
    assert application.get_financial_report_xlsx is not application.get_financial_statements_xlsx
    assert callable(application.get_trial_balance)
