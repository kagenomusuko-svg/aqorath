"""Application-facing surface for AQR-011 fiscal V1.

The presentation layer supplies recognizable business facts only. This module
translates those facts into FiscalV1Facts and delegates all tax selection,
calculation, confirmation, posting and audit to fiscal_v1_operation.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from . import economic_facts as _facts
from . import entity_repository as _entities
from . import fiscal_v1_coverage as _coverage
from . import fiscal_v1_operation as _operations
from . import storage as _storage


@dataclass(frozen=True)
class FiscalV1SurfaceKind:
    key: str
    label: str
    fact_type: str
    payment_method: str
    entity_role: str
    activity: str


@dataclass(frozen=True)
class PreparedFiscalV1SurfaceOperation:
    kind: FiscalV1SurfaceKind
    prepared: _operations.PreparedFiscalV1Operation
    common_preview: dict


_KINDS = (
    FiscalV1SurfaceKind(
        "sale_general_paid",
        "Venta gravada cobrada en efectivo",
        "sale",
        "cash",
        "provider",
        "ordinary_taxable_sale",
    ),
    FiscalV1SurfaceKind(
        "sale_own_publication_paid",
        "Venta cobrada de publicación propia",
        "sale",
        "cash",
        "provider",
        "own_edited_publication_sale",
    ),
    FiscalV1SurfaceKind(
        "professional_service_paid",
        "Servicio profesional pagado por banco",
        "professional_services_expense",
        "bank",
        "recipient",
        "business_consulting_professional_service",
    ),
    FiscalV1SurfaceKind(
        "freight_goods_paid",
        "Autotransporte terrestre de bienes pagado por banco",
        "freight_expense",
        "bank",
        "recipient",
        "land_freight_goods",
    ),
)
_KIND_BY_KEY = {item.key: item for item in _KINDS}


def list_fiscal_v1_surface_kinds():
    return _KINDS


def _decimal(value, field):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{field} must be a valid decimal amount") from exc
    if not amount.is_finite() or amount <= 0:
        raise ValueError(f"{field} must be greater than zero")
    return amount


def _date(value):
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value:
        raise ValueError("operation_date is required")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("operation_date must use YYYY-MM-DD") from exc


def _optional_positive_int(value, field):
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a positive integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a positive integer") from exc
    if result <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return result


def _common_preview(kind, prepared):
    facts = prepared.facts
    explanations = [item.explanation for item in prepared.treatments]
    return {
        "operation": kind.label,
        "amount": str(facts.base),
        "posting_date": facts.operation_date.isoformat(),
        "explanation": " ".join(explanations),
        "operation_date": facts.operation_date.isoformat(),
        "base": str(facts.base),
        "counterparty_third_party_id": prepared.third_party_id,
        "cfdi_source_id": prepared.cfdi_source_id,
        "coverage_version": _coverage.COVERAGE_VERSION,
        "treatments": [
            {
                "name": item.treatment_key,
                "amount": str(
                    prepared.snapshot.provenance.fiscal_effects[index].rounded_fiscal_amount
                ),
                "explanation": item.explanation,
            }
            for index, item in enumerate(prepared.treatments)
        ],
        "limitations": list(prepared.limitations),
        "requires_confirmation": True,
        "warning": "Nada se contabiliza hasta confirmar exactamente esta preparación.",
    }


def prepare_fiscal_v1_surface_operation(payload):
    if not isinstance(payload, dict):
        raise TypeError("payload must be a dict")
    try:
        kind = _KIND_BY_KEY[payload.get("operation_key")]
    except KeyError as exc:
        raise ValueError("select a supported AQR-011 fiscal operation") from exc

    amount = _decimal(payload.get("amount"), "amount")
    operation_date = _date(payload.get("operation_date"))
    third_party_id = _optional_positive_int(payload.get("third_party_id"), "third_party_id")
    cfdi_source_id = _optional_positive_int(payload.get("cfdi_source_id"), "cfdi_source_id")

    with _storage.get_session() as session:
        entity = _entities.load_active_entity(session)
        if entity is None or entity.id is None:
            raise LookupError("active Entity is required")
        fact = _facts.EconomicFact(kind.fact_type, amount, kind.payment_method)
        facts = _coverage.FiscalV1Facts(
            fact=fact,
            operation_date=operation_date,
            entity_role=kind.entity_role,
            entity_legal_personality=entity.legal_personality,
            counterparty_legal_personality=None,
            counterparty_fiscal_regime=payload.get("counterparty_fiscal_regime"),
            activity=kind.activity,
            territory="MX",
            base=amount,
            effectively_paid=True,
            cfdi_transferred_vat=None,
        )
        prepared = _operations.prepare_fiscal_v1_operation(
            session,
            facts,
            third_party_id=third_party_id,
            cfdi_source_id=cfdi_source_id,
        )
    return PreparedFiscalV1SurfaceOperation(
        kind=kind,
        prepared=prepared,
        common_preview=_common_preview(kind, prepared),
    )


def professional_fiscal_v1_preview(value):
    if not isinstance(value, PreparedFiscalV1SurfaceOperation):
        raise TypeError("value must be PreparedFiscalV1SurfaceOperation")
    prepared = value.prepared
    return {
        "operation": value.kind.label,
        "coverage_version": _coverage.COVERAGE_VERSION,
        "facts": {
            "operation_date": prepared.facts.operation_date.isoformat(),
            "entity_role": prepared.facts.entity_role,
            "activity": prepared.facts.activity,
            "base": str(prepared.facts.base),
            "effectively_paid": prepared.facts.effectively_paid,
            "counterparty_legal_personality": prepared.facts.counterparty_legal_personality,
            "counterparty_fiscal_regime": prepared.facts.counterparty_fiscal_regime,
        },
        "treatments": [
            {
                "rule_key": item.treatment_key,
                "rule_set_key": item.rule_set_key,
                "rule_set_version": item.rule_set_version,
                "source_ref": item.rule.source_ref,
                "formula": item.formula,
                "exact_amount": str(item.exact_amount),
                "rounded_amount": str(
                    prepared.snapshot.provenance.fiscal_effects[index].rounded_fiscal_amount
                ),
                "account_role": item.fiscal_role,
                "side": item.fiscal_side,
            }
            for index, item in enumerate(prepared.treatments)
        ],
        "accounting": [
            {
                "account_role": line.account_role,
                "side": line.side,
                "amount": str(line.amount),
            }
            for line in prepared.snapshot.lines
        ],
        "third_party_id": prepared.third_party_id,
        "cfdi_source_id": prepared.cfdi_source_id,
        "cfdi_uuid": prepared.cfdi_source_uuid,
        "limitations": list(prepared.limitations),
    }


def confirm_and_execute_fiscal_v1_surface_operation(value):
    if not isinstance(value, PreparedFiscalV1SurfaceOperation):
        raise TypeError("value must be PreparedFiscalV1SurfaceOperation")
    confirmed = _operations.confirm_fiscal_v1_operation(value.prepared)
    result = _operations.execute_fiscal_v1_operation(confirmed)
    return {
        "entry_id": result.entry_id,
        "audit_event_id": result.audit_event_id,
        "cfdi_source_link_id": result.cfdi_source_link_id,
        "document_reference_id": result.document_reference_id,
        "coverage_version": _coverage.COVERAGE_VERSION,
        "state": "posted",
    }


def load_fiscal_v1_surface_professional(entry_id):
    if type(entry_id) is not int or entry_id <= 0:
        raise ValueError("entry_id must be a positive integer")
    with _storage.get_session() as session:
        entity = _entities.load_active_entity(session)
        if entity is None or entity.id is None:
            raise LookupError("active Entity is required")
        return _operations.load_fiscal_v1_operation(session, entity.id, entry_id)


__all__ = [
    "FiscalV1SurfaceKind",
    "PreparedFiscalV1SurfaceOperation",
    "list_fiscal_v1_surface_kinds",
    "prepare_fiscal_v1_surface_operation",
    "professional_fiscal_v1_preview",
    "confirm_and_execute_fiscal_v1_surface_operation",
    "load_fiscal_v1_surface_professional",
]
