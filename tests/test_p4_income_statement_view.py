"""Phase 4H.1 — formal Income Statement view contracts."""

from dataclasses import FrozenInstanceError
from decimal import Decimal
from inspect import signature

import pytest


def _line(code, name, account_type, amount):
    from aqorath.reporting import FinancialReportLine

    nature = "CREDIT" if account_type == "Ingreso" else "DEBIT"
    ledger = -amount if nature == "CREDIT" else amount
    return FinancialReportLine(
        account_code=code,
        account_name=name,
        account_type=account_type,
        account_subtype="",
        nature=nature,
        ledger_balance=ledger,
        normal_balance=amount,
    )


def _snapshot(
    *,
    as_of="2026-07-31",
    income_total=Decimal("500.00"),
    cost_total=Decimal("125.00"),
    expense_total=Decimal("75.00"),
    result=Decimal("300.00"),
):
    from aqorath.reporting import FinancialReportSnapshot, FinancialReportTotal

    return FinancialReportSnapshot(
        as_of=as_of,
        lines=(
            _line("1101", "Bancos", "Activo", Decimal("999.00")),
            _line("4201", "Ventas", "Ingreso", Decimal("500.00")),
            _line("5101", "Costo de ventas", "Costo", Decimal("125.00")),
            _line("6101", "Servicios", "Gasto", Decimal("75.00")),
            _line("2101", "Proveedores", "Pasivo", Decimal("50.00")),
        ),
        totals=(
            FinancialReportTotal("Activo", Decimal("999.00")),
            FinancialReportTotal("Pasivo", Decimal("50.00")),
            FinancialReportTotal("Patrimonio", Decimal("0")),
            FinancialReportTotal("Ingreso", income_total),
            FinancialReportTotal("Costo", cost_total),
            FinancialReportTotal("Gasto", expense_total),
        ),
        result=result,
    )


def test_income_statement_public_contract_and_exact_signature_exist():
    import aqorath.income_statement as income_statement

    assert callable(income_statement.build_income_statement_view)
    assert income_statement.IncomeStatementSection is not None
    assert income_statement.IncomeStatementView is not None

    params = signature(income_statement.build_income_statement_view).parameters
    assert list(params) == ["snapshot"]

    section_fields = tuple(income_statement.IncomeStatementSection.__dataclass_fields__)
    view_fields = tuple(income_statement.IncomeStatementView.__dataclass_fields__)
    assert section_fields == ("account_type", "lines", "total")
    assert view_fields == ("as_of", "income", "costs", "expenses", "result")


def test_income_statement_view_is_deeply_immutable():
    import aqorath.income_statement as income_statement

    view = income_statement.build_income_statement_view(_snapshot())

    with pytest.raises(FrozenInstanceError):
        view.result = Decimal("0")
    with pytest.raises(FrozenInstanceError):
        view.income.total = Decimal("0")

    assert isinstance(view.income.lines, tuple)
    with pytest.raises(TypeError):
        view.income.lines[0] = view.income.lines[0]


def test_income_statement_selects_only_income_cost_and_expense_lines_preserving_order_and_identity():
    import aqorath.income_statement as income_statement

    snapshot = _snapshot()
    view = income_statement.build_income_statement_view(snapshot)

    assert view.income.account_type == "Ingreso"
    assert view.costs.account_type == "Costo"
    assert view.expenses.account_type == "Gasto"

    assert tuple(line.account_code for line in view.income.lines) == ("4201",)
    assert tuple(line.account_code for line in view.costs.lines) == ("5101",)
    assert tuple(line.account_code for line in view.expenses.lines) == ("6101",)

    assert view.income.lines[0] is snapshot.lines[1]
    assert view.costs.lines[0] is snapshot.lines[2]
    assert view.expenses.lines[0] is snapshot.lines[3]

    all_codes = {
        line.account_code
        for section in (view.income, view.costs, view.expenses)
        for line in section.lines
    }
    assert all_codes == {"4201", "5101", "6101"}


