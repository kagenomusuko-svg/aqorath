"""Presentation-facing AQR-012 inventory service.

The common projection speaks in product/quantity/price language and never exposes
account codes or debit/credit. The professional projection reconstructs the same
persisted operation from inventory provenance plus canonical ledger evidence.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import json

from sqlmodel import select

from . import fiscal_v1_operation as _fiscal_v1
from . import inventory_operations as _operations
from . import inventory_repository as _inventory
from . import inventory_reversal as _reversal
from . import open_item_repository as _open_items
from . import storage as _storage
from .inventory import MerchandisePurchaseFact, MerchandiseSaleFact, Product
from .inventory_models import InventoryMovementRecord, ProductRecord
from .open_item_models import OpenItemRecord
from .models import (
    AuditEventRecord,
    DocumentReferenceRecord,
    JournalEntry,
    JournalEntryReversalRecord,
    JournalLine,
    ThirdPartyRecord,
)
from .cfdi_models import CfdiSourceLinkRecord, CfdiSourceRecord


@dataclass(frozen=True)
class PreparedInventorySurfaceOperation:
    kind: str
    prepared: object
    preview: dict


def _decimal(value, name):
    if type(value) is Decimal:
        result = value
    elif type(value) is str:
        try:
            result = Decimal(value)
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"{name} must be exact decimal text") from exc
    elif type(value) is int:
        result = Decimal(value)
    else:
        raise TypeError(f"{name} must be Decimal, int or exact decimal text")
    if not result.is_finite() or result <= 0:
        raise ValueError(f"{name} must be finite and greater than zero")
    return result


def _date(value, name):
    if type(value) is date:
        return value
    if type(value) is not str:
        raise TypeError(f"{name} must be date or ISO date text")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be YYYY-MM-DD") from exc


def _positive_id(value, name, optional=False):
    if value is None and optional:
        return None
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def list_inventory_surface_products():
    with _storage.get_session() as session:
        entity = _inventory.require_inventory_entity(session)
        rows = session.exec(
            select(ProductRecord)
            .where(ProductRecord.entity_id == entity.id)
            .order_by(ProductRecord.sku, ProductRecord.id)
        ).all()
        return [
            {
                "id": row.id,
                "sku": row.sku,
                "name": row.name,
                "unit": row.unit,
                "is_active": row.is_active,
            }
            for row in rows
        ]


def create_inventory_surface_product(payload):
    if type(payload) is not dict:
        raise TypeError("payload must be dict")
    with _storage.get_session() as session:
        entity = _inventory.require_inventory_entity(session)
        product = _inventory.create_product(
            session,
            Product(
                None,
                entity.id,
                payload.get("sku"),
                payload.get("name"),
                payload.get("unit", "unidad"),
                True,
            ),
        )
        return {
            "id": product.id,
            "sku": product.sku,
            "name": product.name,
            "unit": product.unit,
            "is_active": product.is_active,
        }


def _document(payload):
    number = payload.get("document_number")
    document_type = payload.get("document_type")
    document_date = payload.get("document_date")
    supplied = (number is not None, document_type is not None, document_date is not None)
    if not any(supplied):
        return None
    if not all(supplied):
        raise ValueError("document_type, document_number and document_date must be supplied together")
    return _operations.InventoryDocumentInput(
        document_type,
        number,
        _date(document_date, "document_date"),
        payload.get("issuer_name"),
    )


def _party_summary(session, party_id):
    if party_id is None:
        return None
    party = session.get(ThirdPartyRecord, party_id)
    if party is None:
        raise LookupError("ThirdParty not found")
    return {"id": party.id, "name": party.name, "rfc": party.rfc, "party_type": party.party_type}


def _common_preview(kind, prepared, product, party):
    fact = prepared.fact
    result = {
        "operation": "Compra de mercancía" if kind == "purchase" else "Venta de mercancía",
        "product": {"id": product.id, "sku": product.sku, "name": product.name, "unit": product.unit},
        "quantity": str(fact.quantity),
        "unit_price": str(fact.unit_price),
        "operation_date": fact.operation_date.isoformat(),
        "settlement_method": fact.settlement_method,
        "counterparty": party,
        "stock_before": str(prepared.before.quantity),
        "stock_after": str(prepared.after.quantity),
        "inventory_value_before": str(prepared.before.value),
        "inventory_value_after": str(prepared.after.value),
        "moving_average_before": str(prepared.before.average),
        "moving_average_after": str(prepared.after.average),
        "document": None if prepared.document is None else {
            "type": prepared.document.document_type,
            "number": prepared.document.document_number,
            "date": prepared.document.document_date.isoformat(),
        },
        "cfdi_source_id": prepared.cfdi_source_id,
        "requires_confirmation": True,
        "explanation": prepared.explanation,
    }
    if kind == "purchase":
        result["purchase_amount"] = str(prepared.revenue_or_purchase_amount)
    else:
        result["revenue"] = str(prepared.revenue_or_purchase_amount)
        result["estimated_cost_of_sale"] = str(prepared.inventory_cost)
        result["margin_before_tax"] = str(
            prepared.revenue_or_purchase_amount - prepared.inventory_cost
        )
    return result


def prepare_inventory_surface_operation(payload):
    if type(payload) is not dict:
        raise TypeError("payload must be dict")
    kind = payload.get("operation_kind")
    if kind not in {"purchase", "sale"}:
        raise ValueError("operation_kind must be purchase or sale")
    quantity = _decimal(payload.get("quantity"), "quantity")
    unit_price = _decimal(payload.get("unit_price"), "unit_price")
    operation_date = _date(payload.get("operation_date"), "operation_date")
    product_id = _positive_id(payload.get("product_id"), "product_id")
    settlement = payload.get("settlement_method")
    due_date = payload.get("due_date")
    due_date = None if due_date is None else _date(due_date, "due_date")
    document = _document(payload)
    cfdi_source_id = _positive_id(payload.get("cfdi_source_id"), "cfdi_source_id", optional=True)

    with _storage.get_session() as session:
        entity = _inventory.require_inventory_entity(session)
        product = _inventory.load_product(session, entity.id, product_id)
        if kind == "purchase":
            party_id = _positive_id(payload.get("third_party_id"), "third_party_id")
            fact = MerchandisePurchaseFact(
                entity.id,
                product.id,
                quantity,
                unit_price,
                operation_date,
                party_id,
                settlement,
            )
            prepared = _operations.prepare_inventory_purchase(
                session,
                fact,
                document=document,
                cfdi_source_id=cfdi_source_id,
                due_date=due_date,
            )
        else:
            party_id = _positive_id(payload.get("third_party_id"), "third_party_id", optional=True)
            fact = MerchandiseSaleFact(
                entity.id,
                product.id,
                quantity,
                unit_price,
                operation_date,
                settlement,
                party_id,
            )
            prepared = _operations.prepare_inventory_sale(
                session,
                fact,
                document=document,
                cfdi_source_id=cfdi_source_id,
                due_date=due_date,
            )
        party = _party_summary(session, party_id)
        preview = _common_preview(kind, prepared, product, party)
    return PreparedInventorySurfaceOperation(kind, prepared, preview)


def professional_inventory_preview(value):
    if not isinstance(value, PreparedInventorySurfaceOperation):
        raise TypeError("value must be PreparedInventorySurfaceOperation")
    prepared = value.prepared
    return {
        **value.preview,
        "physical_effect": {
            "quantity_before": str(prepared.before.quantity),
            "quantity_after": str(prepared.after.quantity),
            "value_before": str(prepared.before.value),
            "value_after": str(prepared.after.value),
            "moving_average_before": str(prepared.before.average),
            "moving_average_after": str(prepared.after.average),
            "cost_release": None if value.kind == "purchase" else str(prepared.inventory_cost),
        },
        "accounting": "JournalEntry/JournalLine se construyen al confirmar; inventario no almacena un ledger monetario paralelo.",
        "fiscality": "La operación de inventario no selecciona reglas fiscales; AQR-011 permanece como autoridad fiscal.",
    }


def confirm_inventory_surface_operation(value):
    if not isinstance(value, PreparedInventorySurfaceOperation):
        raise TypeError("value must be PreparedInventorySurfaceOperation")
    return _operations.execute_inventory_operation(
        _operations.confirm_inventory_operation(value.prepared)
    )


def reverse_inventory_surface_operation(movement_id, reason, reversal_date=None):
    day = None if reversal_date is None else _date(reversal_date, "reversal_date")
    return _reversal.reverse_inventory_movement(movement_id, reason, day)


def _open_item_projection(session, entity_id, movement):
    rows = session.exec(
        select(OpenItemRecord).where(OpenItemRecord.source_entry_id == movement.entry_id)
    ).all()
    if not rows:
        return None
    if len(rows) != 1:
        raise RuntimeError("inventory JournalEntry must identify at most one OpenItem")
    record = rows[0]
    if record.entity_id != entity_id:
        raise RuntimeError("inventory OpenItem belongs to a different Entity")
    if movement.third_party_id is None or record.third_party_id != movement.third_party_id:
        raise RuntimeError("inventory OpenItem counterparty diverges from movement")
    if movement.document_reference_id is None or record.source_document_reference_id != movement.document_reference_id:
        raise RuntimeError("inventory OpenItem document diverges from movement")
    view = _open_items.load_open_item(session, record.id, as_of=movement.occurred_on)
    return {
        "id": view.id,
        "kind": view.kind,
        "third_party_id": view.third_party_id,
        "source_entry_id": view.source_entry_id,
        "source_line_id": view.source_line_id,
        "source_document_reference_id": view.source_document_reference_id,
        "due_date": view.due_date.isoformat(),
        "original_amount": str(view.original_amount),
        "applied_amount": str(view.applied_amount),
        "open_balance": str(view.open_balance),
        "status": view.status,
        "aging_bucket": view.aging_bucket,
    }


def _fiscal_projection(session, entity_id, entry_id):
    try:
        return _fiscal_v1.load_fiscal_v1_operation(session, entity_id, entry_id)
    except LookupError:
        return None


def _monetary_projection(movement, lines, fiscality):
    value_delta = Decimal(movement.value_delta)
    if movement.movement_kind in {"purchase", "reversal_purchase"}:
        return {
            "purchase_amount": str(abs(value_delta)),
            "revenue": None,
            "cost_of_sale": None,
            "margin": None,
        }
    if movement.movement_kind not in {"sale", "reversal_sale"}:
        return {
            "purchase_amount": None,
            "revenue": None,
            "cost_of_sale": None,
            "margin": None,
        }
    cost = abs(value_delta)
    if fiscality is not None:
        facts = fiscality.get("facts") or {}
        raw_revenue = facts.get("amount")
        if raw_revenue is None:
            raise RuntimeError("AQR-011 fiscal readback lacks economic amount")
        revenue = Decimal(raw_revenue)
    else:
        excluded = {movement.inventory_line_id, movement.cogs_line_id}
        commercial = [line for line in lines if line.id not in excluded]
        debit = sum((Decimal(line.debit) for line in commercial), Decimal("0"))
        credit = sum((Decimal(line.credit) for line in commercial), Decimal("0"))
        if debit != credit or debit < Decimal("0"):
            raise RuntimeError("commercial JournalLines do not expose one balanced sale amount")
        revenue = debit
    margin = revenue - cost
    return {
        "purchase_amount": None,
        "revenue": str(revenue),
        "cost_of_sale": str(cost),
        "margin": str(margin),
    }


def load_inventory_surface_professional(movement_id):
    movement_id = _positive_id(movement_id, "movement_id")
    with _storage.get_session() as session:
        movement = session.get(InventoryMovementRecord, movement_id)
        if movement is None:
            raise LookupError("inventory movement not found")
        entity = _inventory.require_inventory_entity(session, movement.entity_id)
        product = _inventory.load_product(session, entity.id, movement.product_id)
        _inventory.validate_movement_reconciliation(session, movement)
        entry = session.get(JournalEntry, movement.entry_id)
        if entry is None:
            raise RuntimeError("inventory movement JournalEntry is missing")
        lines = session.exec(
            select(JournalLine)
            .where(JournalLine.entry_id == movement.entry_id)
            .order_by(JournalLine.id)
        ).all()
        party = None if movement.third_party_id is None else session.get(ThirdPartyRecord, movement.third_party_id)
        if movement.third_party_id is not None and (party is None or party.entity_id != entity.id):
            raise RuntimeError("inventory ThirdParty belongs to a different Entity")
        document = None if movement.document_reference_id is None else session.get(
            DocumentReferenceRecord, movement.document_reference_id
        )
        if movement.document_reference_id is not None:
            if document is None:
                raise RuntimeError("inventory DocumentReference is missing")
            if document.entry_id != movement.entry_id:
                raise RuntimeError("inventory DocumentReference belongs to a different JournalEntry")
            if document.third_party_id != movement.third_party_id:
                raise RuntimeError("inventory DocumentReference counterparty diverges from movement")
        cfdi_link = None
        cfdi = None
        if movement.document_reference_id is not None:
            cfdi_link = session.exec(
                select(CfdiSourceLinkRecord).where(
                    CfdiSourceLinkRecord.document_reference_id == movement.document_reference_id
                )
            ).one_or_none()
            if cfdi_link is not None:
                cfdi = session.get(CfdiSourceRecord, cfdi_link.cfdi_source_id)
                if cfdi is None or cfdi.entity_id != entity.id:
                    raise RuntimeError("inventory CFDI evidence belongs to a different Entity")
        open_item = _open_item_projection(session, entity.id, movement)
        fiscality = _fiscal_projection(session, entity.id, entry.id)
        monetary = _monetary_projection(movement, lines, fiscality)
        audits = []
        for row in session.exec(
            select(AuditEventRecord)
            .where(AuditEventRecord.entity_id == entity.id)
            .order_by(AuditEventRecord.id)
        ).all():
            try:
                details = json.loads(row.details_json)
            except (TypeError, ValueError):
                continue
            if (
                details.get("movement_id") == movement.id
                or details.get("original_movement_id") == movement.id
                or details.get("entry_id") == movement.entry_id
            ):
                audits.append({"id": row.id, "event_type": row.event_type, "details": details})
        reversal = session.exec(
            select(InventoryMovementRecord).where(
                InventoryMovementRecord.source_movement_id == movement.id
            )
        ).one_or_none()
        accounting_reversal = session.exec(
            select(JournalEntryReversalRecord).where(
                JournalEntryReversalRecord.original_entry_id == movement.entry_id
            )
        ).one_or_none()
        as_of_state = _inventory.inventory_state(
            session, entity.id, product.id, movement.occurred_on
        )
        return {
            "movement": {
                "id": movement.id,
                "kind": movement.movement_kind,
                "date": movement.occurred_on.isoformat(),
                "quantity_delta": movement.quantity_delta,
                "value_delta": movement.value_delta,
                "unit_price": movement.unit_price,
                "unit_cost_basis": movement.unit_cost_basis,
                "quantity_after": movement.quantity_after,
                "value_after": movement.value_after,
                "moving_average_after": movement.moving_average_after,
            },
            "product": {"id": product.id, "sku": product.sku, "name": product.name, "unit": product.unit},
            "state_as_of_operation": {
                "quantity": str(as_of_state.quantity),
                "value": str(as_of_state.value),
                "moving_average": str(as_of_state.average),
            },
            "monetary": monetary,
            "ledger": {
                "entry_id": entry.id,
                "state": entry.state,
                "period_id": entry.period_id,
                "lines": [
                    {
                        "id": line.id,
                        "account_id": line.account_id,
                        "account_code": line.account_code,
                        "debit": line.debit,
                        "credit": line.credit,
                    }
                    for line in lines
                ],
            },
            "third_party": None if party is None else {"id": party.id, "name": party.name, "rfc": party.rfc},
            "open_item": open_item,
            "document": None if document is None else {
                "id": document.id,
                "type": document.document_type,
                "number": document.document_number,
                "date": document.date,
            },
            "cfdi": None if cfdi is None else {"source_id": cfdi.id, "uuid": cfdi.uuid, "total": cfdi.total},
            "fiscality": fiscality,
            "audit": audits,
            "reversal": None if reversal is None else {
                "movement_id": reversal.id,
                "entry_id": reversal.entry_id,
                "accounting_reversal_id": None if accounting_reversal is None else accounting_reversal.id,
            },
            "reconciled": True,
        }


__all__ = [
    "PreparedInventorySurfaceOperation",
    "list_inventory_surface_products",
    "create_inventory_surface_product",
    "prepare_inventory_surface_operation",
    "professional_inventory_preview",
    "confirm_inventory_surface_operation",
    "reverse_inventory_surface_operation",
    "load_inventory_surface_professional",
]
