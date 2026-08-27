"""Pure explicit dated recognition of one allocated depreciation period."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .fixed_asset_depreciation_allocation import FixedAssetDepreciationAllocation


_FACTORY_TOKEN = object()


def _require_period_number(value):
    if type(value) is not int:
        raise TypeError("period_number must be an int")
    if value <= 0:
        raise ValueError("period_number must be positive")


def _require_date(value, field_name):
    if type(value) is not date:
        raise TypeError(f"{field_name} must be a date")


def _require_nonempty_text(value, field_name):
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_nonnegative_decimal(value, field_name):
    if type(value) is not Decimal:
        raise TypeError(f"{field_name} must be Decimal")
    if not value.is_finite():
        raise ValueError(f"{field_name} must be finite")
    if value < Decimal("0"):
        raise ValueError(f"{field_name} must be non-negative")


@dataclass(frozen=True, init=False)
class FixedAssetDepreciationRecognitionFact:
    """One explicit dated economic fact for an allocated depreciation period."""

    allocation: FixedAssetDepreciationAllocation
    period_number: int
    recognition_date: date
    recognition_source_ref: str
    amount: Decimal
    allocation_kind: str

    def __init__(
        self,
        allocation,
        period_number,
        recognition_date,
        recognition_source_ref,
        amount,
        allocation_kind,
        *,
        _factory_token=None,
    ):
        if _factory_token is not _FACTORY_TOKEN:
            raise TypeError(
                "FixedAssetDepreciationRecognitionFact must be created by its declaration factory"
            )
        object.__setattr__(self, "allocation", allocation)
        object.__setattr__(self, "period_number", period_number)
        object.__setattr__(self, "recognition_date", recognition_date)
        object.__setattr__(self, "recognition_source_ref", recognition_source_ref)
        object.__setattr__(self, "amount", amount)
        object.__setattr__(self, "allocation_kind", allocation_kind)
        self.__post_init__()

    def __post_init__(self):
        if not isinstance(self.allocation, FixedAssetDepreciationAllocation):
            raise TypeError("allocation must be FixedAssetDepreciationAllocation")
        _require_period_number(self.period_number)
        _require_date(self.recognition_date, "recognition_date")
        _require_nonempty_text(
            self.recognition_source_ref,
            "recognition_source_ref",
        )
        if self.period_number > len(self.allocation.periods):
            raise ValueError("period_number is outside the allocation")
        if self.recognition_date < self.allocation.calculation.in_service_date:
            raise ValueError("recognition_date cannot precede in_service_date")

        selected = self.allocation.periods[self.period_number - 1]
        if selected.period_number != self.period_number:
            raise ValueError("allocation period identity is inconsistent")

        _require_nonnegative_decimal(self.amount, "amount")
        if self.amount.as_tuple() != selected.amount.as_tuple():
            raise ValueError("amount must match the selected allocated period exactly")
        if self.allocation_kind != selected.allocation_kind:
            raise ValueError(
                "allocation_kind must match the selected allocated period exactly"
            )


def declare_fixed_asset_depreciation_recognition(
    allocation,
    period_number,
    recognition_date,
    recognition_source_ref,
):
    """Declare one explicit dated depreciation economic fact."""
    if not isinstance(allocation, FixedAssetDepreciationAllocation):
        raise TypeError("allocation must be FixedAssetDepreciationAllocation")
    _require_period_number(period_number)
    _require_date(recognition_date, "recognition_date")
    _require_nonempty_text(recognition_source_ref, "recognition_source_ref")
    if period_number > len(allocation.periods):
        raise ValueError("period_number is outside the allocation")
    if recognition_date < allocation.calculation.in_service_date:
        raise ValueError("recognition_date cannot precede in_service_date")

    selected = allocation.periods[period_number - 1]
    return FixedAssetDepreciationRecognitionFact(
        allocation=allocation,
        period_number=period_number,
        recognition_date=recognition_date,
        recognition_source_ref=recognition_source_ref,
        amount=selected.amount,
        allocation_kind=selected.allocation_kind,
        _factory_token=_FACTORY_TOKEN,
    )


__all__ = [
    "FixedAssetDepreciationRecognitionFact",
    "declare_fixed_asset_depreciation_recognition",
]
