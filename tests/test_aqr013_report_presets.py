from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
import sqlite3

import pytest
from sqlmodel import Session, select


def _preset_setup(tmp_path, monkeypatch):
    from test_aqr012_inventory import _setup

    return _setup(tmp_path, monkeypatch)


def _package(entity_id, name, definitions):
    from aqorath.custom_report_package import CustomReportPackage

    return CustomReportPackage(
        id=None,
        owner_entity_id=entity_id,
        name=name,
        included_reports=tuple(definitions),
        created_at=datetime(2026, 9, 11, 6, 20, tzinfo=timezone.utc),
    )


def test_preset_crud_is_owner_scoped_and_preserves_order_format_and_options(tmp_path, monkeypatch):
    from aqorath import report_product_catalog as catalog
    from aqorath.entity import Entity, EntityProfile
    from aqorath.entity_repository import create_entity
    from aqorath.report_preset_repository import (
        create_report_preset,
        delete_report_preset,
        get_report_preset,
        list_report_presets,
        replace_report_preset,
    )

    engine, entity, _supplier, _customer, _product, _other = _preset_setup(tmp_path, monkeypatch)
    with Session(engine) as session:
        other_entity = create_entity(
            session,
            Entity(
                None,
                "Otra entidad",
                "ZZZ010101ZZZ",
                "persona_moral",
                "S.A.",
                EntityProfile("lucrativo", False, (), ()),
                False,
            ),
        )
        created = create_report_preset(
            session,
            _package(
                entity.id,
                "Consejo mensual",
                (catalog.TRIAL_BALANCE_PERIOD, catalog.ANALYTICAL_ACTIVITY_PERIOD),
            ),
            "json",
            ((), (("dimension_key", "program"),)),
        )
        preset_id = created.package.id
        assert preset_id is not None
        assert created.package.owner_entity_id == entity.id
        assert [item.id for item in created.package.included_reports] == [1301, 1306]
        assert created.item_parameters == ((), (("dimension_key", "program"),))
        assert created.format == "json"

    with Session(engine) as session:
        loaded = get_report_preset(session, entity.id, preset_id)
        assert loaded == list_report_presets(session, entity.id)[0]
        updated = replace_report_preset(
            session,
            entity.id,
            preset_id,
            name="Consejo reordenado",
            included_reports=(catalog.ANALYTICAL_ACTIVITY_PERIOD, catalog.TRIAL_BALANCE_PERIOD),
            format="json",
            item_parameters=((('dimension_key', 'fund'),), ()),
        )
        assert updated.package.id == preset_id
        assert updated.package.name == "Consejo reordenado"
        assert [item.id for item in updated.package.included_reports] == [1306, 1301]
        assert updated.item_parameters == ((("dimension_key", "fund"),), ())

        for operation in (
            lambda: get_report_preset(session, other_entity.id, preset_id),
            lambda: replace_report_preset(
                session,
                other_entity.id,
                preset_id,
                name="No permitido",
                included_reports=(catalog.TRIAL_BALANCE_PERIOD,),
                format="json",
            ),
            lambda: delete_report_preset(session, other_entity.id, preset_id),
        ):
            with pytest.raises(ValueError, match="active Entity"):
                operation()

        deleted = delete_report_preset(session, entity.id, preset_id)
        assert deleted == {"preset_id": preset_id, "deleted": True}
        assert list_report_presets(session, entity.id) == ()


def test_preset_rejects_forged_definition_disallowed_parameter_duplicate_and_format(tmp_path, monkeypatch):
    from aqorath import report_product_catalog as catalog
    from aqorath.report_preset_repository import create_report_preset

    engine, entity, _supplier, _customer, _product, _other = _preset_setup(tmp_path, monkeypatch)
    forged = replace(catalog.TRIAL_BALANCE_PERIOD, name="Balanza forjada")

    with Session(engine) as session:
        with pytest.raises(ValueError, match="canonical governed"):
            create_report_preset(
                session,
                _package(entity.id, "Forjado", (forged,)),
                "json",
            )
        with pytest.raises(ValueError, match="unsupported persisted parameter"):
            create_report_preset(
                session,
                _package(entity.id, "SQL", (catalog.TRIAL_BALANCE_PERIOD,)),
                "json",
                ((("sql", "select * from journalline"),),),
            )
        with pytest.raises(ValueError, match="duplicate report definitions"):
            create_report_preset(
                session,
                _package(
                    entity.id,
                    "Duplicado",
                    (catalog.TRIAL_BALANCE_PERIOD, catalog.TRIAL_BALANCE_PERIOD),
                ),
                "json",
            )
        with pytest.raises(ValueError, match="not supported"):
            create_report_preset(
                session,
                _package(entity.id, "Fiscal XLSX", (catalog.FISCAL_EVIDENCE_PERIOD,)),
                "xlsx",
            )


