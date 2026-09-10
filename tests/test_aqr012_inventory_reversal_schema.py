from datetime import date
from decimal import Decimal
import sqlite3

import pytest
from sqlmodel import Session, select

from test_aqr012_inventory import _purchase, _sale, _setup


def test_sale_reversal_restores_exact_pre_sale_physical_and_value_state(tmp_path, monkeypatch):
    from aqorath.inventory_operations import execute_inventory_operation
    from aqorath.inventory_repository import inventory_state
    from aqorath.inventory_reversal import reverse_inventory_movement

    engine, entity, supplier, _, product, _ = _setup(tmp_path, monkeypatch)
    with Session(engine) as s:
        _, c1 = _purchase(s, entity, supplier, product, "10", "10", date(2026, 9, 8))
    execute_inventory_operation(c1)
    with Session(engine) as s:
        _, c2 = _purchase(s, entity, supplier, product, "10", "20", date(2026, 9, 9))
    execute_inventory_operation(c2)
    with Session(engine) as s:
        _, cs = _sale(s, entity, product, "4", "25", date(2026, 9, 10))
    sale_result = execute_inventory_operation(cs)

    reversed_result = reverse_inventory_movement(
        sale_result["movement_id"], "Cliente canceló la venta", date(2026, 9, 11)
    )
    assert reversed_result["idempotent"] is False

    with Session(engine) as s:
        at_sale = inventory_state(s, entity.id, product.id, date(2026, 9, 10))
        after_reversal = inventory_state(s, entity.id, product.id, date(2026, 9, 11))
        assert (at_sale.quantity, at_sale.value, at_sale.average) == (
            Decimal("16"), Decimal("240.00"), Decimal("15.000000000000")
        )
        assert (after_reversal.quantity, after_reversal.value, after_reversal.average) == (
            Decimal("20"), Decimal("300.00"), Decimal("15.000000000000")
        )


def test_purchase_reversal_restores_zero_without_deleting_original_history(tmp_path, monkeypatch):
    from aqorath.inventory_models import InventoryMovementRecord
    from aqorath.inventory_operations import execute_inventory_operation
    from aqorath.inventory_repository import inventory_state
    from aqorath.inventory_reversal import reverse_inventory_movement
    from aqorath.models import JournalEntry

    engine, entity, supplier, _, product, _ = _setup(tmp_path, monkeypatch)
    with Session(engine) as s:
        _, confirmed = _purchase(s, entity, supplier, product, "10", "10")
    result = execute_inventory_operation(confirmed)
    first = reverse_inventory_movement(result["movement_id"], "Compra cancelada", date(2026, 9, 11))
    second = reverse_inventory_movement(result["movement_id"], "Compra cancelada", date(2026, 9, 11))
    assert first["reversal_movement_id"] == second["reversal_movement_id"]
    assert second["idempotent"] is True

    with Session(engine) as s:
        state = inventory_state(s, entity.id, product.id)
        assert state.quantity == Decimal("0")
        assert state.value == Decimal("0")
        moves = s.exec(select(InventoryMovementRecord).order_by(InventoryMovementRecord.id)).all()
        assert len(moves) == 2
        assert moves[1].source_movement_id == moves[0].id
        original_entry = s.get(JournalEntry, result["entry_id"])
        reversal_entry = s.get(JournalEntry, first["reversal_entry_id"])
        assert original_entry.state == "reversed"
        assert reversal_entry.state == "posted"


def test_late_audit_failure_rolls_back_entry_movement_and_units(tmp_path, monkeypatch):
    from aqorath import inventory_operations as operations
    from aqorath.inventory_models import InventoryMovementRecord
    from aqorath.inventory_repository import inventory_state
    from aqorath.models import JournalEntry

    engine, entity, supplier, _, product, _ = _setup(tmp_path, monkeypatch)
    with Session(engine) as s:
        _, confirmed = _purchase(s, entity, supplier, product, "10", "10")

    def fail(*args, **kwargs):
        raise RuntimeError("forced inventory audit failure")

    monkeypatch.setattr(operations._audit, "stage_audit_event", fail)
    with pytest.raises(RuntimeError, match="forced inventory audit failure"):
        operations.execute_inventory_operation(confirmed)

    with Session(engine) as s:
        assert s.exec(select(JournalEntry)).all() == []
        assert s.exec(select(InventoryMovementRecord)).all() == []
        assert inventory_state(s, entity.id, product.id).quantity == Decimal("0")


def test_schema_11_to_12_is_additive_and_does_not_invent_inventory_history(tmp_path):
    from aqorath import migrations
    from test_aqr010_cfdi_source import _schema10_snapshot

    path = tmp_path / "historical-v11.db"
    _schema10_snapshot(path)
    migrations._migrate_10_to_11(path)
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA user_version = 11")
        prior_tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        conn.commit()

    result = migrations.migrate_database(path)
    assert result["from_version"] == 11
    assert result["to_version"] == 12
    with sqlite3.connect(path) as conn:
        current_tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        assert prior_tables <= current_tables
        assert {"inventoryproduct", "inventorymovement"} <= current_tables
        assert conn.execute("SELECT COUNT(*) FROM inventoryproduct").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM inventorymovement").fetchone()[0] == 0
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 12


def test_credit_purchase_reuses_third_party_document_and_payable_control_line(tmp_path, monkeypatch):
    from aqorath.inventory import MerchandisePurchaseFact
    from aqorath.inventory_operations import (
        InventoryDocumentInput,
        confirm_inventory_operation,
        execute_inventory_operation,
        prepare_inventory_purchase,
    )
    from aqorath.models import DocumentReferenceRecord
    from aqorath.open_item_models import OpenItemRecord

    engine, entity, supplier, _, product, _ = _setup(tmp_path, monkeypatch)
    with Session(engine) as s:
        prepared = prepare_inventory_purchase(
            s,
            MerchandisePurchaseFact(
                entity.id, product.id, Decimal("10"), Decimal("10"),
                date(2026, 9, 10), supplier.id, "credit",
            ),
            document=InventoryDocumentInput("invoice", "INV-001", date(2026, 9, 10), supplier.name),
            due_date=date(2026, 10, 10),
        )
        confirmed = confirm_inventory_operation(prepared)
    result = execute_inventory_operation(confirmed)

    with Session(engine) as s:
        doc = s.get(DocumentReferenceRecord, result["document_reference_id"])
        item = s.exec(select(OpenItemRecord)).one()
        assert doc.third_party_id == supplier.id
        assert doc.entry_id == result["entry_id"]
        assert item.third_party_id == supplier.id
        assert item.source_entry_id == result["entry_id"]
        assert item.source_document_reference_id == doc.id
