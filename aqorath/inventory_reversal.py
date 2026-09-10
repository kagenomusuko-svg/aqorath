"""AQR-012 reversal adapter over the canonical AQR-003 reversal authority."""

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlmodel import select

from . import audit_event_repository as _audit
from . import inventory_repository as _inventory
from . import reversal as _reversal
from . import storage as _storage
from .audit_event import AuditEvent
from .inventory import InventoryState, moving_average, money
from .inventory_models import InventoryMovementRecord
from .models import JournalLine


def _find_line(session, entry_id, account_code, signed_value):
    rows = session.exec(
        select(JournalLine).where(
            JournalLine.entry_id == entry_id,
            JournalLine.account_code == account_code,
        )
    ).all()
    matches = []
    for line in rows:
        signed = Decimal(line.debit) - Decimal(line.credit)
        if money(signed) == money(signed_value):
            matches.append(line)
    if len(matches) != 1 or matches[0].id is None:
        raise RuntimeError("reversal does not expose one exact inventory ledger line")
    return matches[0]


def reverse_inventory_movement(movement_id, reason, reversal_date=None):
    """Reverse ledger and physical movement atomically without rewriting history."""
    if type(movement_id) is not int or movement_id <= 0:
        raise ValueError("movement_id must be a positive integer")
    if type(reason) is not str or not reason.strip():
        raise ValueError("reason must be nonblank")
    day = reversal_date or date.today()
    if type(day) is not date:
        raise TypeError("reversal_date must be date or None")

    session = None
    try:
        with _storage.get_session() as session:
            original = session.get(InventoryMovementRecord, movement_id)
            if original is None:
                raise LookupError("inventory movement not found")
            if original.source_movement_id is not None:
                raise ValueError("a reversal movement cannot itself be reversed through this adapter")
            existing = session.exec(
                select(InventoryMovementRecord).where(
                    InventoryMovementRecord.source_movement_id == movement_id
                )
            ).one_or_none()
            if existing is not None:
                return {
                    "original_movement_id": movement_id,
                    "reversal_movement_id": existing.id,
                    "reversal_entry_id": existing.entry_id,
                    "idempotent": True,
                }
            _inventory.require_inventory_entity(session, original.entity_id)
            _inventory.require_append_date(session, original.entity_id, original.product_id, day)
            current = _inventory.inventory_state(session, original.entity_id, original.product_id)
            inverse_quantity = -Decimal(original.quantity_delta)
            inverse_value = -Decimal(original.value_delta)
            new_quantity = current.quantity + inverse_quantity
            new_value = money(current.value + inverse_value)
            if new_quantity < 0 or new_value < 0:
                raise ValueError("inventory reversal would produce negative stock or carrying value")
            if new_quantity == 0:
                if new_value != Decimal("0"):
                    raise ValueError("inventory reversal would leave value without physical stock")
                new_value = Decimal("0")
            after = InventoryState(new_quantity, new_value, moving_average(new_value, new_quantity))

            reversal = _reversal.reverse_posted_entry(
                session,
                original.entry_id,
                reason,
                day,
            )
            reversal_entry_id = reversal["reversal_entry_id"]
            original_inventory_line = session.get(JournalLine, original.inventory_line_id)
            if original_inventory_line is None:
                raise RuntimeError("original inventory JournalLine is missing")
            inventory_line = _find_line(
                session,
                reversal_entry_id,
                original_inventory_line.account_code,
                inverse_value,
            )
            cogs_line_id = None
            if original.cogs_line_id is not None:
                original_cogs = session.get(JournalLine, original.cogs_line_id)
                if original_cogs is None:
                    raise RuntimeError("original COGS JournalLine is missing")
                cogs = _find_line(
                    session,
                    reversal_entry_id,
                    original_cogs.account_code,
                    -inverse_value,
                )
                cogs_line_id = cogs.id

            movement = InventoryMovementRecord(
                operation_id=f"reversal:{movement_id}",
                entity_id=original.entity_id,
                product_id=original.product_id,
                entry_id=reversal_entry_id,
                movement_kind=f"reversal_{original.movement_kind}",
                occurred_on=day,
                quantity_delta=str(inverse_quantity),
                value_delta=str(inverse_value),
                unit_price=original.unit_price,
                unit_cost_basis=original.unit_cost_basis,
                quantity_after=str(after.quantity),
                value_after=str(after.value),
                moving_average_after=str(after.average),
                third_party_id=original.third_party_id,
                document_reference_id=original.document_reference_id,
                inventory_line_id=inventory_line.id,
                cogs_line_id=cogs_line_id,
                source_movement_id=original.id,
            )
            session.add(movement)
            session.flush()
            _inventory.validate_movement_reconciliation(session, movement)
            event = _audit.stage_audit_event(
                session,
                AuditEvent(
                    None,
                    original.entity_id,
                    "inventory_operation_reversed",
                    datetime.now(timezone.utc),
                    {
                        "original_movement_id": original.id,
                        "reversal_movement_id": movement.id,
                        "original_entry_id": original.entry_id,
                        "reversal_entry_id": reversal_entry_id,
                        "reason": reason,
                        "quantity_after": str(after.quantity),
                        "value_after": str(after.value),
                        "moving_average_after": str(after.average),
                    },
                ),
            )
            session.commit()
            return {
                "original_movement_id": original.id,
                "reversal_movement_id": movement.id,
                "reversal_entry_id": reversal_entry_id,
                "audit_event_id": event.id,
                "idempotent": False,
            }
    except Exception:
        if session is not None:
            try:
                session.rollback()
            except Exception:
                pass
        raise


__all__ = ["reverse_inventory_movement"]
