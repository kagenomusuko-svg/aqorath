"""Phase 4K.1 — formal Balance Sheet view contracts."""

from dataclasses import FrozenInstanceError
from decimal import Decimal
from inspect import signature

import pytest


def _line(code, name, account_type, ledger_balance, *, subtype="", normal_balance=Decimal("9999.99"), nature="DEBIT"):
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
    from aqorath.reporting import FinancialReportSnapshot

    return FinancialReportSnapshot(
        as_of=as_of,
        lines=(
            _line("1101.001", "BBVA", "Activo", Decimal("1000.00"), subtype="Circulante"),
            _line("1205", "Depreciación acumulada", "Activo", Decimal("-200.00"), subtype="No circulante", nature="CREDIT"),
            _line("2101", "Proveedores", "Pasivo", Decimal("-350.00"), subtype="Corto plazo", nature="CREDIT"),
            _line("2199", "Contra pasivo", "Pasivo", Decimal("50.00"), subtype="Corto plazo"),
            _line("3101", "Capital social", "Patrimonio", Decimal("-400.00"), nature="CREDIT"),
            _line("4201", "Ventas", "Ingreso", Decimal("-250.00"), nature="CREDIT"),
            _line("4299", "Devoluciones sobre ventas", "Ingreso", Decimal("50.00")),
            _line("5102", "Servicios", "Gasto", Decimal("120.00")),
            _line("5199", "Recuperación de gasto", "Gasto", Decimal("-20.00"), nature="CREDIT"),
        ),
        totals=(),
        result=Decimal("999999.00"),
    )


def test_balance_sheet_public_contract_and_exact_signature_exist():
    import aqorath.balance_sheet as balance_sheet

    assert balance_sheet.BalanceSheetLine is not None
    assert balance_sheet.BalanceSheetSection is not None
    assert balance_sheet.BalanceSheetView is not None
    assert callable(balance_sheet.build_balance_sheet_view)

    params = signature(balance_sheet.build_balance_sheet_view).parameters
    assert list(params) == ["snapshot"]

    assert tuple(balance_sheet.BalanceSheetLine.__dataclass_fields__) == (
        "account_code",
        "account_name",
        "account_subtype",
        "amount",
    )
    assert tuple(balance_sheet.BalanceSheetSection.__dataclass_fields__) == (
        "account_type",
        "lines",
        "total",
    )
    assert tuple(balance_sheet.BalanceSheetView.__dataclass_fields__) == (
        "as_of",
        "assets",
        "liabilities",
        "recorded_equity",
        "current_result",
        "total_equity",
        "liabilities_and_equity",
        "balance_difference",
    )


def test_balance_sheet_view_is_deeply_immutable():
    import aqorath.balance_sheet as balance_sheet

    view = balance_sheet.build_balance_sheet_view(_snapshot())

    with pytest.raises(FrozenInstanceError):
        view.current_result = Decimal("0")
    with pytest.raises(FrozenInstanceError):
        view.assets.total = Decimal("0")
    with pytest.raises(FrozenInstanceError):
        view.assets.lines[0].amount = Decimal("0")
    with pytest.raises(TypeError):
        view.assets.lines[0] = view.assets.lines[0]


def test_balance_sheet_calls_net_semantics_exactly_once_and_uses_returned_totals(monkeypatch):
    import aqorath.balance_sheet as balance_sheet
    import aqorath.financial_statement_semantics as semantics

    snapshot = _snapshot()
    calls = []
    sent = semantics.FinancialStatementTotals(
        as_of="SENTINEL-AS-OF",
        assets=Decimal("800.01"),
        liabilities=Decimal("300.02"),
        recorded_equity=Decimal("400.03"),
        income=Decimal("200.04"),
        costs=Decimal("0.05"),
        expenses=Decimal("100.06"),
        result=Decimal("99.93"),
        total_equity=Decimal("499.96"),
        liabilities_and_equity=Decimal("799.98"),
        balance_difference=Decimal("0.03"),
    )

    def fake_compute(value):
        calls.append(value)
        return sent

    monkeypatch.setattr(semantics, "compute_financial_statement_totals", fake_compute)

    view = balance_sheet.build_balance_sheet_view(snapshot)
    assert calls == [snapshot]
    assert view.as_of == "SENTINEL-AS-OF"
    assert view.assets.total is sent.assets
    assert view.liabilities.total is sent.liabilities
    assert view.recorded_equity.total is sent.recorded_equity
    assert view.current_result is sent.result
    assert view.total_equity is sent.total_equity
    assert view.liabilities_and_equity is sent.liabilities_and_equity
    assert view.balance_difference is sent.balance_difference


