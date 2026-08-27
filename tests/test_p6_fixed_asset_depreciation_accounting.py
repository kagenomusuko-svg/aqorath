"""Phase 6J.1 — canonical fixed-asset depreciation accounting contracts.

Contracts only. One explicit dated Phase 6I recognition fact resolves to semantic
accounting truth. Positive depreciation becomes a canonical two-line AccountingProposal;
zero depreciation remains an explicit non-postable outcome. Concrete accounts,
persistence, confirmation, and posting remain outside this phase.
"""

from dataclasses import FrozenInstanceError, fields, replace
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import inspect
from types import SimpleNamespace

import pytest


def _recognition(
    *,
    acquisition_cost=Decimal("100.00"),
    residual_value=Decimal("0.00"),
    useful_life_months=3,
    period_number=1,
    recognition_date=date(2026, 2, 28),
):
    from aqorath.fixed_asset import FixedAsset
    from aqorath.fixed_asset_depreciation import (
        calculate_monthly_straight_line_depreciation,
    )
    from aqorath.fixed_asset_depreciation_allocation import (
        FixedAssetDepreciationAllocationPolicy,
        allocate_monthly_depreciation,
    )
    from aqorath.fixed_asset_depreciation_recognition import (
        declare_fixed_asset_depreciation_recognition,
    )

    asset = FixedAsset(
        id=41,
        entity_id=7,
        code="EQ-001",
        name="Equipo de cómputo",
        acquisition_date=date(2026, 1, 15),
        in_service_date=date(2026, 2, 1),
        acquisition_cost=acquisition_cost,
        residual_value=residual_value,
        useful_life_months=useful_life_months,
        depreciation_method="straight_line",
        is_active=True,
    )
    calculation = calculate_monthly_straight_line_depreciation(asset)
    allocation = allocate_monthly_depreciation(
        calculation,
        FixedAssetDepreciationAllocationPolicy(
            policy_key="monthly-monetary-allocation-v1",
            quantizer=Decimal("0.01"),
            rounding_mode=ROUND_HALF_UP,
            remainder_policy="final_period",
            source_ref="EXPLICIT:6H",
        ),
    )
    return declare_fixed_asset_depreciation_recognition(
        allocation,
        period_number,
        recognition_date,
        "EXPLICIT:6I",
    )


def test_accounting_resolution_public_type_is_frozen_semantic_truth_not_resolved_or_posted():
    import aqorath.fixed_asset_depreciation_accounting as accounting

    result = accounting.resolve_fixed_asset_depreciation_accounting(_recognition())

    assert [field.name for field in fields(accounting.FixedAssetDepreciationAccountingResolution)] == [
        "recognition_fact",
        "outcome",
        "proposal",
        "explanation",
    ]
    with pytest.raises(FrozenInstanceError):
        result.outcome = "other"

    forbidden = {
        "account_id",
        "account_code",
        "journal_entry_id",
        "journal_line_id",
        "posting_instruction",
        "entry_id",
    }
    assert forbidden.isdisjoint({field.name for field in fields(result)})


def test_accounting_resolver_has_one_exact_nominal_signature_without_user_side_or_role_choices():
    import aqorath.fixed_asset_depreciation_accounting as accounting

    signature = inspect.signature(accounting.resolve_fixed_asset_depreciation_accounting)
    assert str(signature) == "(recognition_fact)"
    assert all(
        parameter.default is inspect._empty
        for parameter in signature.parameters.values()
    )


def test_accounting_resolution_requires_nominal_phase_6i_recognition_fact():
    from aqorath.fixed_asset_depreciation_accounting import (
        resolve_fixed_asset_depreciation_accounting,
    )

    with pytest.raises(TypeError):
        resolve_fixed_asset_depreciation_accounting(object())

    shape = SimpleNamespace(
        amount=Decimal("33.33"),
        period_number=1,
        recognition_date=date(2026, 2, 28),
        allocation_kind="regular",
    )
    with pytest.raises(TypeError):
        resolve_fixed_asset_depreciation_accounting(shape)


def test_positive_recognition_becomes_canonical_balanced_two_line_accounting_proposal():
    from aqorath.economic_facts import AccountingProposal, ProposalLine
    from aqorath.fixed_asset_depreciation_accounting import (
        resolve_fixed_asset_depreciation_accounting,
    )

    recognition = _recognition()
    result = resolve_fixed_asset_depreciation_accounting(recognition)

    assert result.recognition_fact is recognition
    assert result.outcome == "accounting_proposal"
    assert isinstance(result.proposal, AccountingProposal)
    assert isinstance(result.proposal.lines, tuple)
    assert len(result.proposal.lines) == 2
    assert all(isinstance(line, ProposalLine) for line in result.proposal.lines)
    assert [line.account_role for line in result.proposal.lines] == [
        "depreciation_expense",
        "accumulated_depreciation",
    ]
    assert [line.side for line in result.proposal.lines] == ["debit", "credit"]
    assert [line.amount.as_tuple() for line in result.proposal.lines] == [
        Decimal("33.33").as_tuple(),
        Decimal("33.33").as_tuple(),
    ]
    assert sum(
        (line.amount for line in result.proposal.lines if line.side == "debit"),
        Decimal("0"),
    ) == sum(
        (line.amount for line in result.proposal.lines if line.side == "credit"),
        Decimal("0"),
    )


