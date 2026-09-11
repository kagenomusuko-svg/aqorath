"""SQLite authority for AQR-012 product identity and physical movement history."""

from dataclasses import replace
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlmodel import select

from .entity_repository import load_active_entity
from .inventory import InventoryState, Product, ZERO_STATE, moving_average, money
from .inventory_models import InventoryMovementRecord, ProductRecord
from .models import JournalEntry, JournalLine, ThirdPartyRecord


def _decimal(raw, field):
    try:
        value = Decimal(raw)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise RuntimeError(f"persisted {field} is not exact Decimal text") from exc
    if not value.is_finite():
        raise RuntimeError(f"persisted {field} must be finite")
    return value


def require_inventory_entity(session, entity_id=None):
    entity = load_active_entity(session)
    if entity is None or entity.id is None:
        raise LookupError("active Entity is required")
    if entity_id is not None and entity.id != entity_id:
        raise ValueError("inventory fact does not belong to active Entity")
    if "inventory_control" not in entity.profile.special_capabilities:
        raise ValueError("active EntityProfile does not enable inventory_control")
    if "inventory" not in entity.profile.modules_enabled:
        raise ValueError("active EntityProfile does not enable inventory module")
    return entity


def create_product(session, product):
    if not isinstance(product, Product):
        raise TypeError("product must be Product")
    if product.id is not None:
        raise ValueError("new product id must be None")
    require_inventory_entity(session, product.entity_id)
    existing = session.exec(
        select(ProductRecord).where(
            ProductRecord.entity_id == product.entity_id,
            ProductRecord.sku == product.sku,
        )
    ).one_or_none()
    if existing is not None:
        raise ValueError("product SKU already exists for Entity")
    record = ProductRecord(
        entity_id=product.entity_id,
        sku=product.sku,
        name=product.name,
        unit=product.unit,
        is_active=product.is_active,
    )
    try:
        session.add(record)
        session.flush()
        if record.id is None:
            raise RuntimeError("product persistence did not assign identity")
        session.commit()
    except Exception:
        session.rollback()
        raise
    return replace(product, id=record.id)


def load_product(session, entity_id, product_id):
    require_inventory_entity(session, entity_id)
    if type(product_id) is not int or product_id <= 0:
        raise ValueError("product_id must be a positive integer")
    record = session.get(ProductRecord, product_id)
    if record is None or record.entity_id != entity_id:
        raise LookupError("product does not belong to active Entity")
    return Product(record.id, record.entity_id, record.sku, record.name, record.unit, record.is_active)


def list_movements(session, entity_id, product_id, as_of=None):
    load_product(session, entity_id, product_id)
    if as_of is not None and type(as_of) is not date:
        raise TypeError("as_of must be date or None")
    rows = session.exec(
        select(InventoryMovementRecord).where(
            InventoryMovementRecord.entity_id == entity_id,
            InventoryMovementRecord.product_id == product_id,
        ).order_by(InventoryMovementRecord.occurred_on, InventoryMovementRecord.id)
    ).all()
    return [row for row in rows if as_of is None or row.occurred_on <= as_of]


def inventory_state(session, entity_id, product_id, as_of=None):
    rows = list_movements(session, entity_id, product_id, as_of)
    if not rows:
        return ZERO_STATE
    quantity = Decimal("0")
    value = Decimal("0")
    for row in rows:
        quantity += _decimal(row.quantity_delta, "quantity_delta")
        value += _decimal(row.value_delta, "value_delta")
        if quantity < 0 or value < 0:
            raise RuntimeError("persisted inventory history produces negative state")
        persisted_q = _decimal(row.quantity_after, "quantity_after")
        persisted_v = _decimal(row.value_after, "value_after")
        persisted_avg = _decimal(row.moving_average_after, "moving_average_after")
        expected_value = money(value)
        if persisted_q != quantity or persisted_v != expected_value:
            raise RuntimeError("inventory movement snapshot diverges from movement history")
        expected_avg = moving_average(expected_value, quantity)
        if persisted_avg != expected_avg:
            raise RuntimeError("persisted moving average diverges from deterministic history")
        value = expected_value
    if quantity == 0:
        value = Decimal("0")
    return InventoryState(quantity, value, moving_average(value, quantity))


def require_append_date(session, entity_id, product_id, operation_date):
    rows = list_movements(session, entity_id, product_id)
    if rows and operation_date < rows[-1].occurred_on:
        raise ValueError(
            "inventory movements are append-only by product date; backdating would recalculate historical cost"
        )


def find_operation(session, operation_id):
    if type(operation_id) is not str or not operation_id:
        raise ValueError("operation_id must be non-empty text")
    return session.exec(
        select(InventoryMovementRecord).where(
            InventoryMovementRecord.operation_id == operation_id
        )
    ).one_or_none()


def validate_movement_reconciliation(session, movement):
    if not isinstance(movement, InventoryMovementRecord):
        raise TypeError("movement must be InventoryMovementRecord")
    entry = session.get(JournalEntry, movement.entry_id)
    if entry is None:
        raise RuntimeError("inventory movement references missing JournalEntry")
    inventory_line = session.get(JournalLine, movement.inventory_line_id)
    if inventory_line is None or inventory_line.entry_id != entry.id:
        raise RuntimeError("inventory movement references invalid inventory JournalLine")
    value_delta = _decimal(movement.value_delta, "value_delta")
    signed_inventory = _decimal(inventory_line.debit, "inventory debit") - _decimal(
        inventory_line.credit, "inventory credit"
    )
    if money(signed_inventory) != money(value_delta):
        raise RuntimeError("inventory carrying value diverges from canonical inventory JournalLine")
    if movement.movement_kind == "sale":
        if movement.cogs_line_id is None:
            raise RuntimeError("sale movement must reference COGS JournalLine")
        cogs = session.get(JournalLine, movement.cogs_line_id)
        if cogs is None or cogs.entry_id != entry.id:
            raise RuntimeError("sale movement references invalid COGS JournalLine")
        cogs_amount = _decimal(cogs.debit, "cogs debit") - _decimal(cogs.credit, "cogs credit")
        if money(cogs_amount) != money(-value_delta):
            raise RuntimeError("COGS JournalLine does not equal inventory cost release")
    if movement.third_party_id is not None:
        party = session.get(ThirdPartyRecord, movement.third_party_id)
        if party is None or party.entity_id != movement.entity_id:
            raise RuntimeError("inventory movement counterparty does not belong to Entity")
    return True


__all__ = [
    "require_inventory_entity", "create_product", "load_product", "list_movements",
    "inventory_state", "require_append_date", "find_operation", "validate_movement_reconciliation",
]
