from datetime import date
from decimal import Decimal

import pytest
from sqlmodel import Session, select

from test_aqr012_inventory import _purchase, _sale, _setup


def _surface_payload(kind, product, party, *, quantity, unit_price, settlement="bank", **extra):
    payload = {
        "operation_kind": kind,
        "product_id": product.id,
        "quantity": str(quantity),
        "unit_price": str(unit_price),
        "operation_date": "2026-09-10",
        "settlement_method": settlement,
        "third_party_id": None if party is None else party.id,
    }
    payload.update(extra)
    return payload


def test_v1_21_survives_common_surface_persistence_professional_and_audit(tmp_path, monkeypatch):
    from aqorath.inventory_models import InventoryMovementRecord
    from aqorath.models import JournalEntry, JournalLine
    from aqorath.presentation_controller import LocalPresentationController

    engine, _entity, supplier, customer, product, _ = _setup(tmp_path, monkeypatch)
    controller = LocalPresentationController()

    first = controller.prepare_inventory(
        _surface_payload("purchase", product, supplier, quantity="10", unit_price="10")
    )
    assert first["preview"]["stock_before"] == "0"
    assert first["preview"]["stock_after"] == "10"
    assert first["preview"]["moving_average_after"] == "10.000000000000"
    first_result = controller.confirm(first["token"])

    second = controller.prepare_inventory(
        _surface_payload("purchase", product, supplier, quantity="10", unit_price="20")
    )
    assert second["preview"]["stock_after"] == "20"
    assert second["preview"]["inventory_value_after"] == "300.00"
    assert second["preview"]["moving_average_after"] == "15.000000000000"
    second_result = controller.confirm(second["token"])

    sale = controller.prepare_inventory(
        _surface_payload("sale", product, customer, quantity="4", unit_price="25", settlement="cash")
    )
    assert sale["preview"]["stock_before"] == "20"
    assert sale["preview"]["stock_after"] == "16"
    assert sale["preview"]["revenue"] == "100.00"
    assert sale["preview"]["estimated_cost_of_sale"] == "60.00"
    assert sale["preview"]["margin_before_tax"] == "40.00"
    sale_result = controller.confirm(sale["token"])

    professional = controller.professional_inventory(sale_result["movement_id"])
    assert professional["product"]["id"] == product.id
    assert professional["movement"]["quantity_delta"] == "-4"
    assert professional["movement"]["value_delta"] == "-60.00"
    assert professional["movement"]["quantity_after"] == "16"
    assert professional["movement"]["value_after"] == "240.00"
    assert professional["movement"]["moving_average_after"] == "15.000000000000"
    assert professional["monetary"] == {
        "purchase_amount": None,
        "revenue": "100.00",
        "cost_of_sale": "60.00",
        "margin": "40.00",
    }
    assert len(professional["ledger"]["lines"]) == 4
    assert any(event["event_type"] == "inventory_operation_posted" for event in professional["audit"])
    assert professional["reconciled"] is True

    with Session(engine) as session:
        assert len(session.exec(select(InventoryMovementRecord)).all()) == 3
        assert len(session.exec(select(JournalEntry)).all()) == 3
        lines = session.exec(
            select(JournalLine).where(JournalLine.entry_id == sale_result["entry_id"])
        ).all()
        assert sum((Decimal(line.debit) for line in lines), Decimal("0")) == Decimal("160.00")
        assert sum((Decimal(line.credit) for line in lines), Decimal("0")) == Decimal("160.00")
        assert first_result["entry_id"] != second_result["entry_id"] != sale_result["entry_id"]


def test_surface_cancel_does_not_write_inventory_or_ledger(tmp_path, monkeypatch):
    from aqorath.inventory_models import InventoryMovementRecord
    from aqorath.models import JournalEntry
    from aqorath.presentation_controller import LocalPresentationController

    engine, _entity, supplier, _customer, product, _ = _setup(tmp_path, monkeypatch)
    controller = LocalPresentationController()
    pending = controller.prepare_inventory(
        _surface_payload("purchase", product, supplier, quantity="10", unit_price="10")
    )
    assert controller.cancel(pending["token"]) == {"cancelled": True}
    with Session(engine) as session:
        assert session.exec(select(InventoryMovementRecord)).all() == []
        assert session.exec(select(JournalEntry)).all() == []


