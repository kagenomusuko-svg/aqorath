"""Phase 4R.1 — pure formal financial-statements PDF renderer contracts."""

from dataclasses import replace
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
        normal_balance=Decimal("9999.9999"),
    )


def _bundle(as_of="2026-07-31"):
    from aqorath.financial_statements import build_financial_statements_bundle
    from aqorath.reporting import FinancialReportSnapshot

    snapshot = FinancialReportSnapshot(
        as_of=as_of,
        lines=(
            _line("1101.001", "BBVA", "Activo", Decimal("1000.0000"), subtype="Circulante"),
            _line("1205", "Depreciacion acumulada", "Activo", Decimal("-200.0000"), subtype="No circulante", nature="CREDIT"),
            _line("2101", "Proveedores", "Pasivo", Decimal("-300.0000"), subtype="Corto plazo", nature="CREDIT"),
            _line("3101", "Capital social", "Patrimonio", Decimal("-400.0000"), nature="CREDIT"),
            _line("4201", "Ventas", "Ingreso", Decimal("-275.0000"), subtype="Operacion", nature="CREDIT"),
            _line("4299", "Devoluciones sobre ventas", "Ingreso", Decimal("50.0000"), subtype="Operacion"),
            _line("5101", "Costo de ventas", "Costo", Decimal("25.0000"), subtype="Operacion"),
            _line("6101", "Servicios", "Gasto", Decimal("120.0000"), subtype="Administracion"),
            _line("6199", "Recuperacion de gasto", "Gasto", Decimal("-20.0000"), subtype="Administracion", nature="CREDIT"),
        ),
        totals=(),
        result=Decimal("777777.7777"),
    )
    return build_financial_statements_bundle(snapshot)


def _render(bundle):
    from aqorath.financial_statements_pdf import render_financial_statements_pdf

    data = render_financial_statements_pdf(bundle)
    assert isinstance(data, bytes)
    assert data.startswith(b"%PDF-")
    assert data.rstrip().endswith(b"%%EOF")
    return data


def _page_count(data):
    return data.count(b"/Type /Page") - data.count(b"/Type /Pages")


def _pdf_text(value):
    return f"({value}) Tj".encode("ascii")


def test_formal_pdf_renderer_public_contract_and_exact_signature_exist():
    import aqorath.financial_statements_pdf as renderer

    assert callable(renderer.render_financial_statements_pdf)
    assert list(signature(renderer.render_financial_statements_pdf).parameters) == ["bundle"]


def test_formal_pdf_renderer_returns_valid_two_statement_pdf_with_titles_and_as_of():
    data = _render(_bundle("2026-07-31"))
    assert _page_count(data) == 2
    assert b"Estado de Resultados" in data
    assert b"Balance General" in data
    assert data.count(b"2026-07-31") >= 2


def test_income_statement_pdf_preserves_order_identity_and_presentation_signs():
    data = _render(_bundle())
    tokens = [
        b"4201", b"Ventas", _pdf_text("275.0000"),
        b"4299", b"Devoluciones sobre ventas", _pdf_text("-50.0000"),
        b"5101", b"Costo de ventas", _pdf_text("25.0000"),
        b"6101", b"Servicios", _pdf_text("120.0000"),
        b"6199", b"Recuperacion de gasto", _pdf_text("-20.0000"),
    ]
    positions = [data.index(token) for token in tokens]
    assert positions == sorted(positions)


def test_income_statement_pdf_uses_view_totals_and_result_verbatim_without_recalculation():
    bundle = _bundle()
    income = replace(
        bundle.income_statement,
        income=replace(bundle.income_statement.income, total=Decimal("225.123400")),
        costs=replace(bundle.income_statement.costs, total=Decimal("25.234500")),
        expenses=replace(bundle.income_statement.expenses, total=Decimal("100.345600")),
        result=Decimal("99.543300"),
    )
    data = _render(replace(bundle, income_statement=income))
    for token in (b"225.123400", b"25.234500", b"100.345600", b"99.543300"):
        assert token in data
    assert b"777777.7777" not in data


