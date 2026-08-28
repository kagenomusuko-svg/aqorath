"""Structured deterministic explanation projected from existing accounting provenance."""

from dataclasses import dataclass
from decimal import Decimal

from . import economic_fact_accounting_provenance as _accounting_provenance


def _require_text(value, field_name):
    if type(value) is not str:
        raise TypeError(f"{field_name} must be str")
    if not value or value.strip() != value:
        raise ValueError(f"{field_name} must be nonblank without surrounding whitespace")
    return value


def _require_positive_decimal(value, field_name):
    if type(value) is not Decimal:
        raise TypeError(f"{field_name} must be Decimal")
    if not value.is_finite() or value <= Decimal("0"):
        raise ValueError(f"{field_name} must be finite and positive")
    return value


@dataclass(frozen=True)
class ExplanationEffect:
    """One immutable semantic accounting effect presented by an explanation."""

    account_role: str
    side: str
    amount: Decimal

    def __post_init__(self):
        _require_text(self.account_role, "account_role")
        if self.side not in {"debit", "credit"}:
            raise ValueError("side must be exactly 'debit' or 'credit'")
        _require_positive_decimal(self.amount, "amount")


@dataclass(frozen=True)
class ExplanationData:
    """Immutable structured presentation truth derived from an accounting resolution."""

    fact_type: str
    payment_method: str
    amount: Decimal
    rule_key: str
    effects: tuple[ExplanationEffect, ...]
    concepts: tuple[str, ...]
    professional_summary: str

    def __post_init__(self):
        _require_text(self.fact_type, "fact_type")
        _require_text(self.payment_method, "payment_method")
        _require_positive_decimal(self.amount, "amount")
        _require_text(self.rule_key, "rule_key")
        _require_text(self.professional_summary, "professional_summary")

        if type(self.effects) is not tuple:
            raise TypeError("effects must be tuple")
        if not self.effects:
            raise ValueError("effects must not be empty")
        if any(not isinstance(effect, ExplanationEffect) for effect in self.effects):
            raise TypeError("effects must contain only ExplanationEffect values")

        if type(self.concepts) is not tuple:
            raise TypeError("concepts must be tuple")
        if not self.concepts:
            raise ValueError("concepts must not be empty")
        for concept in self.concepts:
            _require_text(concept, "concept")
        if len(set(self.concepts)) != len(self.concepts):
            raise ValueError("concepts must be unique")


def build_economic_fact_explanation(accounting_resolution):
    """Project one existing economic-fact accounting resolution into value data."""
    if not isinstance(
        accounting_resolution,
        _accounting_provenance.EconomicFactAccountingResolution,
    ):
        raise TypeError(
            "accounting_resolution must be EconomicFactAccountingResolution"
        )

    fact = accounting_resolution.fact
    proposal = accounting_resolution.proposal
    effects = tuple(
        ExplanationEffect(
            account_role=line.account_role,
            side=line.side,
            amount=line.amount,
        )
        for line in proposal.lines
    )

    return ExplanationData(
        fact_type=fact.type,
        payment_method=fact.payment_method,
        amount=fact.amount,
        rule_key=f"economic_fact:{fact.type}:{fact.payment_method}",
        effects=effects,
        concepts=("economic_fact", "double_entry"),
        professional_summary=proposal.explanation,
    )
