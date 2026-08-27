"""Pure canonical fixed-asset acquisition accounting semantics."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .economic_facts import AccountingProposal, ProposalLine
from .fixed_asset import FixedAsset


_ASSET_CLASS_DEBIT_ROLES = {
    "furniture_equipment": "fixed_asset_furniture_equipment",
    "computer_equipment": "fixed_asset_computer_equipment",
    "machinery_tools": "fixed_asset_machinery_tools",
    "land_buildings": "fixed_asset_land_buildings",
}

_SETTLEMENT_CREDIT_ROLES = {
    "bank": "bank",
    "cash": "cash",
    "credit": "accounts_payable",
}


def _require_positive_id(value, field_name):
    if type(value) is not int:
        raise TypeError(f"{field_name} must be an int")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


def _require_nonempty_text(value, field_name):
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_date(value, field_name):
    if type(value) is not date:
        raise TypeError(f"{field_name} must be a date")


def _require_nonnegative_decimal(value, field_name):
    if type(value) is not Decimal:
        raise TypeError(f"{field_name} must be Decimal")
    if not value.is_finite():
        raise ValueError(f"{field_name} must be finite")
    if value < Decimal("0"):
        raise ValueError(f"{field_name} must be non-negative")


def _require_asset_class(value):
    if not isinstance(value, str):
        raise TypeError("asset_class must be a string")
    if value not in _ASSET_CLASS_DEBIT_ROLES:
        allowed = ", ".join(repr(item) for item in _ASSET_CLASS_DEBIT_ROLES)
        raise ValueError(f"asset_class must be one of: {allowed}")


def _require_settlement_method(value):
    if not isinstance(value, str):
        raise TypeError("settlement_method must be a string")
    if value not in _SETTLEMENT_CREDIT_ROLES:
        allowed = ", ".join(repr(item) for item in _SETTLEMENT_CREDIT_ROLES)
        raise ValueError(f"settlement_method must be one of: {allowed}")


def _positive_explanation(fact):
    return (
        f"Fixed asset acquisition {fact.fixed_asset_code}: {fact.acquisition_cost} "
        f"classified as {fact.asset_class}, settled by {fact.settlement_method}. "
        "The asset class increases (debit) and the settlement source increases or "
        "decreases as required (credit)."
    )


def _zero_explanation(fact):
    return (
        f"Fixed asset acquisition {fact.fixed_asset_code}: zero acquisition cost; "
        "no accounting entry is created."
    )


def _expected_lines(fact):
    return (
        ProposalLine(
            _ASSET_CLASS_DEBIT_ROLES[fact.asset_class],
            "debit",
            fact.acquisition_cost,
        ),
        ProposalLine(
            _SETTLEMENT_CREDIT_ROLES[fact.settlement_method],
            "credit",
            fact.acquisition_cost,
        ),
    )


@dataclass(frozen=True)
class FixedAssetAcquisitionFact:
    """One exact acquisition fact derived from a registered fixed asset."""

    fixed_asset_id: int
    entity_id: int
    fixed_asset_code: str
    acquisition_date: date
    acquisition_cost: Decimal
    asset_class: str
    settlement_method: str

    def __post_init__(self):
        _require_positive_id(self.fixed_asset_id, "fixed_asset_id")
        _require_positive_id(self.entity_id, "entity_id")
        _require_nonempty_text(self.fixed_asset_code, "fixed_asset_code")
        _require_date(self.acquisition_date, "acquisition_date")
        _require_nonnegative_decimal(self.acquisition_cost, "acquisition_cost")
        _require_asset_class(self.asset_class)
        _require_settlement_method(self.settlement_method)


@dataclass(frozen=True)
class FixedAssetAcquisitionAccountingResolution:
    """Validated semantic accounting result for one acquisition fact."""

    acquisition_fact: FixedAssetAcquisitionFact
    outcome: str
    proposal: object
    explanation: str

    def __post_init__(self):
        if not isinstance(self.acquisition_fact, FixedAssetAcquisitionFact):
            raise TypeError("acquisition_fact must be FixedAssetAcquisitionFact")
        if not isinstance(self.explanation, str):
            raise TypeError("explanation must be a string")

        if self.acquisition_fact.acquisition_cost == Decimal("0"):
            expected_explanation = _zero_explanation(self.acquisition_fact)
            if self.outcome != "zero_cost_no_entry":
                raise ValueError("zero-cost acquisition requires zero_cost_no_entry")
            if self.proposal is not None:
                raise ValueError("zero-cost acquisition must not contain a proposal")
            if self.explanation != expected_explanation:
                raise ValueError("zero-cost explanation does not match acquisition truth")
            return

        expected_explanation = _positive_explanation(self.acquisition_fact)
        if self.outcome != "accounting_proposal":
            raise ValueError("positive acquisition requires accounting_proposal")
        if not isinstance(self.proposal, AccountingProposal):
            raise TypeError("positive acquisition requires AccountingProposal")
        if tuple(self.proposal.lines) != _expected_lines(self.acquisition_fact):
            raise ValueError("proposal lines do not match acquisition truth")
        if self.proposal.explanation != expected_explanation:
            raise ValueError("proposal explanation does not match acquisition truth")
        if self.explanation != expected_explanation:
            raise ValueError("resolution explanation does not match acquisition truth")


def create_fixed_asset_acquisition_fact(fixed_asset, asset_class, settlement_method):
    """Create one explicit acquisition fact from a registered FixedAsset."""
    if not isinstance(fixed_asset, FixedAsset):
        raise TypeError("fixed_asset must be FixedAsset")
    if fixed_asset.id is None:
        raise ValueError("fixed_asset must already have a persisted identity")
    _require_positive_id(fixed_asset.id, "fixed_asset.id")
    _require_asset_class(asset_class)
    _require_settlement_method(settlement_method)

    return FixedAssetAcquisitionFact(
        fixed_asset_id=fixed_asset.id,
        entity_id=fixed_asset.entity_id,
        fixed_asset_code=fixed_asset.code,
        acquisition_date=fixed_asset.acquisition_date,
        acquisition_cost=fixed_asset.acquisition_cost,
        asset_class=asset_class,
        settlement_method=settlement_method,
    )


def resolve_fixed_asset_acquisition_accounting(acquisition_fact):
    """Resolve one acquisition fact to deterministic semantic double entry."""
    if not isinstance(acquisition_fact, FixedAssetAcquisitionFact):
        raise TypeError("acquisition_fact must be FixedAssetAcquisitionFact")

    if acquisition_fact.acquisition_cost == Decimal("0"):
        explanation = _zero_explanation(acquisition_fact)
        return FixedAssetAcquisitionAccountingResolution(
            acquisition_fact=acquisition_fact,
            outcome="zero_cost_no_entry",
            proposal=None,
            explanation=explanation,
        )

    explanation = _positive_explanation(acquisition_fact)
    proposal = AccountingProposal(
        lines=_expected_lines(acquisition_fact),
        explanation=explanation,
    )
    return FixedAssetAcquisitionAccountingResolution(
        acquisition_fact=acquisition_fact,
        outcome="accounting_proposal",
        proposal=proposal,
        explanation=explanation,
    )


__all__ = [
    "FixedAssetAcquisitionFact",
    "FixedAssetAcquisitionAccountingResolution",
    "create_fixed_asset_acquisition_fact",
    "resolve_fixed_asset_acquisition_accounting",
]
