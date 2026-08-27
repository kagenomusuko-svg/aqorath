"""Phase 4L.1 — canonical Balance Sheet runtime/application contracts."""

from inspect import signature

import pytest


def test_balance_sheet_runtime_and_application_public_contracts_exist():
    import aqorath.application as application
    import aqorath.reporting_runtime as reporting_runtime

    assert callable(reporting_runtime.get_balance_sheet_view)
    assert callable(application.get_balance_sheet_view)

    runtime_params = signature(reporting_runtime.get_balance_sheet_view).parameters
    app_params = signature(application.get_balance_sheet_view).parameters
    assert list(runtime_params) == ["as_of"]
    assert list(app_params) == ["as_of"]
    assert runtime_params["as_of"].default is None
    assert app_params["as_of"].default is None


def test_balance_sheet_runtime_builds_snapshot_then_view_exactly_once(monkeypatch):
    import aqorath.balance_sheet as balance_sheet
    import aqorath.reporting_runtime as reporting_runtime

    snapshot = object()
    view = object()
    calls = []

    def fake_snapshot(as_of=None):
        calls.append(("snapshot", as_of))
        return snapshot

    def fake_view(value):
        calls.append(("view", value))
        return view

    monkeypatch.setattr(reporting_runtime, "get_financial_report_snapshot", fake_snapshot)
    monkeypatch.setattr(balance_sheet, "build_balance_sheet_view", fake_view)

    result = reporting_runtime.get_balance_sheet_view("2026-07-31")
    assert result is view
    assert calls == [
        ("snapshot", "2026-07-31"),
        ("view", snapshot),
    ]


def test_balance_sheet_runtime_passes_exact_none_as_of(monkeypatch):
    import aqorath.balance_sheet as balance_sheet
    import aqorath.reporting_runtime as reporting_runtime

    snapshot = object()
    seen = []

    def fake_snapshot(as_of=None):
        seen.append(as_of)
        return snapshot

    monkeypatch.setattr(reporting_runtime, "get_financial_report_snapshot", fake_snapshot)
    monkeypatch.setattr(balance_sheet, "build_balance_sheet_view", lambda value: "view")

    assert reporting_runtime.get_balance_sheet_view() == "view"
    assert seen == [None]


def test_balance_sheet_runtime_reuses_snapshot_authority_instead_of_resolving_storage_itself(monkeypatch):
    import aqorath.accounting_rules as accounting_rules
    import aqorath.balance_sheet as balance_sheet
    import aqorath.reporting_runtime as reporting_runtime
    import aqorath.reporting_source as reporting_source
    import aqorath.storage as storage

    snapshot = object()

    def forbidden(*args, **kwargs):
        raise AssertionError("Balance Sheet runtime must reuse get_financial_report_snapshot")

    monkeypatch.setattr(storage, "get_db_path", forbidden)
    monkeypatch.setattr(accounting_rules, "load_catalog", forbidden)
    monkeypatch.setattr(reporting_source, "build_financial_report_snapshot_from_sqlite", forbidden)
    monkeypatch.setattr(reporting_runtime, "get_financial_report_snapshot", lambda as_of=None: snapshot)
    monkeypatch.setattr(balance_sheet, "build_balance_sheet_view", lambda value: "view")

    assert reporting_runtime.get_balance_sheet_view("2026-03-31") == "view"


def test_balance_sheet_runtime_propagates_snapshot_failure_without_projection_or_retry(monkeypatch):
    import aqorath.balance_sheet as balance_sheet
    import aqorath.reporting_runtime as reporting_runtime

    failure = RuntimeError("snapshot failure")
    calls = []

    def fail_snapshot(as_of=None):
        calls.append(as_of)
        raise failure

    def forbidden_projection(snapshot):
        raise AssertionError("projection must not run after snapshot failure")

    monkeypatch.setattr(reporting_runtime, "get_financial_report_snapshot", fail_snapshot)
    monkeypatch.setattr(balance_sheet, "build_balance_sheet_view", forbidden_projection)

    with pytest.raises(RuntimeError) as caught:
        reporting_runtime.get_balance_sheet_view("2026-06-30")

    assert caught.value is failure
    assert calls == ["2026-06-30"]


def test_balance_sheet_runtime_propagates_projection_failure_without_rebuilding_snapshot(monkeypatch):
    import aqorath.balance_sheet as balance_sheet
    import aqorath.reporting_runtime as reporting_runtime

    snapshot = object()
    failure = ValueError("view failure")
    calls = []

    def fake_snapshot(as_of=None):
        calls.append(("snapshot", as_of))
        return snapshot

    def fail_view(value):
        calls.append(("view", value))
        raise failure

    monkeypatch.setattr(reporting_runtime, "get_financial_report_snapshot", fake_snapshot)
    monkeypatch.setattr(balance_sheet, "build_balance_sheet_view", fail_view)

    with pytest.raises(ValueError) as caught:
        reporting_runtime.get_balance_sheet_view("2026-05-31")

    assert caught.value is failure
    assert calls == [
        ("snapshot", "2026-05-31"),
        ("view", snapshot),
    ]


def test_application_delegates_balance_sheet_exactly_once(monkeypatch):
    import aqorath.application as application
    import aqorath.reporting_runtime as reporting_runtime

    assert application._reporting_runtime is reporting_runtime
    view = object()
    calls = []

    def fake_view(as_of=None):
        calls.append(as_of)
        return view

    monkeypatch.setattr(reporting_runtime, "get_balance_sheet_view", fake_view)

    assert application.get_balance_sheet_view("2026-04-30") is view
    assert calls == ["2026-04-30"]


def test_application_balance_sheet_does_not_build_snapshot_or_projection_itself(monkeypatch):
    import aqorath.application as application
    import aqorath.balance_sheet as balance_sheet
    import aqorath.reporting_runtime as reporting_runtime

    def forbidden(*args, **kwargs):
        raise AssertionError("application must delegate Balance Sheet to reporting_runtime")

    monkeypatch.setattr(reporting_runtime, "get_financial_report_snapshot", forbidden)
    monkeypatch.setattr(balance_sheet, "build_balance_sheet_view", forbidden)
    monkeypatch.setattr(reporting_runtime, "get_balance_sheet_view", lambda as_of=None: "delegated")

    assert application.get_balance_sheet_view(as_of=None) == "delegated"


def test_existing_reporting_application_api_remains_available_after_balance_sheet_integration():
    import aqorath.application as application

    assert callable(application.get_financial_report_snapshot)
    assert callable(application.get_income_statement_view)
    assert callable(application.get_financial_report_csv)
    assert callable(application.get_financial_report_xlsx)
    assert callable(application.get_trial_balance)
    assert callable(application.preview_economic_fact)
    assert callable(application.post_confirmed_economic_fact)
