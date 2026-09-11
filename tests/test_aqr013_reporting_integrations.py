from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
import inspect
import sqlite3

import pytest
from sqlmodel import Session, select


def test_custom_package_selects_only_canonical_governed_reports_and_owner():
    from aqorath import report_product_catalog as catalog
    from aqorath.custom_report_package import CustomReportPackage
    from aqorath.custom_report_product_runtime import build_custom_package_requests

    package = CustomReportPackage(
        id=None,
        owner_entity_id=7,
        name="Mi paquete",
        included_reports=(catalog.GENERAL_LEDGER_PERIOD, catalog.BALANCE_SHEET_AS_OF),
        created_at=datetime(2026, 9, 11, tzinfo=timezone.utc),
    )
    requests = build_custom_package_requests(
        package, 7, date(2026, 8, 1), date(2026, 8, 31), "json"
    )
    assert [item.report_definition_id for item in requests] == [1305, 1303]
    assert requests[0].as_of_date is None
    assert requests[1].as_of_date == date(2026, 8, 31)

    with pytest.raises(ValueError, match="does not belong"):
        build_custom_package_requests(
            package, 8, date(2026, 8, 1), date(2026, 8, 31), "json"
        )

    forged = replace(catalog.GENERAL_LEDGER_PERIOD, name="Mayor alterado")
    forged_package = replace(package, included_reports=(forged,))
    with pytest.raises(ValueError, match="canonical governed"):
        build_custom_package_requests(
            forged_package, 7, date(2026, 8, 1), date(2026, 8, 31), "json"
        )


def test_analytical_view_is_exact_projection_of_aqr008_assignments(tmp_path):
    from test_p6_analytical_dimension_foundation import (
        _create_entity,
        _create_line,
        _dimension,
        _dimension_value,
        _fresh_db,
    )
    from aqorath.analytical_dimension_repository import (
        assign_analytical_dimension_value,
        create_analytical_dimension,
        create_analytical_dimension_value,
    )
    from aqorath.models import JournalLine
    from aqorath.report_authority_views import build_analytical_period_view

    _db, engine = _fresh_db(tmp_path, "aqr013-analytical.db")
    with Session(engine) as session:
        entity = _create_entity(session)
        dimension = create_analytical_dimension(session, _dimension(entity.id))
        value = create_analytical_dimension_value(session, _dimension_value(dimension.id))
        entry, _line = _create_line(session)
        lines = session.exec(select(JournalLine).where(JournalLine.entry_id == entry.id)).all()
        assert len(lines) == 2
        for line in lines:
            assign_analytical_dimension_value(session, line.id, value.id)

        view = build_analytical_period_view(
            session, entity.id, "program", date(2026, 8, 1), date(2026, 8, 31)
        )
        assert len(view.segments) == 1
        segment = view.segments[0]
        assert segment.value_code == "education"
        assert segment.debit == Decimal("100.00")
        assert segment.credit == Decimal("100.00")
        assert segment.net == Decimal("0.00")
        assert view.total_debit == view.total_credit == Decimal("100.00")


def test_inventory_valuation_consumes_exact_aqr012_state(tmp_path, monkeypatch):
    from test_aqr012_inventory import _purchase, _setup
    from aqorath.inventory_operations import execute_inventory_operation
    from aqorath.inventory_repository import inventory_state
    from aqorath.report_authority_views import build_inventory_valuation_view

    engine, entity, supplier, _customer, product, _other = _setup(tmp_path, monkeypatch)
    with Session(engine) as session:
        _prepared, confirmed = _purchase(
            session, entity, supplier, product, "3", "12.34", date(2026, 9, 10)
        )
    execute_inventory_operation(confirmed)

    with Session(engine) as session:
        expected = inventory_state(session, entity.id, product.id, date(2026, 9, 10))
        view = build_inventory_valuation_view(session, entity.id, date(2026, 9, 10))
        line = next(item for item in view.lines if item.product_id == product.id)
        assert line.quantity == expected.quantity
        assert line.carrying_value == expected.value
        assert line.moving_average == expected.average
        assert view.total_carrying_value == expected.value


