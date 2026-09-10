"""AQR-011 application-domain composition over the existing fiscalized pipeline.

The module owns no tax rates, journal persistence, account codes or UI rules. It
composes factual V1 applicability with the already-existing fiscal confirmation,
rounding, accounting-effect, fiscalized proposal and account-resolution
authorities. Preparation is read-only; explicit consent is a separate step.
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from . import account_bindings as _bindings
from . import economic_fact_accounting_provenance as _economic
from . import fiscal_accounting_effect as _effect
from . import fiscal_accounting_treatment as _treatment
from . import fiscal_confirmation as _confirmation
from . import fiscal_economic_composition as _composition
from . import fiscal_monetary_confirmation as _money
from . import fiscal_rounding as _rounding
from . import fiscal_v1_coverage as _coverage
from . import fiscalized_account_resolution as _account_resolution
from . import fiscalized_accounting_proposal as _proposal
from . import fiscalized_confirmation as _fiscalized_confirmation


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

    facts: _coverage.FiscalV1Facts
    treatments: tuple[_coverage.FiscalV1ResolvedTreatment, ...]
    snapshot: _fiscalized_confirmation.FiscalizedConfirmationSnapshot
    common_explanation: tuple[str, ...]
    limitations: tuple[str, ...]

    def __post_init__(self):
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


__all__ = [
    "MXN_ROUNDING_POLICY",
    "PreparedFiscalV1Operation",
    "ConfirmedFiscalV1Operation",
    "prepare_fiscal_v1_operation",
    "confirm_fiscal_v1_operation",
]
