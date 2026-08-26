"""Phase 4A.1 — immutable financial reporting snapshot contracts."""

from dataclasses import FrozenInstanceError
from decimal import Decimal
from inspect import signature
from types import SimpleNamespace

import pytest


def _catalog():
    return {
        "1101": {
            "tipo": "Activo",
            "subtipo": "Circulante",
            "naturaleza": "Deudora",
        },
        "2101": {
            "tipo": "Pasivo",
            "subtipo": "Corto plazo",
            "naturaleza": "Acreedora",
        },
        "3101": {
            "tipo": "Patrimonio",
            "subtipo": "",
            "naturaleza": "Acreedora",
        },
        "4201": {
            "tipo": "Ingreso",
            "subtipo": "Actividades con causa",
            "naturaleza": "Acreedora",
        },
        "5102": {
            "tipo": "Gasto",
            "subtipo": "Operación",
            "naturaleza": "Deudora",
        },
    }


def _account(code, name, nature, *, origin="canonical"):
    return SimpleNamespace(
        code=code,
        name=name,
        nature=nature,
        origin=origin,
    )


def test_reporting_module_public_contract_and_exact_signature_exist():
    import aqorath.reporting as reporting

    assert reporting.FinancialReportLine is not None
    assert reporting.FinancialReportTotal is not None
    assert reporting.FinancialReportSnapshot is not None
    assert callable(reporting.build_financial_report_snapshot)

    params = signature(reporting.build_financial_report_snapshot).parameters
    assert list(params) == ["balances", "accounts_by_code", "catalog", "as_of"]
    assert params["as_of"].default is None


def test_financial_report_snapshot_is_deeply_immutable():
    import aqorath.reporting as reporting

    snapshot = reporting.build_financial_report_snapshot(
        {"1101": Decimal("10.00")},
        {"1101": _account("1101", "Bancos", "DEBIT")},
        _catalog(),
        as_of="2026-08-26",
    )

    assert isinstance(snapshot.lines, tuple)
    assert isinstance(snapshot.totals, tuple)
    assert isinstance(snapshot.lines[0], reporting.FinancialReportLine)
    assert isinstance(snapshot.totals[0], reporting.FinancialReportTotal)

    with pytest.raises(FrozenInstanceError):
        snapshot.as_of = "2026-08-27"
    with pytest.raises(FrozenInstanceError):
        snapshot.lines[0].account_name = "Changed"
    with pytest.raises(FrozenInstanceError):
        snapshot.totals[0].amount = Decimal("999")


def test_canonical_balances_become_exact_report_lines_with_account_identity():
    import aqorath.reporting as reporting

    snapshot = reporting.build_financial_report_snapshot(
        {
            "1101": Decimal("150.00"),
            "2101": Decimal("-100.00"),
        },
        {
            "1101": _account("1101", "Bancos", "DEBIT"),
            "2101": _account("2101", "Proveedores", "CREDIT"),
        },
        _catalog(),
    )

    assert [line.account_code for line in snapshot.lines] == ["1101", "2101"]

    asset, liability = snapshot.lines
    assert (
        asset.account_code,
        asset.account_name,
        asset.account_type,
        asset.account_subtype,
        asset.nature,
        asset.ledger_balance,
        asset.normal_balance,
    ) == (
        "1101",
        "Bancos",
        "Activo",
        "Circulante",
        "DEBIT",
        Decimal("150.00"),
        Decimal("150.00"),
    )
    assert (
        liability.account_code,
        liability.account_name,
        liability.account_type,
        liability.account_subtype,
        liability.nature,
        liability.ledger_balance,
        liability.normal_balance,
    ) == (
        "2101",
        "Proveedores",
        "Pasivo",
        "Corto plazo",
        "CREDIT",
        Decimal("-100.00"),
        Decimal("100.00"),
    )


def test_entity_account_inherits_parent_classification_but_preserves_entity_identity():
    import aqorath.reporting as reporting

    snapshot = reporting.build_financial_report_snapshot(
        {"1101.001": Decimal("321.45")},
        {
            "1101.001": _account(
                "1101.001",
                "BBVA principal",
                "DEBIT",
                origin="entity",
            )
        },
        _catalog(),
    )

    line = snapshot.lines[0]
    assert line.account_code == "1101.001"
    assert line.account_name == "BBVA principal"
    assert line.account_type == "Activo"
    assert line.account_subtype == "Circulante"
    assert line.nature == "DEBIT"
    assert line.ledger_balance == Decimal("321.45")
    assert line.normal_balance == Decimal("321.45")


def test_reporting_preserves_decimal_exactness_and_normal_balance_semantics():
    import aqorath.reporting as reporting

    snapshot = reporting.build_financial_report_snapshot(
        {
            "4201": Decimal("-0.30"),
            "5102": Decimal("0.10") + Decimal("0.20"),
        },
        {
            "4201": _account("4201", "Venta de productos", "CREDIT"),
            "5102": _account("5102", "Servicios básicos", "DEBIT"),
        },
        _catalog(),
    )

    by_code = {line.account_code: line for line in snapshot.lines}
    assert by_code["4201"].ledger_balance == Decimal("-0.30")
    assert by_code["4201"].normal_balance == Decimal("0.30")
    assert by_code["5102"].ledger_balance == Decimal("0.30")
    assert by_code["5102"].normal_balance == Decimal("0.30")
    assert all(isinstance(line.ledger_balance, Decimal) for line in snapshot.lines)
    assert all(isinstance(line.normal_balance, Decimal) for line in snapshot.lines)