def test_credit_purchase_and_sale_reuse_aqr006_and_reconcile_exact_control_lines(tmp_path, monkeypatch):
    from aqorath.inventory import MerchandisePurchaseFact, MerchandiseSaleFact
    from aqorath.inventory_operations import (
        InventoryDocumentInput,
        confirm_inventory_operation,
        execute_inventory_operation,
        prepare_inventory_purchase,
        prepare_inventory_sale,
    )
    from aqorath.inventory_surface_application import load_inventory_surface_professional
    from aqorath.models import JournalLine
    from aqorath.open_item_models import OpenItemRecord

    engine, entity, supplier, customer, product, _ = _setup(tmp_path, monkeypatch)

    with Session(engine) as session:
        purchase = prepare_inventory_purchase(
            session,
            MerchandisePurchaseFact(
                entity.id, product.id, Decimal("10"), Decimal("10"),
                date(2026, 9, 10), supplier.id, "credit",
            ),
            document=InventoryDocumentInput("invoice", "P-001", date(2026, 9, 10), supplier.name),
            due_date=date(2026, 10, 10),
        )
    purchase_result = execute_inventory_operation(confirm_inventory_operation(purchase))

    with Session(engine) as session:
        sale = prepare_inventory_sale(
            session,
            MerchandiseSaleFact(
                entity.id, product.id, Decimal("4"), Decimal("25"),
                date(2026, 9, 10), "credit", customer.id,
            ),
            document=InventoryDocumentInput("invoice", "S-001", date(2026, 9, 10), entity.name),
            due_date=date(2026, 10, 15),
        )
    sale_result = execute_inventory_operation(confirm_inventory_operation(sale))

    purchase_view = load_inventory_surface_professional(purchase_result["movement_id"])
    sale_view = load_inventory_surface_professional(sale_result["movement_id"])
    assert purchase_view["open_item"]["kind"] == "payable"
    assert purchase_view["open_item"]["original_amount"] == "100.00"
    assert sale_view["open_item"]["kind"] == "receivable"
    assert sale_view["open_item"]["original_amount"] == "100.00"
    assert sale_view["monetary"]["revenue"] == "100.00"
    assert sale_view["monetary"]["cost_of_sale"] == "40.00"

    with Session(engine) as session:
        items = session.exec(select(OpenItemRecord).order_by(OpenItemRecord.id)).all()
        assert len(items) == 2
        for item in items:
            line = session.get(JournalLine, item.source_line_id)
            amount = Decimal(line.debit) if item.kind == "receivable" else Decimal(line.credit)
            assert amount == Decimal("100.00")
            assert item.source_entry_id == line.entry_id


