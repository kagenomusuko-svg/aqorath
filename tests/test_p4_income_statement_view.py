"""Phase 4M.1 — Income Statement net-semantics hardening contracts.

These contracts explicitly supersede the historical 4H rule that treated
FinancialReportSnapshot.totals/result as formal Income Statement authority.
Formal statement totals now come from ledger-based net semantics (Phase 4J).
"""

from dataclasses import FrozenInstanceError
from decimal import Decimal
from inspect import signature

import pytest


def _line(code, name, account_type, ledger_balance, *, subtype="", nature="DEBIT", normal_balance=Decimal("9999.99")):
    from aqorath.reporting import FinancialReportLine

    return FinancialReportLine(
        account_code=code,
        account_name=name,
        account_type=account_type,
        account_subtype=subtype,
        nature=nature,
        ledger_balance=ledger_balance,
        normal_balance=normal_balance,
    )


def _snapshot(as_of="2026-07-31"):
    from aqorath.reporting import FinancialReportSnapshot, FinancialReportTotal

    return FinancialReportSnapshot(
        as_of=as_of,
        lines=(
            _line("1101.001", "BBVA", "Activo", Decimal("1000.00"), subtype="Circulante"),
            _line("1205", "Depreciación acumulada", "Activo", Decimal("-200.00"), subtype="No circulante", nature="CREDIT"),
            _line("2101", "Proveedores", "Pasivo", Decimal("-300.00"), nature="CREDIT"),
            _line("3101", "Capital social", "Patrimonio", Decimal("-400.00"), nature="CREDIT"),
            _line("4201", "Ventas", "Ingreso", Decimal("-275.00"), nature="CREDIT"),
            _line("4299", "Devoluciones sobre ventas", "Ingreso", Decimal("50.00")),
            _line("5101", "Costo de ventas", "Costo", Decimal("25.00")),
            _line("6101", "Servicios", "Gasto", Decimal("120.00")),
            _line("6199", "Recuperación de gasto", "Gasto", Decimal("-20.00"), nature="CREDIT"),
        ),
        # Deliberately poisoned legacy summary fields. Formal statements must ignore them.
        totals=(
            FinancialReportTotal("Ingreso", Decimal("999999.01")),
            FinancialReportTotal("Costo", Decimal("999999.02")),
            FinancialReportTotal("Gasto", Decimal("999999.03")),
        ),
        result=Decimal("999999.04"),
    )


def test_income_statement_public_contract_and_exact_signature_remain_stable():
    import aqorath.income_statement as income_statement

    assert callable(income_statement.build_income_statement_view)
    assert income_statement.IncomeStatementSection is not None
    assert income_statement.IncomeStatementView is not None

    params = signature(income_statement.build_income_statement_view).parameters
    assert list(params) == ["snapshot"]
    assert tuple(income_statement.IncomeStatementSection.__dataclass_fields__) == (
        "account_type",
        "lines",
        "total",
    )
    assert tuple(income_statement.IncomeStatementView.__dataclass_fields__) == (
        "as_of",
        "income",
        "costs",
        "expenses",
        "result",
    )


def test_income_statement_view_remains_deeply_immutable():
    import aqorath.income_statement as income_statement

    view = income_statement.build_income_statement_view(_snapshot())

    with pytest.raises(FrozenInstanceError):
        view.result = Decimal("0")
    with pytest.raises(FrozenInstanceError):
        view.income.total = Decimal("0")
    assert isinstance(view.income.lines, tuple)
    with pytest.raises(TypeError):
        view.income.lines[0] = view.income.lines[0]


def test_income_statement_selects_only_profit_and_loss_lines_preserving_order_and_identity():
    import aqorath.income_statement as income_statement

    snapshot = _snapshot()
    view = income_statement.build_income_statement_view(snapshot)

    assert tuple(line.account_code for line in view.income.lines) == ("4201", "4299")
    assert tuple(line.account_code for line in view.costs.lines) == ("5101",)
    assert tuple(line.account_code for line in view.expenses.lines) == ("6101", "6199")

    assert view.income.lines[0] is snapshot.lines[4]
    assert view.income.lines[1] is snapshot.lines[5]
    assert view.costs.lines[0] is snapshot.lines[6]
    assert view.expenses.lines[0] is snapshot.lines[7]
    assert view.expenses.lines[1] is snapshot.lines[8]

    visible_codes = {
        line.account_code
        for section in (view.income, view.costs, view.expenses)
        for line in section.lines
    }
    assert visible_codes == {"4201", "4299", "5101", "6101", "6199"}


def test_income_statement_calls_net_semantics_exactly_once_and_uses_returned_values(monkeypatch):
    import aqorath.financial_statement_semantics as semantics
    import aqorath.income_statement as income_statement

    snapshot = _snapshot()
    calls = []
    sent = semantics.FinancialStatementTotals(
        as_of="SENTINEL-AS-OF",
        assets=Decimal("1"),
        liabilities=Decimal("2"),
        recorded_equity=Decimal("3"),
        income=Decimal("444.4400"),
        costs=Decimal("55.5500"),
        expenses=Decimal("66.6600"),
        result=Decimal("322.2300"),
        total_equity=Decimal("325.2300"),
        liabilities_and_equity=Decimal("327.2300"),
        balance_difference=Decimal("-326.2300"),
    )

    def fake_compute(value):
        calls.append(value)
        return sent

    monkeypatch.setattr(semantics, "compute_financial_statement_totals", fake_compute)

    view = income_statement.build_income_statement_view(snapshot)
    assert calls == [snapshot]
    assert view.as_of == "SENTINEL-AS-OF"
    assert view.income.total is sent.income
    assert view.costs.total is sent.costs
    assert view.expenses.total is sent.expenses
    assert view.result is sent.result