def test_reporting_order_is_deterministic_and_as_of_is_preserved_exactly():
    import aqorath.reporting as reporting

    balances = {
        "5102": Decimal("50.00"),
        "1101": Decimal("20.00"),
        "4201": Decimal("-200.00"),
    }
    accounts = {
        "5102": _account("5102", "Servicios básicos", "DEBIT"),
        "1101": _account("1101", "Bancos", "DEBIT"),
        "4201": _account("4201", "Venta de productos", "CREDIT"),
    }

    first = reporting.build_financial_report_snapshot(
        balances,
        accounts,
        _catalog(),
        as_of="2026-07-31",
    )
    second = reporting.build_financial_report_snapshot(
        dict(reversed(list(balances.items()))),
        accounts,
        _catalog(),
        as_of="2026-07-31",
    )

    assert first == second
    assert first.as_of == "2026-07-31"
    assert [line.account_code for line in first.lines] == ["1101", "4201", "5102"]


def test_reporting_totals_by_type_and_resultado_are_exact():
    import aqorath.reporting as reporting

    snapshot = reporting.build_financial_report_snapshot(
        {
            "1101": Decimal("150.00"),
            "2101": Decimal("-40.00"),
            "4201": Decimal("-200.00"),
            "5102": Decimal("50.00"),
        },
        {
            "1101": _account("1101", "Bancos", "DEBIT"),
            "2101": _account("2101", "Proveedores", "CREDIT"),
            "4201": _account("4201", "Venta de productos", "CREDIT"),
            "5102": _account("5102", "Servicios básicos", "DEBIT"),
        },
        _catalog(),
    )

    totals = {total.account_type: total.amount for total in snapshot.totals}
    assert totals == {
        "Activo": Decimal("150.00"),
        "Pasivo": Decimal("40.00"),
        "Patrimonio": Decimal("0"),
        "Ingreso": Decimal("200.00"),
        "Costo": Decimal("0"),
        "Gasto": Decimal("50.00"),
    }
    assert snapshot.result == Decimal("150.00")


def test_zero_balance_accounts_are_preserved_in_snapshot():
    import aqorath.reporting as reporting

    snapshot = reporting.build_financial_report_snapshot(
        {"1101": Decimal("0")},
        {"1101": _account("1101", "Bancos", "DEBIT")},
        _catalog(),
    )

    assert len(snapshot.lines) == 1
    assert snapshot.lines[0].ledger_balance == Decimal("0")
    assert snapshot.lines[0].normal_balance == Decimal("0")


def test_reporting_rejects_balance_without_matching_account_identity():
    import aqorath.reporting as reporting

    with pytest.raises((KeyError, LookupError, ValueError)):
        reporting.build_financial_report_snapshot(
            {"1101": Decimal("10")},
            {},
            _catalog(),
        )

    with pytest.raises((KeyError, LookupError, ValueError)):
        reporting.build_financial_report_snapshot(
            {"1101": Decimal("10")},
            {"1101": _account("9999", "Wrong identity", "DEBIT")},
            _catalog(),
        )


def test_reporting_rejects_missing_or_unknown_classification_instead_of_other_bucket():
    import aqorath.reporting as reporting

    account = {"9999": _account("9999", "Unclassified", "DEBIT")}
    with pytest.raises((KeyError, LookupError, ValueError)):
        reporting.build_financial_report_snapshot(
            {"9999": Decimal("10")},
            account,
            _catalog(),
        )

    catalog = _catalog()
    catalog["9999"] = {
        "tipo": "Mystery",
        "subtipo": "",
        "naturaleza": "Deudora",
    }
    with pytest.raises(ValueError):
        reporting.build_financial_report_snapshot(
            {"9999": Decimal("10")},
            account,
            catalog,
        )


def test_reporting_rejects_unknown_nature_and_non_decimal_balances():
    import aqorath.reporting as reporting

    with pytest.raises(ValueError):
        reporting.build_financial_report_snapshot(
            {"1101": Decimal("10")},
            {"1101": _account("1101", "Bancos", "SIDEWAYS")},
            _catalog(),
        )

    with pytest.raises(TypeError):
        reporting.build_financial_report_snapshot(
            {"1101": 10.0},
            {"1101": _account("1101", "Bancos", "DEBIT")},
            _catalog(),
        )


def test_reporting_builder_is_pure_and_does_not_open_authorities_or_render_files(monkeypatch):
    import sqlite3

    import aqorath.accounting_rules as accounting_rules
    import aqorath.core as core
    import aqorath.reporting as reporting
    import aqorath.storage as storage

    def forbidden(*args, **kwargs):
        raise AssertionError("report snapshot builder must use only supplied inputs")

    monkeypatch.setattr(accounting_rules, "load_catalog", forbidden)
    monkeypatch.setattr(core, "trial_balance", forbidden)
    monkeypatch.setattr(storage, "get_session", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)

    snapshot = reporting.build_financial_report_snapshot(
        {"1101": Decimal("10.00")},
        {"1101": _account("1101", "Bancos", "DEBIT")},
        _catalog(),
    )

    assert snapshot.lines[0].normal_balance == Decimal("10.00")