def test_depreciation_semantics_choose_debit_credit_and_roles_as_system_rule_not_user_input():
    from aqorath.fixed_asset_depreciation_accounting import (
        resolve_fixed_asset_depreciation_accounting,
    )

    result = resolve_fixed_asset_depreciation_accounting(_recognition())
    debit, credit = result.proposal.lines

    assert (debit.account_role, debit.side) == ("depreciation_expense", "debit")
    assert (credit.account_role, credit.side) == (
        "accumulated_depreciation",
        "credit",
    )
    assert "debit" not in inspect.signature(
        resolve_fixed_asset_depreciation_accounting
    ).parameters
    assert "credit" not in inspect.signature(
        resolve_fixed_asset_depreciation_accounting
    ).parameters
    assert "account_role" not in inspect.signature(
        resolve_fixed_asset_depreciation_accounting
    ).parameters


def test_positive_explanation_is_deterministic_and_reports_only_confirmed_recognition_truth():
    from aqorath.fixed_asset_depreciation_accounting import (
        resolve_fixed_asset_depreciation_accounting,
    )

    result = resolve_fixed_asset_depreciation_accounting(_recognition())
    expected = (
        "Fixed asset depreciation recognition: asset EQ-001, period 1, "
        "recognition date 2026-02-28, amount 33.33. "
        "Depreciation expense recognized (debit), accumulated depreciation increased (credit)."
    )

    assert result.explanation == expected
    assert result.proposal.explanation == expected


def test_final_remainder_amount_and_decimal_scale_are_preserved_without_recalculation():
    from aqorath.fixed_asset_depreciation_accounting import (
        resolve_fixed_asset_depreciation_accounting,
    )

    recognition = _recognition(
        period_number=3,
        recognition_date=date(2026, 4, 30),
    )
    assert recognition.amount.as_tuple() == Decimal("33.34").as_tuple()
    assert recognition.allocation_kind == "final_remainder"

    result = resolve_fixed_asset_depreciation_accounting(recognition)
    assert [line.amount.as_tuple() for line in result.proposal.lines] == [
        recognition.amount.as_tuple(),
        recognition.amount.as_tuple(),
    ]
    assert "amount 33.34" in result.explanation
    assert "period 3" in result.explanation
    assert "2026-04-30" in result.explanation


def test_zero_recognition_is_explicit_no_entry_outcome_not_invalid_zero_line_proposal():
    from aqorath.fixed_asset_depreciation_accounting import (
        resolve_fixed_asset_depreciation_accounting,
    )

    recognition = _recognition(
        acquisition_cost=Decimal("100.00"),
        residual_value=Decimal("100.00"),
    )
    assert recognition.amount.as_tuple() == Decimal("0.00").as_tuple()

    result = resolve_fixed_asset_depreciation_accounting(recognition)
    assert result.recognition_fact is recognition
    assert result.outcome == "zero_amount_no_entry"
    assert result.proposal is None
    assert result.explanation == (
        "Fixed asset depreciation recognition: asset EQ-001, period 1, "
        "recognition date 2026-02-28, amount 0.00. "
        "Zero allocated depreciation produces no accounting entry."
    )


