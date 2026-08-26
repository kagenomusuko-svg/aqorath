"""Phase 4D.1 — deterministic CSV financial-report renderer contracts."""

import csv
from dataclasses import replace
from decimal import Decimal
from inspect import signature
from io import StringIO

import pytest


def _snapshot(as_of="2026-07-31"):
    from aqorath.reporting import (
        FinancialReportLine,
        FinancialReportSnapshot,
        FinancialReportTotal,
    )

    return FinancialReportSnapshot(
        as_of=as_of,
        lines=(
            FinancialReportLine(
                account_code="1101",
                account_name="Bancos",
                account_type="Activo",
                account_subtype="Circulante",
                nature="DEBIT",
                ledger_balance=Decimal("200.00"),
                normal_balance=Decimal("200.00"),
            ),
            FinancialReportLine(
                account_code="4201",
                account_name="Venta de productos elaborados",
                account_type="Ingreso",
                account_subtype="Actividades con causa",
                nature="CREDIT",
                ledger_balance=Decimal("-200.00"),
                normal_balance=Decimal("200.00"),
            ),
        ),
        totals=(
            FinancialReportTotal("Activo", Decimal("200.00")),
            FinancialReportTotal("Pasivo", Decimal("0")),
            FinancialReportTotal("Patrimonio", Decimal("0")),
            FinancialReportTotal("Ingreso", Decimal("200.00")),
            FinancialReportTotal("Costo", Decimal("0")),
            FinancialReportTotal("Gasto", Decimal("0")),
        ),
        result=Decimal("200.00"),
    )


def _rows(text):
    return list(csv.reader(StringIO(text)))


def test_csv_renderer_public_contract_and_exact_signature_exist():
    import aqorath.reporting_csv as reporting_csv

    assert callable(reporting_csv.render_financial_report_csv)
    params = signature(reporting_csv.render_financial_report_csv).parameters
    assert list(params) == ["snapshot"]


def test_csv_renderer_has_exact_header_and_preserves_account_rows_in_snapshot_order():
    import aqorath.reporting_csv as reporting_csv

    rows = _rows(reporting_csv.render_financial_report_csv(_snapshot()))

    assert rows[0] == [
        "record_type",
        "account_code",
        "account_name",
        "account_type",
        "account_subtype",
        "nature",
        "ledger_balance",
        "normal_balance",
        "amount",
        "as_of",
    ]
    assert rows[1] == [
        "ACCOUNT",
        "1101",
        "Bancos",
        "Activo",
        "Circulante",
        "DEBIT",
        "200.00",
        "200.00",
        "",
        "2026-07-31",
    ]
    assert rows[2] == [
        "ACCOUNT",
        "4201",
        "Venta de productos elaborados",
        "Ingreso",
        "Actividades con causa",
        "CREDIT",
        "-200.00",
        "200.00",
        "",
        "2026-07-31",
    ]


def test_csv_renderer_preserves_totals_and_result_without_recalculation():
    import aqorath.reporting_csv as reporting_csv

    snapshot = _snapshot()
    rows = _rows(reporting_csv.render_financial_report_csv(snapshot))

    total_rows = [row for row in rows if row[0] == "TOTAL"]
    assert [(row[3], row[8]) for row in total_rows] == [
        ("Activo", "200.00"),
        ("Pasivo", "0"),
        ("Patrimonio", "0"),
        ("Ingreso", "200.00"),
        ("Costo", "0"),
        ("Gasto", "0"),
    ]

    result_rows = [row for row in rows if row[0] == "RESULT"]
    assert len(result_rows) == 1
    assert result_rows[0] == [
        "RESULT",
        "",
        "Resultado del ejercicio",
        "",
        "",
        "",
        "",
        "",
        "200.00",
        "2026-07-31",
    ]


