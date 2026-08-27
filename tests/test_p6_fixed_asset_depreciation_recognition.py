"""Phase 6I.1 — canonical fixed-asset depreciation recognition contracts.

Contracts only. One already-calculated and already-allocated depreciation period becomes
an explicit dated economic fact. This phase does not generate a calendar, select accounts,
resolve debit/credit, post, persist, or infer recognition dates from asset lifecycle data.
"""

from dataclasses import FrozenInstanceError, fields, replace
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
import inspect
from types import SimpleNamespace

import pytest


def _allocation():
    from aqorath.fixed_asset import FixedAsset
    from aqorath.fixed_asset_depreciation import (
        calculate_monthly_straight_line_depreciation,
    )
    from aqorath.fixed_asset_depreciation_allocation import (
        FixedAssetDepreciationAllocationPolicy,
        allocate_monthly_depreciation,
    )

    asset = FixedAsset(
        id=41,
        entity_id=7,
        code="EQ-001",
        name="Equipo de cómputo",
        acquisition_date=date(2026, 1, 15),
        in_service_date=date(2026, 2, 1),
        acquisition_cost=Decimal("100.00"),
        residual_value=Decimal("0.00"),
        useful_life_months=3,
        depreciation_method="straight_line",
        is_active=True,
    )
    calculation = calculate_monthly_straight_line_depreciation(asset)
    policy = FixedAssetDepreciationAllocationPolicy(
        policy_key="monthly-monetary-allocation-v1",
        quantizer=Decimal("0.01"),
        rounding_mode=ROUND_HALF_UP,
        remainder_policy="final_period",
        source_ref="EXPLICIT:6H",
    )
    return allocate_monthly_depreciation(calculation, policy)


def test_recognition_public_fact_is_frozen_dated_economic_truth_not_accounting_or_schedule():
    import aqorath.fixed_asset_depreciation_recognition as recognition

    allocation = _allocation()
    fact = recognition.declare_fixed_asset_depreciation_recognition(
        allocation,
        1,
        date(2026, 2, 28),
        "EXPLICIT:6I",
    )

    assert [field.name for field in fields(recognition.FixedAssetDepreciationRecognitionFact)] == [
        "allocation",
        "period_number",
        "recognition_date",
        "recognition_source_ref",
        "amount",
        "allocation_kind",
    ]
    with pytest.raises(FrozenInstanceError):
        fact.amount = Decimal("0.00")

    forbidden = {
        "account_id",
        "account_code",
        "account_role",
        "side",
        "debit",
        "credit",
        "journal_entry_id",
        "journal_line_id",
        "next_recognition_date",
        "period_start",
        "period_end",
    }
    assert forbidden.isdisjoint({field.name for field in fields(fact)})


def test_recognition_factory_has_one_exact_explicit_signature_without_defaults():
    import aqorath.fixed_asset_depreciation_recognition as recognition

    signature = inspect.signature(
        recognition.declare_fixed_asset_depreciation_recognition
    )
    assert str(signature) == (
        "(allocation, period_number, recognition_date, recognition_source_ref)"
    )
    assert all(
        parameter.default is inspect._empty
        for parameter in signature.parameters.values()
    )


def test_recognition_requires_nominal_phase_6h_allocation_before_selecting_period():
    from aqorath.fixed_asset_depreciation_recognition import (
        declare_fixed_asset_depreciation_recognition,
    )

    with pytest.raises(TypeError):
        declare_fixed_asset_depreciation_recognition(
            object(), 1, date(2026, 2, 28), "EXPLICIT:6I"
        )

    shape = SimpleNamespace(
        periods=(SimpleNamespace(period_number=1, amount=Decimal("33.33")),),
        calculation=SimpleNamespace(in_service_date=date(2026, 2, 1)),
    )
    with pytest.raises(TypeError):
        declare_fixed_asset_depreciation_recognition(
            shape, 1, date(2026, 2, 28), "EXPLICIT:6I"
        )


