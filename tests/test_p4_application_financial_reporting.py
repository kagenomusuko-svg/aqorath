"""Phase 4C.1 — canonical reporting runtime + application boundary contracts."""

from decimal import Decimal
from inspect import signature

import pytest


def test_reporting_runtime_and_application_public_contracts_exist():
    import aqorath.application as application
    import aqorath.reporting_runtime as runtime

    assert callable(runtime.get_financial_report_snapshot)
    assert callable(application.get_financial_report_snapshot)

    runtime_params = signature(runtime.get_financial_report_snapshot).parameters
    app_params = signature(application.get_financial_report_snapshot).parameters
    assert list(runtime_params) == ["as_of"]
    assert list(app_params) == ["as_of"]
    assert runtime_params["as_of"].default is None
    assert app_params["as_of"].default is None


def test_reporting_runtime_resolves_canonical_path_catalog_and_source_exactly_once(monkeypatch):
    import aqorath.accounting_rules as accounting_rules
    import aqorath.reporting_runtime as runtime
    import aqorath.reporting_source as reporting_source
    import aqorath.storage as storage

    db_path = object()
    catalog = object()
    snapshot = object()
    calls = []

    def get_db_path():
        calls.append(("path",))
        return db_path

    def load_catalog():
        calls.append(("catalog",))
        return catalog

    def build(path, supplied_catalog, as_of=None):
        calls.append(("source", path, supplied_catalog, as_of))
        return snapshot

    monkeypatch.setattr(storage, "get_db_path", get_db_path)
    monkeypatch.setattr(accounting_rules, "load_catalog", load_catalog)
    monkeypatch.setattr(
        reporting_source,
        "build_financial_report_snapshot_from_sqlite",
        build,
    )

    result = runtime.get_financial_report_snapshot(as_of="2026-07-31")

    assert result is snapshot
    assert calls.count(("path",)) == 1
    assert calls.count(("catalog",)) == 1
    assert calls.count(("source", db_path, catalog, "2026-07-31")) == 1
    assert calls[-1] == ("source", db_path, catalog, "2026-07-31")


def test_reporting_runtime_passes_exact_none_as_of_and_dependency_objects(monkeypatch):
    import aqorath.accounting_rules as accounting_rules
    import aqorath.reporting_runtime as runtime
    import aqorath.reporting_source as reporting_source
    import aqorath.storage as storage

    db_path = object()
    catalog = object()
    snapshot = object()
    seen = []

    monkeypatch.setattr(storage, "get_db_path", lambda: db_path)
    monkeypatch.setattr(accounting_rules, "load_catalog", lambda: catalog)

    def build(path, supplied_catalog, as_of=None):
        seen.append((path, supplied_catalog, as_of))
        return snapshot

    monkeypatch.setattr(
        reporting_source,
        "build_financial_report_snapshot_from_sqlite",
        build,
    )

    assert runtime.get_financial_report_snapshot() is snapshot
    assert seen == [(db_path, catalog, None)]


def test_reporting_runtime_does_not_use_core_trial_balance_or_hidden_db_discovery(monkeypatch):
    import aqorath.accounting_rules as accounting_rules
    import aqorath.core as core
    import aqorath.reporting_runtime as runtime
    import aqorath.reporting_source as reporting_source
    import aqorath.storage as storage

    snapshot = object()

    def forbidden(*args, **kwargs):
        raise AssertionError("reporting runtime must not use core balance/path discovery")

    monkeypatch.setattr(core, "trial_balance", forbidden)
    monkeypatch.setattr(core, "_find_db_path", forbidden)
    monkeypatch.setattr(storage, "get_db_path", lambda: "canonical.db")
    monkeypatch.setattr(accounting_rules, "load_catalog", lambda: {"catalog": True})
    monkeypatch.setattr(
        reporting_source,
        "build_financial_report_snapshot_from_sqlite",
        lambda path, catalog, as_of=None: snapshot,
    )

    assert runtime.get_financial_report_snapshot("2026-08-26") is snapshot


def test_reporting_runtime_propagates_source_failure_without_retry_or_fallback(monkeypatch):
    import aqorath.accounting_rules as accounting_rules
    import aqorath.reporting_runtime as runtime
    import aqorath.reporting_source as reporting_source
    import aqorath.storage as storage

    calls = []

    class SourceFailure(RuntimeError):
        pass

    monkeypatch.setattr(storage, "get_db_path", lambda: "canonical.db")
    monkeypatch.setattr(accounting_rules, "load_catalog", lambda: {"catalog": True})

    def fail(path, catalog, as_of=None):
        calls.append((path, catalog, as_of))
        raise SourceFailure("report source failed")

    monkeypatch.setattr(
        reporting_source,
        "build_financial_report_snapshot_from_sqlite",
        fail,
    )

    with pytest.raises(SourceFailure, match="report source failed"):
        runtime.get_financial_report_snapshot("2026-08-26")

    assert calls == [("canonical.db", {"catalog": True}, "2026-08-26")]