def test_income_statement_section_totals_are_taken_verbatim_from_snapshot_not_recalculated():
    import aqorath.income_statement as income_statement

    snapshot = _snapshot(
        income_total=Decimal("777.7700"),
        cost_total=Decimal("222.2200"),
        expense_total=Decimal("111.1100"),
    )
    view = income_statement.build_income_statement_view(snapshot)

    assert view.income.total is snapshot.totals[3].amount
    assert view.costs.total is snapshot.totals[4].amount
    assert view.expenses.total is snapshot.totals[5].amount
    assert view.income.total == Decimal("777.7700")
    assert view.costs.total == Decimal("222.2200")
    assert view.expenses.total == Decimal("111.1100")

    # Deliberately inconsistent with line sums: presentation must not recalculate.
    assert sum((line.normal_balance for line in view.income.lines), Decimal("0")) != view.income.total


def test_income_statement_result_is_preserved_verbatim_from_snapshot_not_recalculated():
    import aqorath.income_statement as income_statement

    snapshot = _snapshot(result=Decimal("987.6540"))
    view = income_statement.build_income_statement_view(snapshot)

    assert view.result is snapshot.result
    assert view.result == Decimal("987.6540")
    assert view.result != view.income.total - view.costs.total - view.expenses.total


def test_income_statement_preserves_as_of_exactly_including_none():
    import aqorath.income_statement as income_statement

    dated = _snapshot(as_of="2026-02-28")
    undated = _snapshot(as_of=None)

    assert income_statement.build_income_statement_view(dated).as_of == "2026-02-28"
    assert income_statement.build_income_statement_view(undated).as_of is None


def test_income_statement_preserves_empty_sections_and_zero_totals():
    from aqorath.reporting import FinancialReportSnapshot, FinancialReportTotal
    import aqorath.income_statement as income_statement

    snapshot = FinancialReportSnapshot(
        as_of="2026-01-31",
        lines=(_line("1101", "Bancos", "Activo", Decimal("10.00")),),
        totals=(
            FinancialReportTotal("Activo", Decimal("10.00")),
            FinancialReportTotal("Pasivo", Decimal("0")),
            FinancialReportTotal("Patrimonio", Decimal("0")),
            FinancialReportTotal("Ingreso", Decimal("0.00")),
            FinancialReportTotal("Costo", Decimal("0.00")),
            FinancialReportTotal("Gasto", Decimal("0.00")),
        ),
        result=Decimal("0.00"),
    )

    view = income_statement.build_income_statement_view(snapshot)
    assert view.income.lines == ()
    assert view.costs.lines == ()
    assert view.expenses.lines == ()
    assert view.income.total == Decimal("0.00")
    assert view.costs.total == Decimal("0.00")
    assert view.expenses.total == Decimal("0.00")
    assert view.result == Decimal("0.00")


def test_income_statement_requires_nominal_financial_report_snapshot():
    import aqorath.income_statement as income_statement

    class FakeSnapshot:
        as_of = None
        lines = ()
        totals = ()
        result = Decimal("0")

    with pytest.raises(TypeError):
        income_statement.build_income_statement_view(FakeSnapshot())


def test_income_statement_rejects_missing_duplicate_or_non_decimal_required_totals():
    from aqorath.reporting import FinancialReportSnapshot, FinancialReportTotal
    import aqorath.income_statement as income_statement

    base = _snapshot()

    missing = FinancialReportSnapshot(
        as_of=base.as_of,
        lines=base.lines,
        totals=tuple(total for total in base.totals if total.account_type != "Gasto"),
        result=base.result,
    )
    with pytest.raises(ValueError):
        income_statement.build_income_statement_view(missing)

    duplicate = FinancialReportSnapshot(
        as_of=base.as_of,
        lines=base.lines,
        totals=base.totals + (FinancialReportTotal("Ingreso", Decimal("1.00")),),
        result=base.result,
    )
    with pytest.raises(ValueError):
        income_statement.build_income_statement_view(duplicate)

    bad_amount = FinancialReportSnapshot(
        as_of=base.as_of,
        lines=base.lines,
        totals=tuple(
            FinancialReportTotal(total.account_type, "500.00")
            if total.account_type == "Ingreso"
            else total
            for total in base.totals
        ),
        result=base.result,
    )
    with pytest.raises(TypeError):
        income_statement.build_income_statement_view(bad_amount)


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
        raise AssertionError("income statement view must consume only the supplied snapshot")

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
    assert view.result == Decimal("300.00")
