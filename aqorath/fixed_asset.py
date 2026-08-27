"""Pure canonical fixed-asset registry domain."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional


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


@dataclass(frozen=True)
class FixedAsset:
    """One explicit durable-asset registry record owned by an Entity."""

    id: Optional[int]
    entity_id: int
    code: str
    name: str
    acquisition_date: date
    in_service_date: date
    acquisition_cost: Decimal
    residual_value: Decimal
    useful_life_months: int
    depreciation_method: str
    is_active: bool

    def __post_init__(self):
        _require_optional_id(self.id, "id")
        _require_positive_id(self.entity_id, "entity_id")
        _require_nonempty_text(self.code, "code")
        _require_nonempty_text(self.name, "name")
        _require_date(self.acquisition_date, "acquisition_date")
        _require_date(self.in_service_date, "in_service_date")
        _require_nonnegative_decimal(self.acquisition_cost, "acquisition_cost")
        _require_nonnegative_decimal(self.residual_value, "residual_value")
        if type(self.useful_life_months) is not int:
            raise TypeError("useful_life_months must be an int")
        if self.useful_life_months <= 0:
            raise ValueError("useful_life_months must be positive")
        _require_nonempty_text(self.depreciation_method, "depreciation_method")
        if type(self.is_active) is not bool:
            raise TypeError("is_active must be bool")
        if self.in_service_date < self.acquisition_date:
            raise ValueError("in_service_date cannot precede acquisition_date")
        if self.residual_value > self.acquisition_cost:
            raise ValueError("residual_value cannot exceed acquisition_cost")
