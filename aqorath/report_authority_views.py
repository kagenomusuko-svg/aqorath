"""Read-only AQR-013 views over AQR-008/AQR-010/AQR-011/AQR-012 authorities.

This module deliberately contains no posting, tax rule selection, CFDI interpretation
or inventory costing policy. It asks existing authorities for persisted or validated
truth and shapes that truth for reporting.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlmodel import select

from . import analytical_dimension_repository as _analytics
from . import fiscal_posting_audit_read as _fiscal_read
from . import inventory_repository as _inventory
from .cfdi_models import CfdiSourceLinkRecord, CfdiSourceRecord
from .inventory_models import ProductRecord
from .models import (
    AnalyticalDimensionValueRecord,
    CfdiImportMetadataRecord,
    DocumentReferenceRecord,
    FiscalPostingAuditRecord,
    JournalEntry,
    JournalLine,
    JournalLineAnalyticalDimensionRecord,
)


@dataclass(frozen=True)
class AnalyticalSegment:
    value_id: int
    value_code: str
    value_name: str
    debit: Decimal
    credit: Decimal
    net: Decimal


@dataclass(frozen=True)
class AnalyticalPeriodView:
    entity_id: int
    dimension_id: int
    dimension_key: str
    dimension_name: str
    from_date: date
    to_date: date
    segments: tuple[AnalyticalSegment, ...]
    total_debit: Decimal
    total_credit: Decimal


@dataclass(frozen=True)
class InventoryValuationLine:
    product_id: int
    sku: str
    name: str
    unit: str
    quantity: Decimal
    carrying_value: Decimal
    moving_average: Decimal


@dataclass(frozen=True)
class InventoryValuationView:
    entity_id: int
    as_of: date
    lines: tuple[InventoryValuationLine, ...]
    total_carrying_value: Decimal


@dataclass(frozen=True)
class DocumentEvidence:
    document_reference_id: int
    cfdi_source_id: int | None
    document_type: str
    document_number: str
    issuer_name: str | None
    document_date: str
    third_party_id: int | None
    is_validated: bool
    cfdi_uuid: str | None
    cfdi_version: str | None


@dataclass(frozen=True)
class FiscalEvidenceItem:
    entry_id: int
    effective_date: date
    audit_snapshot: object
    documents: tuple[DocumentEvidence, ...]


@dataclass(frozen=True)
class FiscalEvidencePeriodView:
    from_date: date
    to_date: date
    items: tuple[FiscalEvidenceItem, ...]


def _entry_day(entry):
    raw = entry.date
    return raw if type(raw) is date else raw.date()


def build_analytical_period_view(session, entity_id, dimension_key, from_date, to_date):
    """Aggregate exact canonical JournalLine amounts by one existing AQR-008 value."""
    if type(entity_id) is not int or entity_id <= 0:
        raise ValueError("entity_id must be positive int")
    if type(dimension_key) is not str or not dimension_key or dimension_key.strip() != dimension_key:
        raise ValueError("dimension_key must be nonblank text")
    if type(from_date) is not date or type(to_date) is not date:
        raise TypeError("from_date and to_date must be date")
    if to_date < from_date:
        raise ValueError("to_date cannot precede from_date")

    dimensions = [item for item in _analytics.list_analytical_dimensions(session, entity_id) if item.key == dimension_key]
    if not dimensions:
        raise LookupError(f"analytical dimension {dimension_key!r} not found for Entity")
    if len(dimensions) != 1:
        raise RuntimeError("analytical dimension key is structurally ambiguous")
    dimension = dimensions[0]

    assignments = session.exec(
        select(JournalLineAnalyticalDimensionRecord)
        .where(JournalLineAnalyticalDimensionRecord.dimension_id == dimension.id)
        .order_by(JournalLineAnalyticalDimensionRecord.id)
    ).all()
    totals = {}
    for assignment in assignments:
        line = session.get(JournalLine, assignment.journal_line_id)
        value = session.get(AnalyticalDimensionValueRecord, assignment.dimension_value_id)
        if line is None or value is None:
            raise RuntimeError("analytical assignment references missing ledger/value identity")
        entry = session.get(JournalEntry, line.entry_id)
        if entry is None:
            raise RuntimeError("analytical assignment references missing JournalEntry")
        day = _entry_day(entry)
        if day < from_date or day > to_date:
            continue
        debit = Decimal(str(line.debit or "0"))
        credit = Decimal(str(line.credit or "0"))
        current = totals.setdefault(value.id, [value.code, value.name, Decimal("0"), Decimal("0")])
        current[2] += debit
        current[3] += credit

    segments = tuple(
        AnalyticalSegment(value_id, values[0], values[1], values[2], values[3], values[2] - values[3])
        for value_id, values in sorted(totals.items(), key=lambda item: (item[1][0], item[0]))
    )
    return AnalyticalPeriodView(
        entity.id if False else entity_id,
        dimension.id,
        dimension.key,
        dimension.name,
        from_date,
        to_date,
        segments,
        sum((item.debit for item in segments), Decimal("0")),
        sum((item.credit for item in segments), Decimal("0")),
    )


def build_inventory_valuation_view(session, entity_id, as_of):
    """Consume AQR-012 inventory_state; never implement moving-average policy here."""
    if type(as_of) is not date:
        raise TypeError("as_of must be date")
    _inventory.require_inventory_entity(session, entity_id)
    products = session.exec(
        select(ProductRecord).where(ProductRecord.entity_id == entity_id).order_by(ProductRecord.id)
    ).all()
    lines = []
    for product in products:
        state = _inventory.inventory_state(session, entity_id, product.id, as_of)
        lines.append(
            InventoryValuationLine(
                product.id,
                product.sku,
                product.name,
                product.unit,
                state.quantity,
                state.value,
                state.average,
            )
        )
    return InventoryValuationView(
        entity_id,
        as_of,
        tuple(lines),
        sum((item.carrying_value for item in lines), Decimal("0")),
    )


def _document_evidence(session, entry_id):
    documents = session.exec(
        select(DocumentReferenceRecord)
        .where(DocumentReferenceRecord.entry_id == entry_id)
        .order_by(DocumentReferenceRecord.id)
    ).all()
    result = []
    for document in documents:
        legacy_cfdi = session.exec(
            select(CfdiImportMetadataRecord).where(CfdiImportMetadataRecord.document_reference_id == document.id)
        ).one_or_none()
        link = session.exec(
            select(CfdiSourceLinkRecord).where(CfdiSourceLinkRecord.document_reference_id == document.id)
        ).one_or_none()
        source = None
        if link is not None:
            source = session.get(CfdiSourceRecord, link.cfdi_source_id)
            if source is None:
                raise RuntimeError("CFDI source link references missing AQR-010 source")
        result.append(
            DocumentEvidence(
                document.id,
                None if source is None else source.id,
                document.document_type,
                document.document_number,
                document.issuer_name,
                document.date,
                document.third_party_id,
                document.is_validated,
                source.uuid if source is not None else (None if legacy_cfdi is None else legacy_cfdi.uuid),
                source.version if source is not None else (None if legacy_cfdi is None else legacy_cfdi.cfdi_version),
            )
        )
    return tuple(result)


def build_fiscal_evidence_period_view(session, from_date, to_date):
    """Present persisted AQR-011 audit and AQR-010 document/CFDI evidence as-is."""
    if type(from_date) is not date or type(to_date) is not date:
        raise TypeError("from_date and to_date must be date")
    if to_date < from_date:
        raise ValueError("to_date cannot precede from_date")
    records = session.exec(
        select(FiscalPostingAuditRecord)
        .where(
            FiscalPostingAuditRecord.effective_date >= from_date,
            FiscalPostingAuditRecord.effective_date <= to_date,
        )
        .order_by(FiscalPostingAuditRecord.effective_date, FiscalPostingAuditRecord.entry_id)
    ).all()
    items = tuple(
        FiscalEvidenceItem(
            record.entry_id,
            record.effective_date,
            _fiscal_read.load_fiscal_posting_audit_snapshot(session, record.entry_id),
            _document_evidence(session, record.entry_id),
        )
        for record in records
    )
    return FiscalEvidencePeriodView(from_date, to_date, items)


__all__ = [
    "AnalyticalSegment",
    "AnalyticalPeriodView",
    "InventoryValuationLine",
    "InventoryValuationView",
    "DocumentEvidence",
    "FiscalEvidenceItem",
    "FiscalEvidencePeriodView",
    "build_analytical_period_view",
    "build_inventory_valuation_view",
    "build_fiscal_evidence_period_view",
]