def test_csv_renderer_preserves_decimal_text_exactly_without_float_conversion():
    from aqorath.reporting import (
        FinancialReportLine,
        FinancialReportSnapshot,
        FinancialReportTotal,
    )
    import aqorath.reporting_csv as reporting_csv

    precise = Decimal("12345678901234567890.0100")
    snapshot = FinancialReportSnapshot(
        as_of=None,
        lines=(
            FinancialReportLine(
                "1101",
                "Bancos",
                "Activo",
                "Circulante",
                "DEBIT",
                precise,
                precise,
            ),
        ),
        totals=(FinancialReportTotal("Activo", precise),),
        result=Decimal("0.10"),
    )

    rows = _rows(reporting_csv.render_financial_report_csv(snapshot))
    assert rows[1][6] == "12345678901234567890.0100"
    assert rows[1][7] == "12345678901234567890.0100"
    assert [row for row in rows if row[0] == "TOTAL"][0][8] == "12345678901234567890.0100"
    assert [row for row in rows if row[0] == "RESULT"][0][8] == "0.10"


def test_csv_renderer_uses_standard_csv_escaping_for_names_and_subtypes():
    from aqorath.reporting import FinancialReportLine
    import aqorath.reporting_csv as reporting_csv

    snapshot = _snapshot()
    special_line = replace(
        snapshot.lines[0],
        account_name='Banco "Principal", MX',
        account_subtype="Caja, bancos y equivalentes",
    )
    snapshot = replace(snapshot, lines=(special_line, snapshot.lines[1]))

    text = reporting_csv.render_financial_report_csv(snapshot)
    rows = _rows(text)
    assert rows[1][2] == 'Banco "Principal", MX'
    assert rows[1][4] == "Caja, bancos y equivalentes"
    assert '"Banco ""Principal"", MX"' in text


def test_csv_renderer_preserves_as_of_exactly_and_uses_empty_cell_for_none():
    import aqorath.reporting_csv as reporting_csv

    dated = _rows(reporting_csv.render_financial_report_csv(_snapshot("2026-01-31")))
    assert all(row[-1] == "2026-01-31" for row in dated[1:])

    undated = _rows(reporting_csv.render_financial_report_csv(_snapshot(None)))
    assert all(row[-1] == "" for row in undated[1:])


def test_csv_renderer_is_deterministic_and_does_not_mutate_snapshot():
    import aqorath.reporting_csv as reporting_csv

    snapshot = _snapshot()
    before = snapshot
    first = reporting_csv.render_financial_report_csv(snapshot)
    second = reporting_csv.render_financial_report_csv(snapshot)

    assert isinstance(first, str)
    assert first == second
    assert snapshot == before
    assert first.endswith("\n")
    assert "\r\n" not in first


def test_csv_renderer_requires_nominal_financial_report_snapshot():
    import aqorath.reporting_csv as reporting_csv

    class FakeSnapshot:
        lines = ()
        totals = ()
        result = Decimal("0")
        as_of = None

    with pytest.raises(TypeError):
        reporting_csv.render_financial_report_csv(FakeSnapshot())


def test_csv_renderer_is_pure_and_does_not_query_rebuild_or_write(monkeypatch):
    import builtins
    import sqlite3

    import aqorath.accounting_rules as accounting_rules
    import aqorath.reporting as reporting
    import aqorath.reporting_csv as reporting_csv
    import aqorath.reporting_source as reporting_source
    import aqorath.storage as storage

    def forbidden(*args, **kwargs):
        raise AssertionError("CSV renderer must consume only the supplied snapshot")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    monkeypatch.setattr(storage, "get_db_path", forbidden)
    monkeypatch.setattr(accounting_rules, "load_catalog", forbidden)
    monkeypatch.setattr(reporting, "build_financial_report_snapshot", forbidden)
    monkeypatch.setattr(
        reporting_source,
        "build_financial_report_snapshot_from_sqlite",
        forbidden,
    )

    text = reporting_csv.render_financial_report_csv(_snapshot())
    assert _rows(text)[1][0] == "ACCOUNT"
