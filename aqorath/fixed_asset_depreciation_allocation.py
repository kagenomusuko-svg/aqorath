"""Pure monetary allocation of exact canonical fixed-asset depreciation."""

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_EVEN, ROUND_HALF_UP, ROUND_UP

from .fixed_asset_depreciation import FixedAssetDepreciationCalculation


_VALID_ROUNDING_MODES = frozenset(
    {
        ROUND_DOWN,
        ROUND_HALF_EVEN,
        ROUND_HALF_UP,
        ROUND_UP,
    }
)
_VALID_ALLOCATION_KINDS = frozenset({"regular", "final_remainder"})


def _require_nonempty_text(value, field_name):
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_exact_decimal(value, field_name, *, nonnegative=False):
    if type(value) is not Decimal:
        raise TypeError(f"{field_name} must be Decimal")
    if not value.is_finite():
        raise ValueError(f"{field_name} must be finite")
    if nonnegative and value < Decimal("0"):
        raise ValueError(f"{field_name} must be non-negative")


def _require_quantizer(value):
    _require_exact_decimal(value, "quantizer")
    if value <= Decimal("0"):
        raise ValueError("quantizer must be positive")
    decimal_tuple = value.as_tuple()
    if decimal_tuple.sign or decimal_tuple.digits != (1,):
        raise ValueError("quantizer must be an exact power of ten")


def _require_rounding_mode(value):
    if value not in _VALID_ROUNDING_MODES:
        raise ValueError("rounding_mode is not supported")


def _decimal_coefficient(value):
    sign, digits, exponent = value.as_tuple()
    coefficient = 0
    for digit in digits:
        coefficient = coefficient * 10 + digit
    if sign:
        coefficient = -coefficient
    return coefficient, exponent


def _decimal_to_units_exact(value, target_exponent, field_name):
    _require_exact_decimal(value, field_name)
    coefficient, value_exponent = _decimal_coefficient(value)
    if value_exponent >= target_exponent:
        return coefficient * (10 ** (value_exponent - target_exponent))

    factor = 10 ** (target_exponent - value_exponent)
    absolute = -coefficient if coefficient < 0 else coefficient
    units, remainder = divmod(absolute, factor)
    if remainder:
        raise ValueError(
            f"{field_name} cannot be represented exactly by the supplied quantizer"
        )
    return -units if coefficient < 0 else units


def _decimal_from_units(units, exponent):
    sign = 1 if units < 0 else 0
    absolute = -units if units < 0 else units
    digits = tuple(int(char) for char in str(absolute)) if absolute else (0,)
    return Decimal((sign, digits, exponent))


def _round_nonnegative_ratio_units(numerator_units, denominator, rounding_mode):
    if type(numerator_units) is not int or numerator_units < 0:
        raise ValueError("numerator units must be a non-negative integer")
    if type(denominator) is not int or denominator <= 0:
        raise ValueError("denominator must be a positive integer")
    _require_rounding_mode(rounding_mode)

    whole_units, remainder = divmod(numerator_units, denominator)
    if not remainder:
        return whole_units

    if rounding_mode == ROUND_DOWN:
        return whole_units
    if rounding_mode == ROUND_UP:
        return whole_units + 1

    doubled_remainder = remainder * 2
    if rounding_mode == ROUND_HALF_UP:
        return whole_units + (1 if doubled_remainder >= denominator else 0)
    if rounding_mode == ROUND_HALF_EVEN:
        if doubled_remainder > denominator:
            return whole_units + 1
        if doubled_remainder < denominator:
            return whole_units
        return whole_units + (1 if whole_units % 2 else 0)

    raise ValueError("rounding_mode is not supported")


@dataclass(frozen=True)
class FixedAssetDepreciationAllocationPolicy:
    """One explicit provenance-bearing monetary allocation policy."""

    policy_key: str
    quantizer: Decimal
    rounding_mode: str
    remainder_policy: str
    source_ref: str

    def __post_init__(self):
        _require_nonempty_text(self.policy_key, "policy_key")
        _require_quantizer(self.quantizer)
        _require_rounding_mode(self.rounding_mode)
        if self.remainder_policy != "final_period":
            raise ValueError("remainder_policy must be exactly 'final_period'")
        _require_nonempty_text(self.source_ref, "source_ref")


@dataclass(frozen=True)
class FixedAssetDepreciationPeriodAllocation:
    """One ordinal monetary allocation period."""

    period_number: int
    amount: Decimal
    allocation_kind: str

    def __post_init__(self):
        if type(self.period_number) is not int:
            raise TypeError("period_number must be an int")
        if self.period_number <= 0:
            raise ValueError("period_number must be positive")
        _require_exact_decimal(self.amount, "amount", nonnegative=True)
        if self.allocation_kind not in _VALID_ALLOCATION_KINDS:
            raise ValueError("allocation_kind is invalid")