def test_balance_sheet_projects_signed_line_amounts_and_nets_contra_accounts():
    import aqorath.balance_sheet as balance_sheet

    view = balance_sheet.build_balance_sheet_view(_snapshot())

    assert [(line.account_code, line.amount) for line in view.assets.lines] == [
        ("1101.001", Decimal("1000.00")),
        ("1205", Decimal("-200.00")),
    ]
    assert [(line.account_code, line.amount) for line in view.liabilities.lines] == [
        ("2101", Decimal("350.00")),
        ("2199", Decimal("-50.00")),
    ]
    assert [(line.account_code, line.amount) for line in view.recorded_equity.lines] == [
        ("3101", Decimal("400.00")),
    ]

    assert view.assets.total == Decimal("800.00")
    assert view.liabilities.total == Decimal("300.00")
    assert view.recorded_equity.total == Decimal("400.00")


def test_balance_sheet_uses_ledger_balance_not_normal_balance_or_nature_for_line_amounts():
    import aqorath.balance_sheet as balance_sheet

    snapshot = _snapshot()
    assert all(line.normal_balance == Decimal("9999.99") for line in snapshot.lines)

    view = balance_sheet.build_balance_sheet_view(snapshot)
    assert view.assets.lines[1].amount == Decimal("-200.00")
    assert view.liabilities.lines[1].amount == Decimal("-50.00")
    assert view.assets.total != sum((line.normal_balance for line in snapshot.lines if line.account_type == "Activo"), Decimal("0"))


def test_balance_sheet_excludes_profit_and_loss_lines_but_includes_current_result_from_semantics():
    import aqorath.balance_sheet as balance_sheet

    view = balance_sheet.build_balance_sheet_view(_snapshot())

    visible_codes = {
        line.account_code
        for section in (view.assets, view.liabilities, view.recorded_equity)
        for line in section.lines
    }
    assert visible_codes == {"1101.001", "1205", "2101", "2199", "3101"}
    assert "4201" not in visible_codes
    assert "5102" not in visible_codes

    assert view.current_result == Decimal("100.00")
    assert view.total_equity == Decimal("500.00")
    assert view.liabilities_and_equity == Decimal("800.00")
    assert view.balance_difference == Decimal("0.00")


def test_balance_sheet_preserves_account_identity_subtype_order_and_as_of():
    import aqorath.balance_sheet as balance_sheet

    view = balance_sheet.build_balance_sheet_view(_snapshot("2026-02-28"))

    assert view.as_of == "2026-02-28"
    assert [(line.account_code, line.account_name, line.account_subtype) for line in view.assets.lines] == [
        ("1101.001", "BBVA", "Circulante"),
        ("1205", "Depreciación acumulada", "No circulante"),
    ]

    undated = balance_sheet.build_balance_sheet_view(_snapshot(None))
    assert undated.as_of is None


def test_balance_sheet_requires_nominal_financial_report_snapshot():
    import aqorath.balance_sheet as balance_sheet

    class FakeSnapshot:
        lines = ()
        as_of = None

    with pytest.raises(TypeError):
        balance_sheet.build_balance_sheet_view(FakeSnapshot())


def test_balance_sheet_propagates_net_semantics_failure_without_partial_repair(monkeypatch):
    import aqorath.balance_sheet as balance_sheet
    import aqorath.financial_statement_semantics as semantics

    failure = ValueError("balance failure")
    calls = []

    def fail(value):
        calls.append(value)
        raise failure

    snapshot = _snapshot()
    monkeypatch.setattr(semantics, "compute_financial_statement_totals", fail)

    with pytest.raises(ValueError) as caught:
        balance_sheet.build_balance_sheet_view(snapshot)

    assert caught.value is failure
    assert calls == [snapshot]


def test_balance_sheet_builder_is_pure_does_not_mutate_or_open_other_authorities(monkeypatch):
    import builtins
    import sqlite3

    import aqorath.accounting_rules as accounting_rules
    import aqorath.balance_sheet as balance_sheet
    import aqorath.reporting as reporting
    import aqorath.reporting_export as reporting_export
    import aqorath.reporting_runtime as reporting_runtime
    import aqorath.reporting_source as reporting_source
    import aqorath.storage as storage

    snapshot = _snapshot()
    before = snapshot

    def forbidden(*args, **kwargs):
        raise AssertionError("Balance Sheet view must consume only snapshot + net semantics")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    monkeypatch.setattr(storage, "get_db_path", forbidden)
    monkeypatch.setattr(accounting_rules, "load_catalog", forbidden)
    monkeypatch.setattr(reporting, "build_financial_report_snapshot", forbidden)
    monkeypatch.setattr(reporting_runtime, "get_financial_report_snapshot", forbidden)
    monkeypatch.setattr(reporting_source, "build_financial_report_snapshot_from_sqlite", forbidden)
    monkeypatch.setattr(reporting_export, "get_financial_report_csv", forbidden)
    monkeypatch.setattr(reporting_export, "get_financial_report_xlsx", forbidden)

    view = balance_sheet.build_balance_sheet_view(snapshot)
    assert snapshot == before
    assert view.balance_difference == Decimal("0.00")
