from datetime import date
from decimal import Decimal

import pytest
from sqlmodel import Session, select

from test_aqr010_cfdi_source import _xml
from test_aqr012_inventory import _purchase, _setup
from test_aqr012_inventory_fiscal import _enable_general_sale_fiscality


def _customer_for_source(session, entity):
    from aqorath.third_party import ThirdParty
    from aqorath.third_party_repository import create_third_party

    return create_third_party(
        session,
        ThirdParty(
            None, entity.id, "Receptor CFDI", "MER260101AB1", None, None,
            "customer", None, None, None, True,
        ),
    )


def _seed_stock(engine, entity, supplier, product):
    from aqorath.inventory_operations import execute_inventory_operation

    with Session(engine) as session:
        _prepared, confirmed = _purchase(
            session, entity, supplier, product, "10", "100", date(2026, 9, 9)
        )
    return execute_inventory_operation(confirmed)


def test_supported_cfdi_fiscal_sale_composes_one_document_one_entry_and_inventory(tmp_path, monkeypatch):
    from aqorath.cfdi_models import CfdiSourceLinkRecord
    from aqorath.cfdi_source_repository import import_cfdi_source
    from aqorath.inventory import MerchandiseSaleFact
    from aqorath.inventory_operations import (
        confirm_inventory_operation,
        execute_inventory_operation,
        prepare_inventory_sale,
    )
    from aqorath.inventory_surface_application import load_inventory_surface_professional
    from aqorath.models import DocumentReferenceRecord, FiscalPostingAuditRecord, JournalEntry, JournalLine

    engine, entity, supplier, _customer, product, _ = _setup(tmp_path, monkeypatch)
    _enable_general_sale_fiscality(engine, entity)
    with Session(engine) as session:
        customer = _customer_for_source(session, entity)
        source = import_cfdi_source(session, _xml()).source
    _seed_stock(engine, entity, supplier, product)

    with Session(engine) as session:
        prepared = prepare_inventory_sale(
            session,
            MerchandiseSaleFact(
                entity.id, product.id, Decimal("4"), Decimal("250"),
                date(2026, 9, 10), "cash", customer.id,
            ),
            cfdi_source_id=source.id,
            fiscal_activity="ordinary_taxable_sale",
        )
        assert prepared.revenue_or_purchase_amount == Decimal("1000.00")
        assert prepared.inventory_cost == Decimal("400.00")
        assert prepared.fiscal_prepared.cfdi_source_id == source.id
        confirmed = confirm_inventory_operation(prepared)
    result = execute_inventory_operation(confirmed)

    with Session(engine) as session:
        assert len(session.exec(select(JournalEntry)).all()) == 2
        docs = session.exec(select(DocumentReferenceRecord)).all()
        links = session.exec(select(CfdiSourceLinkRecord)).all()
        assert len(docs) == len(links) == 1
        assert docs[0].id == links[0].document_reference_id == result["document_reference_id"]
        assert docs[0].entry_id == result["entry_id"]
        assert links[0].cfdi_source_id == source.id
        assert len(session.exec(
            select(FiscalPostingAuditRecord).where(FiscalPostingAuditRecord.entry_id == result["entry_id"])
        ).all()) == 1
        lines = session.exec(select(JournalLine).where(JournalLine.entry_id == result["entry_id"])).all()
        assert len(lines) == 5
        assert sum((Decimal(line.debit) for line in lines), Decimal("0")) == Decimal("1560.00")
        assert sum((Decimal(line.credit) for line in lines), Decimal("0")) == Decimal("1560.00")

    professional = load_inventory_surface_professional(result["movement_id"])
    assert professional["cfdi"]["source_id"] == source.id
    assert professional["cfdi"]["total"] == "1160.00"
    assert professional["fiscality"]["facts"]["base"] == "1000.00"
    assert professional["monetary"] == {
        "purchase_amount": None,
        "revenue": "1000.00",
        "cost_of_sale": "400.00",
        "margin": "600.00",
    }