@dataclass(frozen=True)
class FixedAssetDepreciationAllocation:
    """Complete exact-close monetary allocation for one Phase 6G calculation."""

    calculation: FixedAssetDepreciationCalculation
    policy: FixedAssetDepreciationAllocationPolicy
    periods: tuple
    total_allocated: Decimal

    def __post_init__(self):
        if not isinstance(self.calculation, FixedAssetDepreciationCalculation):
            raise TypeError("calculation must be FixedAssetDepreciationCalculation")
        if not isinstance(self.policy, FixedAssetDepreciationAllocationPolicy):
            raise TypeError("policy must be FixedAssetDepreciationAllocationPolicy")
        if type(self.periods) is not tuple:
            raise TypeError("periods must be a tuple")
        if not self.periods:
            raise ValueError("periods must not be empty")
        if len(self.periods) != self.calculation.useful_life_months:
            raise ValueError("period count must equal useful_life_months")

        quantizer_exponent = self.policy.quantizer.as_tuple().exponent
        base_units = _decimal_to_units_exact(
            self.calculation.depreciable_base,
            quantizer_exponent,
            "depreciable_base",
        )
        if base_units < 0:
            raise ValueError("depreciable_base must be non-negative")

        expected_regular_units = _round_nonnegative_ratio_units(
            base_units,
            self.calculation.useful_life_months,
            self.policy.rounding_mode,
        )
        expected_final_units = base_units - (
            expected_regular_units * (self.calculation.useful_life_months - 1)
        )
        if expected_final_units < 0:
            raise ValueError("rounding policy would make final remainder negative")

        allocated_units = 0
        last_index = len(self.periods) - 1
        for index, period in enumerate(self.periods):
            if not isinstance(period, FixedAssetDepreciationPeriodAllocation):
                raise TypeError(
                    "periods must contain FixedAssetDepreciationPeriodAllocation"
                )
            expected_number = index + 1
            if period.period_number != expected_number:
                raise ValueError("period numbers must be consecutive from one")
            expected_kind = "final_remainder" if index == last_index else "regular"
            if period.allocation_kind != expected_kind:
                raise ValueError("allocation_kind must identify only the final remainder")
            if period.amount.as_tuple().exponent != quantizer_exponent:
                raise ValueError("period amount must use exact quantizer scale")
            period_units = _decimal_to_units_exact(
                period.amount,
                quantizer_exponent,
                "period amount",
            )
            if period_units < 0:
                raise ValueError("period amount must be non-negative")
            expected_units = (
                expected_final_units if index == last_index else expected_regular_units
            )
            if period_units != expected_units:
                raise ValueError("period amount is inconsistent with allocation policy")
            allocated_units += period_units

        _require_exact_decimal(
            self.total_allocated,
            "total_allocated",
            nonnegative=True,
        )
        if self.total_allocated.as_tuple().exponent != quantizer_exponent:
            raise ValueError("total_allocated must use exact quantizer scale")
        total_units = _decimal_to_units_exact(
            self.total_allocated,
            quantizer_exponent,
            "total_allocated",
        )
        if allocated_units != base_units or total_units != base_units:
            raise ValueError("allocation must close exactly to depreciable_base")


def allocate_monthly_depreciation(calculation, policy):
    """Materialize one exact monthly rational into ordinal monetary periods."""
    if not isinstance(calculation, FixedAssetDepreciationCalculation):
        raise TypeError("calculation must be FixedAssetDepreciationCalculation")
    if not isinstance(policy, FixedAssetDepreciationAllocationPolicy):
        raise TypeError("policy must be FixedAssetDepreciationAllocationPolicy")

    quantizer_exponent = policy.quantizer.as_tuple().exponent
    base_units = _decimal_to_units_exact(
        calculation.depreciable_base,
        quantizer_exponent,
        "depreciable_base",
    )
    if base_units < 0:
        raise ValueError("depreciable_base must be non-negative")

    regular_units = _round_nonnegative_ratio_units(
        base_units,
        calculation.useful_life_months,
        policy.rounding_mode,
    )
    final_units = base_units - (
        regular_units * (calculation.useful_life_months - 1)
    )
    if final_units < 0:
        raise ValueError("rounding policy would make final remainder negative")

    periods = []
    for period_number in range(1, calculation.useful_life_months + 1):
        is_final = period_number == calculation.useful_life_months
        amount_units = final_units if is_final else regular_units
        periods.append(
            FixedAssetDepreciationPeriodAllocation(
                period_number=period_number,
                amount=_decimal_from_units(amount_units, quantizer_exponent),
                allocation_kind="final_remainder" if is_final else "regular",
            )
        )

    return FixedAssetDepreciationAllocation(
        calculation=calculation,
        policy=policy,
        periods=tuple(periods),
        total_allocated=_decimal_from_units(base_units, quantizer_exponent),
    )


__all__ = [
    "FixedAssetDepreciationAllocationPolicy",
    "FixedAssetDepreciationPeriodAllocation",
    "FixedAssetDepreciationAllocation",
    "allocate_monthly_depreciation",
]
