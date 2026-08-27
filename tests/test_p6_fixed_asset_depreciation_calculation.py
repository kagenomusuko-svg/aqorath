"""Phase 6G.1 — canonical fixed-asset depreciation calculation contracts.

Contracts only. Straight-line monthly depreciation is calculated as an exact rational
monetary amount: depreciable base as Decimal numerator and useful-life months as integer
denominator. No division, quantization, calendar convention, account selection, or posting
belongs to this phase.
"""

import ast
from dataclasses import FrozenInstanceError, fields, replace
from datetime import date
from decimal import Decimal, localcontext
import inspect

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
        "residual_value": Decimal("10.00"),
        "useful_life_months": 3,
        "depreciation_method": "straight_line",
        "is_active": True,
    }
    values.update(overrides)
    return FixedAsset(**values)


def test_depreciation_calculation_public_result_is_frozen_value_truth_not_posting_or_schedule():
    import aqorath.fixed_asset_depreciation as depreciation
    from aqorath.fixed_asset_depreciation import FixedAssetDepreciationCalculation

    result = depreciation.calculate_monthly_straight_line_depreciation(_asset())

    assert [field.name for field in fields(FixedAssetDepreciationCalculation)] == [
        "fixed_asset_id",
        "entity_id",
        "fixed_asset_code",
        "in_service_date",
        "depreciation_method",
        "acquisition_cost",
        "residual_value",
        "depreciable_base",
        "useful_life_months",
        "monthly_amount_numerator",
        "monthly_amount_denominator",
    ]
    with pytest.raises(FrozenInstanceError):
        result.useful_life_months = 99

    forbidden = {
        "monthly_amount",
        "rounded_amount",
        "period_start",
        "period_end",
        "journal_entry_id",
        "account_id",
        "account_code",
        "debit",
        "credit",
    }
    assert forbidden.isdisjoint({field.name for field in fields(result)})


def test_depreciation_calculation_has_one_exact_explicit_signature():
    import aqorath.fixed_asset_depreciation as depreciation

    assert str(
        inspect.signature(depreciation.calculate_monthly_straight_line_depreciation)
    ) == "(fixed_asset)"


def test_straight_line_calculation_requires_nominal_fixed_asset_and_exact_supported_method():
    from aqorath.fixed_asset_depreciation import (
        calculate_monthly_straight_line_depreciation,
    )

    with pytest.raises(TypeError):
        calculate_monthly_straight_line_depreciation(object())

    result = calculate_monthly_straight_line_depreciation(_asset())
    assert result.depreciation_method == "straight_line"

    for unsupported in (
        "Straight_Line",
        "straight-line",
        " straight_line ",
        "declining_balance",
        "units_of_production.future",
    ):
        with pytest.raises(ValueError):
            calculate_monthly_straight_line_depreciation(
                _asset(depreciation_method=unsupported)
            )


def test_straight_line_calculation_is_exact_base_over_useful_life_without_premature_division():
    from aqorath.fixed_asset_depreciation import (
        calculate_monthly_straight_line_depreciation,
    )

    result = calculate_monthly_straight_line_depreciation(
        _asset(
            acquisition_cost=Decimal("100.00"),
            residual_value=Decimal("0.00"),
            useful_life_months=3,
        )
    )

    assert result.depreciable_base.as_tuple() == Decimal("100.00").as_tuple()
    assert result.monthly_amount_numerator.as_tuple() == Decimal("100.00").as_tuple()
    assert result.monthly_amount_denominator == 3
    assert isinstance(result.monthly_amount_numerator, Decimal)
    assert type(result.monthly_amount_denominator) is int

    source = inspect.getsource(__import__(
        "aqorath.fixed_asset_depreciation",
        fromlist=["fixed_asset_depreciation"],
    ))
    tree = ast.parse(source)
    assert not any(isinstance(node, ast.Div) for node in ast.walk(tree))


def test_depreciable_base_preserves_decimal_scale_and_is_independent_from_ambient_precision():
    from aqorath.fixed_asset_depreciation import (
        calculate_monthly_straight_line_depreciation,
    )

    asset = _asset(
        acquisition_cost=Decimal("12345678901234567890.123400"),
        residual_value=Decimal("0.000100"),
        useful_life_months=60,
    )
    expected = Decimal("12345678901234567890.123300")

    with localcontext() as ctx:
        ctx.prec = 3
        result = calculate_monthly_straight_line_depreciation(asset)

    assert result.depreciable_base.as_tuple() == expected.as_tuple()
    assert result.monthly_amount_numerator.as_tuple() == expected.as_tuple()
    assert result.monthly_amount_denominator == 60


def test_zero_depreciable_base_is_explicit_exact_zero_ratio_not_dropped_or_special_cased():
    from aqorath.fixed_asset_depreciation import (
        calculate_monthly_straight_line_depreciation,
    )

    result = calculate_monthly_straight_line_depreciation(
        _asset(
            acquisition_cost=Decimal("100.0000"),
            residual_value=Decimal("100.0000"),
            useful_life_months=48,
        )
    )
    assert result.depreciable_base.as_tuple() == Decimal("0.0000").as_tuple()
    assert result.monthly_amount_numerator.as_tuple() == Decimal("0.0000").as_tuple()
    assert result.monthly_amount_denominator == 48


