from datetime import date
from decimal import Decimal
import json
import sqlite3

import pytest


def _catalog():
    return {
        "1101": {"tipo": "Activo", "subtipo": "circulante", "naturaleza": "debit"},
        "1104": {"tipo": "Activo", "subtipo": "inventario", "naturaleza": "debit"},
        "3101": {"tipo": "Patrimonio", "subtipo": "capital", "naturaleza": "credit"},
        "4101": {"tipo": "Ingreso", "subtipo": "ventas", "naturaleza": "credit"},
        "5101": {"tipo": "Costo", "subtipo": "ventas", "naturaleza": "debit"},
    }


def _period_db(tmp_path):
    path = tmp_path / "aqr013-period.db"
    conn = sqlite3.connect(path)
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
                concept TEXT,
                state TEXT NOT NULL
            );
            CREATE TABLE journalline (
                id INTEGER PRIMARY KEY,
                entry_id INTEGER NOT NULL,
                account_code TEXT,
                account_id INTEGER,
                debit TEXT NOT NULL,
                credit TEXT NOT NULL
            );
            """
        )
        conn.executemany(
            "INSERT INTO account(id, code, name, nature) VALUES(?, ?, ?, ?)",
            (
                (1, "1101", "Bancos", "debit"),
                (2, "1104", "Inventarios", "debit"),
                (3, "3101", "Patrimonio", "credit"),
                (4, "4101", "Ventas", "credit"),
                (5, "5101", "Costo de ventas", "debit"),
            ),
        )
        # Opening truth: assets 200 = equity 200.
        conn.execute(
            "INSERT INTO journalentry(id,date,concept,state) VALUES(1,?,?,?)",
            ("2025-12-31T12:00:00+00:00", "opening", "posted"),
        )
        conn.executemany(
            "INSERT INTO journalline(id,entry_id,account_code,account_id,debit,credit) VALUES(?,?,?,?,?,?)",
            (
                (1, 1, "1101", 1, "100", "0"),
                (2, 1, "1104", 2, "100", "0"),
                (3, 1, "3101", 3, "0", "200"),
            ),
        )
        # January sale 100 and COGS 60.
        conn.execute(
            "INSERT INTO journalentry(id,date,concept,state) VALUES(2,?,?,?)",
            ("2026-01-15T12:00:00+00:00", "sale", "posted"),
        )
        conn.executemany(
            "INSERT INTO journalline(id,entry_id,account_code,account_id,debit,credit) VALUES(?,?,?,?,?,?)",
            (
                (4, 2, "1101", 1, "100", "0"),
                (5, 2, "4101", 4, "0", "100"),
                (6, 2, "5101", 5, "60", "0"),
                (7, 2, "1104", 2, "0", "60"),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return path


def _entity():
    from aqorath.entity import Entity, EntityProfile

    return Entity(
        id=1,
        name="Entidad Uno",
        rfc="AAA010101AAA",
        legal_personality="persona_moral",
        legal_form="sociedad",
        profile=EntityProfile(
            economic_purpose="lucrativo",
            is_donor_authorized=False,
            special_capabilities=(),
            modules_enabled=(),
        ),
        is_active=True,
    )


def test_governed_catalog_preserves_definition_request_package_boundaries():
    from aqorath import report_product_catalog as catalog
    from aqorath.report_definition import ReportDefinition
    from aqorath.report_package import ReportPackage

    definitions = catalog.list_report_definitions()
    assert tuple(definition.id for definition in definitions) == (1301, 1302, 1303)
    assert all(isinstance(definition, ReportDefinition) for definition in definitions)
    assert catalog.get_financial_period_package() == ReportPackage(
        id=13001,
        name="Paquete financiero por período",
        included_reports=definitions,
        suggested_parameters=(("period_semantics", "inclusive_range"),),
    )
    assert catalog.get_report_policy(1302) == {
        "product_type": "income_statement",
        "version": "1",
        "period_semantics": "inclusive_range",
        "allowed_filters": (),
        "allowed_dimensions": (),
    }
    with pytest.raises(LookupError):
        catalog.get_report_definition(999999)


def test_period_source_reconciles_opening_movements_closing_and_statement_truth(tmp_path):
    from aqorath.report_period_source import build_period_reporting_snapshot_from_sqlite
    from aqorath.income_statement import build_income_statement_view
    from aqorath.balance_sheet import build_balance_sheet_view

    snapshot = build_period_reporting_snapshot_from_sqlite(
        _period_db(tmp_path),
        _catalog(),
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
    )
    by_code = {line.account_code: line for line in snapshot.trial_balance.lines}
    assert by_code["1101"].opening_balance == Decimal("100")
    assert by_code["1101"].debits == Decimal("100")
    assert by_code["1101"].closing_balance == Decimal("200")
    assert by_code["1104"].opening_balance == Decimal("100")
    assert by_code["1104"].credits == Decimal("60")
    assert by_code["1104"].closing_balance == Decimal("40")
    assert snapshot.trial_balance.total_debits == Decimal("160")
    assert snapshot.trial_balance.total_credits == Decimal("160")

    income = build_income_statement_view(snapshot.movement_snapshot)
    balance = build_balance_sheet_view(snapshot.closing_snapshot)
    assert income.income.total == Decimal("100")
    assert income.costs.total == Decimal("60")
    assert income.result == Decimal("40")
    assert balance.assets.total == Decimal("240")
    assert balance.total_equity == Decimal("240")
    assert balance.balance_difference == Decimal("0")


def test_period_source_does_not_leak_post_range_movements(tmp_path):
    path = _period_db(tmp_path)
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "INSERT INTO journalentry(id,date,concept,state) VALUES(3,?,?,?)",
            ("2026-02-01T00:00:00+00:00", "later", "posted"),
        )
        conn.executemany(
            "INSERT INTO journalline(id,entry_id,account_code,account_id,debit,credit) VALUES(?,?,?,?,?,?)",
            (
                (8, 3, "1101", 1, "999", "0"),
                (9, 3, "4101", 4, "0", "999"),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    from aqorath.report_period_source import build_period_reporting_snapshot_from_sqlite
    snapshot = build_period_reporting_snapshot_from_sqlite(
        path,
        _catalog(),
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
    )
    by_code = {line.account_code: line for line in snapshot.trial_balance.lines}
    assert by_code["1101"].closing_balance == Decimal("200")
    assert snapshot.movement_snapshot.result == Decimal("40")


def test_first_package_uses_same_canonical_bundle_as_individual_reports(tmp_path, monkeypatch):
    from aqorath import report_period_runtime as runtime
    from aqorath import report_product_application as app

    path = _period_db(tmp_path)
    monkeypatch.setattr(runtime._storage, "get_db_path", lambda: path)
    monkeypatch.setattr(runtime._accounting_rules, "load_catalog", _catalog)
    monkeypatch.setattr(app._entities, "load_active_entity", lambda session: _entity())

    prepared = app.prepare_financial_period_package(
        object(),
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
        format="json",
    )
    assert tuple(request.report_definition_id for request in prepared.requests) == (
        1301,
        1302,
        1303,
    )
    package_result = app.build_financial_period_package(object(), prepared)
    individual = tuple(
        app.build_report_product(object(), request)
        for request in prepared.requests
    )
    assert tuple(report.content for report in package_result.reports) == tuple(
        report.content for report in individual
    )
    assert package_result.reports[1].content.result == Decimal("40")
    assert package_result.reports[2].content.balance_difference == Decimal("0")

    rendered = json.loads(app.render_report_package(package_result))
    assert rendered["package"]["name"] == "Paquete financiero por período"
    assert rendered["reports"][1]["content"]["result"] == "40"
    assert rendered["reports"][2]["content"]["assets"]["total"] == "240"


def test_request_validation_fails_closed_for_format_filters_dimensions_and_ownership(monkeypatch):
    from aqorath import report_product_application as app
    from aqorath.report_request import ReportRequest

    monkeypatch.setattr(app._entities, "load_active_entity", lambda session: _entity())

    with pytest.raises(ValueError, match="supported"):
        app.prepare_report_request(
            object(),
            1301,
            from_date=date(2026, 1, 1),
            to_date=date(2026, 1, 31),
            format="pdf",
        )
    with pytest.raises(ValueError, match="filters"):
        app.prepare_report_request(
            object(),
            1301,
            from_date=date(2026, 1, 1),
            to_date=date(2026, 1, 31),
            format="json",
            filters=(("arbitrary_sql", "select *"),),
        )
    with pytest.raises(ValueError, match="dimensions"):
        app.prepare_report_request(
            object(),
            1301,
            from_date=date(2026, 1, 1),
            to_date=date(2026, 1, 31),
            format="json",
            dimensions_to_group=("unknown",),
        )

    foreign = ReportRequest(
        id=None,
        report_definition_id=1301,
        entity_id=2,
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
        as_of_date=date(2026, 1, 31),
        filters=(),
        dimensions_to_group=(),
        format="json",
    )
    with pytest.raises(ValueError, match="active Entity"):
        app.build_report_product(object(), foreign)