def test_recognition_selects_exact_existing_period_and_copies_amount_scale_and_kind():
    from aqorath.fixed_asset_depreciation_recognition import (
        declare_fixed_asset_depreciation_recognition,
    )

    allocation = _allocation()
    first = declare_fixed_asset_depreciation_recognition(
        allocation, 1, date(2026, 2, 28), "EXPLICIT:first"
    )
    final = declare_fixed_asset_depreciation_recognition(
        allocation, 3, date(2026, 4, 30), "EXPLICIT:final"
    )

    assert first.allocation is allocation
    assert first.period_number == 1
    assert first.amount.as_tuple() == Decimal("33.33").as_tuple()
    assert first.allocation_kind == "regular"
    assert final.period_number == 3
    assert final.amount.as_tuple() == Decimal("33.34").as_tuple()
    assert final.allocation_kind == "final_remainder"


def test_recognition_rejects_invalid_or_out_of_range_period_identity_without_fallback():
    from aqorath.fixed_asset_depreciation_recognition import (
        declare_fixed_asset_depreciation_recognition,
    )

    allocation = _allocation()
    for value in (True, False, 0, -1, 4, 1.0, "1", None):
        with pytest.raises((TypeError, ValueError)):
            declare_fixed_asset_depreciation_recognition(
                allocation,
                value,
                date(2026, 2, 28),
                "EXPLICIT:6I",
            )


def test_recognition_date_is_explicit_exact_date_and_cannot_precede_in_service_date():
    from aqorath.fixed_asset_depreciation_recognition import (
        declare_fixed_asset_depreciation_recognition,
    )

    allocation = _allocation()
    fact = declare_fixed_asset_depreciation_recognition(
        allocation,
        1,
        date(2026, 2, 1),
        "EXPLICIT:boundary",
    )
    assert fact.recognition_date == date(2026, 2, 1)

    with pytest.raises(ValueError):
        declare_fixed_asset_depreciation_recognition(
            allocation,
            1,
            date(2026, 1, 31),
            "EXPLICIT:before-service",
        )
    with pytest.raises(TypeError):
        declare_fixed_asset_depreciation_recognition(
            allocation,
            1,
            datetime(2026, 2, 28, 12, 0),
            "EXPLICIT:datetime",
        )
    with pytest.raises(TypeError):
        declare_fixed_asset_depreciation_recognition(
            allocation,
            1,
            "2026-02-28",
            "EXPLICIT:string",
        )


def test_recognition_source_ref_is_explicit_preserved_and_never_normalized_or_defaulted():
    from aqorath.fixed_asset_depreciation_recognition import (
        declare_fixed_asset_depreciation_recognition,
    )

    allocation = _allocation()
    fact = declare_fixed_asset_depreciation_recognition(
        allocation,
        1,
        date(2026, 2, 28),
        "  POLICY:board-approved-v1  ",
    )
    assert fact.recognition_source_ref == "  POLICY:board-approved-v1  "

    for value in ("", "   ", None, 7):
        with pytest.raises((TypeError, ValueError)):
            declare_fixed_asset_depreciation_recognition(
                allocation,
                1,
                date(2026, 2, 28),
                value,
            )


def test_explicit_date_changes_only_temporal_declaration_not_allocated_monetary_truth():
    from aqorath.fixed_asset_depreciation_recognition import (
        declare_fixed_asset_depreciation_recognition,
    )

    allocation = _allocation()
    month_end = declare_fixed_asset_depreciation_recognition(
        allocation, 1, date(2026, 2, 28), "EXPLICIT:month-end"
    )
    next_month = declare_fixed_asset_depreciation_recognition(
        allocation, 1, date(2026, 3, 5), "EXPLICIT:next-month"
    )

    assert month_end.recognition_date != next_month.recognition_date
    assert month_end.amount.as_tuple() == next_month.amount.as_tuple()
    assert month_end.allocation_kind == next_month.allocation_kind
    assert month_end.period_number == next_month.period_number == 1
    assert month_end.allocation is next_month.allocation is allocation


