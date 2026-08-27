"""Phase 6H.1 — canonical fixed-asset depreciation monetary allocation contracts.

Contracts only. One exact Phase 6G rational monthly calculation is materialized into
ordinal monetary periods under an explicit caller-supplied rounding policy. Calendar
recognition, proration, account selection, posting, persistence, and lifecycle inference
remain outside this phase.
"""

import ast
from dataclasses import FrozenInstanceError, fields, replace
from datetime import date
from decimal import (
    Decimal,
    ROUND_DOWN,
    ROUND_HALF_EVEN,
    ROUND_HALF_UP,
    ROUND_UP,
    localcontext,
)
import inspect
from types import SimpleNamespace

import pytest


def _asset(**overrides):
    from aqorath.fixed_asset import FixedAsset

    values = {
        "id": 41,
        "entity_id": 7,
        "code": "EQ-001",
        "name": "Equipo de cómputo",
        "acquisition_date": date(2026, 1, 15),
        "in_service_date": date(2026, 2, 1),
        "acquisition_cost": Decimal("100.00"),
        "residual_value": Decimal("0.00"),
        "useful_life_months": 3,
        "depreciation_method": "straight_line",
        "is_active": True,
    }
    values.update(overrides)
    return FixedAsset(**values)


def _calculation(**asset_overrides):
    from aqorath.fixed_asset_depreciation import (
        calculate_monthly_straight_line_depreciation,
    )

    return calculate_monthly_straight_line_depreciation(
        _asset(**asset_overrides)
    )


def _policy(**overrides):
    from aqorath.fixed_asset_depreciation_allocation import (
        FixedAssetDepreciationAllocationPolicy,
    )

    values = {
        "policy_key": "monthly-monetary-allocation-v1",
        "quantizer": Decimal("0.01"),
        "rounding_mode": ROUND_HALF_UP,
        "remainder_policy": "final_period",
        "source_ref": "EXPLICIT:6H",
    }
    values.update(overrides)
    return FixedAssetDepreciationAllocationPolicy(**values)


def test_allocation_public_types_are_frozen_ordinal_value_truth_not_calendar_or_posting():
    import aqorath.fixed_asset_depreciation_allocation as allocation
    from aqorath.fixed_asset_depreciation_allocation import (
        FixedAssetDepreciationAllocation,
        FixedAssetDepreciationAllocationPolicy,
        FixedAssetDepreciationPeriodAllocation,
    )

    result = allocation.allocate_monthly_depreciation(
        _calculation(),
        _policy(),
    )

    assert [field.name for field in fields(FixedAssetDepreciationAllocationPolicy)] == [
        "policy_key",
        "quantizer",
        "rounding_mode",
        "remainder_policy",
        "source_ref",
    ]
    assert [field.name for field in fields(FixedAssetDepreciationPeriodAllocation)] == [
        "period_number",
        "amount",
        "allocation_kind",
    ]
    assert [field.name for field in fields(FixedAssetDepreciationAllocation)] == [
        "calculation",
        "policy",
        "periods",
        "total_allocated",
    ]

    with pytest.raises(FrozenInstanceError):
        result.total_allocated = Decimal("0.00")
    with pytest.raises(FrozenInstanceError):
        result.periods[0].amount = Decimal("0.00")

    forbidden = {
        "period_start",
        "period_end",
        "recognition_date",
        "journal_entry_id",
        "journal_line_id",
        "account_id",
        "account_code",
        "debit",
        "credit",
    }
    assert forbidden.isdisjoint({field.name for field in fields(result)})
    assert forbidden.isdisjoint({field.name for field in fields(result.periods[0])})


def test_allocation_has_one_exact_explicit_signature_and_policy_has_no_defaults():
    import aqorath.fixed_asset_depreciation_allocation as allocation

    assert str(inspect.signature(allocation.allocate_monthly_depreciation)) == (
        "(calculation, policy)"
    )

    params = inspect.signature(
        allocation.FixedAssetDepreciationAllocationPolicy
    ).parameters.values()
    assert all(param.default is inspect._empty for param in params)