def test_nonfiscal_cfdi_inventory_sale_requires_compatible_commercial_total_before_write(tmp_path, monkeypatch):
    from aqorath.cfdi_source_repository import import_cfdi_source
    from aqorath.inventory import MerchandiseSaleFact
    from aqorath.inventory_models import InventoryMovementRecord
    from aqorath.inventory_operations import prepare_inventory_sale
    from aqorath.models import JournalEntry

    engine, entity, supplier, _customer, product, _ = _setup(tmp_path, monkeypatch)
    with Session(engine) as session:
        customer = _customer_for_source(session, entity)
        source = import_cfdi_source(session, _xml()).source
    _seed_stock(engine, entity, supplier, product)

    with Session(engine) as session:
        before_entries = len(session.exec(select(JournalEntry)).all())
        before_moves = len(session.exec(select(InventoryMovementRecord)).all())
        with pytest.raises(ValueError, match="CFDI total differs"):
            prepare_inventory_sale(
                session,
                MerchandiseSaleFact(
                    entity.id, product.id, Decimal("4"), Decimal("250"),
                    date(2026, 9, 10), "cash", customer.id,
                ),
                cfdi_source_id=source.id,
            )
        assert len(session.exec(select(JournalEntry)).all()) == before_entries
        assert len(session.exec(select(InventoryMovementRecord)).all()) == before_moves


def test_late_failure_in_cfdi_fiscal_inventory_keeps_only_independent_source_and_prior_stock(tmp_path, monkeypatch):
    import aqorath.inventory_operations as operations
    from aqorath.cfdi_models import CfdiSourceLinkRecord, CfdiSourceRecord
    from aqorath.cfdi_source_repository import import_cfdi_source
    from aqorath.inventory import MerchandiseSaleFact
    from aqorath.inventory_models import InventoryMovementRecord
    from aqorath.models import AuditEventRecord, DocumentReferenceRecord, FiscalPostingAuditRecord, JournalEntry

    engine, entity, supplier, _customer, product, _ = _setup(tmp_path, monkeypatch)
    _enable_general_sale_fiscality(engine, entity)
    with Session(engine) as session:
        customer = _customer_for_source(session, entity)
        source = import_cfdi_source(session, _xml()).source
    _seed_stock(engine, entity, supplier, product)

    with Session(engine) as session:
        prepared = operations.prepare_inventory_sale(
            session,
            MerchandiseSaleFact(
                entity.id, product.id, Decimal("4"), Decimal("250"),
                date(2026, 9, 10), "cash", customer.id,
            ),
            cfdi_source_id=source.id,
            fiscal_activity="ordinary_taxable_sale",
        )
        confirmed = operations.confirm_inventory_operation(prepared)

    real = operations._audit.stage_audit_event

    def fail_inventory_audit(session, event):
        if event.event_type == "inventory_operation_posted":
            raise RuntimeError("forced late composed inventory failure")
        return real(session, event)

    monkeypatch.setattr(operations._audit, "stage_audit_event", fail_inventory_audit)
    with pytest.raises(RuntimeError, match="forced late composed inventory failure"):
        operations.execute_inventory_operation(confirmed)

    with Session(engine) as session:
        assert len(session.exec(select(CfdiSourceRecord)).all()) == 1
        assert session.exec(select(CfdiSourceLinkRecord)).all() == []
        assert session.exec(select(DocumentReferenceRecord)).all() == []
        assert session.exec(select(FiscalPostingAuditRecord)).all() == []
        assert len(session.exec(select(InventoryMovementRecord)).all()) == 1
        assert len(session.exec(select(JournalEntry)).all()) == 1
        event_types = [event.event_type for event in session.exec(select(AuditEventRecord)).all()]
        assert event_types.count("cfdi_source_imported") == 1
        assert event_types.count("inventory_operation_posted") == 1
        assert event_types.count("entry_posted") == 1
