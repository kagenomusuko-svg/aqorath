"""Pure semantic accounting resolution for dated fixed-asset depreciation truth."""

from dataclasses import dataclass
from decimal import Decimal

from .economic_facts import AccountingProposal, ProposalLine
from .fixed_asset_depreciation_recognition import (
    FixedAssetDepreciationRecognitionFact,
)


_POSITIVE_OUTCOME = "accounting_proposal"
_ZERO_OUTCOME = "zero_amount_no_entry"


def _require_recognition_fact(value):
    if not isinstance(value, FixedAssetDepreciationRecognitionFact):
        raise TypeError(
            "recognition_fact must be FixedAssetDepreciationRecognitionFact"
        )


def _expected_explanation(recognition_fact):
    prefix = (
        "Fixed asset depreciation recognition: asset "
        f"{recognition_fact.allocation.calculation.fixed_asset_code}, "
        f"period {recognition_fact.period_number}, "
        f"recognition date {recognition_fact.recognition_date.isoformat()}, "
        f"amount {recognition_fact.amount}. "
    )
    if recognition_fact.amount == Decimal("0"):
        return prefix + "Zero allocated depreciation produces no accounting entry."
    return (
        prefix
        + "Depreciation expense recognized (debit), accumulated depreciation increased (credit)."
    )


def _validate_positive_proposal(recognition_fact, proposal, explanation):
    if not isinstance(proposal, AccountingProposal):
        raise TypeError("positive depreciation requires AccountingProposal")
    if not isinstance(proposal.lines, tuple):
        raise TypeError("depreciation proposal lines must be an immutable tuple")
    if len(proposal.lines) != 2:
        raise ValueError("depreciation proposal must contain exactly two lines")

    debit, credit = proposal.lines
    if not isinstance(debit, ProposalLine) or not isinstance(credit, ProposalLine):
        raise TypeError("depreciation proposal must contain ProposalLine values")
    if (debit.account_role, debit.side) != ("depreciation_expense", "debit"):
        raise ValueError("depreciation expense semantic line is inconsistent")
    if (credit.account_role, credit.side) != (
        "accumulated_depreciation",
        "credit",
    ):
        raise ValueError("accumulated depreciation semantic line is inconsistent")
    if debit.amount.as_tuple() != recognition_fact.amount.as_tuple():
        raise ValueError("debit amount must exactly match recognized depreciation")
    if credit.amount.as_tuple() != recognition_fact.amount.as_tuple():
        raise ValueError("credit amount must exactly match recognized depreciation")
    if proposal.explanation != explanation:
        raise ValueError("proposal explanation must match accounting resolution")


@dataclass(frozen=True)
class FixedAssetDepreciationAccountingResolution:
    """Semantic result of resolving one dated depreciation recognition fact."""

    recognition_fact: FixedAssetDepreciationRecognitionFact
    outcome: str
    proposal: object
    explanation: str

    def __post_init__(self):
        _require_recognition_fact(self.recognition_fact)
        if self.outcome not in (_POSITIVE_OUTCOME, _ZERO_OUTCOME):
            raise ValueError("unsupported depreciation accounting outcome")
        if not isinstance(self.explanation, str) or not self.explanation.strip():
            raise ValueError("explanation must be non-empty text")

        expected_explanation = _expected_explanation(self.recognition_fact)
        if self.explanation != expected_explanation:
            raise ValueError("explanation must exactly reflect recognition truth")

        if self.recognition_fact.amount == Decimal("0"):
            if self.outcome != _ZERO_OUTCOME:
                raise ValueError("zero depreciation must use zero_amount_no_entry")
            if self.proposal is not None:
                raise ValueError("zero depreciation must not create an accounting proposal")
            return

        if self.outcome != _POSITIVE_OUTCOME:
            raise ValueError("positive depreciation must use accounting_proposal")
        _validate_positive_proposal(
            self.recognition_fact,
            self.proposal,
            self.explanation,
        )


def resolve_fixed_asset_depreciation_accounting(recognition_fact):
    """Resolve one dated depreciation fact into semantic accounting truth."""
    _require_recognition_fact(recognition_fact)
    explanation = _expected_explanation(recognition_fact)

    if recognition_fact.amount == Decimal("0"):
        return FixedAssetDepreciationAccountingResolution(
            recognition_fact=recognition_fact,
            outcome=_ZERO_OUTCOME,
            proposal=None,
            explanation=explanation,
        )

    proposal = AccountingProposal(
        lines=(
            ProposalLine(
                account_role="depreciation_expense",
                side="debit",
                amount=recognition_fact.amount,
            ),
            ProposalLine(
                account_role="accumulated_depreciation",
                side="credit",
                amount=recognition_fact.amount,
            ),
        ),
        explanation=explanation,
    )
    return FixedAssetDepreciationAccountingResolution(
        recognition_fact=recognition_fact,
        outcome=_POSITIVE_OUTCOME,
        proposal=proposal,
        explanation=explanation,
    )


__all__ = [
    "FixedAssetDepreciationAccountingResolution",
    "resolve_fixed_asset_depreciation_accounting",
]
