"""AQR-012 adapter that composes inventory with the existing AQR-011 authority.

This module selects no tax rule and owns no posting engine. The caller supplies an
explicit business ``activity``; AQR-011 resolves coverage, rules, accounts,
rounding and fiscal provenance. At execution time the already-confirmed fiscal
proposal is staged once with an independently balanced COGS/inventory pair before
the canonical JournalEntry is created. AQR-011 AuditEvent/CFDI evidence are then
staged in the same caller-owned transaction.
"""

from datetime import datetime, timezone
from decimal import Decimal

from . import audit_event_repository as _audit_events
from . import cfdi_source_repository as _cfdi_sources
from . import fiscal_v1_operation as _fiscal
from . import fiscalized_posting as _posting
from . import fiscalized_posting_persistence as _persistence
from .audit_event import AuditEvent
from .economic_facts import EconomicFact
from .fiscal_v1_coverage import FiscalV1Facts, UnsupportedFiscalV1Case, UNSUPPORTED_MESSAGE


def prepare_inventory_sale_fiscal(
    session,
    entity,
    fact,
    revenue,
    *,
    activity,
    third_party_id=None,
    cfdi_source_id=None,
):
    """Prepare AQR-011 from explicit inventory-sale facts; no rule key is accepted."""
    if activity is None:
        return None
    if not isinstance(activity, str) or not activity.strip():
        raise ValueError("fiscal_activity must be non-empty text or None")
    if not isinstance(revenue, Decimal) or not revenue.is_finite() or revenue <= 0:
        raise ValueError("inventory fiscal revenue must be a positive Decimal")
    if fact.settlement_method not in {"cash", "credit"}:
        raise UnsupportedFiscalV1Case(
            f"{UNSUPPORTED_MESSAGE} AQR-011 no declara la liquidación "
            f"{fact.settlement_method!r} para una venta fiscalizada de inventario."
        )
    facts = FiscalV1Facts(
        fact=EconomicFact("sale", revenue, fact.settlement_method),
        operation_date=fact.operation_date,
        entity_role="provider",
        entity_legal_personality=entity.legal_personality,
        counterparty_legal_personality=None,
        counterparty_fiscal_regime=None,
        activity=activity,
        territory="MX",
        base=revenue,
        effectively_paid=fact.settlement_method != "credit",
        cfdi_transferred_vat=None,
    )
    return _fiscal.prepare_fiscal_v1_operation(
        session,
        facts,
        third_party_id=third_party_id,
        cfdi_source_id=cfdi_source_id,
    )


def confirm_inventory_sale_fiscal(prepared):
    if prepared is None:
        return None
    return _fiscal.confirm_fiscal_v1_operation(prepared)


def _validated_context(session, confirmed):
    prepared = confirmed.prepared
    entity, profile = _fiscal._entity_context(session, prepared.facts)
    if entity.id != prepared.entity_id or profile.id != prepared.fiscal_profile_id:
        raise RuntimeError(
            "Entity/FiscalProfile authority changed after fiscal preparation; prepare again"
        )
    effective_facts, party, source = _fiscal._factual_context(
        session,
        entity,
        prepared.facts,
        third_party_id=prepared.third_party_id,
        cfdi_source_id=prepared.cfdi_source_id,
    )
    if effective_facts != prepared.facts:
        raise RuntimeError("factual authority changed after fiscal preparation; prepare again")
    if source is not None and (
        source.parsed.uuid != prepared.cfdi_source_uuid
        or source.parsed.sha256 != prepared.cfdi_source_hash
    ):
        raise RuntimeError("CFDI evidence changed after fiscal preparation; prepare again")
    return entity, profile, party, source


def stage_inventory_fiscal_sale(
    session,
    confirmed,
    *,
    additional_balanced_lines,
):
    """Stage one fiscalized sale + COGS/inventory in the caller-owned transaction."""
    if confirmed is None:
        raise TypeError("confirmed fiscal sale is required")
    entity, profile, party, source = _validated_context(session, confirmed)
    instruction = _posting.create_fiscalized_posting_instruction(
        confirmed.confirmed_proposal,
        _fiscal._zero_policy(confirmed.prepared.snapshot),
    )
    entry_id = _persistence.stage_fiscalized_posting_with_audit(
        session,
        instruction,
        posting_date=confirmed.prepared.facts.operation_date,
        state="posted",
        additional_balanced_lines=additional_balanced_lines,
    )
    event = _audit_events.stage_audit_event(
        session,
        AuditEvent(
            id=None,
            entity_id=entity.id,
            event_type="entry_posted",
            timestamp=datetime.now(timezone.utc),
            details=_fiscal._audit_details(
                confirmed,
                entry_id,
                entity,
                profile,
                party,
                source,
            ),
        ),
    )
    if event.id is None:
        raise RuntimeError("AQR-011 AuditEvent did not receive an identity")
    link = None
    if source is not None:
        link = _cfdi_sources.stage_cfdi_source_link(
            session,
            entity.id,
            source.id,
            entry_id,
        )
    return {
        "entry_id": entry_id,
        "audit_event_id": event.id,
        "document_reference_id": None if link is None else link.document_reference_id,
        "cfdi_source_link_id": None if link is None else link.id,
    }


__all__ = [
    "prepare_inventory_sale_fiscal",
    "confirm_inventory_sale_fiscal",
    "stage_inventory_fiscal_sale",
]