def test_income_statement_nets_contra_income_and_contra_expense_from_ledger_balances():
    import aqorath.income_statement as income_statement

    view = income_statement.build_income_statement_view(_snapshot())

    assert view.income.total == Decimal("225.00")
    assert view.costs.total == Decimal("25.00")
    assert view.expenses.total == Decimal("100.00")
    assert view.result == Decimal("100.00")


def test_income_statement_ignores_poisoned_snapshot_totals_result_normal_balance_and_nature():
    import aqorath.income_statement as income_statement

    snapshot = _snapshot()
    view = income_statement.build_income_statement_view(snapshot)

    assert snapshot.totals[0].amount == Decimal("999999.01")
    assert snapshot.result == Decimal("999999.04")
    assert all(line.normal_balance == Decimal("9999.99") for line in snapshot.lines)

    assert view.income.total != snapshot.totals[0].amount
    assert view.costs.total != snapshot.totals[1].amount
    assert view.expenses.total != snapshot.totals[2].amount
    assert view.result != snapshot.result
    assert view.result == Decimal("100.00")


def test_income_statement_preserves_empty_sections_decimal_exactness_and_as_of():
    from aqorath.reporting import FinancialReportSnapshot
    import aqorath.income_statement as income_statement

    snapshot = FinancialReportSnapshot(
        as_of=None,
        lines=(
            _line("1101", "Bancos", "Activo", Decimal("10.0000")),
            _line("3101", "Capital", "Patrimonio", Decimal("-10.0000"), nature="CREDIT"),
        ),
        totals=(),
        result=Decimal("123456.78"),
    )

    view = income_statement.build_income_statement_view(snapshot)
    assert view.as_of is None
    assert view.income.lines == ()
    assert view.costs.lines == ()
    assert view.expenses.lines == ()
    assert view.income.total == Decimal("0")
    assert view.costs.total == Decimal("0")
    assert view.expenses.total == Decimal("0")
    assert view.result == Decimal("0")
    assert all(isinstance(value, Decimal) for value in (
        view.income.total,
        view.costs.total,
        view.expenses.total,
        view.result,
    ))


def test_income_statement_requires_nominal_snapshot_and_decimal_ledger_balances_via_net_semantics():
    from aqorath.reporting import FinancialReportSnapshot
    import aqorath.income_statement as income_statement

    class FakeSnapshot:
        as_of = None
        lines = ()

    with pytest.raises(TypeError):
        income_statement.build_income_statement_view(FakeSnapshot())

    bad = FinancialReportSnapshot(
        as_of=None,
        lines=(
            _line("1101", "Bancos", "Activo", "10.00"),
        ),
        totals=(),
        result=Decimal("0"),
    )
    with pytest.raises(TypeError):
        income_statement.build_income_statement_view(bad)


def test_income_statement_propagates_net_semantics_failure_without_retry_or_repair(monkeypatch):
    import aqorath.financial_statement_semantics as semantics
    import aqorath.income_statement as income_statement

    failure = ValueError("net semantics failure")
    calls = []

    def fail(value):
        calls.append(value)
        raise failure

    snapshot = _snapshot()
    monkeypatch.setattr(semantics, "compute_financial_statement_totals", fail)

    with pytest.raises(ValueError) as caught:
        income_statement.build_income_statement_view(snapshot)

    assert caught.value is failure
    assert calls == [snapshot]


def test_income_statement_builder_is_pure_does_not_mutate_or_open_other_authorities(monkeypatch):
    import builtins
    import sqlite3

    import aqorath.accounting_rules as accounting_rules
    import aqorath.income_statement as income_statement
    import aqorath.reporting as reporting
    import aqorath.reporting_export as reporting_export
    import aqorath.reporting_runtime as reporting_runtime
    import aqorath.reporting_source as reporting_source
    import aqorath.storage as storage

    snapshot = _snapshot()
    before = snapshot

    def forbidden(*args, **kwargs):
        raise AssertionError("Income Statement view must consume only snapshot + net semantics")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    monkeypatch.setattr(storage, "get_db_path", forbidden)
    monkeypatch.setattr(accounting_rules, "load_catalog", forbidden)
    monkeypatch.setattr(reporting, "build_financial_report_snapshot", forbidden)
    monkeypatch.setattr(reporting_runtime, "get_financial_report_snapshot", forbidden)
    monkeypatch.setattr(reporting_source, "build_financial_report_snapshot_from_sqlite", forbidden)
    monkeypatch.setattr(reporting_export, "get_financial_report_csv", forbidden)
    monkeypatch.setattr(reporting_export, "get_financial_report_xlsx", forbidden)

    view = income_statement.build_income_statement_view(snapshot)
    assert snapshot == before
    assert view.result == Decimal("100.00")
