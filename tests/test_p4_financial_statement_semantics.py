"""Phase 4J.1 — net financial-statement semantics contracts."""

from dataclasses import FrozenInstanceError
from decimal import Decimal
from inspect import signature

import pytest


def _line(code, account_type, ledger_balance, normal_balance=Decimal("999999.99"), nature="DEBIT"):
    from aqorath.reporting import FinancialReportLine

    return FinancialReportLine(
        account_code=code,
        account_name=f"Account {code}",
        account_type=account_type,
        account_subtype="",
        nature=nature,
        ledger_balance=ledger_balance,
        normal_balance=normal_balance,
    )


def _snapshot(lines, *, as_of="2026-07-31", totals=(), result=Decimal("999999.99")):
    from aqorath.reporting import FinancialReportSnapshot

    return FinancialReportSnapshot(
        as_of=as_of,
        lines=tuple(lines),
        totals=tuple(totals),
        result=result,
    )


def _balanced_snapshot(*, as_of="2026-07-31"):
    """Balanced open-period ledger with contra accounts in several classes."""
    return _snapshot(
        (
            # Assets: 1000 debit less 200 credit contra-asset = 800 net.
            _line("1101", "Activo", Decimal("1000.00"), nature="DEBIT"),
            _line("1205", "Activo", Decimal("-200.00"), nature="CREDIT"),
            # Liabilities: 350 credit less 50 debit contra-liability = 300 net.
            _line("2101", "Pasivo", Decimal("-350.00"), nature="CREDIT"),
            _line("2199", "Pasivo", Decimal("50.00"), nature="DEBIT"),
            # Recorded equity = 400 credit.
            _line("3101", "Patrimonio", Decimal("-400.00"), nature="CREDIT"),
            # Income: 250 credit less 50 debit contra-income = 200 net.
            _line("4201", "Ingreso", Decimal("-250.00"), nature="CREDIT"),
            _line("4299", "Ingreso", Decimal("50.00"), nature="DEBIT"),
            # Expenses: 120 debit less 20 credit contra-expense = 100 net.
            _line("5102", "Gasto", Decimal("120.00"), nature="DEBIT"),
            _line("5199", "Gasto", Decimal("-20.00"), nature="CREDIT"),
        ),
        as_of=as_of,
    )


def test_net_semantics_public_contract_and_exact_signature_exist():
    import aqorath.financial_statement_semantics as semantics

    assert semantics.FinancialStatementTotals is not None
    assert callable(semantics.compute_financial_statement_totals)

    params = signature(semantics.compute_financial_statement_totals).parameters
    assert list(params) == ["snapshot"]

    fields = tuple(semantics.FinancialStatementTotals.__dataclass_fields__)
    assert fields == (
        "as_of",
        "assets",
        "liabilities",
        "recorded_equity",
        "income",
        "costs",
        "expenses",
        "result",
        "total_equity",
        "liabilities_and_equity",
        "balance_difference",
    )


def test_net_semantics_result_is_deeply_immutable():
    import aqorath.financial_statement_semantics as semantics

    totals = semantics.compute_financial_statement_totals(_balanced_snapshot())
    with pytest.raises(FrozenInstanceError):
        totals.assets = Decimal("0")


def test_net_semantics_uses_ledger_direction_to_net_contra_accounts():
    import aqorath.financial_statement_semantics as semantics

    totals = semantics.compute_financial_statement_totals(_balanced_snapshot())

    assert totals.assets == Decimal("800.00")
    assert totals.liabilities == Decimal("300.00")
    assert totals.recorded_equity == Decimal("400.00")
    assert totals.income == Decimal("200.00")
    assert totals.costs == Decimal("0")
    assert totals.expenses == Decimal("100.00")


def test_net_semantics_derives_result_and_equity_from_ledger_not_snapshot_summary_fields():
    from aqorath.reporting import FinancialReportTotal
    import aqorath.financial_statement_semantics as semantics

    snapshot = _balanced_snapshot()
    poisoned = _snapshot(
        snapshot.lines,
        as_of=snapshot.as_of,
        totals=(
            FinancialReportTotal("Activo", Decimal("999999.00")),
            FinancialReportTotal("Pasivo", Decimal("888888.00")),
            FinancialReportTotal("Patrimonio", Decimal("777777.00")),
            FinancialReportTotal("Ingreso", Decimal("666666.00")),
            FinancialReportTotal("Costo", Decimal("555555.00")),
            FinancialReportTotal("Gasto", Decimal("444444.00")),
        ),
        result=Decimal("333333.00"),
    )

    totals = semantics.compute_financial_statement_totals(poisoned)
    assert totals.result == Decimal("100.00")
    assert totals.total_equity == Decimal("500.00")
    assert totals.liabilities_and_equity == Decimal("800.00")
    assert totals.balance_difference == Decimal("0.00")


