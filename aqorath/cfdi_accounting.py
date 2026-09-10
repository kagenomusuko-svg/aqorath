"""Atomic confirmation of a user-classified operation backed by imported CFDI."""

from dataclasses import dataclass
import json
from uuid import uuid4

from sqlmodel import select

from . import accounting_operation as _operations
from . import accounting_operation_persistence as _persistence
from . import cfdi_source_repository as _sources
from . import posting as _posting
from . import storage as _storage
from .cfdi_models import CfdiSourceRecord
from .economic_facts import EconomicFact
from .models import AuditEventRecord, EntityRecord


@dataclass(frozen=True)
class PreparedCfdiAccounting:
    source_id: int
    source_uuid: str
    source_hash: str
    operation_kind: str
    decision: object
    operation_id: str


_KINDS = {
    "purchase_utility_bank": ("purchase", "03", "utility_expense", "bank"),
    "sale_cash": ("sale", "01", "sale", "cash"),
}


def prepare_cfdi_accounting(session, source_id, operation_kind):
    if operation_kind not in _KINDS:
        raise ValueError("unsupported CFDI accounting operation kind")
    entity = session.exec(
        select(EntityRecord).where(EntityRecord.is_active.is_(True))
    ).one_or_none()
    if entity is None:
        raise LookupError("active Entity is required")
    source = _sources.load_cfdi_source(session, entity.id, source_id)
    expected_relationship, expected_payment_form, fact_type, payment_method = _KINDS[operation_kind]
    if source.relationship != expected_relationship:
        raise ValueError(
            "selected operation kind conflicts with CFDI issuer/receiver relationship"
        )
    if source.parsed.payment_form != expected_payment_form:
        raise ValueError("selected operation kind conflicts with CFDI FormaPago")
    decision = _operations.prepare_accounting_operation(
        session,
        EconomicFact(fact_type, source.parsed.total, payment_method),
        source.parsed.issued_at.date(),
    )
    return PreparedCfdiAccounting(
        source.id,
        source.parsed.uuid,
        source.parsed.sha256,
        operation_kind,
        decision,
        uuid4().hex,
    )


def confirm_cfdi_accounting(prepared):
    if not isinstance(prepared, PreparedCfdiAccounting):
        raise TypeError("prepared must be PreparedCfdiAccounting")
    confirmed = _operations.confirm_accounting_operation(prepared.decision)
    instruction = _posting.create_posting_instruction(confirmed.confirmed_proposal)
    with _storage.get_session() as session:
        events = session.exec(
            select(AuditEventRecord).where(AuditEventRecord.event_type == "entry_posted")
        ).all()
        for event in events:
            try:
                details = json.loads(event.details_json)
            except (TypeError, ValueError):
                continue
            if details.get("cfdi_operation_id") == prepared.operation_id:
                return details["cfdi_operation_result"]
        entity = session.exec(
            select(EntityRecord).where(EntityRecord.is_active.is_(True))
        ).one()
        source = session.get(CfdiSourceRecord, prepared.source_id)
        if source is None or source.entity_id != entity.id:
            raise LookupError("prepared CFDI source no longer belongs to active Entity")
        if source.uuid != prepared.source_uuid or source.file_hash != prepared.source_hash:
            raise ValueError("prepared CFDI source snapshot changed")
        try:
            result = _persistence.stage_posting_with_audit(
                session, instruction, confirmed
            )
            link = _sources.stage_cfdi_source_link(
                session, entity.id, source.id, result.entry_id
            )
            output = {
                "entry_id": result.entry_id,
                "audit_event_id": result.audit_event_id,
                "cfdi_source_id": source.id,
                "cfdi_source_link_id": link.id,
                "document_reference_id": link.document_reference_id,
            }
            audit = session.get(AuditEventRecord, result.audit_event_id)
            audit.details_json = json.dumps(
                {
                    **json.loads(audit.details_json),
                    "cfdi_operation_id": prepared.operation_id,
                    "cfdi_source_id": source.id,
                    "cfdi_uuid": source.uuid,
                    "cfdi_operation_result": output,
                },
                sort_keys=True,
            )
            session.add(audit)
            session.commit()
            return output
        except Exception:
            session.rollback()
            raise


__all__ = [
    "PreparedCfdiAccounting",
    "prepare_cfdi_accounting",
    "confirm_cfdi_accounting",
]