def test_balance_sheet_pdf_preserves_signed_lines_and_uses_view_totals_verbatim():
    bundle = _bundle()
    balance = replace(
        bundle.balance_sheet,
        assets=replace(bundle.balance_sheet.assets, total=Decimal("800.111100")),
        liabilities=replace(bundle.balance_sheet.liabilities, total=Decimal("300.222200")),
        recorded_equity=replace(bundle.balance_sheet.recorded_equity, total=Decimal("400.333300")),
        current_result=Decimal("100.444400"),
        total_equity=Decimal("500.555500"),
        liabilities_and_equity=Decimal("800.777700"),
    )
    data = _render(replace(bundle, balance_sheet=balance))
    for token in (
        b"1000.0000", b"-200.0000", b"300.0000", b"400.0000",
        b"800.111100", b"300.222200", b"400.333300",
        b"100.444400", b"500.555500", b"800.777700",
    ):
        assert token in data


def test_formal_pdf_renderer_preserves_decimal_text_exactly_without_float_rounding():
    bundle = _bundle()
    income = replace(bundle.income_statement, result=Decimal("0.1234567890123456789012345678"))
    data = _render(replace(bundle, income_statement=income))
    assert b"0.1234567890123456789012345678" in data


def test_formal_pdf_renderer_preserves_none_as_of_as_blank_not_literal_none():
    data = _render(_bundle(as_of=None))
    assert b"(None) Tj" not in data
    assert data.count(b"(Al: ) Tj") >= 2


def test_formal_pdf_renderer_requires_nominal_financial_statements_bundle():
    from aqorath.financial_statements_pdf import render_financial_statements_pdf

    class FakeBundle:
        pass

    with pytest.raises(TypeError):
        render_financial_statements_pdf(FakeBundle())


def test_formal_pdf_renderer_is_byte_deterministic_and_paginates_long_statements_without_data_loss():
    from aqorath.balance_sheet import BalanceSheetLine

    bundle = _bundle()
    long_lines = tuple(
        BalanceSheetLine(
            account_code=f"11{i:03d}",
            account_name=f"Activo {i:03d}",
            account_subtype="Circulante",
            amount=Decimal(f"{i}.0000"),
        )
        for i in range(1, 91)
    )
    balance = replace(bundle.balance_sheet, assets=replace(bundle.balance_sheet.assets, lines=long_lines))
    long_bundle = replace(bundle, balance_sheet=balance)
    first = _render(long_bundle)
    second = _render(long_bundle)
    assert first == second
    assert _page_count(first) > 2
    assert b"11090" in first
    assert b"Activo 090" in first
    assert _pdf_text("90.0000") in first


def test_formal_pdf_renderer_is_pure_uses_bundle_only_and_never_writes_files(monkeypatch):
    import builtins
    import sqlite3
    import tempfile

    import aqorath.accounting_rules as accounting_rules
    import aqorath.balance_sheet as balance_sheet
    import aqorath.financial_statement_semantics as semantics
    import aqorath.financial_statements as financial_statements
    import aqorath.financial_statements_pdf as renderer
    import aqorath.financial_statements_xlsx as xlsx_renderer
    import aqorath.income_statement as income_statement
    import aqorath.reporting_runtime as reporting_runtime
    import aqorath.storage as storage

    bundle = _bundle()

    def forbidden(*args, **kwargs):
        raise AssertionError("formal PDF renderer must consume only its supplied bundle")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    monkeypatch.setattr(tempfile, "NamedTemporaryFile", forbidden)
    monkeypatch.setattr(storage, "get_db_path", forbidden)
    monkeypatch.setattr(accounting_rules, "load_catalog", forbidden)
    monkeypatch.setattr(reporting_runtime, "get_financial_report_snapshot", forbidden)
    monkeypatch.setattr(reporting_runtime, "get_financial_statements_bundle", forbidden)
    monkeypatch.setattr(financial_statements, "build_financial_statements_bundle", forbidden)
    monkeypatch.setattr(income_statement, "build_income_statement_view", forbidden)
    monkeypatch.setattr(balance_sheet, "build_balance_sheet_view", forbidden)
    monkeypatch.setattr(semantics, "compute_financial_statement_totals", forbidden)
    monkeypatch.setattr(xlsx_renderer, "render_financial_statements_xlsx", forbidden)

    data = renderer.render_financial_statements_pdf(bundle)
    assert isinstance(data, bytes)
    assert data.startswith(b"%PDF-")
