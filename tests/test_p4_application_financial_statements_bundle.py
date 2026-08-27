"""Phase 4O.1 — canonical coherent financial-statements bundle boundary contracts."""

from inspect import signature

import pytest


def test_financial_statements_runtime_and_application_public_contracts_exist():
    import aqorath.application as application
    import aqorath.reporting_runtime as reporting_runtime

    assert callable(reporting_runtime.get_financial_statements_bundle)
    assert callable(application.get_financial_statements_bundle)

    runtime_params = signature(reporting_runtime.get_financial_statements_bundle).parameters
    app_params = signature(application.get_financial_statements_bundle).parameters
    assert list(runtime_params) == ["as_of"]
    assert list(app_params) == ["as_of"]
    assert runtime_params["as_of"].default is None
    assert app_params["as_of"].default is None


def test_bundle_runtime_builds_one_snapshot_then_bundle_exactly_once(monkeypatch):
    import aqorath.financial_statements as financial_statements
    import aqorath.reporting_runtime as reporting_runtime

    snapshot = object()
    bundle = object()
    calls = []

    def fake_snapshot(as_of=None):
        calls.append(("snapshot", as_of))
        return snapshot

    def fake_bundle(value):
        calls.append(("bundle", value))
        return bundle

    monkeypatch.setattr(reporting_runtime, "get_financial_report_snapshot", fake_snapshot)
    monkeypatch.setattr(financial_statements, "build_financial_statements_bundle", fake_bundle)

    result = reporting_runtime.get_financial_statements_bundle("2026-07-31")
    assert result is bundle
    assert calls == [
        ("snapshot", "2026-07-31"),
        ("bundle", snapshot),
    ]


def test_bundle_runtime_passes_exact_none_as_of(monkeypatch):
    import aqorath.financial_statements as financial_statements
    import aqorath.reporting_runtime as reporting_runtime

    snapshot = object()
    seen = []

    def fake_snapshot(as_of=None):
        seen.append(as_of)
        return snapshot

    monkeypatch.setattr(reporting_runtime, "get_financial_report_snapshot", fake_snapshot)
    monkeypatch.setattr(financial_statements, "build_financial_statements_bundle", lambda value: "bundle")

    assert reporting_runtime.get_financial_statements_bundle() == "bundle"
    assert seen == [None]


def test_bundle_runtime_reuses_snapshot_authority_and_never_calls_independent_statement_endpoints(monkeypatch):
    import aqorath.accounting_rules as accounting_rules
    import aqorath.financial_statements as financial_statements
    import aqorath.reporting_runtime as reporting_runtime
    import aqorath.reporting_source as reporting_source
    import aqorath.storage as storage

    snapshot = object()

    def forbidden(*args, **kwargs):
        raise AssertionError("bundle runtime must use exactly one canonical snapshot")

    monkeypatch.setattr(storage, "get_db_path", forbidden)
    monkeypatch.setattr(accounting_rules, "load_catalog", forbidden)
    monkeypatch.setattr(reporting_source, "build_financial_report_snapshot_from_sqlite", forbidden)
    monkeypatch.setattr(reporting_runtime, "get_income_statement_view", forbidden)
    monkeypatch.setattr(reporting_runtime, "get_balance_sheet_view", forbidden)
    monkeypatch.setattr(reporting_runtime, "get_financial_report_snapshot", lambda as_of=None: snapshot)
    monkeypatch.setattr(financial_statements, "build_financial_statements_bundle", lambda value: "bundle")

    assert reporting_runtime.get_financial_statements_bundle("2026-03-31") == "bundle"


def test_bundle_runtime_propagates_snapshot_failure_without_bundle_build_or_retry(monkeypatch):
    import aqorath.financial_statements as financial_statements
    import aqorath.reporting_runtime as reporting_runtime

    failure = RuntimeError("snapshot failure")
    calls = []

    def fail_snapshot(as_of=None):
        calls.append(as_of)
        raise failure

    def forbidden_bundle(snapshot):
        raise AssertionError("bundle builder must not run after snapshot failure")

    monkeypatch.setattr(reporting_runtime, "get_financial_report_snapshot", fail_snapshot)
    monkeypatch.setattr(financial_statements, "build_financial_statements_bundle", forbidden_bundle)

    with pytest.raises(RuntimeError) as caught:
        reporting_runtime.get_financial_statements_bundle("2026-06-30")

    assert caught.value is failure
    assert calls == ["2026-06-30"]


def test_bundle_runtime_propagates_bundle_failure_without_rebuilding_snapshot(monkeypatch):
    import aqorath.financial_statements as financial_statements
    import aqorath.reporting_runtime as reporting_runtime

    snapshot = object()
    failure = ValueError("bundle failure")
    calls = []

    def fake_snapshot(as_of=None):
        calls.append(("snapshot", as_of))
        return snapshot

    def fail_bundle(value):
        calls.append(("bundle", value))
        raise failure

    monkeypatch.setattr(reporting_runtime, "get_financial_report_snapshot", fake_snapshot)
    monkeypatch.setattr(financial_statements, "build_financial_statements_bundle", fail_bundle)

    with pytest.raises(ValueError) as caught:
        reporting_runtime.get_financial_statements_bundle("2026-05-31")

    assert caught.value is failure
    assert calls == [
        ("snapshot", "2026-05-31"),
        ("bundle", snapshot),
    ]


def test_application_delegates_financial_statements_bundle_exactly_once(monkeypatch):
    import aqorath.application as application
    import aqorath.reporting_runtime as reporting_runtime

    bundle = object()
    calls = []

    def fake_bundle(as_of=None):
        calls.append(as_of)
        return bundle

    monkeypatch.setattr(reporting_runtime, "get_financial_statements_bundle", fake_bundle)

    assert application.get_financial_statements_bundle("2026-04-30") is bundle
    assert calls == ["2026-04-30"]


def test_application_bundle_does_not_build_snapshot_or_statements_itself(monkeypatch):
    import aqorath.application as application
    import aqorath.financial_statements as financial_statements
    import aqorath.reporting_runtime as reporting_runtime

    def forbidden(*args, **kwargs):
        raise AssertionError("application must delegate bundle construction to reporting_runtime")

    monkeypatch.setattr(reporting_runtime, "get_financial_report_snapshot", forbidden)
    monkeypatch.setattr(financial_statements, "build_financial_statements_bundle", forbidden)
    monkeypatch.setattr(reporting_runtime, "get_financial_statements_bundle", lambda as_of=None: "delegated")

    assert application.get_financial_statements_bundle(as_of=None) == "delegated"


def test_existing_reporting_application_api_remains_available_after_bundle_integration():
    import aqorath.application as application

    assert callable(application.get_financial_report_snapshot)
    assert callable(application.get_income_statement_view)
    assert callable(application.get_balance_sheet_view)
    assert callable(application.get_financial_report_csv)
    assert callable(application.get_financial_report_xlsx)
    assert callable(application.get_trial_balance)
    assert callable(application.preview_economic_fact)
    assert callable(application.post_confirmed_economic_fact)