def test_result_copies_complete_calculation_provenance_by_value():
    from aqorath.fixed_asset_depreciation import (
        calculate_monthly_straight_line_depreciation,
    )

    asset = _asset(
        id=None,
        entity_id=23,
        code="MOB-9",
        in_service_date=date(2026, 7, 19),
        acquisition_cost=Decimal("987.6500"),
        residual_value=Decimal("87.65"),
        useful_life_months=24,
    )
    result = calculate_monthly_straight_line_depreciation(asset)

    assert result.fixed_asset_id is None
    assert result.entity_id == 23
    assert result.fixed_asset_code == "MOB-9"
    assert result.in_service_date == date(2026, 7, 19)
    assert result.depreciation_method == "straight_line"
    assert result.acquisition_cost.as_tuple() == Decimal("987.6500").as_tuple()
    assert result.residual_value.as_tuple() == Decimal("87.65").as_tuple()
    assert result.depreciable_base.as_tuple() == Decimal("900.0000").as_tuple()
    assert result.useful_life_months == 24
    assert result.monthly_amount_numerator.as_tuple() == Decimal("900.0000").as_tuple()
    assert result.monthly_amount_denominator == 24


def test_public_result_type_fails_closed_on_inconsistent_or_coerced_direct_construction():
    from aqorath.fixed_asset_depreciation import FixedAssetDepreciationCalculation

    valid = dict(
        fixed_asset_id=41,
        entity_id=7,
        fixed_asset_code="EQ-001",
        in_service_date=date(2026, 2, 1),
        depreciation_method="straight_line",
        acquisition_cost=Decimal("100.00"),
        residual_value=Decimal("10.00"),
        depreciable_base=Decimal("90.00"),
        useful_life_months=3,
        monthly_amount_numerator=Decimal("90.00"),
        monthly_amount_denominator=3,
    )
    result = FixedAssetDepreciationCalculation(**valid)
    assert result.monthly_amount_numerator.as_tuple() == Decimal("90.00").as_tuple()

    invalid_patches = (
        {"fixed_asset_id": 0},
        {"entity_id": True},
        {"fixed_asset_code": " "},
        {"in_service_date": "2026-02-01"},
        {"depreciation_method": "Straight_Line"},
        {"acquisition_cost": 100.0},
        {"residual_value": Decimal("-1")},
        {"depreciable_base": Decimal("89.00")},
        {"useful_life_months": 0},
        {"monthly_amount_numerator": Decimal("90.0")},
        {"monthly_amount_denominator": 4},
        {"monthly_amount_denominator": True},
    )
    for patch in invalid_patches:
        payload = dict(valid)
        payload.update(patch)
        with pytest.raises((TypeError, ValueError)):
            FixedAssetDepreciationCalculation(**payload)


def test_calculation_does_not_infer_lifecycle_from_active_state():
    from aqorath.fixed_asset_depreciation import (
        calculate_monthly_straight_line_depreciation,
    )

    active = calculate_monthly_straight_line_depreciation(_asset(is_active=True))
    inactive = calculate_monthly_straight_line_depreciation(_asset(is_active=False))
    assert active == inactive


def test_calculation_does_not_infer_calendar_proration_or_full_month_convention():
    from aqorath.fixed_asset_depreciation import (
        calculate_monthly_straight_line_depreciation,
    )

    first_day = calculate_monthly_straight_line_depreciation(
        _asset(in_service_date=date(2026, 2, 1))
    )
    late_month = calculate_monthly_straight_line_depreciation(
        _asset(in_service_date=date(2026, 2, 27))
    )

    assert first_day.depreciable_base == late_month.depreciable_base
    assert first_day.monthly_amount_numerator == late_month.monthly_amount_numerator
    assert first_day.monthly_amount_denominator == late_month.monthly_amount_denominator
    assert first_day.in_service_date == date(2026, 2, 1)
    assert late_month.in_service_date == date(2026, 2, 27)


def test_calculation_is_pure_and_contains_no_rounding_storage_accounting_or_legacy_asset_authority():
    import aqorath.fixed_asset_depreciation as depreciation

    source = inspect.getsource(depreciation).lower()
    for forbidden in (
        "float(",
        ".quantize(",
        "round_half",
        "sqlmodel",
        "sqlalchemy",
        "get_session",
        "create_engine",
        "journalentry",
        "journalline",
        "accountrolebinding",
        "post_entry",
        "from .assets",
        "import aqorath.assets",
        '"6000"',
        '"1700"',
    ):
        assert forbidden not in source


def test_calculation_is_deterministic_and_does_not_mutate_or_replace_source_asset():
    from aqorath.fixed_asset_depreciation import (
        calculate_monthly_straight_line_depreciation,
    )

    asset = _asset(
        acquisition_cost=Decimal("777.7700"),
        residual_value=Decimal("77.77"),
        useful_life_months=13,
    )
    before = asset
    first = calculate_monthly_straight_line_depreciation(asset)
    second = calculate_monthly_straight_line_depreciation(asset)

    assert asset is before
    assert first == second
    assert first is not second
    assert asset == _asset(
        acquisition_cost=Decimal("777.7700"),
        residual_value=Decimal("77.77"),
        useful_life_months=13,
    )


def test_application_exposes_depreciation_calculation_as_thin_interface_agnostic_delegation(monkeypatch):
    import aqorath.application as application
    import aqorath.fixed_asset_depreciation as depreciation

    assert str(inspect.signature(application.calculate_fixed_asset_monthly_depreciation)) == (
        "(fixed_asset)"
    )

    calls = []
    sentinel = object()
    fixed_asset = object()

    def calculate(value):
        calls.append(value)
        return sentinel

    monkeypatch.setattr(
        depreciation,
        "calculate_monthly_straight_line_depreciation",
        calculate,
    )

    assert application.calculate_fixed_asset_monthly_depreciation(fixed_asset) is sentinel
    assert calls == [fixed_asset]

    source = inspect.getsource(application.calculate_fixed_asset_monthly_depreciation).lower()
    for forbidden in (
        "get_session",
        "quantize",
        "post",
        "account",
        "assets.",
    ):
        assert forbidden not in source
