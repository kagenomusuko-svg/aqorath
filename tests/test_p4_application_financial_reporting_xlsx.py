"""Phase 4G.1 — canonical XLSX reporting export boundary contracts."""

from inspect import signature

import pytest


def test_xlsx_export_and_application_public_contracts_exist():
    import aqorath.application as application
    import aqorath.reporting_export as reporting_export

    assert callable(reporting_export.get_financial_report_xlsx)
    assert callable(application.get_financial_report_xlsx)

    export_params = signature(reporting_export.get_financial_report_xlsx).parameters
    app_params = signature(application.get_financial_report_xlsx).parameters
    assert list(export_params) == ["as_of"]
    assert list(app_params) == ["as_of"]
    assert export_params["as_of"].default is None
    assert app_params["as_of"].default is None


def test_xlsx_export_builds_snapshot_then_renders_exactly_once(monkeypatch):
    import aqorath.reporting_export as reporting_export
    import aqorath.reporting_runtime as reporting_runtime
    import aqorath.reporting_xlsx as reporting_xlsx

    snapshot = object()
    calls = []
    expected = b"XLSX-BYTES"

    def fake_snapshot(as_of=None):
        calls.append(("snapshot", as_of))
        return snapshot

    def fake_render(value):
        calls.append(("render", value))
        return expected

    monkeypatch.setattr(reporting_runtime, "get_financial_report_snapshot", fake_snapshot)
    monkeypatch.setattr(reporting_xlsx, "render_financial_report_xlsx", fake_render)

    result = reporting_export.get_financial_report_xlsx(as_of="2026-07-31")

    assert result is expected
    assert calls == [
        ("snapshot", "2026-07-31"),
        ("render", snapshot),
    ]


def test_xlsx_export_passes_exact_none_as_of(monkeypatch):
    import aqorath.reporting_export as reporting_export
    import aqorath.reporting_runtime as reporting_runtime
    import aqorath.reporting_xlsx as reporting_xlsx

    snapshot = object()
    seen = []

    def fake_snapshot(as_of=None):
        seen.append(as_of)
        return snapshot

    monkeypatch.setattr(reporting_runtime, "get_financial_report_snapshot", fake_snapshot)
    monkeypatch.setattr(reporting_xlsx, "render_financial_report_xlsx", lambda value: b"ok")

    assert reporting_export.get_financial_report_xlsx() == b"ok"
    assert seen == [None]


def test_xlsx_export_does_not_resolve_storage_catalog_or_sqlite_source_itself(monkeypatch):
    import aqorath.accounting_rules as accounting_rules
    import aqorath.reporting_export as reporting_export
    import aqorath.reporting_runtime as reporting_runtime
    import aqorath.reporting_source as reporting_source
    import aqorath.reporting_xlsx as reporting_xlsx
    import aqorath.storage as storage

    snapshot = object()

    def forbidden(*args, **kwargs):
        raise AssertionError("reporting_export must delegate authority resolution to reporting_runtime")

    monkeypatch.setattr(storage, "get_db_path", forbidden)
    monkeypatch.setattr(accounting_rules, "load_catalog", forbidden)
    monkeypatch.setattr(reporting_source, "build_financial_report_snapshot_from_sqlite", forbidden)
    monkeypatch.setattr(reporting_runtime, "get_financial_report_snapshot", lambda as_of=None: snapshot)
    monkeypatch.setattr(reporting_xlsx, "render_financial_report_xlsx", lambda value: b"xlsx")

    assert reporting_export.get_financial_report_xlsx("2026-01-31") == b"xlsx"


def test_xlsx_export_propagates_runtime_failure_without_render_or_retry(monkeypatch):
    import aqorath.reporting_export as reporting_export
    import aqorath.reporting_runtime as reporting_runtime
    import aqorath.reporting_xlsx as reporting_xlsx

    failure = RuntimeError("snapshot failure")
    calls = []

    def fail_snapshot(as_of=None):
        calls.append(as_of)
        raise failure

    def forbidden_render(snapshot):
        raise AssertionError("renderer must not run after snapshot failure")

    monkeypatch.setattr(reporting_runtime, "get_financial_report_snapshot", fail_snapshot)
    monkeypatch.setattr(reporting_xlsx, "render_financial_report_xlsx", forbidden_render)

    with pytest.raises(RuntimeError) as caught:
        reporting_export.get_financial_report_xlsx("2026-06-30")

    assert caught.value is failure
    assert calls == ["2026-06-30"]


def test_xlsx_export_propagates_renderer_failure_without_retry_or_rebuild(monkeypatch):
    import aqorath.reporting_export as reporting_export
    import aqorath.reporting_runtime as reporting_runtime
    import aqorath.reporting_xlsx as reporting_xlsx

    snapshot = object()
    failure = ValueError("render failure")
    calls = []

    def fake_snapshot(as_of=None):
        calls.append(("snapshot", as_of))
        return snapshot

    def fail_render(value):
        calls.append(("render", value))
        raise failure

    monkeypatch.setattr(reporting_runtime, "get_financial_report_snapshot", fake_snapshot)
    monkeypatch.setattr(reporting_xlsx, "render_financial_report_xlsx", fail_render)

    with pytest.raises(ValueError) as caught:
        reporting_export.get_financial_report_xlsx("2026-05-31")

    assert caught.value is failure
    assert calls == [
        ("snapshot", "2026-05-31"),
        ("render", snapshot),
    ]


def test_application_delegates_xlsx_export_exactly_once(monkeypatch):
    import aqorath.application as application
    import aqorath.reporting_export as reporting_export

    assert application._reporting_export is reporting_export
    calls = []
    expected = b"APP-XLSX"

    def fake_export(as_of=None):
        calls.append(as_of)
        return expected

    monkeypatch.setattr(reporting_export, "get_financial_report_xlsx", fake_export)

    assert application.get_financial_report_xlsx("2026-04-30") is expected
    assert calls == ["2026-04-30"]


def test_application_xlsx_export_does_not_build_or_render_itself(monkeypatch):
    import aqorath.application as application
    import aqorath.reporting_export as reporting_export
    import aqorath.reporting_runtime as reporting_runtime
    import aqorath.reporting_xlsx as reporting_xlsx

    def forbidden(*args, **kwargs):
        raise AssertionError("application must delegate XLSX export to reporting_export")

    monkeypatch.setattr(reporting_runtime, "get_financial_report_snapshot", forbidden)
    monkeypatch.setattr(reporting_xlsx, "render_financial_report_xlsx", forbidden)
    monkeypatch.setattr(reporting_export, "get_financial_report_xlsx", lambda as_of=None: b"delegated")

    assert application.get_financial_report_xlsx(as_of=None) == b"delegated"


def test_existing_reporting_application_api_remains_available_after_xlsx_export():
    import aqorath.application as application

    assert callable(application.get_financial_report_snapshot)
    assert callable(application.get_financial_report_csv)
    assert callable(application.get_trial_balance)
    assert callable(application.preview_economic_fact)
    assert callable(application.post_confirmed_economic_fact)