def test_allocation_policy_is_explicit_provenance_bearing_and_fail_closed():
    from aqorath.fixed_asset_depreciation_allocation import (
        FixedAssetDepreciationAllocationPolicy,
    )

    for mode in (ROUND_HALF_UP, ROUND_HALF_EVEN, ROUND_DOWN, ROUND_UP):
        policy = _policy(rounding_mode=mode)
        assert policy.rounding_mode == mode

    invalid = (
        {"policy_key": ""},
        {"policy_key": "   "},
        {"quantizer": 0.01},
        {"quantizer": Decimal("NaN")},
        {"quantizer": Decimal("0")},
        {"quantizer": Decimal("-0.01")},
        {"quantizer": Decimal("0.05")},
        {"rounding_mode": "ROUND_UNKNOWN"},
        {"remainder_policy": ""},
        {"remainder_policy": "largest_remainder"},
        {"remainder_policy": " final_period "},
        {"source_ref": ""},
        {"source_ref": "   "},
    )
    for patch in invalid:
        with pytest.raises((TypeError, ValueError)):
            _policy(**patch)

    fiscal_policy = None
    from aqorath.fiscal_rounding import FiscalRoundingPolicy

    fiscal_policy = FiscalRoundingPolicy(
        policy_key="fiscal",
        quantizer=Decimal("0.01"),
        rounding_mode=ROUND_HALF_UP,
        source_ref="FISCAL",
    )
    assert not isinstance(fiscal_policy, FixedAssetDepreciationAllocationPolicy)


def test_allocation_requires_nominal_phase_6g_calculation_not_asset_or_shape():
    from aqorath.fixed_asset_depreciation_allocation import (
        allocate_monthly_depreciation,
    )

    policy = _policy()

    with pytest.raises(TypeError):
        allocate_monthly_depreciation(object(), policy)
    with pytest.raises(TypeError):
        allocate_monthly_depreciation(_asset(), policy)

    shape = SimpleNamespace(
        depreciable_base=Decimal("100.00"),
        useful_life_months=3,
        monthly_amount_numerator=Decimal("100.00"),
        monthly_amount_denominator=3,
    )
    with pytest.raises(TypeError):
        allocate_monthly_depreciation(shape, policy)


def test_exactly_divisible_base_materializes_equal_quantized_periods_and_exact_total():
    from aqorath.fixed_asset_depreciation_allocation import (
        allocate_monthly_depreciation,
    )

    calculation = _calculation(
        acquisition_cost=Decimal("90.00"),
        residual_value=Decimal("0.00"),
        useful_life_months=3,
    )
    policy = _policy()
    result = allocate_monthly_depreciation(calculation, policy)

    assert result.calculation is calculation
    assert result.policy is policy
    assert isinstance(result.periods, tuple)
    assert [period.period_number for period in result.periods] == [1, 2, 3]
    assert [period.allocation_kind for period in result.periods] == [
        "regular",
        "regular",
        "final_remainder",
    ]
    assert [period.amount.as_tuple() for period in result.periods] == [
        Decimal("30.00").as_tuple(),
        Decimal("30.00").as_tuple(),
        Decimal("30.00").as_tuple(),
    ]
    assert result.total_allocated.as_tuple() == Decimal("90.00").as_tuple()


def test_repeating_rational_monthly_amount_uses_explicit_final_remainder_to_close_exactly():
    from aqorath.fixed_asset_depreciation_allocation import (
        allocate_monthly_depreciation,
    )

    result = allocate_monthly_depreciation(
        _calculation(
            acquisition_cost=Decimal("100.00"),
            residual_value=Decimal("0.00"),
            useful_life_months=3,
        ),
        _policy(rounding_mode=ROUND_HALF_UP),
    )

    assert [period.amount.as_tuple() for period in result.periods] == [
        Decimal("33.33").as_tuple(),
        Decimal("33.33").as_tuple(),
        Decimal("33.34").as_tuple(),
    ]
    assert result.periods[-1].allocation_kind == "final_remainder"
    assert result.total_allocated.as_tuple() == Decimal("100.00").as_tuple()
    assert sum(period.amount for period in result.periods) == Decimal("100.00")


