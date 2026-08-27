"""Pure exact depreciation calculation for canonical fixed assets."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from .fixed_asset import FixedAsset


def _require_optional_id(value, field_name):
    if value is None:
        return
    if type(value) is not int:
        raise TypeError(f"{field_name} must be an int or None")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


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


def _decimal_to_scaled_integer(value, common_exponent):
    sign, digits, exponent = value.as_tuple()
    coefficient = 0
    for digit in digits:
        coefficient = coefficient * 10 + digit
    if sign:
        coefficient = -coefficient
    return coefficient * (10 ** (exponent - common_exponent))


def _decimal_from_scaled_integer(value, exponent):
    sign = 1 if value < 0 else 0
    absolute = -value if value < 0 else value
    digits = tuple(int(char) for char in str(absolute)) if absolute else (0,)
    return Decimal((sign, digits, exponent))


def _subtract_exact(left, right):
    """Subtract finite Decimals without consulting ambient decimal precision."""
    common_exponent = min(left.as_tuple().exponent, right.as_tuple().exponent)
    left_integer = _decimal_to_scaled_integer(left, common_exponent)
    right_integer = _decimal_to_scaled_integer(right, common_exponent)
    return _decimal_from_scaled_integer(left_integer - right_integer, common_exponent)


@dataclass(frozen=True)
class FixedAssetDepreciationCalculation:
    """Exact straight-line monthly amount represented as Decimal numerator / int denominator."""

    fixed_asset_id: Optional[int]
    entity_id: int
    fixed_asset_code: str
    in_service_date: date
    depreciation_method: str
    acquisition_cost: Decimal
    residual_value: Decimal
    depreciable_base: Decimal
    useful_life_months: int
    monthly_amount_numerator: Decimal
    monthly_amount_denominator: int

    def __post_init__(self):
        _require_optional_id(self.fixed_asset_id, "fixed_asset_id")
        _require_positive_id(self.entity_id, "entity_id")
        _require_nonempty_text(self.fixed_asset_code, "fixed_asset_code")
        _require_date(self.in_service_date, "in_service_date")
        if self.depreciation_method != "straight_line":
            raise ValueError("depreciation_method must be exactly 'straight_line'")
        _require_nonnegative_decimal(self.acquisition_cost, "acquisition_cost")
        _require_nonnegative_decimal(self.residual_value, "residual_value")
        _require_nonnegative_decimal(self.depreciable_base, "depreciable_base")
        _require_nonnegative_decimal(
            self.monthly_amount_numerator,
            "monthly_amount_numerator",
        )
        if self.residual_value > self.acquisition_cost:
            raise ValueError("residual_value cannot exceed acquisition_cost")
        if type(self.useful_life_months) is not int:
            raise TypeError("useful_life_months must be an int")
        if self.useful_life_months <= 0:
            raise ValueError("useful_life_months must be positive")
        if type(self.monthly_amount_denominator) is not int:
            raise TypeError("monthly_amount_denominator must be an int")
        if self.monthly_amount_denominator <= 0:
            raise ValueError("monthly_amount_denominator must be positive")

        expected_base = _subtract_exact(self.acquisition_cost, self.residual_value)
        if self.depreciable_base.as_tuple() != expected_base.as_tuple():
            raise ValueError("depreciable_base must exactly equal acquisition_cost minus residual_value")
        if self.monthly_amount_numerator.as_tuple() != self.depreciable_base.as_tuple():
            raise ValueError("monthly_amount_numerator must exactly equal depreciable_base")
        if self.monthly_amount_denominator != self.useful_life_months:
            raise ValueError("monthly_amount_denominator must equal useful_life_months")


def calculate_monthly_straight_line_depreciation(fixed_asset):
    """Return exact monthly straight-line depreciation as an unreduced rational amount."""
    if not isinstance(fixed_asset, FixedAsset):
        raise TypeError("fixed_asset must be FixedAsset")
    if fixed_asset.depreciation_method != "straight_line":
        raise ValueError("unsupported depreciation_method")

    depreciable_base = _subtract_exact(
        fixed_asset.acquisition_cost,
        fixed_asset.residual_value,
    )
    return FixedAssetDepreciationCalculation(
        fixed_asset_id=fixed_asset.id,
        entity_id=fixed_asset.entity_id,
        fixed_asset_code=fixed_asset.code,
        in_service_date=fixed_asset.in_service_date,
        depreciation_method=fixed_asset.depreciation_method,
        acquisition_cost=fixed_asset.acquisition_cost,
        residual_value=fixed_asset.residual_value,
        depreciable_base=depreciable_base,
        useful_life_months=fixed_asset.useful_life_months,
        monthly_amount_numerator=depreciable_base,
        monthly_amount_denominator=fixed_asset.useful_life_months,
    )
