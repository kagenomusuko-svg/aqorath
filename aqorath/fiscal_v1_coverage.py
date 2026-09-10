"""AQR-011 factual applicability authority for the declared Mexican V1 coverage.

This module is deliberately upstream of the existing fiscal calculation,
confirmation, composition and posting authorities.  Common-surface callers
provide recognizable business facts; they never provide ``rule_key`` or a tax
rate.  The module selects only treatments declared by
``docs/AQR_011_FISCAL_COVERAGE_V1.md`` and resolves their already-versioned rule
records for the operation date.

CFDI values are documentary evidence only.  They can be contrasted with a
supported calculation after applicability has been established, but they never
select a treatment.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext
from typing import Optional, Tuple

from . import fiscal_calculation as _calculation
from . import fiscal_rule_data_mx as _data
from . import fiscal_rules as _rules
from .economic_facts import EconomicFact


COVERAGE_VERSION = "mx-fiscal-v1.2026-09-10"
COVERAGE_EFFECTIVE_FROM = date(2026, 1, 1)
COVERAGE_REVIEWED_THROUGH = date(2026, 9, 10)
UNSUPPORTED_MESSAGE = "Aqorath no tiene una regla fiscal V1 declarada para este caso."

_ACTIVITY_ORDINARY_TAXABLE_SALE = "ordinary_taxable_sale"
_ACTIVITY_OWN_EDITED_PUBLICATION_SALE = "own_edited_publication_sale"
_ACTIVITY_PROFESSIONAL_SERVICE = "professional_service"
_ACTIVITY_LAND_FREIGHT_GOODS = "land_freight_goods"

_ALLOWED_ACTIVITIES = frozenset(
    {
        _ACTIVITY_ORDINARY_TAXABLE_SALE,
        _ACTIVITY_OWN_EDITED_PUBLICATION_SALE,
        _ACTIVITY_PROFESSIONAL_SERVICE,
        _ACTIVITY_LAND_FREIGHT_GOODS,
    }
)
_ALLOWED_ROLES = frozenset({"provider", "recipient"})
_ALLOWED_PERSONALITIES = frozenset({"persona_fisica", "persona_moral"})


class UnsupportedFiscalV1Case(ValueError):
    """Facts do not establish one of the explicitly reviewed V1 treatments."""


class FiscalV1EvidenceConflict(ValueError):
    """Supported fiscal calculation contradicts supplied documentary evidence."""


def _unsupported(detail):
    raise UnsupportedFiscalV1Case(f"{UNSUPPORTED_MESSAGE} {detail}")


def _require_decimal(value, field_name, *, positive=False):
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be Decimal")
    if not value.is_finite():
        raise ValueError(f"{field_name} must be finite")
    if positive and value <= Decimal("0"):
        raise ValueError(f"{field_name} must be greater than zero")
    if not positive and value < Decimal("0"):
        raise ValueError(f"{field_name} must not be negative")


@dataclass(frozen=True)
class FiscalV1Facts:
    """Recognizable facts required to decide the limited AQR-011 coverage.

    ``entity_role`` is the active Entity's role in the taxable act, not its
    documentary issuer/receiver position in a CFDI.
    """

    fact: EconomicFact
    operation_date: date
    entity_role: str
    entity_legal_personality: str
    counterparty_legal_personality: Optional[str]
    counterparty_fiscal_regime: Optional[str]
    activity: str
    territory: str
    base: Decimal
    effectively_paid: bool
    cfdi_transferred_vat: Optional[Decimal] = None

    def __post_init__(self):
        if not isinstance(self.fact, EconomicFact):
            raise TypeError("fact must be EconomicFact")
        if type(self.operation_date) is not date:
            raise TypeError("operation_date must be datetime.date")
        if self.entity_role not in _ALLOWED_ROLES:
            raise ValueError("entity_role must be 'provider' or 'recipient'")
        if self.entity_legal_personality not in _ALLOWED_PERSONALITIES:
            raise ValueError("entity_legal_personality must be persona_fisica or persona_moral")
        if (
            self.counterparty_legal_personality is not None
            and self.counterparty_legal_personality not in _ALLOWED_PERSONALITIES
        ):
            raise ValueError(
                "counterparty_legal_personality must be persona_fisica, persona_moral or None"
            )
        if self.activity not in _ALLOWED_ACTIVITIES:
            _unsupported("La naturaleza de la operación no está dentro de la matriz AQR-011.")
        if self.territory != "MX":
            _unsupported("La cobertura V1 sólo declara estos tratamientos para territorio MX.")
        if type(self.effectively_paid) is not bool:
            raise TypeError("effectively_paid must be bool")
        _require_decimal(self.base, "base", positive=True)
        if self.cfdi_transferred_vat is not None:
            _require_decimal(self.cfdi_transferred_vat, "cfdi_transferred_vat")


@dataclass(frozen=True)
class FiscalV1ResolvedTreatment:
    coverage_version: str
    treatment_key: str
    calculation_kind: str
    rule: _rules.ResolvedFiscalRule
    base: Decimal
    exact_amount: Decimal
    formula: str
    fiscal_role: str
    fiscal_side: str
    explanation: str

    def __post_init__(self):
        if self.coverage_version != COVERAGE_VERSION:
            raise ValueError("unexpected fiscal coverage version")
        if self.calculation_kind not in {"rate", "fraction"}:
            raise ValueError("calculation_kind must be rate or fraction")
        _require_decimal(self.base, "base")
        _require_decimal(self.exact_amount, "exact_amount")
        if self.fiscal_side not in {"debit", "credit"}:
            raise ValueError("fiscal_side must be debit or credit")
        for name in ("treatment_key", "formula", "fiscal_role", "explanation"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty text")


def _require_coverage_date(operation_date):
    if not (COVERAGE_EFFECTIVE_FROM <= operation_date <= COVERAGE_REVIEWED_THROUGH):
        _unsupported(
            "La fecha está fuera de la ventana normativa revisada "
            f"{COVERAGE_EFFECTIVE_FROM.isoformat()}..{COVERAGE_REVIEWED_THROUGH.isoformat()}."
        )


def _resolved_rate(session, rule_key, context, operation_date, base, role, side, explanation):
    rule = _rules.resolve_fiscal_rule(session, rule_key, operation_date, context)
    calculation = _calculation.calculate_fiscal_rate_amount(base, rule)
    return FiscalV1ResolvedTreatment(
        coverage_version=COVERAGE_VERSION,
        treatment_key=rule_key,
        calculation_kind="rate",
        rule=rule,
        base=base,
        exact_amount=calculation.amount,
        formula=f"base × {rule.value}",
        fiscal_role=role,
        fiscal_side=side,
        explanation=explanation,
    )


def _resolved_two_thirds(session, operation_date, transferred_vat):
    rule_key = "iva.professional_services_retention_fraction"
    rule = _rules.resolve_fiscal_rule(
        session,
        rule_key,
        operation_date,
        _data.MX_GENERAL_PERSONA_FISICA_PROFESSIONAL_IVA_RETENTION.context,
    )
    if rule.unit != "fraction_2_3_of_transferred_vat" or rule.value != Decimal("2"):
        raise ValueError("authoritative two-thirds VAT rule is malformed")
    # Decimal is the money authority.  The legal fraction remains represented by
    # numerator/denominator semantics in the rule unit instead of a truncated
    # repeating decimal rate.  Extra precision keeps the pre-rounding amount
    # deterministic until FiscalRoundingPolicy applies the monetary quantizer.
    with localcontext() as context:
        context.prec = 50
        amount = transferred_vat * rule.value / Decimal("3")
    return FiscalV1ResolvedTreatment(
        coverage_version=COVERAGE_VERSION,
        treatment_key=rule_key,
        calculation_kind="fraction",
        rule=rule,
        base=transferred_vat,
        exact_amount=amount,
        formula="2/3 × IVA trasladado y efectivamente pagado",
        fiscal_role="vat_withholding_payable",
        fiscal_side="credit",
        explanation=(
            "Retención de IVA: la entidad persona moral recibió servicios personales "
            "independientes de una persona física y retiene dos terceras partes del "
            "IVA trasladado efectivamente pagado conforme a LIVA 1-A II a y RLIVA 3 I a."
        ),
    )


def _general_iva(session, facts, *, input_tax):
    return _resolved_rate(
        session,
        "iva.general_rate",
        _data.MX_GENERAL_COMMERCIAL_IVA.context,
        facts.operation_date,
        facts.base,
        "tax_input" if input_tax else "tax_payable",
        "debit" if input_tax else "credit",
        (
            "IVA general V1: acto gravado identificado por hechos, en territorio MX, "
            "con contraprestación efectivamente cobrada/pagada; la tasa proviene de "
            "la regla versionada, no del CFDI."
        ),
    )


def _validate_documentary_vat(facts, expected):
    documentary = facts.cfdi_transferred_vat
    if documentary is None:
        return
    if documentary.as_tuple() != expected.as_tuple():
        raise FiscalV1EvidenceConflict(
            "DETECT → EXPLAIN → STOP: el IVA trasladado declarado por el CFDI "
            f"({documentary}) diverge del cálculo fiscal V1 soportado ({expected})."
        )


def _require_paid(facts):
    if not facts.effectively_paid:
        _unsupported(
            "Este vertical V1 sólo está declarado para el momento de cobro/pago efectivo."
        )


def _resolve_provider_sale(session, facts):
    if facts.fact.type != "sale":
        _unsupported("El rol proveedor V1 requiere un hecho económico de venta.")
    _require_paid(facts)

    if facts.activity == _ACTIVITY_ORDINARY_TAXABLE_SALE:
        iva = _general_iva(session, facts, input_tax=False)
        _validate_documentary_vat(facts, iva.exact_amount)
        return (iva,)

    if facts.activity == _ACTIVITY_OWN_EDITED_PUBLICATION_SALE:
        zero = _resolved_rate(
            session,
            "iva.zero_rate",
            _data.MX_GENERAL_COMMERCIAL_IVA_ZERO.context,
            facts.operation_date,
            facts.base,
            "tax_payable",
            "credit",
            (
                "IVA tasa 0% V1: enajenación de libro, periódico o revista editado por "
                "el propio contribuyente, subcategoría limitada del artículo 2-A I i LIVA."
            ),
        )
        if zero.exact_amount != Decimal("0.00"):
            raise ValueError("zero-rate rule must calculate exactly zero")
        _validate_documentary_vat(facts, Decimal("0"))
        return (zero,)

    _unsupported("La actividad indicada no es una venta V1 soportada para el proveedor.")


def _require_pm_recipient_with_counterparty(facts):
    if facts.entity_legal_personality != "persona_moral":
        _unsupported("Las retenciones V1 declaradas requieren receptor persona moral.")
    if facts.counterparty_legal_personality is None:
        _unsupported("Falta acreditar la personalidad jurídica/fiscal de la contraparte.")


def _resolve_professional_service(session, facts):
    if facts.fact.type not in {"professional_services_expense", "professional_services_expense_incurred"}:
        _unsupported("El hecho económico no identifica un servicio profesional V1.")
    _require_paid(facts)
    _require_pm_recipient_with_counterparty(facts)
    if facts.counterparty_legal_personality != "persona_fisica":
        _unsupported("El prestador de la vertical de honorarios V1 debe ser persona física.")
    if facts.counterparty_fiscal_regime not in {"general", "resico"}:
        _unsupported(
            "Falta acreditar si la persona física prestadora está en el supuesto general o RESICO."
        )

    iva = _general_iva(session, facts, input_tax=True)
    _validate_documentary_vat(facts, iva.exact_amount)

    if facts.counterparty_fiscal_regime == "resico":
        isr = _resolved_rate(
            session,
            "isr.resico_retention_rate",
            _data.MX_RESICO_PERSONA_FISICA_ISR_RETENTION.context,
            facts.operation_date,
            facts.base,
            "isr_withholding_payable",
            "credit",
            (
                "Retención ISR RESICO V1: persona física acreditada en el supuesto del "
                "artículo 113-E presta actividad profesional a persona moral; se aplica "
                "únicamente la retención del artículo 113-J, no el ISR integral del régimen."
            ),
        )
    else:
        isr = _resolved_rate(
            session,
            "isr.professional_services_retention_rate",
            _data.MX_GENERAL_PERSONA_FISICA_PROFESSIONAL_ISR_RETENTION.context,
            facts.operation_date,
            facts.base,
            "isr_withholding_payable",
            "credit",
            (
                "Retención ISR por servicios profesionales V1: persona física presta un "
                "servicio profesional a persona moral; 10% sobre el pago conforme a LISR 106."
            ),
        )

    vat_retention = _resolved_two_thirds(session, facts.operation_date, iva.exact_amount)
    return (iva, isr, vat_retention)


def _resolve_freight(session, facts):
    if facts.fact.type not in {"freight_expense", "freight_expense_incurred"}:
        _unsupported("El hecho económico no identifica autotransporte terrestre de bienes.")
    _require_paid(facts)
    _require_pm_recipient_with_counterparty(facts)
    if facts.counterparty_legal_personality not in {"persona_fisica", "persona_moral"}:
        _unsupported("El prestador de autotransporte V1 debe ser PF o PM acreditada.")

    iva = _general_iva(session, facts, input_tax=True)
    _validate_documentary_vat(facts, iva.exact_amount)
    freight_retention = _resolved_rate(
        session,
        "iva.freight_transport_retention_rate",
        _data.MX_GENERAL_PERSONA_MORAL_IVA_FREIGHT_RETENTION.context,
        facts.operation_date,
        facts.base,
        "vat_withholding_payable",
        "credit",
        (
            "Retención IVA autotransporte V1: persona moral recibe autotransporte terrestre "
            "de bienes y retiene 4% del valor de la contraprestación efectivamente pagada "
            "conforme a LIVA 1-A II c y RLIVA 3 II."
        ),
    )

    effects = [iva, freight_retention]
    if (
        facts.counterparty_legal_personality == "persona_fisica"
        and facts.counterparty_fiscal_regime == "resico"
    ):
        effects.append(
            _resolved_rate(
                session,
                "isr.resico_retention_rate",
                _data.MX_RESICO_PERSONA_FISICA_ISR_RETENTION.context,
                facts.operation_date,
                facts.base,
                "isr_withholding_payable",
                "credit",
                (
                    "Retención ISR RESICO V1 concurrente: prestador persona física RESICO "
                    "realiza actividad empresarial de autotransporte a persona moral; se "
                    "modela sólo la retención del artículo 113-J."
                ),
            )
        )
    return tuple(effects)


def resolve_fiscal_v1_treatments(session, facts):
    """Resolve all and only supported V1 fiscal effects from recognizable facts.

    No rule key, rate, account code or debit/credit instruction is accepted from
    the caller.  Unsupported or incomplete contexts fail closed.
    """
    if not isinstance(facts, FiscalV1Facts):
        raise TypeError("facts must be FiscalV1Facts")
    _require_coverage_date(facts.operation_date)

    if facts.entity_role == "provider":
        return _resolve_provider_sale(session, facts)

    if facts.activity == _ACTIVITY_PROFESSIONAL_SERVICE:
        return _resolve_professional_service(session, facts)
    if facts.activity == _ACTIVITY_LAND_FREIGHT_GOODS:
        return _resolve_freight(session, facts)

    # Documentary IVA alone deliberately cannot turn an unknown recipient-side
    # transaction into general-rate support.
    _unsupported("El caso del receptor no acredita un tratamiento V1 por hechos.")


__all__ = [
    "COVERAGE_VERSION",
    "COVERAGE_EFFECTIVE_FROM",
    "COVERAGE_REVIEWED_THROUGH",
    "UNSUPPORTED_MESSAGE",
    "UnsupportedFiscalV1Case",
    "FiscalV1EvidenceConflict",
    "FiscalV1Facts",
    "FiscalV1ResolvedTreatment",
    "resolve_fiscal_v1_treatments",
]