@pytest.mark.parametrize(
    ("source_kind", "expected_quantity", "expected_value"),
    [
        ("first_purchase", Decimal("6"), Decimal("140.00")),
        ("second_purchase", Decimal("6"), Decimal("40.00")),
        ("sale", Decimal("20"), Decimal("300.00")),
    ],
)
def test_reversal_after_later_movements_preserves_original_consolidated_cost_and_as_of(
    tmp_path, monkeypatch, source_kind, expected_quantity, expected_value
):
    from aqorath.inventory_models import InventoryMovementRecord
    from aqorath.inventory_operations import execute_inventory_operation
    from aqorath.inventory_repository import inventory_state
    from aqorath.inventory_reversal import reverse_inventory_movement

    engine, entity, supplier, _customer, product, _ = _setup(tmp_path, monkeypatch)
    with Session(engine) as session:
        _prepared, c1 = _purchase(session, entity, supplier, product, "10", "10", date(2026, 9, 8))
    r1 = execute_inventory_operation(c1)
    with Session(engine) as session:
        _prepared, c2 = _purchase(session, entity, supplier, product, "10", "20", date(2026, 9, 9))
    r2 = execute_inventory_operation(c2)
    with Session(engine) as session:
        _prepared, cs = _sale(session, entity, product, "4", "25", date(2026, 9, 10))
    rs = execute_inventory_operation(cs)

    target = {
        "first_purchase": r1["movement_id"],
        "second_purchase": r2["movement_id"],
        "sale": rs["movement_id"],
    }[source_kind]
    reverse_inventory_movement(target, f"reverse {source_kind}", date(2026, 9, 11))

    with Session(engine) as session:
        historical = inventory_state(session, entity.id, product.id, date(2026, 9, 10))
        current = inventory_state(session, entity.id, product.id, date(2026, 9, 11))
        assert (historical.quantity, historical.value) == (Decimal("16"), Decimal("240.00"))
        assert (current.quantity, current.value) == (expected_quantity, expected_value)
        original_sale = session.get(InventoryMovementRecord, rs["movement_id"])
        assert original_sale.quantity_delta == "-4"
        assert original_sale.value_delta == "-60.00"
        assert len(session.exec(select(InventoryMovementRecord)).all()) == 4


def test_cfdi_inventory_late_failure_keeps_preimported_source_and_rolls_back_operation(tmp_path, monkeypatch):
    import aqorath.inventory_operations as operations
    from aqorath.cfdi_models import CfdiSourceLinkRecord, CfdiSourceRecord
    from aqorath.cfdi_source_repository import import_cfdi_source
    from aqorath.inventory import MerchandiseSaleFact
    from aqorath.inventory_models import InventoryMovementRecord
    from aqorath.models import AuditEventRecord, DocumentReferenceRecord, JournalEntry
    from aqorath.third_party import ThirdParty
    from aqorath.third_party_repository import create_third_party
    from test_aqr010_cfdi_source import _xml

    engine, entity, supplier, _customer, product, _ = _setup(tmp_path, monkeypatch)
    with Session(engine) as session:
        customer = create_third_party(
            session,
            ThirdParty(
                None, entity.id, "Receptor CFDI", "MER260101AB1", None, None,
                "customer", None, None, None, True,
            ),
        )
        source = import_cfdi_source(session, _xml()).source
        _prepared, stock = _purchase(
            session, entity, supplier, product, "10", "100", date(2026, 9, 9)
        )
    operations.execute_inventory_operation(stock)

    with Session(engine) as session:
        prepared = operations.prepare_inventory_sale(
            session,
            MerchandiseSaleFact(
                entity.id, product.id, Decimal("4"), Decimal("290"),
                date(2026, 9, 10), "cash", customer.id,
            ),
            cfdi_source_id=source.id,
        )
        confirmed = operations.confirm_inventory_operation(prepared)

    real = operations._audit.stage_audit_event

    def fail_inventory_audit(session, event):
        if event.event_type == "inventory_operation_posted":
            raise RuntimeError("forced late inventory audit failure")
        return real(session, event)

    monkeypatch.setattr(operations._audit, "stage_audit_event", fail_inventory_audit)
    with pytest.raises(RuntimeError, match="forced late inventory audit failure"):
        operations.execute_inventory_operation(confirmed)

    with Session(engine) as session:
        assert len(session.exec(select(CfdiSourceRecord)).all()) == 1
        assert session.exec(select(CfdiSourceLinkRecord)).all() == []
        assert session.exec(select(DocumentReferenceRecord)).all() == []
        assert len(session.exec(select(InventoryMovementRecord)).all()) == 1
        assert len(session.exec(select(JournalEntry)).all()) == 1
        event_types = [event.event_type for event in session.exec(select(AuditEventRecord)).all()]
        assert event_types.count("cfdi_source_imported") == 1
        assert "inventory_operation_posted" not in event_types