def test_v1_12_preset_survives_new_session_and_requeries_authorities(tmp_path, monkeypatch):
    from test_aqr012_inventory import _purchase
    from aqorath import report_product_catalog as catalog
    from aqorath.custom_report_product_runtime import generate_persisted_report_preset
    from aqorath.inventory_operations import execute_inventory_operation
    from aqorath.report_preset_repository import create_report_preset, get_report_preset, replace_report_preset
    from aqorath.report_product_runtime import generate_report

    engine, entity, supplier, _customer, product, _other = _preset_setup(tmp_path, monkeypatch)
    with Session(engine) as session:
        _prepared, confirmed = _purchase(
            session, entity, supplier, product, "2", "10", date(2026, 9, 10)
        )
    execute_inventory_operation(confirmed)

    with Session(engine) as session:
        created = create_report_preset(
            session,
            _package(
                entity.id,
                "Paquete consejo",
                (
                    catalog.TRIAL_BALANCE_PERIOD,
                    catalog.INCOME_STATEMENT_PERIOD,
                    catalog.BALANCE_SHEET_AS_OF,
                    catalog.JOURNAL_PERIOD,
                ),
            ),
            "json",
        )
        preset_id = created.package.id
        replaced = replace_report_preset(
            session,
            entity.id,
            preset_id,
            name="Paquete consejo mensual",
            included_reports=(
                catalog.JOURNAL_PERIOD,
                catalog.TRIAL_BALANCE_PERIOD,
                catalog.INCOME_STATEMENT_PERIOD,
                catalog.BALANCE_SHEET_AS_OF,
            ),
            format="json",
        )
        assert [item.id for item in replaced.package.included_reports] == [1304, 1301, 1302, 1303]

    with Session(engine) as reopened:
        persisted = get_report_preset(reopened, entity.id, preset_id)
    first = generate_persisted_report_preset(
        persisted, entity.id, date(2026, 9, 1), date(2026, 9, 30)
    )
    individual = tuple(generate_report(request) for request in first.requests)
    assert [report.definition.id for report in first.reports] == [1304, 1301, 1302, 1303]
    assert tuple(report.content for report in first.reports) == tuple(
        report.content for report in individual
    )
    first_trial = first.reports[1].content
    assert first_trial.total_debit == first_trial.total_credit == Decimal("20.00")

    with Session(engine) as session:
        _prepared, confirmed = _purchase(
            session, entity, supplier, product, "1", "5", date(2026, 9, 11)
        )
    execute_inventory_operation(confirmed)

    with Session(engine) as reopened_again:
        persisted_again = get_report_preset(reopened_again, entity.id, preset_id)
    second = generate_persisted_report_preset(
        persisted_again, entity.id, date(2026, 9, 1), date(2026, 9, 30)
    )
    second_trial = second.reports[1].content
    assert second_trial.total_debit == second_trial.total_credit == Decimal("25.00")
    assert persisted_again.package.included_reports == persisted.package.included_reports
    assert persisted_again.item_parameters == persisted.item_parameters


def test_executing_preset_for_wrong_entity_is_rejected(tmp_path, monkeypatch):
    from aqorath import report_product_catalog as catalog
    from aqorath.custom_report_product_runtime import generate_persisted_report_preset
    from aqorath.report_preset_repository import create_report_preset

    engine, entity, _supplier, _customer, _product, _other = _preset_setup(tmp_path, monkeypatch)
    with Session(engine) as session:
        preset = create_report_preset(
            session,
            _package(entity.id, "Owner", (catalog.TRIAL_BALANCE_PERIOD,)),
            "json",
        )
    with pytest.raises(ValueError, match="does not belong"):
        generate_persisted_report_preset(
            preset,
            entity.id + 999,
            date(2026, 9, 1),
            date(2026, 9, 30),
        )


def test_schema_12_to_13_is_additive_and_does_not_invent_presets(tmp_path):
    from aqorath import migrations
    from test_aqr010_cfdi_source import _schema10_snapshot

    path = tmp_path / "historical-v12.db"
    _schema10_snapshot(path)
    migrations._migrate_10_to_11(path)
    migrations._migrate_11_to_12(path)
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA user_version = 12")
        prior_tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        prior_cfdi_sources = conn.execute("SELECT COUNT(*) FROM cfdisource").fetchone()[0]
        prior_inventory_products = conn.execute("SELECT COUNT(*) FROM inventoryproduct").fetchone()[0]
        conn.commit()

    result = migrations.migrate_database(path)
    assert result["from_version"] == 12
    assert result["to_version"] == 13
    with sqlite3.connect(path) as conn:
        current_tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        assert prior_tables <= current_tables
        assert {"reportpreset", "reportpresetitem"} <= current_tables
        assert conn.execute("SELECT COUNT(*) FROM reportpreset").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM reportpresetitem").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM cfdisource").fetchone()[0] == prior_cfdi_sources
        assert conn.execute("SELECT COUNT(*) FROM inventoryproduct").fetchone()[0] == prior_inventory_products
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 13