def test_zero_outcome_does_not_silently_drop_recognition_or_construct_zero_proposal_lines(monkeypatch):
    import aqorath.economic_facts as economic_facts
    import aqorath.fixed_asset_depreciation_accounting as accounting

    recognition = _recognition(
        acquisition_cost=Decimal("50.00"),
        residual_value=Decimal("50.00"),
    )
    calls = []

    original_line = economic_facts.ProposalLine

    def forbidden_line(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("zero recognition must not create ProposalLine")

    monkeypatch.setattr(economic_facts, "ProposalLine", forbidden_line)
    result = accounting.resolve_fixed_asset_depreciation_accounting(recognition)

    assert result.recognition_fact is recognition
    assert result.outcome == "zero_amount_no_entry"
    assert result.proposal is None
    assert calls == []
    assert original_line is not None


def test_public_resolution_type_fails_closed_on_forged_outcome_proposal_lines_or_explanation():
    from aqorath.economic_facts import AccountingProposal, ProposalLine
    from aqorath.fixed_asset_depreciation_accounting import (
        resolve_fixed_asset_depreciation_accounting,
    )

    positive = resolve_fixed_asset_depreciation_accounting(_recognition())
    zero = resolve_fixed_asset_depreciation_accounting(
        _recognition(
            acquisition_cost=Decimal("10.00"),
            residual_value=Decimal("10.00"),
        )
    )

    with pytest.raises((TypeError, ValueError)):
        replace(positive, outcome="zero_amount_no_entry")
    with pytest.raises((TypeError, ValueError)):
        replace(positive, proposal=None)
    with pytest.raises((TypeError, ValueError)):
        replace(positive, explanation="forged")
    with pytest.raises((TypeError, ValueError)):
        replace(zero, outcome="accounting_proposal")
    with pytest.raises((TypeError, ValueError)):
        replace(zero, proposal=positive.proposal)
    with pytest.raises((TypeError, ValueError)):
        replace(zero, explanation="forged")

    wrong_roles = AccountingProposal(
        lines=(
            ProposalLine("utilities_expense", "debit", Decimal("33.33")),
            ProposalLine("bank", "credit", Decimal("33.33")),
        ),
        explanation=positive.explanation,
    )
    with pytest.raises((TypeError, ValueError)):
        replace(positive, proposal=wrong_roles)


def test_depreciation_account_roles_remain_semantic_and_resolvable_by_existing_binding_authority():
    from aqorath import account_bindings
    from aqorath.fixed_asset_depreciation_accounting import (
        resolve_fixed_asset_depreciation_accounting,
    )

    result = resolve_fixed_asset_depreciation_accounting(_recognition())
    roles = tuple(line.account_role for line in result.proposal.lines)

    assert roles == ("depreciation_expense", "accumulated_depreciation")
    for role in roles:
        account_bindings._validate_role(role)


def test_accounting_resolution_contains_no_hardcoded_accounts_or_legacy_asset_authority():
    import aqorath.fixed_asset_depreciation_accounting as accounting

    source = inspect.getsource(accounting).lower()
    for forbidden in (
        '"6000"',
        '"1700"',
        "resolve_account_by_code",
        "account_bindings",
        "get_account_binding",
        "get_session",
        "sqlmodel",
        "sqlalchemy",
        "journalentry",
        "journalline",
        "post_entry",
        "from .assets",
        "import aqorath.assets",
    ):
        assert forbidden not in source


def test_accounting_resolution_is_pure_and_never_recalculates_reallocates_or_rerecognizes():
    import aqorath.fixed_asset_depreciation_accounting as accounting

    source = inspect.getsource(accounting).lower()
    for forbidden in (
        "calculate_monthly_straight_line_depreciation",
        "allocate_monthly_depreciation(",
        "declare_fixed_asset_depreciation_recognition(",
        "resolve_economic_fact(",
        "quantize",
        "float(",
        "commit(",
        "rollback(",
    ):
        assert forbidden not in source


def test_accounting_resolution_is_deterministic_and_does_not_mutate_recognition_truth():
    from aqorath.fixed_asset_depreciation_accounting import (
        resolve_fixed_asset_depreciation_accounting,
    )

    recognition = _recognition(
        period_number=2,
        recognition_date=date(2026, 3, 31),
    )
    before = recognition

    first = resolve_fixed_asset_depreciation_accounting(recognition)
    second = resolve_fixed_asset_depreciation_accounting(recognition)

    assert recognition is before
    assert first == second
    assert first is not second
    assert first.recognition_fact is second.recognition_fact is recognition
    assert first.proposal is not second.proposal
    assert first.proposal.lines is not second.proposal.lines


def test_application_exposes_accounting_resolution_as_thin_interface_agnostic_delegation(monkeypatch):
    import aqorath.application as application
    import aqorath.fixed_asset_depreciation_accounting as accounting

    assert str(
        inspect.signature(application.resolve_fixed_asset_depreciation_accounting)
    ) == "(recognition_fact)"

    calls = []
    recognition = object()
    sentinel = object()

    def resolve(value):
        calls.append(value)
        return sentinel

    monkeypatch.setattr(
        accounting,
        "resolve_fixed_asset_depreciation_accounting",
        resolve,
    )

    assert application.resolve_fixed_asset_depreciation_accounting(recognition) is sentinel
    assert calls == [recognition]

    source = inspect.getsource(
        application.resolve_fixed_asset_depreciation_accounting
    ).lower()
    for forbidden in (
        "get_session",
        "resolve_account",
        "binding",
        "post_entry",
        "calculate",
        "allocate",
        "recognition_date",
    ):
        assert forbidden not in source
