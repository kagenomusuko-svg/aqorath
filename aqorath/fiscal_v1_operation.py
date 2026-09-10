"""AQR-011 application-domain composition over the existing fiscalized pipeline.

The module owns no tax rates, journal persistence, account codes or UI rules. It
composes factual V1 applicability with the already-existing fiscal confirmation,
rounding, accounting-effect, fiscalized proposal, account-resolution, posting
and audit authorities. Preparation is read-only; consent and execution are
separate boundaries.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlmodel import select

from . import account_bindings as _bindings
from . import audit_event_repository as _audit_events
from . import economic_fact_accounting_provenance as _economic
from . import entity_repository as _entities
from . import fiscal_accounting_effect as _effect
from . import fiscal_accounting_treatment as _treatment
from . import fiscal_confirmation as _confirmation
from . import fiscal_economic_composition as _composition
from . import fiscal_monetary_confirmation as _money
from . import fiscal_posting_audit_read as _audit_read
from . import fiscal_rounding as _rounding
from . import fiscal_v1_coverage as _coverage
from . import fiscalized_account_resolution as _account_resolution
from . import fiscalized_accounting_proposal as _proposal
from . import fiscalized_confirmation as _fiscalized_confirmation
from . import fiscalized_posting as _posting
from . import fiscalized_posting_persistence as _persistence
from . import models as _models
from . import storage as _storage
from .audit_event import AuditEvent


MXN_ROUNDING_POLICY = _rounding.FiscalRoundingPolicy(
    policy_key="mx-fiscal-v1.mxn-two-decimals-half-up",
    quantizer=Decimal("0.01"),
    rounding_mode=ROUND_HALF_UP,
    source_ref=(
        "AQR-011:explicit-monetary-presentation-policy;"
        "legal-formulas-remain-unrounded-in-rule-provenance"
    ),
)


@dataclass(frozen=True)
class PreparedFiscalV1Operation:
    """Read-only V1 proposal ready for informed confirmation."""

    entity_id: int
    fiscal_profile_id: int
    facts: _coverage.FiscalV1Facts
    treatments: tuple[_coverage.FiscalV1ResolvedTreatment, ...]
    snapshot: _fiscalized_confirmation.FiscalizedConfirmationSnapshot
    common_explanation: tuple[str, ...]
    limitations: tuple[str, ...]

    def __post_init__(self):
        for value, name in (
            (self.entity_id, "entity_id"),
            (self.fiscal_profile_id, "fiscal_profile_id"),
        ):
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if not isinstance(self.facts, _coverage.FiscalV1Facts):
            raise TypeError("facts must be FiscalV1Facts")
        if not isinstance(self.treatments, tuple) or not self.treatments:
            raise ValueError("treatments must be a non-empty tuple")
        if not all(
            isinstance(item, _coverage.FiscalV1ResolvedTreatment)
            for item in self.treatments
        ):
            raise TypeError("all treatments must be FiscalV1ResolvedTreatment")
        if not isinstance(
            self.snapshot,
            _fiscalized_confirmation.FiscalizedConfirmationSnapshot,
        ):
            raise TypeError("snapshot must be FiscalizedConfirmationSnapshot")
        if not self.common_explanation or not all(
            isinstance(item, str) and item.strip() for item in self.common_explanation
        ):
            raise ValueError("common_explanation must contain non-empty text")
        if not self.limitations or not all(
            isinstance(item, str) and item.strip() for item in self.limitations
        ):
            raise ValueError("limitations must contain non-empty text")


@dataclass(frozen=True)
class ConfirmedFiscalV1Operation:
    """Explicit consent to exactly one prepared V1 fiscalized snapshot."""

    prepared: PreparedFiscalV1Operation
    confirmed_proposal: _fiscalized_confirmation.ConfirmedFiscalizedProposal

    def __post_init__(self):
        if not isinstance(self.prepared, PreparedFiscalV1Operation):
            raise TypeError("prepared must be PreparedFiscalV1Operation")
        if not isinstance(
            self.confirmed_proposal,
            _fiscalized_confirmation.ConfirmedFiscalizedProposal,
        ):
            raise TypeError("confirmed_proposal must be ConfirmedFiscalizedProposal")
        if self.confirmed_proposal.snapshot != self.prepared.snapshot:
            raise ValueError("confirmation must preserve exactly the prepared snapshot")


@dataclass(frozen=True)
class FiscalV1OperationResult:
    entry_id: int
    audit_event_id: int

    def __post_init__(self):
        if type(self.entry_id) is not int or self.entry_id <= 0:
            raise ValueError("entry_id must be a positive integer")
        if type(self.audit_event_id) is not int or self.audit_event_id <= 0:
            raise ValueError("audit_event_id must be a positive integer")


def _entity_context(session, facts):
    entity = _entities.load_active_entity(session)
    if entity is None or entity.id is None:
        raise LookupError("active Entity is required for AQR-011 fiscal operations")
    if entity.legal_personality != facts.entity_legal_personality:
        raise _coverage.UnsupportedFiscalV1Case(
            f"{_coverage.UNSUPPORTED_MESSAGE} "
            "La personalidad de la entidad no coincide con la autoridad Entity."
        )
    profile = _entities.resolve_fiscal_profile(
        session,
        entity.id,
        facts.operation_date,
    )
    if profile.id is None:
        raise RuntimeError("resolved FiscalProfile has no persistent identity")
    if profile.jurisdiction != "MX":
        raise _coverage.UnsupportedFiscalV1Case(
            f"{_coverage.UNSUPPORTED_MESSAGE} "
            "El perfil fiscal vigente de la entidad no acredita jurisdicción MX."
        )
    return entity, profile


def _round_treatment(facts, treatment):
    fiscal_snapshot = _confirmation.create_resolved_fiscal_confirmation_snapshot(
        facts.fact,
        facts.operation_date,
        treatment.rule,
        treatment.base,
        treatment.exact_amount,
    )
    confirmed_fiscal = _confirmation.confirm_fiscal_snapshot(fiscal_snapshot)
    rounded = _rounding.round_confirmed_fiscal_amount(
        confirmed_fiscal,
        MXN_ROUNDING_POLICY,
    )
    monetary_snapshot = _money.create_fiscal_monetary_confirmation_snapshot(rounded)
    confirmed_money = _money.confirm_fiscal_monetary_snapshot(monetary_snapshot)
    declaration = _treatment.declare_fiscal_accounting_treatment(
        confirmed_money,
        treatment.fiscal_role,
        treatment.fiscal_side,
    )
    return _effect.build_fiscal_accounting_effect(declaration)


def _composition_inputs(facts):
    if facts.entity_role == "provider":
        if facts.fact.type != "sale" or facts.fact.payment_method != "cash":
            raise _coverage.UnsupportedFiscalV1Case(
                f"{_coverage.UNSUPPORTED_MESSAGE} "
                "El posting V1 de ventas fiscales está limitado a cobro inmediato en efectivo."
            )
        return "net_before_fiscal", "cash"

    if facts.fact.type in {"professional_services_expense", "freight_expense"}:
        if facts.fact.payment_method != "bank":
            raise _coverage.UnsupportedFiscalV1Case(
                f"{_coverage.UNSUPPORTED_MESSAGE} "
                "La erogación fiscal V1 soportada debe liquidarse por banco."
            )
        return "base_before_fiscal_settlement", "bank"

    raise _coverage.UnsupportedFiscalV1Case(
        f"{_coverage.UNSUPPORTED_MESSAGE} "
        "No existe composición contable V1 para este hecho fiscal."
    )


def _common_explanation(treatments):
    items = []
    for item in treatments:
        items.append(
            f"{item.treatment_key}: {item.explanation} "
            f"Base {item.base}; resultado exacto {item.exact_amount}; "
            f"fórmula {item.formula}; fuente {item.rule.source_ref}; "
            f"versión {item.rule_set_version}; vigencia desde "
            f"{item.rule.effective_from.isoformat()}."
        )
    return tuple(items)


def prepare_fiscal_v1_operation(session, facts):
    """Prepare one complete supported V1 fiscalized operation without writes."""
    if not isinstance(facts, _coverage.FiscalV1Facts):
        raise TypeError("facts must be FiscalV1Facts")
    entity, profile = _entity_context(session, facts)
    treatments = tuple(_coverage.resolve_fiscal_v1_treatments(session, facts))
    effects = tuple(_round_treatment(facts, item) for item in treatments)
    accounting = _economic.resolve_economic_fact_with_provenance(facts.fact)
    amount_basis, adjustment_role = _composition_inputs(facts)
    declaration = _composition.declare_fiscal_economic_composition(
        accounting,
        effects,
        amount_basis,
        adjustment_role,
    )
    fiscalized = _proposal.compose_fiscal_economic_accounting(declaration)

    roles = tuple(dict.fromkeys(line.account_role for line in fiscalized.lines))
    configured_bindings = _bindings.get_account_bindings(session, roles)
    resolved = _account_resolution.resolve_fiscalized_proposal_accounts(
        session,
        fiscalized,
        configured_bindings,
    )
    snapshot = _fiscalized_confirmation.create_fiscalized_confirmation_snapshot(resolved)

    return PreparedFiscalV1Operation(
        entity_id=entity.id,
        fiscal_profile_id=profile.id,
        facts=facts,
        treatments=treatments,
        snapshot=snapshot,
        common_explanation=_common_explanation(treatments),
        limitations=(
            "Cobertura fiscal limitada a mx-fiscal-v1.2026-09-10.",
            "El IVA de erogaciones se reconoce pendiente de acreditar; no se certifica acreditamiento ni deducibilidad.",
            "No se determina IVA o ISR mensual/anual ni se prepara una declaración fiscal.",
            "Los impuestos declarados por CFDI son evidencia y no seleccionan la regla jurídica.",
        ),
    )


def confirm_fiscal_v1_operation(prepared):
    """Record explicit in-memory consent to the exact prepared fiscalized truth."""
    if not isinstance(prepared, PreparedFiscalV1Operation):
        raise TypeError("prepared must be PreparedFiscalV1Operation")
    confirmed = _fiscalized_confirmation.confirm_fiscalized_snapshot(prepared.snapshot)
    return ConfirmedFiscalV1Operation(
        prepared=prepared,
        confirmed_proposal=confirmed,
    )


def _zero_policy(snapshot):
    zero_effects = tuple(
        item
        for item in snapshot.provenance.fiscal_effects
        if item.rounded_fiscal_amount == Decimal("0")
    )
    if not zero_effects:
        return "reject_zero_fiscal_line"
    if len(zero_effects) != 1:
        raise ValueError(
            "AQR-011 singular zero-line audit contract cannot omit multiple zero effects"
        )
    return "omit_confirmed_zero_fiscal_line"


def _audit_details(confirmed, entry_id, entity, profile):
    prepared = confirmed.prepared
    provenance_effects = prepared.snapshot.provenance.fiscal_effects
    if len(provenance_effects) != len(prepared.treatments):
        raise ValueError("prepared treatment count diverges from confirmed fiscal provenance")

    treatments = []
    for treatment, effect in zip(prepared.treatments, provenance_effects):
        if treatment.treatment_key != effect.rule_key:
            raise ValueError("prepared rule order diverges from confirmed fiscal provenance")
        treatments.append(
            {
                "rule_key": treatment.treatment_key,
                "rule_set_key": treatment.rule_set_key,
                "rule_set_version": treatment.rule_set_version,
                "calculation_kind": treatment.calculation_kind,
                "jurisdiction": treatment.rule.jurisdiction,
                "regime": treatment.rule.regime,
                "entity_type": treatment.rule.entity_type,
                "effective_from": treatment.rule.effective_from.isoformat(),
                "effective_to": (
                    None
                    if treatment.rule.effective_to is None
                    else treatment.rule.effective_to.isoformat()
                ),
                "source_ref": treatment.rule.source_ref,
                "base": str(treatment.base),
                "rule_value": str(treatment.rule.value),
                "unit": treatment.rule.unit,
                "formula": treatment.formula,
                "exact_amount": str(treatment.exact_amount),
                "rounding_policy_key": effect.rounding_policy_key,
                "rounding_quantizer": str(effect.rounding_quantizer),
                "rounding_mode": effect.rounding_mode,
                "rounding_source_ref": effect.rounding_source_ref,
                "rounded_amount": str(effect.rounded_fiscal_amount),
                "account_role": treatment.fiscal_role,
                "side": treatment.fiscal_side,
                "explanation": treatment.explanation,
            }
        )

    facts = prepared.facts
    return {
        "entry_id": entry_id,
        "coverage_version": _coverage.COVERAGE_VERSION,
        "consent": "explicit_confirmation",
        "entity": {
            "entity_id": entity.id,
            "legal_personality": entity.legal_personality,
            "fiscal_profile_id": profile.id,
            "jurisdiction": profile.jurisdiction,
            "fiscal_regime_code": profile.fiscal_regime_code,
        },
        "facts": {
            "type": facts.fact.type,
            "amount": str(facts.fact.amount),
            "payment_method": facts.fact.payment_method,
            "operation_date": facts.operation_date.isoformat(),
            "entity_role": facts.entity_role,
            "counterparty_legal_personality": facts.counterparty_legal_personality,
            "counterparty_fiscal_regime": facts.counterparty_fiscal_regime,
            "activity": facts.activity,
            "territory": facts.territory,
            "base": str(facts.base),
            "effectively_paid": facts.effectively_paid,
            "cfdi_transferred_vat": (
                None
                if facts.cfdi_transferred_vat is None
                else str(facts.cfdi_transferred_vat)
            ),
        },
        "treatments": treatments,
        "limitations": list(prepared.limitations),
    }


def execute_fiscal_v1_operation(confirmed):
    """Atomically persist one confirmed AQR-011 operation and all audit evidence."""
    if not isinstance(confirmed, ConfirmedFiscalV1Operation):
        raise TypeError("confirmed must be ConfirmedFiscalV1Operation")

    instruction = _posting.create_fiscalized_posting_instruction(
        confirmed.confirmed_proposal,
        _zero_policy(confirmed.prepared.snapshot),
    )

    session = None
    try:
        with _storage.get_session() as session:
            entity, profile = _entity_context(session, confirmed.prepared.facts)
            if entity.id != confirmed.prepared.entity_id or profile.id != confirmed.prepared.fiscal_profile_id:
                raise RuntimeError(
                    "Entity/FiscalProfile authority changed after fiscal preparation; prepare again"
                )
            entry_id = _persistence.stage_fiscalized_posting_with_audit(
                session,
                instruction,
                posting_date=confirmed.prepared.facts.operation_date,
                state="posted",
            )
            event = _audit_events.stage_audit_event(
                session,
                AuditEvent(
                    id=None,
                    entity_id=entity.id,
                    event_type="fiscal_v1_posted",
                    timestamp=datetime.now(timezone.utc),
                    details=_audit_details(
                        confirmed,
                        entry_id,
                        entity,
                        profile,
                    ),
                ),
            )
            if event.id is None:
                raise RuntimeError("AQR-011 AuditEvent did not receive an identity")
            session.commit()
            return FiscalV1OperationResult(
                entry_id=entry_id,
                audit_event_id=event.id,
            )
    except Exception:
        if session is not None:
            try:
                session.rollback()
            except Exception:
                pass
        raise


def load_fiscal_v1_operation(session, entity_id, entry_id):
    """Reconstruct professional AQR-011 truth from persisted ledger/audit authorities."""
    if type(entity_id) is not int or entity_id <= 0:
        raise ValueError("entity_id must be a positive integer")
    if type(entry_id) is not int or entry_id <= 0:
        raise ValueError("entry_id must be a positive integer")

    entry = session.get(_models.JournalEntry, entry_id)
    if entry is None:
        raise LookupError("JournalEntry not found")
    events = tuple(
        event
        for event in _audit_events.list_audit_events(session, entity_id)
        if event.event_type == "fiscal_v1_posted"
        and event.details.get("entry_id") == entry_id
    )
    if not events:
        raise LookupError("AQR-011 AuditEvent not found for JournalEntry")
    if len(events) != 1:
        raise RuntimeError("multiple AQR-011 AuditEvents found for JournalEntry")
    event = events[0]
    fiscal_audit = _audit_read.load_fiscal_posting_audit_snapshot(session, entry_id)

    treatment_details = event.details.get("treatments")
    if not isinstance(treatment_details, list):
        raise ValueError("persisted AQR-011 treatments must be a list")
    effects = fiscal_audit.provenance.fiscal_effects
    if len(treatment_details) != len(effects):
        raise ValueError("AQR-011 AuditEvent diverges from fiscal posting audit cardinality")
    for detail, effect in zip(treatment_details, effects):
        if detail.get("rule_key") != effect.rule_key:
            raise ValueError("AQR-011 AuditEvent rule order diverges from fiscal posting audit")
        if Decimal(detail.get("rounded_amount")) != effect.rounded_fiscal_amount:
            raise ValueError("AQR-011 AuditEvent amount diverges from fiscal posting audit")

    lines = session.exec(
        select(_models.JournalLine)
        .where(_models.JournalLine.entry_id == entry_id)
        .order_by(_models.JournalLine.id)
    ).all()
    return {
        "entry_id": entry.id,
        "entry_state": entry.state,
        "posting_date": entry.date.date().isoformat(),
        "concept": entry.concept,
        "coverage_version": event.details.get("coverage_version"),
        "facts": event.details.get("facts"),
        "entity": event.details.get("entity"),
        "treatments": treatment_details,
        "accounting_lines": [
            {
                "journal_line_id": line.id,
                "account_id": line.account_id,
                "account_code": line.account_code,
                "debit": line.debit,
                "credit": line.credit,
                "description": line.description,
            }
            for line in lines
        ],
        "fiscal_audit": {
            "amount_basis": fiscal_audit.provenance.amount_basis,
            "adjustment_role": fiscal_audit.provenance.adjustment_role,
            "zero_fiscal_line_policy": fiscal_audit.zero_fiscal_line_policy,
            "effect_count": len(effects),
        },
        "audit_event_id": event.id,
        "limitations": event.details.get("limitations"),
    }


__all__ = [
    "MXN_ROUNDING_POLICY",
    "PreparedFiscalV1Operation",
    "ConfirmedFiscalV1Operation",
    "FiscalV1OperationResult",
    "prepare_fiscal_v1_operation",
    "confirm_fiscal_v1_operation",
    "execute_fiscal_v1_operation",
    "load_fiscal_v1_operation",
]