def test_public_fact_rejects_forged_period_amount_kind_or_temporal_provenance():
    from aqorath.fixed_asset_depreciation_recognition import (
        declare_fixed_asset_depreciation_recognition,
    )

    fact = declare_fixed_asset_depreciation_recognition(
        _allocation(),
        1,
        date(2026, 2, 28),
        "EXPLICIT:6I",
    )

    with pytest.raises((TypeError, ValueError)):
        replace(fact, period_number=2)
    with pytest.raises((TypeError, ValueError)):
        replace(fact, amount=Decimal("33.34"))
    with pytest.raises((TypeError, ValueError)):
        replace(fact, amount=Decimal("33.330"))
    with pytest.raises((TypeError, ValueError)):
        replace(fact, allocation_kind="final_remainder")
    with pytest.raises((TypeError, ValueError)):
        replace(fact, recognition_date=date(2026, 1, 31))
    with pytest.raises((TypeError, ValueError)):
        replace(fact, recognition_source_ref="")


def test_recognition_does_not_generate_calendar_or_enforce_hidden_month_end_convention():
    from aqorath.fixed_asset_depreciation_recognition import (
        declare_fixed_asset_depreciation_recognition,
    )

    allocation = _allocation()
    arbitrary_valid_date = date(2026, 2, 17)
    fact = declare_fixed_asset_depreciation_recognition(
        allocation,
        1,
        arbitrary_valid_date,
        "EXPLICIT:chosen-date",
    )

    assert fact.recognition_date == arbitrary_valid_date
    assert not hasattr(fact, "next_recognition_date")
    assert not hasattr(fact, "period_start")
    assert not hasattr(fact, "period_end")


def test_recognition_is_pure_and_never_recalculates_reallocates_rounds_resolves_or_posts():
    import aqorath.fixed_asset_depreciation_recognition as recognition

    source = inspect.getsource(recognition).lower()
    for forbidden in (
        "float(",
        "quantize",
        "calculate_monthly_straight_line_depreciation",
        "allocate_monthly_depreciation(",
        "get_session",
        "sqlmodel",
        "sqlalchemy",
        "fixed_asset_repository",
        "account_resolution",
        "account_bindings",
        "post_entry",
        "posting",
        "journalentry",
        "journalline",
        "timedelta",
        "relativedelta",
        "calendar.",
        "from .assets",
    ):
        assert forbidden not in source


def test_recognition_is_deterministic_and_does_not_mutate_or_replace_allocation():
    from aqorath.fixed_asset_depreciation_recognition import (
        declare_fixed_asset_depreciation_recognition,
    )

    allocation = _allocation()
    before = allocation
    first = declare_fixed_asset_depreciation_recognition(
        allocation, 2, date(2026, 3, 31), "EXPLICIT:6I"
    )
    second = declare_fixed_asset_depreciation_recognition(
        allocation, 2, date(2026, 3, 31), "EXPLICIT:6I"
    )

    assert allocation is before
    assert first == second
    assert first is not second
    assert first.allocation is second.allocation is allocation


def test_application_exposes_recognition_as_thin_interface_agnostic_delegation(monkeypatch):
    import aqorath.application as application
    import aqorath.fixed_asset_depreciation_recognition as recognition

    assert str(
        inspect.signature(application.declare_fixed_asset_depreciation_recognition)
    ) == "(allocation, period_number, recognition_date, recognition_source_ref)"

    calls = []
    sentinel = object()
    allocation = object()
    recognition_date = object()

    def declare(value_allocation, period_number, value_date, source_ref):
        calls.append((value_allocation, period_number, value_date, source_ref))
        return sentinel

    monkeypatch.setattr(
        recognition,
        "declare_fixed_asset_depreciation_recognition",
        declare,
    )

    assert application.declare_fixed_asset_depreciation_recognition(
        allocation,
        9,
        recognition_date,
        "SOURCE",
    ) is sentinel
    assert calls == [(allocation, 9, recognition_date, "SOURCE")]

    source = inspect.getsource(
        application.declare_fixed_asset_depreciation_recognition
    ).lower()
    for forbidden in (
        "get_session",
        "account",
        "post",
        "calculate",
        "allocate",
        "datetime",
        "timedelta",
    ):
        assert forbidden not in source