def test_application_delegates_reporting_to_runtime_exactly_once(monkeypatch):
    import aqorath.application as application
    import aqorath.reporting_runtime as runtime

    snapshot = object()
    calls = []

    def get_snapshot(as_of=None):
        calls.append(as_of)
        return snapshot

    monkeypatch.setattr(runtime, "get_financial_report_snapshot", get_snapshot)

    result = application.get_financial_report_snapshot(as_of="2026-06-30")
    assert result is snapshot
    assert calls == ["2026-06-30"]


def test_application_reporting_does_not_resolve_storage_catalog_or_source_itself(monkeypatch):
    import aqorath.accounting_rules as accounting_rules
    import aqorath.application as application
    import aqorath.reporting_runtime as runtime
    import aqorath.reporting_source as reporting_source
    import aqorath.storage as storage

    snapshot = object()

    def forbidden(*args, **kwargs):
        raise AssertionError("application must delegate reporting only to runtime")

    monkeypatch.setattr(storage, "get_db_path", forbidden)
    monkeypatch.setattr(accounting_rules, "load_catalog", forbidden)
    monkeypatch.setattr(
        reporting_source,
        "build_financial_report_snapshot_from_sqlite",
        forbidden,
    )
    monkeypatch.setattr(
        runtime,
        "get_financial_report_snapshot",
        lambda as_of=None: snapshot,
    )

    assert application.get_financial_report_snapshot("2026-08-26") is snapshot


def test_canonical_reporting_runtime_real_sqlite_integration(tmp_path, monkeypatch):
    import sqlite3

    import aqorath.accounting_rules as accounting_rules
    import aqorath.reporting_runtime as runtime

    db = tmp_path / "canonical-report.db"
    conn = sqlite3.connect(str(db))
    try:
        conn.executescript(
            """
            CREATE TABLE account (
                id INTEGER PRIMARY KEY,
                code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                nature TEXT NOT NULL,
                origin TEXT DEFAULT 'canonical',
                parent_id INTEGER
            );
            CREATE TABLE journalentry (
                id INTEGER PRIMARY KEY,
                date TEXT NOT NULL,
                concept TEXT
            );
            CREATE TABLE journalline (
                id INTEGER PRIMARY KEY,
                entry_id INTEGER,
                account_code TEXT,
                account_id INTEGER,
                debit TEXT NOT NULL DEFAULT '0',
                credit TEXT NOT NULL DEFAULT '0'
            );
            INSERT INTO account(id, code, name, nature)
            VALUES (1, '1101', 'Bancos', 'DEBIT');
            INSERT INTO account(id, code, name, nature)
            VALUES (2, '4201', 'Ventas', 'CREDIT');
            INSERT INTO journalentry(id, date, concept)
            VALUES (1, '2026-07-15', 'sale');
            INSERT INTO journalline(entry_id, account_code, account_id, debit, credit)
            VALUES (1, '1101', 1, '200.00', '0');
            INSERT INTO journalline(entry_id, account_code, account_id, debit, credit)
            VALUES (1, '4201', 2, '0', '200.00');
            """
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("AQORATH_DB", str(db))
    monkeypatch.setattr(
        accounting_rules,
        "load_catalog",
        lambda: {
            "1101": {
                "tipo": "Activo",
                "subtipo": "Circulante",
                "naturaleza": "Deudora",
            },
            "4201": {
                "tipo": "Ingreso",
                "subtipo": "Ventas",
                "naturaleza": "Acreedora",
            },
        },
    )

    snapshot = runtime.get_financial_report_snapshot(as_of="2026-07-31")
    assert snapshot.as_of == "2026-07-31"
    assert {line.account_code: line.normal_balance for line in snapshot.lines} == {
        "1101": Decimal("200.00"),
        "4201": Decimal("200.00"),
    }
    assert snapshot.result == Decimal("200.00")


def test_existing_application_api_remains_available_after_reporting_integration():
    import aqorath.application as application

    required = {
        "list_templates",
        "preview_template",
        "post_template",
        "get_trial_balance",
        "preview_economic_fact",
        "prepare_economic_fact_confirmation",
        "prepare_configured_economic_fact_confirmation",
        "set_account_binding",
        "get_account_binding",
        "confirm_economic_fact",
        "post_confirmed_economic_fact",
        "get_financial_report_snapshot",
    }
    assert required.issubset(set(dir(application)))
    assert all(callable(getattr(application, name)) for name in required)
