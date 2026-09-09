"""Application-facing service for the AQR-005 local presentation.

This module is the only local-runtime bridge needed by presentation. It opens the
canonical SQLite session, delegates accounting to AQR-004 and projects immutable
application/read values to JSON-compatible data. It contains no debit/credit rule,
period rule, fiscal calculation, reversal policy or audit persistence.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from . import accounting_operation as _operations
from . import accounting_operation_read as _operation_read
from . import application as _application
from . import economic_facts as _facts
from . import storage as _storage


@dataclass(frozen=True)
class CommonOperationKind:
    key: str
    label: str
    fact_type: str
    payment_method: str


@dataclass(frozen=True)
class PreparedSurfaceOperation:
    kind: CommonOperationKind
    decision: object


_OPERATION_KINDS = (
    CommonOperationKind("sale_cash", "Venta cobrada en efectivo", "sale", "cash"),
    CommonOperationKind("sale_credit", "Venta a crédito", "sale", "credit"),
    CommonOperationKind("utility_bank", "Pago de servicios desde banco", "utility_expense", "bank"),
    CommonOperationKind("utility_credit", "Servicio recibido a crédito", "utility_expense_incurred", "credit"),
    CommonOperationKind("receivable_collection", "Cobro a cliente en banco", "receivable_collection", "bank"),
    CommonOperationKind("supplier_payment", "Pago a proveedor desde banco", "supplier_payment", "bank"),
)
_OPERATION_BY_KEY = {item.key: item for item in _OPERATION_KINDS}


def list_common_operation_kinds():
    """Return only economic-fact inputs actually supported by the current domain."""
    return _OPERATION_KINDS


def _amount(value):
    if type(value) is Decimal:
        result = value
    elif type(value) is str:
        try:
            result = Decimal(value)
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("amount must be exact decimal text") from exc
    else:
        raise TypeError("amount must be exact decimal text")
    if not result.is_finite() or result <= Decimal("0"):
        raise ValueError("amount must be finite and greater than zero")
    return result


def _date(value):
    if type(value) is date:
        return value
    if type(value) is not str:
        raise TypeError("posting_date must be ISO date text")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("posting_date must be YYYY-MM-DD") from exc


def prepare_common_operation(operation_key, amount, posting_date):
    """Prepare one AQR-004 decision without exposing persistence to presentation."""
    if type(operation_key) is not str or operation_key not in _OPERATION_BY_KEY:
        raise ValueError("unsupported operation_key")
    kind = _OPERATION_BY_KEY[operation_key]
    fact = _facts.EconomicFact(
        type=kind.fact_type,
        amount=_amount(amount),
        payment_method=kind.payment_method,
    )
    with _storage.get_session() as session:
        decision = _operations.prepare_accounting_operation(
            session,
            fact,
            _date(posting_date),
        )
    return PreparedSurfaceOperation(kind=kind, decision=decision)


def common_preview(prepared):
    """Project a prepared decision without account codes or debit/credit inputs."""
    if not isinstance(prepared, PreparedSurfaceOperation):
        raise TypeError("prepared must be PreparedSurfaceOperation")
    decision = prepared.decision
    return {
        "operation_key": prepared.kind.key,
        "operation": prepared.kind.label,
        "amount": str(decision.fact.amount),
        "posting_date": decision.posting_date.isoformat(),
        "explanation": decision.explanation.professional_summary,
        "concepts": list(decision.explanation.concepts),
        "requires_confirmation": True,
    }


def professional_preview(prepared):
    """Project the exact same prepared decision for professional inspection."""
    if not isinstance(prepared, PreparedSurfaceOperation):
        raise TypeError("prepared must be PreparedSurfaceOperation")
    decision = prepared.decision
    lines = []
    for line in decision.resolved_proposal.lines:
        lines.append(
            {
                "account_id": line.account_id,
                "account_code": line.account_code,
                "account_name": line.account_name,
                "side": line.side,
                "amount": str(line.amount),
            }
        )
    return {
        "operation_key": prepared.kind.key,
        "posting_date": decision.posting_date.isoformat(),
        "rule_id": decision.rule_id,
        "rule_version": decision.rule_version,
        "explanation": decision.explanation.professional_summary,
        "lines": lines,
    }


def confirm_and_post(prepared):
    """Confirm exactly the prepared snapshot and execute AQR-004 once."""
    if not isinstance(prepared, PreparedSurfaceOperation):
        raise TypeError("prepared must be PreparedSurfaceOperation")
    confirmed = _operations.confirm_accounting_operation(prepared.decision)
    return _operations.execute_accounting_operation(confirmed)


def _document_dict(document):
    return {
        "id": document.id,
        "third_party_id": document.third_party_id,
        "document_type": document.document_type,
        "document_number": document.document_number,
        "issuer_name": document.issuer_name,
        "date": document.date.isoformat(),
        "file_hash": document.file_hash,
        "file_path": document.file_path,
        "external_url": document.external_url,
        "is_validated": document.is_validated,
        "validation_notes": document.validation_notes,
    }


def _fiscal_effect_dict(effect):
    return {
        "rule_key": effect.rule_key,
        "base": str(effect.base),
        "rate": str(effect.rate),
        "unit": effect.unit,
        "rule_effective_from": effect.rule_effective_from.isoformat(),
        "rule_effective_to": None if effect.rule_effective_to is None else effect.rule_effective_to.isoformat(),
        "rule_source_ref": effect.rule_source_ref,
        "exact_fiscal_amount": str(effect.exact_fiscal_amount),
        "rounding_policy_key": effect.rounding_policy_key,
        "rounding_quantizer": str(effect.rounding_quantizer),
        "rounding_mode": effect.rounding_mode,
        "rounding_source_ref": effect.rounding_source_ref,
        "rounded_fiscal_amount": str(effect.rounded_fiscal_amount),
        "fiscal_role": effect.fiscal_role,
        "fiscal_side": effect.fiscal_side,
    }


def _fiscal_dict(snapshot):
    if snapshot is None:
        return None
    provenance = snapshot.provenance
    omitted = snapshot.omitted_zero_fiscal_line
    return {
        "description": snapshot.description,
        "fact_type": provenance.fact_type,
        "fact_amount": str(provenance.fact_amount),
        "payment_method": provenance.payment_method,
        "effective_date": provenance.effective_date.isoformat(),
        "jurisdiction": provenance.jurisdiction,
        "regime": provenance.regime,
        "entity_type": provenance.entity_type,
        "amount_basis": provenance.amount_basis,
        "adjustment_role": provenance.adjustment_role,
        "effects": [_fiscal_effect_dict(effect) for effect in provenance.fiscal_effects],
        "zero_fiscal_line_policy": snapshot.zero_fiscal_line_policy,
        "omitted_zero_fiscal_line": None if omitted is None else {
            "account_role": omitted.account_role,
            "account_id": omitted.account_id,
            "account_code": omitted.account_code,
            "account_name": omitted.account_name,
            "side": omitted.side,
            "amount": str(omitted.amount),
        },
    }


def load_professional_operation(entry_id):
    """Load one persisted professional projection through the read authorities."""
    with _storage.get_session() as session:
        view = _operation_read.load_professional_accounting_operation(session, entry_id)
    return {
        "entry_id": view.entry_id,
        "posting_date": view.posting_date.isoformat(),
        "concept": view.concept,
        "state": view.state,
        "period": {
            "id": view.period.id,
            "year": view.period.year,
            "month": view.period.month,
            "start": view.period.start.isoformat(),
            "end": view.period.end.isoformat(),
            "state": view.period.state,
            "fiscal_year_state": view.period.fiscal_year_state,
        },
        "lines": [
            {
                "id": line.id,
                "account_id": line.account_id,
                "account_code": line.account_code,
                "account_name": line.account_name,
                "debit": str(line.debit),
                "credit": str(line.credit),
                "description": line.description,
            }
            for line in view.lines
        ],
        "documents": [_document_dict(document) for document in view.documents],
        "audit": None if view.audit is None else {
            "id": view.audit.id,
            "event_type": view.audit.event_type,
            "timestamp": view.audit.timestamp.isoformat(),
            "details": view.audit.details,
        },
        "reversal": None if view.reversal is None else {
            "original_entry_id": view.reversal.original_entry_id,
            "reversal_entry_id": view.reversal.reversal_entry_id,
            "reason": view.reversal.reason,
        },
        "fiscal_audit": _fiscal_dict(view.fiscal_audit),
    }


def _json_value(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value


def get_professional_trial_balance(as_of=None):
    """Expose the existing ledger balance projection without recomputing it."""
    value = None if as_of in (None, "") else _date(as_of)
    return _json_value(_application.get_trial_balance(as_of=value))


def get_surface_entity():
    """Return the active monoentity identity for the local shell."""
    with _storage.get_session() as session:
        entity = _application.get_active_entity(session)
    if entity is None:
        return None
    return {
        "id": entity.id,
        "name": entity.name,
        "rfc": entity.rfc,
        "legal_personality": entity.legal_personality,
        "legal_form": entity.legal_form,
        "economic_purpose": entity.profile.economic_purpose,
        "is_donor_authorized": entity.profile.is_donor_authorized,
    }


__all__ = [
    "CommonOperationKind",
    "PreparedSurfaceOperation",
    "list_common_operation_kinds",
    "prepare_common_operation",
    "common_preview",
    "professional_preview",
    "confirm_and_post",
    "load_professional_operation",
    "get_professional_trial_balance",
    "get_surface_entity",
]
