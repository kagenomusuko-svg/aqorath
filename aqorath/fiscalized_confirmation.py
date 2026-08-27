"""Fiscalized informed confirmation boundary.

Freezes one fully resolved fiscalized accounting proposal into value-only content
for informed confirmation. The snapshot preserves both concrete accounting lines
and the fiscal/composition provenance that produced them. No rule resolution,
rounding, account lookup, persistence, or posting occurs here.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional, Tuple

from . import fiscalized_account_resolution as _resolution


@dataclass(frozen=True)
class FiscalizedConfirmationLine:
    account_role: str
    account_id: int
    account_code: str
    account_name: str
    side: str
    amount: Decimal

    def __post_init__(self):
        if not isinstance(self.account_role, str) or not self.account_role.strip():
            raise ValueError("account_role must be non-empty text")
        if not isinstance(self.account_id, int) or isinstance(self.account_id, bool):
            raise TypeError("account_id must be an integer")
        if not isinstance(self.account_code, str) or not self.account_code.strip():
            raise ValueError("account_code must be non-empty text")
        if not isinstance(self.account_name, str) or not self.account_name.strip():
            raise ValueError("account_name must be non-empty text")
        if self.side not in ("debit", "credit"):
            raise ValueError("side must be 'debit' or 'credit'")
        if not isinstance(self.amount, Decimal):
            raise TypeError("amount must be Decimal")
        if not self.amount.is_finite() or self.amount < Decimal("0"):
            raise ValueError("amount must be finite and non-negative")


@dataclass(frozen=True)
class FiscalizedConfirmationProvenance:
    fact_type: str
    fact_amount: Decimal
    payment_method: str
    effective_date: date
    jurisdiction: str
    regime: str
    entity_type: str
    rule_key: str
    base: Decimal
    rate: Decimal
    unit: str
    rule_effective_from: date
    rule_effective_to: Optional[date]
    rule_source_ref: str
    exact_fiscal_amount: Decimal
    rounding_policy_key: str
    rounding_quantizer: Decimal
    rounding_mode: str
    rounding_source_ref: str
    rounded_fiscal_amount: Decimal
    amount_basis: str
    adjustment_role: str
    fiscal_role: str
    fiscal_side: str

    def __post_init__(self):
        for name in (
            "fact_type",
            "payment_method",
            "jurisdiction",
            "regime",
            "entity_type",
            "rule_key",
            "unit",
            "rule_source_ref",
            "rounding_policy_key",
            "rounding_mode",
            "rounding_source_ref",
            "adjustment_role",
            "fiscal_role",
        ):
            value = getattr(self, name)
            if not isinstance(value, str):
                raise TypeError(f"{name} must be a string")
            if not value.strip():
                raise ValueError(f"{name} must not be empty")

        for name in (
            "fact_amount",
            "base",
            "rate",
            "exact_fiscal_amount",
            "rounding_quantizer",
            "rounded_fiscal_amount",
        ):
            value = getattr(self, name)
            if not isinstance(value, Decimal):
                raise TypeError(f"{name} must be Decimal")
            if not value.is_finite():
                raise ValueError(f"{name} must be finite")

        if self.fact_amount <= Decimal("0"):
            raise ValueError("fact_amount must be greater than zero")
        if self.base < Decimal("0"):
            raise ValueError("base must not be negative")
        if self.rate < Decimal("0"):
            raise ValueError("rate must not be negative")
        if self.exact_fiscal_amount < Decimal("0"):
            raise ValueError("exact_fiscal_amount must not be negative")
        if self.rounding_quantizer <= Decimal("0"):
            raise ValueError("rounding_quantizer must be greater than zero")
        if self.rounded_fiscal_amount < Decimal("0"):
            raise ValueError("rounded_fiscal_amount must not be negative")
        if not isinstance(self.effective_date, date):
            raise TypeError("effective_date must be a date")
        if not isinstance(self.rule_effective_from, date):
            raise TypeError("rule_effective_from must be a date")
        if self.rule_effective_to is not None and not isinstance(self.rule_effective_to, date):
            raise TypeError("rule_effective_to must be a date or None")
        if self.amount_basis not in ("net_before_fiscal", "gross_including_fiscal"):
            raise ValueError("invalid amount_basis")
        if self.fiscal_side not in ("debit", "credit"):
            raise ValueError("fiscal_side must be 'debit' or 'credit'")


@dataclass(frozen=True)
class FiscalizedConfirmationSnapshot:
    lines: Tuple[FiscalizedConfirmationLine, ...]
    explanation: str
    provenance: FiscalizedConfirmationProvenance

    def __post_init__(self):
        if not isinstance(self.lines, tuple) or not self.lines:
            raise ValueError("lines must be a non-empty tuple")
        if not all(isinstance(line, FiscalizedConfirmationLine) for line in self.lines):
            raise TypeError("all lines must be FiscalizedConfirmationLine")
        if not isinstance(self.explanation, str) or not self.explanation.strip():
            raise ValueError("explanation must be non-empty text")
        if not isinstance(self.provenance, FiscalizedConfirmationProvenance):
            raise TypeError("provenance must be FiscalizedConfirmationProvenance")

        total_debit = sum(
            (line.amount for line in self.lines if line.side == "debit"),
            Decimal("0"),
        )
        total_credit = sum(
            (line.amount for line in self.lines if line.side == "credit"),
            Decimal("0"),
        )
        if total_debit != total_credit:
            raise ValueError(
                "fiscalized confirmation snapshot must be balanced: "
                f"debit={total_debit} credit={total_credit}"
            )

        fiscal_line = self.lines[-1]
        if fiscal_line.account_role != self.provenance.fiscal_role:
            raise ValueError("final fiscal line role must match provenance")
        if fiscal_line.side != self.provenance.fiscal_side:
            raise ValueError("final fiscal line side must match provenance")
        if fiscal_line.amount.as_tuple() != self.provenance.rounded_fiscal_amount.as_tuple():
            raise ValueError("final fiscal line amount must match confirmed rounded fiscal amount")


@dataclass(frozen=True)
class ConfirmedFiscalizedProposal:
    snapshot: FiscalizedConfirmationSnapshot

    def __post_init__(self):
        if not isinstance(self.snapshot, FiscalizedConfirmationSnapshot):
            raise TypeError("snapshot must be FiscalizedConfirmationSnapshot")


def create_fiscalized_confirmation_snapshot(resolved_proposal):
    """Copy one resolved fiscalized proposal and its provenance into immutable values."""
    if not isinstance(
        resolved_proposal,
        _resolution.ResolvedFiscalizedAccountingProposal,
    ):
        raise TypeError(
            "create_fiscalized_confirmation_snapshot requires "
            "ResolvedFiscalizedAccountingProposal"
        )

    fiscalized = resolved_proposal.fiscalized_proposal
    composition = fiscalized.declaration
    effect = composition.fiscal_effect
    monetary_snapshot = effect.declaration.confirmed_monetary_amount.snapshot

    lines = tuple(
        FiscalizedConfirmationLine(
            account_role=line.account_role,
            account_id=line.account_id,
            account_code=line.account_code,
            account_name=line.account_name,
            side=line.side,
            amount=line.amount,
        )
        for line in resolved_proposal.lines
    )

    provenance = FiscalizedConfirmationProvenance(
        fact_type=monetary_snapshot.fact_type,
        fact_amount=monetary_snapshot.fact_amount,
        payment_method=monetary_snapshot.payment_method,
        effective_date=monetary_snapshot.effective_date,
        jurisdiction=monetary_snapshot.jurisdiction,
        regime=monetary_snapshot.regime,
        entity_type=monetary_snapshot.entity_type,
        rule_key=monetary_snapshot.rule_key,
        base=monetary_snapshot.base,
        rate=monetary_snapshot.rate,
        unit=monetary_snapshot.unit,
        rule_effective_from=monetary_snapshot.rule_effective_from,
        rule_effective_to=monetary_snapshot.rule_effective_to,
        rule_source_ref=monetary_snapshot.rule_source_ref,
        exact_fiscal_amount=monetary_snapshot.exact_amount,
        rounding_policy_key=monetary_snapshot.rounding_policy_key,
        rounding_quantizer=monetary_snapshot.rounding_quantizer,
        rounding_mode=monetary_snapshot.rounding_mode,
        rounding_source_ref=monetary_snapshot.rounding_source_ref,
        rounded_fiscal_amount=monetary_snapshot.rounded_amount,
        amount_basis=composition.amount_basis,
        adjustment_role=composition.adjustment_role,
        fiscal_role=effect.line.account_role,
        fiscal_side=effect.line.side,
    )

    return FiscalizedConfirmationSnapshot(
        lines=lines,
        explanation=resolved_proposal.explanation,
        provenance=provenance,
    )


def confirm_fiscalized_snapshot(snapshot):
    """Confirm exactly one previously prepared fiscalized confirmation snapshot."""
    if not isinstance(snapshot, FiscalizedConfirmationSnapshot):
        raise TypeError("confirm_fiscalized_snapshot requires FiscalizedConfirmationSnapshot")
    return ConfirmedFiscalizedProposal(snapshot=snapshot)


__all__ = [
    "FiscalizedConfirmationLine",
    "FiscalizedConfirmationProvenance",
    "FiscalizedConfirmationSnapshot",
    "ConfirmedFiscalizedProposal",
    "create_fiscalized_confirmation_snapshot",
    "confirm_fiscalized_snapshot",
]
