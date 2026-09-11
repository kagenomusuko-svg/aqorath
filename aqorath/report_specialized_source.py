"""Read-only AQR-013 specialized report projections.

Every projection delegates to an existing domain/persistence authority.  This module
never calculates moving average, fund availability, fiscal effects or CFDI meaning.
It only selects and structures the persisted/reconstructed truth those authorities
already expose.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import json

from sqlmodel import select

from . import fiscal_posting_audit_read as _fiscal_read
from . import fund_repository as _funds
from . import inventory_repository as _inventory
from .cfdi_models import CfdiSourceRecord
from .fund_models import FundRecord
from .inventory_models import ProductRecord
from .models import AuditEventRecord, FiscalPostingAuditRecord, JournalEntry


@dataclass(frozen=True)
class FundReportItem:
    fund_id: int
    code: str
    name: str
    restriction: str
    program_id: int | None
    balance: Decimal
    traceability: object


@dataclass(frozen=True)
class OscFundReport:
    as_of: date
    funds: tuple[FundReportItem, ...]
    total_balance: Decimal


@dataclass(frozen=True)
class InventoryReportItem:
    product_id: int
    sku: str
    name: str
    unit: str
    quantity: Decimal
    inventory_value: Decimal
    moving_average: Decimal


@dataclass(frozen=True)
class InventoryAsOfReport:
    as_of: date
    products: tuple[InventoryReportItem, ...]
    total_inventory_value: Decimal


@dataclass(frozen=True)
class FiscalReportItem:
    entry_id: int
    posting_date: date
    description: str
    audit_snapshot: object


@dataclass(frozen=True)
class FiscalEvidenceReport:
    from_date: date
    to_date: date
    items: tuple[FiscalReportItem, ...]


@dataclass(frozen=True)
class CfdiReportItem:
    source_id: int
    uuid: str
    document_position: str
    issued_at: datetime
    third_party_id: int
    currency: str
    subtotal: Decimal
    transferred: Decimal
    withheld: Decimal
    total: Decimal
    document_number: str | None


@dataclass(frozen=True)
class CfdiEvidenceReport:
    from_date: date
    to_date: date
    items: tuple[CfdiReportItem, ...]


def _require_range(from_date, to_date):
    if type(from_date) is not date or type(to_date) is not date:
        raise TypeError("from_date and to_date must be date")
    if to_date < from_date:
        raise ValueError("to_date cannot precede from_date")


def build_osc_fund_report(session, entity_id, *, as_of):
    """Project AQR-008 balances/traceability without creating OSC money truth."""
    if type(as_of) is not date:
        raise TypeError("as_of must be date")
    rows = session.exec(
        select(FundRecord)
        .where(FundRecord.entity_id == entity_id)
        .order_by(FundRecord.code, FundRecord.id)
    ).all()
    items = []
    total = Decimal("0")
    for row in rows:
        balance = _funds.load_fund_balance(session, entity_id, row.id, as_of)
        traceability = _funds.load_fund_traceability(session, entity_id, row.id, as_of)
        amount = balance.available_amount
        total += amount
        items.append(
            FundReportItem(
                fund_id=row.id,
                code=row.code,
                name=row.name,
                restriction=row.restriction,
                program_id=row.program_id,
                balance=amount,
                traceability=traceability,
            )
        )
    return OscFundReport(as_of=as_of, funds=tuple(items), total_balance=total)


def build_inventory_as_of_report(session, entity_id, *, as_of):
    """Consume AQR-012 inventory_state; never re-run moving-average arithmetic here."""
    if type(as_of) is not date:
        raise TypeError("as_of must be date")
    entity = _inventory.require_inventory_entity(session, entity_id)
    rows = session.exec(
        select(ProductRecord)
        .where(ProductRecord.entity_id == entity.id)
        .order_by(ProductRecord.sku, ProductRecord.id)
    ).all()
    items = []
    total = Decimal("0")
    for row in rows:
        state = _inventory.inventory_state(session, entity.id, row.id, as_of)
        total += state.value
        items.append(
            InventoryReportItem(
                product_id=row.id,
                sku=row.sku,
                name=row.name,
                unit=row.unit,
                quantity=state.quantity,
                inventory_value=state.value,
                moving_average=state.average,
            )
        )
    return InventoryAsOfReport(
        as_of=as_of,
        products=tuple(items),
        total_inventory_value=total,
    )


def _owned_entry_ids(session, entity_id):
    result = set()
    events = session.exec(
        select(AuditEventRecord).where(AuditEventRecord.event_type == "entry_posted")
    ).all()
    for event in events:
        if event.entity_id != entity_id:
            continue
        try:
            details = json.loads(event.details_json)
        except (TypeError, ValueError):
            continue
        entry_id = details.get("entry_id")
        if type(entry_id) is int and entry_id > 0:
            result.add(entry_id)
    return result


def build_fiscal_evidence_report(session, entity_id, *, from_date, to_date):
    """Read persisted AQR-011 fiscal audit snapshots without recalculation."""
    _require_range(from_date, to_date)
    owned = _owned_entry_ids(session, entity_id)
    records = session.exec(
        select(FiscalPostingAuditRecord).order_by(FiscalPostingAuditRecord.entry_id)
    ).all()
    items = []
    for record in records:
        if record.entry_id not in owned:
            continue
        entry = session.get(JournalEntry, record.entry_id)
        if entry is None:
            raise RuntimeError("fiscal audit references missing JournalEntry")
        day = entry.date.date()
        if not (from_date <= day <= to_date):
            continue
        snapshot = _fiscal_read.load_fiscal_posting_audit_snapshot(session, entry.id)
        items.append(
            FiscalReportItem(
                entry_id=entry.id,
                posting_date=day,
                description=entry.concept,
                audit_snapshot=snapshot,
            )
        )
    return FiscalEvidenceReport(from_date=from_date, to_date=to_date, items=tuple(items))


def build_cfdi_evidence_report(session, entity_id, *, from_date, to_date):
    """Project imported AQR-010 document evidence without economic/fiscal inference."""
    _require_range(from_date, to_date)
    rows = session.exec(
        select(CfdiSourceRecord)
        .where(CfdiSourceRecord.entity_id == entity_id)
        .order_by(CfdiSourceRecord.issued_at, CfdiSourceRecord.id)
    ).all()
    items = []
    for row in rows:
        issued = datetime.fromisoformat(row.issued_at)
        if not (from_date <= issued.date() <= to_date):
            continue
        items.append(
            CfdiReportItem(
                source_id=row.id,
                uuid=row.uuid,
                document_position=row.document_position,
                issued_at=issued,
                third_party_id=row.third_party_id,
                currency=row.currency,
                subtotal=Decimal(row.subtotal),
                transferred=Decimal(row.total_transferred),
                withheld=Decimal(row.total_withheld),
                total=Decimal(row.total),
                document_number=row.document_number,
            )
        )
    return CfdiEvidenceReport(from_date=from_date, to_date=to_date, items=tuple(items))