def test_fiscal_document_view_reads_aqr011_audit_and_current_aqr010_link(tmp_path, monkeypatch):
    from test_aqr010_cfdi_source import _xml
    from test_aqr012_inventory import _setup
    from test_aqr012_inventory_cfdi_fiscal import _customer_for_source, _seed_stock
    from test_aqr012_inventory_fiscal import _enable_general_sale_fiscality
    from aqorath.cfdi_source_repository import import_cfdi_source
    from aqorath.inventory import MerchandiseSaleFact
    from aqorath.inventory_operations import (
        confirm_inventory_operation,
        execute_inventory_operation,
        prepare_inventory_sale,
    )
    from aqorath.report_authority_views import build_fiscal_evidence_period_view

    engine, entity, supplier, _customer, product, _other = _setup(tmp_path, monkeypatch)
    _enable_general_sale_fiscality(engine, entity)
    with Session(engine) as session:
        customer = _customer_for_source(session, entity)
        source = import_cfdi_source(session, _xml()).source
    _seed_stock(engine, entity, supplier, product)

    with Session(engine) as session:
        prepared = prepare_inventory_sale(
            session,
            MerchandiseSaleFact(
                entity.id,
                product.id,
                Decimal("4"),
                Decimal("250"),
                date(2026, 9, 10),
                "cash",
                customer.id,
            ),
            cfdi_source_id=source.id,
            fiscal_activity="ordinary_taxable_sale",
        )
        confirmed = confirm_inventory_operation(prepared)
    posted = execute_inventory_operation(confirmed)

    with Session(engine) as session:
        view = build_fiscal_evidence_period_view(
            session, date(2026, 9, 10), date(2026, 9, 10)
        )
        assert len(view.items) == 1
        item = view.items[0]
        assert item.entry_id == posted["entry_id"]
        assert item.audit_snapshot.provenance.base == Decimal("1000.00")
        assert len(item.documents) == 1
        document = item.documents[0]
        assert document.cfdi_source_id == source.id
        assert document.cfdi_uuid == source.uuid
        assert document.cfdi_version == source.version


def test_closed_period_remains_readable_and_wrong_entity_is_rejected(tmp_path, monkeypatch):
    from test_aqr012_inventory import _purchase, _setup
    from aqorath import report_product_catalog as catalog
    from aqorath.accounting_period_repository import close_period
    from aqorath.inventory_operations import execute_inventory_operation
    from aqorath.report_product_runtime import generate_report
    from aqorath.report_request import ReportRequest

    engine, entity, supplier, _customer, product, _other = _setup(tmp_path, monkeypatch)
    with Session(engine) as session:
        _prepared, confirmed = _purchase(
            session, entity, supplier, product, "2", "10", date(2026, 9, 10)
        )
    execute_inventory_operation(confirmed)
    with Session(engine) as session:
        close_period(session, 202609)
        session.commit()

    request = ReportRequest(
        None,
        catalog.TRIAL_BALANCE_PERIOD.id,
        entity.id,
        date(2026, 9, 1),
        date(2026, 9, 30),
        None,
        (),
        (),
        "json",
    )
    generated = generate_report(request)
    assert generated.content.total_debit == generated.content.total_credit == Decimal("20.00")

    wrong_owner = replace(request, entity_id=entity.id + 999)
    with pytest.raises(ValueError, match="active Entity"):
        generate_report(wrong_owner)


def test_common_and_professional_surfaces_separate_intent_from_provenance(tmp_path, monkeypatch):
    from test_aqr012_inventory import _purchase, _setup
    from aqorath.inventory_operations import execute_inventory_operation
    from aqorath.reporting_surface_application import (
        generate_financial_period_surface,
        professional_financial_period_surface,
    )

    engine, entity, supplier, _customer, product, _other = _setup(tmp_path, monkeypatch)
    with Session(engine) as session:
        _prepared, confirmed = _purchase(
            session, entity, supplier, product, "1", "10", date(2026, 9, 10)
        )
    execute_inventory_operation(confirmed)

    payload = {"from_date": "2026-09-01", "to_date": "2026-09-30", "format": "json"}
    common = generate_financial_period_surface(payload)["common"]
    assert common["package"] == "Paquete financiero por período"
    assert "entity_id" not in common
    assert "definition" not in common
    assert "source_authorities" not in common

    professional = professional_financial_period_surface(payload)
    assert professional["entity_id"] == entity.id
    assert len(professional["requests"]) == 3
    assert all(item["definition"]["id"] for item in professional["requests"])
    assert all(item["source_authorities"] for item in professional["requests"])


def test_http_report_handler_delegates_without_testclient(monkeypatch):
    import aqorath.web_surface as web

    class FakeController:
        def generate_financial_reports(self, payload):
            return {"ok": True, "payload": payload}

    monkeypatch.setattr(web, "controller", FakeController())
    result = web.generate_financial_reports({"from_date": "2026-08-01"})
    assert result == {"ok": True, "payload": {"from_date": "2026-08-01"}}


def test_aqr013_reporting_modules_do_not_persist_shadow_ledger():
    import aqorath.custom_report_product_runtime as custom_runtime
    import aqorath.report_authority_views as authority_views
    import aqorath.report_product_rendering as rendering
    import aqorath.report_product_runtime as runtime

    for module in (custom_runtime, authority_views, rendering, runtime):
        source = inspect.getsource(module)
        assert "table=True" not in source
        assert "session.add(" not in source
        assert ".commit(" not in source