def test_explicit_rounding_mode_changes_regular_periods_without_changing_exact_total():
    from aqorath.fixed_asset_depreciation_allocation import (
        allocate_monthly_depreciation,
    )

    calculation = _calculation(
        acquisition_cost=Decimal("10.00"),
        residual_value=Decimal("0.00"),
        useful_life_months=6,
    )
    half_up = allocate_monthly_depreciation(
        calculation,
        _policy(rounding_mode=ROUND_HALF_UP),
    )
    down = allocate_monthly_depreciation(
        calculation,
        _policy(rounding_mode=ROUND_DOWN),
    )

    assert [period.amount for period in half_up.periods] == [
        Decimal("1.67"),
        Decimal("1.67"),
        Decimal("1.67"),
        Decimal("1.67"),
        Decimal("1.67"),
        Decimal("1.65"),
    ]
    assert [period.amount for period in down.periods] == [
        Decimal("1.66"),
        Decimal("1.66"),
        Decimal("1.66"),
        Decimal("1.66"),
        Decimal("1.66"),
        Decimal("1.70"),
    ]
    assert half_up.total_allocated == Decimal("10.00")
    assert down.total_allocated == Decimal("10.00")


def test_allocation_fails_closed_when_quantizer_cannot_represent_exact_depreciable_base():
    from aqorath.fixed_asset_depreciation_allocation import (
        allocate_monthly_depreciation,
    )

    calculation = _calculation(
        acquisition_cost=Decimal("100.001"),
        residual_value=Decimal("0.000"),
        useful_life_months=3,
    )
    with pytest.raises(ValueError):
        allocate_monthly_depreciation(
            calculation,
            _policy(quantizer=Decimal("0.01")),
        )


def test_allocation_fails_closed_when_regular_rounding_would_make_final_remainder_negative():
    from aqorath.fixed_asset_depreciation_allocation import (
        allocate_monthly_depreciation,
    )

    calculation = _calculation(
        acquisition_cost=Decimal("0.01"),
        residual_value=Decimal("0.00"),
        useful_life_months=3,
    )
    with pytest.raises(ValueError):
        allocate_monthly_depreciation(
            calculation,
            _policy(rounding_mode=ROUND_UP),
        )


def test_zero_depreciable_base_materializes_all_zero_periods_at_explicit_quantizer_scale():
    from aqorath.fixed_asset_depreciation_allocation import (
        allocate_monthly_depreciation,
    )

    result = allocate_monthly_depreciation(
        _calculation(
            acquisition_cost=Decimal("100.0000"),
            residual_value=Decimal("100.0000"),
            useful_life_months=4,
        ),
        _policy(quantizer=Decimal("0.01")),
    )

    assert len(result.periods) == 4
    assert [period.amount.as_tuple() for period in result.periods] == [
        Decimal("0.00").as_tuple(),
        Decimal("0.00").as_tuple(),
        Decimal("0.00").as_tuple(),
        Decimal("0.00").as_tuple(),
    ]
    assert result.total_allocated.as_tuple() == Decimal("0.00").as_tuple()


def test_allocation_is_independent_from_ambient_decimal_precision_and_preserves_exact_close():
    from aqorath.fixed_asset_depreciation_allocation import (
        allocate_monthly_depreciation,
    )

    calculation = _calculation(
        acquisition_cost=Decimal("12345678901234567890.12"),
        residual_value=Decimal("0.00"),
        useful_life_months=7,
    )

    with localcontext() as ctx:
        ctx.prec = 3
        result = allocate_monthly_depreciation(
            calculation,
            _policy(quantizer=Decimal("0.01"), rounding_mode=ROUND_HALF_EVEN),
        )

    assert len(result.periods) == 7
    assert all(period.amount.as_tuple().exponent == -2 for period in result.periods)
    assert result.total_allocated.as_tuple() == Decimal(
        "12345678901234567890.12"
    ).as_tuple()


def test_public_allocation_types_reject_mutable_malformed_or_inconsistent_direct_construction():
    from aqorath.fixed_asset_depreciation_allocation import (
        FixedAssetDepreciationPeriodAllocation,
        allocate_monthly_depreciation,
    )

    valid = allocate_monthly_depreciation(
        _calculation(
            acquisition_cost=Decimal("100.00"),
            residual_value=Decimal("0.00"),
            useful_life_months=3,
        ),
        _policy(),
    )

    with pytest.raises((TypeError, ValueError)):
        replace(valid, periods=list(valid.periods))
    with pytest.raises((TypeError, ValueError)):
        replace(valid, periods=())
    with pytest.raises((TypeError, ValueError)):
        replace(
            valid,
            periods=(
                replace(valid.periods[0], period_number=2),
                valid.periods[1],
                valid.periods[2],
            ),
        )
    with pytest.raises((TypeError, ValueError)):
        replace(
            valid,
            periods=(
                valid.periods[0],
                valid.periods[1],
                replace(valid.periods[2], allocation_kind="regular"),
            ),
        )
    with pytest.raises((TypeError, ValueError)):
        replace(
            valid,
            periods=(
                valid.periods[0],
                FixedAssetDepreciationPeriodAllocation(
                    period_number=2,
                    amount=33.33,
                    allocation_kind="regular",
                ),
                valid.periods[2],
            ),
        )
    with pytest.raises((TypeError, ValueError)):
        replace(
            valid,
            periods=(
                valid.periods[0],
                replace(valid.periods[1], amount=Decimal("-0.01")),
                valid.periods[2],
            ),
        )
    with pytest.raises((TypeError, ValueError)):
        replace(
            valid,
            periods=(
                replace(valid.periods[0], amount=Decimal("33.330")),
                valid.periods[1],
                valid.periods[2],
            ),
        )
    with pytest.raises((TypeError, ValueError)):
        replace(valid, total_allocated=Decimal("99.99"))


