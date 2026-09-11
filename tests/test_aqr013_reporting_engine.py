from datetime import date
from decimal import Decimal
import sqlite3

import pytest


def _catalog():
    return {
        "1101": {"tipo": "Activo", "subtipo": "Circulante", "naturaleza": "Deudora"},
        "3101": {"tipo": "Patrimonio", "subtipo": "Capital", "naturaleza": "Acreedora"},
        "4201": {"tipo": "Ingreso", "subtipo": "Operacion", "naturaleza": "Acreedora"},
        "6101": {"tipo": "Gasto", "subtipo": "Administracion", "naturaleza": "Deudora"},
    }


@pytest.fixture
def period_db(tmp_path, monkeypatch):
    import aqorath.accounting_rules as accounting_rules
    import aqorath.storage as storage
    import aqorath.report_product_runtime as runtime

    db = tmp_path / "aqr013-period.db"
    conn = sqlite3.connect(str(db))
    try:
        conn.executescript(
            """
            CREATE TABLE account (
                id INTEGER PRIMARY KEY,
                code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                nature TEXT NOT NULL
            );
            CREATE TABLE journalentry (
                id INTEGER PRIMARY KEY,
                date TEXT NOT NULL,
                concept TEXT
            );
            CREATE TABLE journalline (
                id INTEGER PRIMARY KEY,
                entry_id INTEGER NOT NULL,
                account_code TEXT,
                account_id INTEGER,
                debit TEXT NOT NULL DEFAULT '0',
                credit TEXT NOT NULL DEFAULT '0'
            );
            INSERT INTO account(id, code, name, nature) VALUES
                (1, '1101', 'Bancos', 'DEBIT'),
                (2, '3101', 'Capital social', 'CREDIT'),
                (3, '4201', 'Ventas', 'CREDIT'),
                (4, '6101', 'Gastos administrativos', 'DEBIT');

            INSERT INTO journalentry(id, date, concept) VALUES
                (1, '2026-01-01', 'capital inicial'),
                (2, '2026-08-10', 'venta agosto'),
                (3, '2026-08-20', 'gasto agosto'),
                (4, '2026-09-05', 'venta futura');

            INSERT INTO journalline(entry_id, account_code, account_id, debit, credit) VALUES
                (1, '1101', 1, '1000.00', '0'),
                (1, '3101', 2, '0', '1000.00'),
                (2, '1101', 1, '200.00', '0'),
                (2, '4201', 3, '0', '200.00'),
                (3, '6101', 4, '50.00', '0'),
                (3, '1101', 1, '0', '50.00'),
                (4, '1101', 1, '100.00', '0'),
                (4, '4201', 3, '0', '100.00');
            """
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("AQORATH_DB", str(db))
    monkeypatch.setattr(storage, "get_db_path", lambda: db)
    monkeypatch.setattr(accounting_rules, "load_catalog", _catalog)
    monkeypatch.setattr(runtime, "_require_active_owner", lambda request, definition: object())
    return db


def test_governed_catalog_separates_definition_request_and_package():
    from aqorath import report_product_catalog as catalog

    definitions = catalog.list_report_definitions()
    governance = catalog.list_report_governance()
    assert [item.key for item in governance] == [
        "financial.trial_balance.period",
        "financial.income_statement.period",
        "financial.balance_sheet.as_of",
        "professional.journal.period",
        "professional.general_ledger.period",
    ]
    assert len({item.id for item in definitions}) == 5
    assert [item.definition_id for item in governance] == [item.id for item in definitions]
    assert all(item.version == "1" for item in governance)
    assert catalog.FINANCIAL_PERIOD_PACKAGE.included_reports == definitions[:3]
    assert catalog.PROFESSIONAL_DETAIL_PACKAGE.included_reports == (
        definitions[3],
        definitions[4],
        definitions[0],
    )
    assert catalog.FINANCIAL_PERIOD_PACKAGE.is_official is True


def test_period_trial_balance_reconciles_opening_movements_and_closing(period_db):
    from aqorath.period_reporting import build_period_trial_balance_from_sqlite

    view = build_period_trial_balance_from_sqlite(
        period_db, date(2026, 8, 1), date(2026, 8, 31)
    )
    by_code = {line.account_code: line for line in view.lines}

    assert by_code["1101"].opening_balance == Decimal("1000.00")
    assert by_code["1101"].debit == Decimal("200.00")
    assert by_code["1101"].credit == Decimal("50.00")
    assert by_code["1101"].closing_balance == Decimal("1150.00")
    assert by_code["4201"].credit == Decimal("200.00")
    assert by_code["6101"].debit == Decimal("50.00")
    assert view.total_debit == Decimal("250.00")
    assert view.total_credit == Decimal("250.00")


def test_financial_period_package_uses_same_authorities_as_individual_reports(period_db):
    from aqorath import report_product_runtime as runtime

    package = runtime.generate_financial_period_package(
        1, date(2026, 8, 1), date(2026, 8, 31), "json"
    )
    assert len(package.reports) == 3

    individual = tuple(runtime.generate_report(request) for request in package.requests)
    assert tuple(item.content for item in package.reports) == tuple(
        item.content for item in individual
    )

    trial, income, balance = [item.content for item in package.reports]
    assert trial.total_debit == trial.total_credit == Decimal("250.00")
    assert income.income.total == Decimal("200.00")
    assert income.expenses.total == Decimal("50.00")
    assert income.result == Decimal("150.00")
    assert balance.assets.total == Decimal("1150.00")
    assert balance.recorded_equity.total == Decimal("1000.00")
    assert balance.current_result == Decimal("150.00")
    assert balance.total_equity == Decimal("1150.00")
    assert balance.balance_difference == Decimal("0.00")


def test_package_excludes_future_movements_from_all_three_products(period_db):
    from aqorath import report_product_runtime as runtime

    august = runtime.generate_financial_period_package(
        1, date(2026, 8, 1), date(2026, 8, 31), "json"
    )
    september = runtime.generate_financial_period_package(
        1, date(2026, 9, 1), date(2026, 9, 30), "json"
    )

    august_income = august.reports[1].content
    september_income = september.reports[1].content
    assert august_income.result == Decimal("150.00")
    assert september_income.result == Decimal("100.00")
    assert august.reports[2].content.assets.total == Decimal("1150.00")
    assert september.reports[2].content.assets.total == Decimal("1250.00")


def test_request_validation_fails_closed_for_format_parameters_dimensions_and_period():
    from aqorath import report_product_catalog as catalog
    from aqorath.report_product_validation import validate_governed_report_request
    from aqorath.report_request import ReportRequest

    base = dict(
        id=None,
        report_definition_id=catalog.TRIAL_BALANCE_PERIOD.id,
        entity_id=1,
        from_date=date(2026, 8, 1),
        to_date=date(2026, 8, 31),
        as_of_date=None,
        filters=(),
        dimensions_to_group=(),
        format="json",
    )
    request = ReportRequest(**base)
    assert validate_governed_report_request(catalog.TRIAL_BALANCE_PERIOD, request) is request

    with pytest.raises(ValueError, match="format"):
        validate_governed_report_request(
            catalog.TRIAL_BALANCE_PERIOD,
            ReportRequest(**{**base, "format": "pdf"}),
        )
    with pytest.raises(ValueError, match="parameter"):
        validate_governed_report_request(
            catalog.TRIAL_BALANCE_PERIOD,
            ReportRequest(**{**base, "filters": (("sql", "select *"),)}),
        )
    with pytest.raises(ValueError, match="dimensions"):
        validate_governed_report_request(
            catalog.TRIAL_BALANCE_PERIOD,
            ReportRequest(**{**base, "dimensions_to_group": ("program",)}),
        )
    with pytest.raises(ValueError, match="as_of_date"):
        validate_governed_report_request(
            catalog.TRIAL_BALANCE_PERIOD,
            ReportRequest(**{**base, "as_of_date": date(2026, 8, 31)}),
        )


def test_financial_period_package_rejects_unsupported_format_before_generation(period_db):
    from aqorath import report_product_runtime as runtime

    with pytest.raises(ValueError, match="not supported"):
        runtime.generate_financial_period_package(
            1, date(2026, 8, 1), date(2026, 8, 31), "pdf"
        )
