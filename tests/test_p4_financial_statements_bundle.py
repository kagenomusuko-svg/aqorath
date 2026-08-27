"""Phase 4N.1 — coherent Financial Statements bundle contracts."""

from dataclasses import FrozenInstanceError
from decimal import Decimal
from inspect import signature

import pytest


def _line(code, name, account_type, ledger_balance, *, subtype="", nature="DEBIT"):
    from aqorath.reporting import FinancialReportLine

    return FinancialReportLine(
        account_code=code,
        account_name=name,
        account_type=account_type,
        account_subtype=subtype,
        nature=nature,
        ledger_balance=ledger_balance,
        normal_balance=Decimal("9999.99"),
    )


def _snapshot(as_of="2026-07-31"):
    from aqorath.reporting import FinancialReportSnapshot

    # 800 assets = 300 liabilities + 400 recorded equity + 100 current result.
    return FinancialReportSnapshot(
        as_of=as_of,
        lines=(
            _line("1101", "Bancos", "Activo", Decimal("1000.00")),
            _line("1205", "Depreciación acumulada", "Activo", Decimal("-200.00"), nature="CREDIT"),
            _line("2101", "Proveedores", "Pasivo", Decimal("-300.00"), nature="CREDIT"),
            _line("3101", "Capital", "Patrimonio", Decimal("-400.00"), nature="CREDIT"),
            _line("4201", "Ventas", "Ingreso", Decimal("-225.00"), nature="CREDIT"),
            _line("5101", "Costo", "Costo", Decimal("25.00")),
            _line("6101", "Gastos", "Gasto", Decimal("100.00")),
        ),
        totals=(),
        result=Decimal("999999.99"),
    )


def test_financial_statements_bundle_public_contract_and_exact_signature_exist():
    import aqorath.financial_statements as financial_statements

    assert financial_statements.FinancialStatementsBundle is not None
    assert callable(financial_statements.build_financial_statements_bundle)

    fields = tuple(financial_statements.FinancialStatementsBundle.__dataclass_fields__)
    assert fields == ("snapshot", "income_statement", "balance_sheet")

    params = signature(financial_statements.build_financial_statements_bundle).parameters
    assert list(params) == ["snapshot"]


def test_financial_statements_bundle_is_deeply_immutable():
    import aqorath.financial_statements as financial_statements

    bundle = financial_statements.build_financial_statements_bundle(_snapshot())

    with pytest.raises(FrozenInstanceError):
        bundle.snapshot = None
    with pytest.raises(FrozenInstanceError):
        bundle.income_statement = None
    with pytest.raises(FrozenInstanceError):
        bundle.balance_sheet = None

    with pytest.raises(FrozenInstanceError):
        bundle.income_statement.result = Decimal("0")
    with pytest.raises(FrozenInstanceError):
        bundle.balance_sheet.current_result = Decimal("0")


def test_bundle_passes_exact_same_snapshot_to_both_statement_builders_once_in_order(monkeypatch):
    import aqorath.balance_sheet as balance_sheet
    import aqorath.financial_statements as financial_statements
    import aqorath.income_statement as income_statement

    snapshot = _snapshot()
    income_view = object()
    balance_view = object()
    calls = []

    def fake_income(value):
        calls.append(("income", value))
        return income_view

    def fake_balance(value):
        calls.append(("balance", value))
        return balance_view

    monkeypatch.setattr(income_statement, "build_income_statement_view", fake_income)
    monkeypatch.setattr(balance_sheet, "build_balance_sheet_view", fake_balance)

    bundle = financial_statements.build_financial_statements_bundle(snapshot)

    assert bundle.snapshot is snapshot
    assert bundle.income_statement is income_view
    assert bundle.balance_sheet is balance_view
    assert calls == [
        ("income", snapshot),
        ("balance", snapshot),
    ]
    assert calls[0][1] is calls[1][1]


def test_bundle_real_views_share_exact_as_of_and_current_result_from_same_snapshot():
    import aqorath.financial_statements as financial_statements

    snapshot = _snapshot(as_of="2026-06-30")
    bundle = financial_statements.build_financial_statements_bundle(snapshot)

    assert bundle.snapshot is snapshot
    assert bundle.income_statement.as_of == "2026-06-30"
    assert bundle.balance_sheet.as_of == "2026-06-30"
    assert bundle.income_statement.result == Decimal("100.00")
    assert bundle.balance_sheet.current_result == Decimal("100.00")
    assert bundle.income_statement.result == bundle.balance_sheet.current_result
    assert bundle.balance_sheet.balance_difference == Decimal("0.00")