def test_allocation_uses_ordinal_periods_only_and_does_not_infer_calendar_recognition():
    from aqorath.fixed_asset_depreciation_allocation import (
        allocate_monthly_depreciation,
    )

    first_day = allocate_monthly_depreciation(
        _calculation(in_service_date=date(2026, 2, 1)),
        _policy(),
    )
    late_month = allocate_monthly_depreciation(
        _calculation(in_service_date=date(2026, 2, 27)),
        _policy(),
    )

    assert first_day.periods == late_month.periods
    assert [period.period_number for period in first_day.periods] == [1, 2, 3]
    assert not hasattr(first_day.periods[0], "period_start")
    assert not hasattr(first_day.periods[0], "period_end")
    assert not hasattr(first_day.periods[0], "recognition_date")


def test_allocation_is_pure_exact_and_does_not_recalculate_persist_post_or_reuse_fiscal_authority():
    import aqorath.fixed_asset_depreciation_allocation as allocation

    source = inspect.getsource(allocation).lower()
    tree = ast.parse(source)

    assert not any(isinstance(node, ast.Div) for node in ast.walk(tree))

    for forbidden in (
        "float(",
        ".quantize(",
        "sqlmodel",
        "sqlalchemy",
        "get_session",
        "create_engine",
        "fixed_asset_repository",
        "journalentry",
        "journalline",
        "accountrolebinding",
        "post_entry",
        "fiscal_rounding",
        "from .assets",
        "import aqorath.assets",
        "timedelta",
        "relativedelta",
        "calendar.",
    ):
        assert forbidden not in source


def test_allocation_is_deterministic_and_does_not_mutate_calculation_or_policy():
    from aqorath.fixed_asset_depreciation_allocation import (
        allocate_monthly_depreciation,
    )

    calculation = _calculation(
        acquisition_cost=Decimal("777.7700"),
        residual_value=Decimal("77.7700"),
        useful_life_months=13,
    )
    policy = _policy(quantizer=Decimal("0.01"), rounding_mode=ROUND_HALF_UP)
    calculation_before = calculation
    policy_before = policy

    first = allocate_monthly_depreciation(calculation, policy)
    second = allocate_monthly_depreciation(calculation, policy)

    assert calculation is calculation_before
    assert policy is policy_before
    assert first == second
    assert first is not second
    assert first.calculation is calculation
    assert first.policy is policy


def test_application_exposes_allocation_as_thin_interface_agnostic_delegation(monkeypatch):
    import aqorath.application as application
    import aqorath.fixed_asset_depreciation_allocation as allocation

    assert str(
        inspect.signature(application.allocate_fixed_asset_monthly_depreciation)
    ) == "(calculation, policy)"

    calls = []
    sentinel = object()
    calculation = object()
    policy = object()

    def allocate(value_calculation, value_policy):
        calls.append((value_calculation, value_policy))
        return sentinel

    monkeypatch.setattr(
        allocation,
        "allocate_monthly_depreciation",
        allocate,
    )

    assert application.allocate_fixed_asset_monthly_depreciation(
        calculation,
        policy,
    ) is sentinel
    assert calls == [(calculation, policy)]

    source = inspect.getsource(
        application.allocate_fixed_asset_monthly_depreciation
    ).lower()
    for forbidden in (
        "get_session",
        "quantize",
        "post",
        "account",
        "calculate_monthly_straight_line_depreciation",
        "assets.",
    ):
        assert forbidden not in source
