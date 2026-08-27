"""Immutable fiscal posting audit metadata — Phase 5AD.2 / 5AK.2.

Builds a value-only audit snapshot from one already validated
FiscalizedPostingInstruction. This module is intentionally non-executable: it
owns no accounting lines, account resolution, persistence, session, or posting
logic.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from . import fiscalized_confirmation as _confirmation
from . import fiscalized_posting as _posting


_ALLOWED_ZERO_POLICIES = (
    "reject_zero_fiscal_line",
    "omit_confirmed_zero_fiscal_line",
)


@dataclass(frozen=True)
class FiscalPostingAuditOmittedLine:
    """Value-only copy of one explicitly omitted confirmed zero fiscal line."""

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


def _same_decimal(left, right):
    return isinstance(left, Decimal) and isinstance(right, Decimal) and (
        left.as_tuple() == right.as_tuple()
    )


def _copy_effect(source):
    return _confirmation.FiscalizedConfirmationEffectProvenance(
        rule_key=source.rule_key,
        base=source.base,
        rate=source.rate,
        unit=source.unit,
        rule_effective_from=source.rule_effective_from,
        rule_effective_to=source.rule_effective_to,
        rule_source_ref=source.rule_source_ref,
        exact_fiscal_amount=source.exact_fiscal_amount,
        rounding_policy_key=source.rounding_policy_key,
        rounding_quantizer=source.rounding_quantizer,
        rounding_mode=source.rounding_mode,
        rounding_source_ref=source.rounding_source_ref,
        rounded_fiscal_amount=source.rounded_fiscal_amount,
        fiscal_role=source.fiscal_role,
        fiscal_side=source.fiscal_side,
    )


def _copy_provenance(source):
    return _confirmation.FiscalizedConfirmationProvenance(
        fact_type=source.fact_type,
        fact_amount=source.fact_amount,
        payment_method=source.payment_method,
        effective_date=source.effective_date,
        jurisdiction=source.jurisdiction,
        regime=source.regime,
        entity_type=source.entity_type,
        rule_key=source.rule_key,
        base=source.base,
        rate=source.rate,
        unit=source.unit,
        rule_effective_from=source.rule_effective_from,
        rule_effective_to=source.rule_effective_to,
        rule_source_ref=source.rule_source_ref,
        exact_fiscal_amount=source.exact_fiscal_amount,
        rounding_policy_key=source.rounding_policy_key,
        rounding_quantizer=source.rounding_quantizer,
        rounding_mode=source.rounding_mode,
        rounding_source_ref=source.rounding_source_ref,
        rounded_fiscal_amount=source.rounded_fiscal_amount,
        amount_basis=source.amount_basis,
        adjustment_role=source.adjustment_role,
        fiscal_role=source.fiscal_role,
        fiscal_side=source.fiscal_side,
        additional_fiscal_effects=tuple(
            _copy_effect(effect)
            for effect in source.additional_fiscal_effects
        ),
    )


def _copy_omitted_line(source):
    if source is None:
        return None
    return FiscalPostingAuditOmittedLine(
        account_role=source.account_role,
        account_id=source.account_id,
        account_code=source.account_code,
        account_name=source.account_name,
        side=source.side,
        amount=source.amount,
    )


@dataclass(frozen=True)
class FiscalPostingAuditSnapshot:
    """Non-executable immutable metadata associated with one fiscalized posting."""

    description: str
    provenance: _confirmation.FiscalizedConfirmationProvenance
    zero_fiscal_line_policy: str
    omitted_zero_fiscal_line: Optional[FiscalPostingAuditOmittedLine]

    def __post_init__(self):
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError("description must be non-empty text")
        if not isinstance(
            self.provenance,
            _confirmation.FiscalizedConfirmationProvenance,
        ):
            raise TypeError(
                "provenance must be FiscalizedConfirmationProvenance"
            )
        if self.zero_fiscal_line_policy not in _ALLOWED_ZERO_POLICIES:
            raise ValueError("invalid zero fiscal line policy")
        if self.omitted_zero_fiscal_line is not None and not isinstance(
            self.omitted_zero_fiscal_line,
            FiscalPostingAuditOmittedLine,
        ):
            raise TypeError(
                "omitted_zero_fiscal_line must be FiscalPostingAuditOmittedLine or None"
            )

        zero_effects = tuple(
            effect
            for effect in self.provenance.fiscal_effects
            if effect.rounded_fiscal_amount == Decimal("0")
        )
        if zero_effects:
            if self.zero_fiscal_line_policy == "reject_zero_fiscal_line":
                raise ValueError(
                    "zero fiscal amount cannot have reject policy in an audit "
                    "of a posting instruction"
                )
            if len(zero_effects) != 1:
                raise ValueError(
                    "singular omitted-line audit metadata cannot represent "
                    "multiple zero fiscal effects"
                )
            if self.omitted_zero_fiscal_line is None:
                raise ValueError(
                    "omitted zero fiscal line metadata is required for zero fiscal amount"
                )
            effect = zero_effects[0]
            omitted = self.omitted_zero_fiscal_line
            if omitted.account_role != effect.fiscal_role:
                raise ValueError("omitted fiscal role must match provenance")
            if omitted.side != effect.fiscal_side:
                raise ValueError("omitted fiscal side must match provenance")
            if not _same_decimal(
                omitted.amount,
                effect.rounded_fiscal_amount,
            ):
                raise ValueError("omitted fiscal amount must match provenance")
        elif self.omitted_zero_fiscal_line is not None:
            raise ValueError(
                "omitted zero fiscal line metadata is invalid for nonzero fiscal amount"
            )


def create_fiscal_posting_audit_snapshot(instruction):
    """Copy audit metadata from exactly one fiscalized posting instruction."""
    if not isinstance(instruction, _posting.FiscalizedPostingInstruction):
        raise TypeError(
            "create_fiscal_posting_audit_snapshot requires FiscalizedPostingInstruction"
        )

    source_snapshot = instruction.confirmed_proposal.snapshot
    return FiscalPostingAuditSnapshot(
        description=instruction.description,
        provenance=_copy_provenance(source_snapshot.provenance),
        zero_fiscal_line_policy=instruction.zero_fiscal_line_policy,
        omitted_zero_fiscal_line=_copy_omitted_line(
            instruction.omitted_zero_fiscal_line
        ),
    )


__all__ = [
    "FiscalPostingAuditOmittedLine",
    "FiscalPostingAuditSnapshot",
    "create_fiscal_posting_audit_snapshot",
]