def test_bundle_preserves_statement_specific_netting_from_same_snapshot():
    import aqorath.financial_statements as financial_statements

    bundle = financial_statements.build_financial_statements_bundle(_snapshot())

    assert bundle.income_statement.income.total == Decimal("225.00")
    assert bundle.income_statement.costs.total == Decimal("25.00")
    assert bundle.income_statement.expenses.total == Decimal("100.00")
    assert bundle.balance_sheet.assets.total == Decimal("800.00")
    assert bundle.balance_sheet.liabilities.total == Decimal("300.00")
    assert bundle.balance_sheet.recorded_equity.total == Decimal("400.00")
    assert bundle.balance_sheet.total_equity == Decimal("500.00")


def test_bundle_rejects_non_nominal_snapshot_before_any_projection(monkeypatch):
    import aqorath.balance_sheet as balance_sheet
    import aqorath.financial_statements as financial_statements
    import aqorath.income_statement as income_statement

    calls = []

    def forbidden(value):
        calls.append(value)
        raise AssertionError("projection must not run for a non-nominal snapshot")

    monkeypatch.setattr(income_statement, "build_income_statement_view", forbidden)
    monkeypatch.setattr(balance_sheet, "build_balance_sheet_view", forbidden)

    class FakeSnapshot:
        pass

    with pytest.raises(TypeError):
        financial_statements.build_financial_statements_bundle(FakeSnapshot())

    assert calls == []


def test_bundle_propagates_income_failure_without_balance_projection_or_retry(monkeypatch):
    import aqorath.balance_sheet as balance_sheet
    import aqorath.financial_statements as financial_statements
    import aqorath.income_statement as income_statement

    snapshot = _snapshot()
    failure = ValueError("income failure")
    calls = []

    def fail_income(value):
        calls.append(("income", value))
        raise failure

    def forbidden_balance(value):
        raise AssertionError("balance projection must not run after income failure")

    monkeypatch.setattr(income_statement, "build_income_statement_view", fail_income)
    monkeypatch.setattr(balance_sheet, "build_balance_sheet_view", forbidden_balance)

    with pytest.raises(ValueError) as caught:
        financial_statements.build_financial_statements_bundle(snapshot)

    assert caught.value is failure
    assert calls == [("income", snapshot)]


def test_bundle_propagates_balance_failure_without_retry_or_alternate_snapshot(monkeypatch):
    import aqorath.balance_sheet as balance_sheet
    import aqorath.financial_statements as financial_statements
    import aqorath.income_statement as income_statement

    snapshot = _snapshot()
    failure = RuntimeError("balance failure")
    calls = []

    def fake_income(value):
        calls.append(("income", value))
        return object()

    def fail_balance(value):
        calls.append(("balance", value))
        raise failure

    monkeypatch.setattr(income_statement, "build_income_statement_view", fake_income)
    monkeypatch.setattr(balance_sheet, "build_balance_sheet_view", fail_balance)

    with pytest.raises(RuntimeError) as caught:
        financial_statements.build_financial_statements_bundle(snapshot)

    assert caught.value is failure
    assert calls == [
        ("income", snapshot),
        ("balance", snapshot),
    ]


def test_bundle_builder_is_pure_and_does_not_mutate_or_open_authorities(monkeypatch):
    import builtins
    import sqlite3

    import aqorath.accounting_rules as accounting_rules
    import aqorath.financial_statements as financial_statements
    import aqorath.reporting as reporting
    import aqorath.reporting_export as reporting_export
    import aqorath.reporting_runtime as reporting_runtime
    import aqorath.reporting_source as reporting_source
    import aqorath.storage as storage

    snapshot = _snapshot()
    before = snapshot

    def forbidden(*args, **kwargs):
        raise AssertionError("bundle must consume only its supplied snapshot")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    monkeypatch.setattr(storage, "get_db_path", forbidden)
    monkeypatch.setattr(accounting_rules, "load_catalog", forbidden)
    monkeypatch.setattr(reporting, "build_financial_report_snapshot", forbidden)
    monkeypatch.setattr(reporting_runtime, "get_financial_report_snapshot", forbidden)
    monkeypatch.setattr(reporting_source, "build_financial_report_snapshot_from_sqlite", forbidden)
    monkeypatch.setattr(reporting_export, "get_financial_report_csv", forbidden)
    monkeypatch.setattr(reporting_export, "get_financial_report_xlsx", forbidden)

    bundle = financial_statements.build_financial_statements_bundle(snapshot)
    assert snapshot == before
    assert bundle.snapshot is snapshot
    assert bundle.income_statement.result == Decimal("100.00")
    assert bundle.balance_sheet.balance_difference == Decimal("0.00")