def test_net_semantics_ignores_normal_balance_and_account_nature_for_statement_netting():
    import aqorath.financial_statement_semantics as semantics

    snapshot = _balanced_snapshot()
    assert all(line.normal_balance == Decimal("999999.99") for line in snapshot.lines)

    totals = semantics.compute_financial_statement_totals(snapshot)
    assert totals.assets == Decimal("800.00")
    assert totals.result == Decimal("100.00")
    assert totals.balance_difference == Decimal("0.00")


def test_net_semantics_preserves_decimal_exactness_and_as_of():
    import aqorath.financial_statement_semantics as semantics

    snapshot = _snapshot(
        (
            _line("1101", "Activo", Decimal("0.0100")),
            _line("3101", "Patrimonio", Decimal("-0.0100"), nature="CREDIT"),
        ),
        as_of="2026-02-28",
    )

    totals = semantics.compute_financial_statement_totals(snapshot)
    assert totals.as_of == "2026-02-28"
    assert totals.assets == Decimal("0.0100")
    assert totals.recorded_equity == Decimal("0.0100")
    assert totals.result == Decimal("0")
    assert totals.total_equity == Decimal("0.0100")
    assert totals.balance_difference == Decimal("0.0000")
    assert all(isinstance(value, Decimal) for value in (
        totals.assets,
        totals.liabilities,
        totals.recorded_equity,
        totals.income,
        totals.costs,
        totals.expenses,
        totals.result,
        totals.total_equity,
        totals.liabilities_and_equity,
        totals.balance_difference,
    ))


def test_net_semantics_supports_closed_period_equity_without_open_profit_and_loss():
    import aqorath.financial_statement_semantics as semantics

    snapshot = _snapshot(
        (
            _line("1101", "Activo", Decimal("500.00")),
            _line("2101", "Pasivo", Decimal("-100.00"), nature="CREDIT"),
            _line("3103", "Patrimonio", Decimal("-400.00"), nature="CREDIT"),
        )
    )

    totals = semantics.compute_financial_statement_totals(snapshot)
    assert totals.result == Decimal("0")
    assert totals.recorded_equity == Decimal("400.00")
    assert totals.total_equity == Decimal("400.00")
    assert totals.liabilities_and_equity == Decimal("500.00")
    assert totals.balance_difference == Decimal("0.00")


def test_net_semantics_requires_nominal_snapshot_and_decimal_ledger_balances():
    import aqorath.financial_statement_semantics as semantics

    class FakeSnapshot:
        lines = ()
        as_of = None

    with pytest.raises(TypeError):
        semantics.compute_financial_statement_totals(FakeSnapshot())

    bad = _snapshot((_line("1101", "Activo", "100.00"),))
    with pytest.raises(TypeError):
        semantics.compute_financial_statement_totals(bad)


def test_net_semantics_rejects_unknown_statement_classification():
    import aqorath.financial_statement_semantics as semantics

    snapshot = _snapshot((_line("9999", "Otros", Decimal("0")),))
    with pytest.raises(ValueError):
        semantics.compute_financial_statement_totals(snapshot)


def test_net_semantics_rejects_unbalanced_snapshot_instead_of_silently_repairing():
    import aqorath.financial_statement_semantics as semantics

    snapshot = _snapshot(
        (
            _line("1101", "Activo", Decimal("100.00")),
            _line("2101", "Pasivo", Decimal("-90.00"), nature="CREDIT"),
        )
    )

    with pytest.raises(ValueError, match="balance"):
        semantics.compute_financial_statement_totals(snapshot)


def test_net_semantics_builder_is_pure_and_does_not_mutate_or_open_other_authorities(monkeypatch):
    import builtins
    import sqlite3

    import aqorath.accounting_rules as accounting_rules
    import aqorath.financial_statement_semantics as semantics
    import aqorath.reporting as reporting
    import aqorath.reporting_export as reporting_export
    import aqorath.reporting_runtime as reporting_runtime
    import aqorath.reporting_source as reporting_source
    import aqorath.storage as storage

    snapshot = _balanced_snapshot(as_of=None)
    before = snapshot

    def forbidden(*args, **kwargs):
        raise AssertionError("net statement semantics must consume only the supplied snapshot")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    monkeypatch.setattr(storage, "get_db_path", forbidden)
    monkeypatch.setattr(accounting_rules, "load_catalog", forbidden)
    monkeypatch.setattr(reporting, "build_financial_report_snapshot", forbidden)
    monkeypatch.setattr(reporting_runtime, "get_financial_report_snapshot", forbidden)
    monkeypatch.setattr(reporting_source, "build_financial_report_snapshot_from_sqlite", forbidden)
    monkeypatch.setattr(reporting_export, "get_financial_report_csv", forbidden)
    monkeypatch.setattr(reporting_export, "get_financial_report_xlsx", forbidden)

    totals = semantics.compute_financial_statement_totals(snapshot)
    assert snapshot == before
    assert totals.as_of is None
    assert totals.balance_difference == Decimal("0.00")
