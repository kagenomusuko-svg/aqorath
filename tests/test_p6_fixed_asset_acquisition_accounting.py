"""Phase 6O.1 — canonical fixed-asset acquisition accounting contracts.

Contracts only. Registration of FixedAsset metadata is not accounting recognition.
This phase freezes one pure economic/acquisition truth and its deterministic semantic
capitalization rule. Concrete accounts, confirmation, posting, persistence, fiscal
composition, source documents, and disposal remain later boundaries.
"""

from dataclasses import FrozenInstanceError, fields
from datetime import date
from decimal import Decimal
import inspect

import pytest


def _asset(**overrides):
    from aqorath.fixed_asset import FixedAsset

    values = {
        "id": 17,
        "entity_id": 3,
        "code": "EQ-017",
        "name": "Servidor de producción",
        "acquisition_date": date(2026, 3, 15),
        "in_service_date": date(2026, 4, 1),
        "acquisition_cost": Decimal("125000.0000"),
        "residual_value": Decimal("5000.00"),
        "useful_life_months": 60,
        "depreciation_method": "straight_line",
        "is_active": True,
    }
    values.update(overrides)
    return FixedAsset(**values)


def _fact(asset_class="computer_equipment", settlement_method="bank", **asset_overrides):
    from aqorath.fixed_asset_acquisition import create_fixed_asset_acquisition_fact

    return create_fixed_asset_acquisition_fact(
        _asset(**asset_overrides),
        asset_class,
        settlement_method,
    )


def test_acquisition_public_contract_and_exact_signatures_exist():
    import aqorath.fixed_asset_acquisition as acquisition

    assert acquisition.FixedAssetAcquisitionFact is not None
    assert acquisition.FixedAssetAcquisitionAccountingResolution is not None
    assert str(inspect.signature(acquisition.create_fixed_asset_acquisition_fact)) == (
        "(fixed_asset, asset_class, settlement_method)"
    )
    assert str(inspect.signature(acquisition.resolve_fixed_asset_acquisition_accounting)) == (
        "(acquisition_fact)"
    )


def test_acquisition_fact_is_frozen_value_truth_copied_from_persisted_fixed_asset():
    from aqorath.fixed_asset_acquisition import FixedAssetAcquisitionFact

    source = _asset(acquisition_cost=Decimal("125000.0000"))
    fact = _fact()

    assert [field.name for field in fields(FixedAssetAcquisitionFact)] == [
        "fixed_asset_id",
        "entity_id",
        "fixed_asset_code",
        "acquisition_date",
        "acquisition_cost",
        "asset_class",
        "settlement_method",
    ]
    assert fact.fixed_asset_id == source.id
    assert fact.entity_id == source.entity_id
    assert fact.fixed_asset_code == source.code
    assert fact.acquisition_date == source.acquisition_date
    assert fact.acquisition_cost.as_tuple() == source.acquisition_cost.as_tuple()
    assert fact.asset_class == "computer_equipment"
    assert fact.settlement_method == "bank"
    with pytest.raises(FrozenInstanceError):
        fact.asset_class = "machinery_tools"


def test_acquisition_requires_nominal_persisted_fixed_asset_before_fact_creation():
    from aqorath.fixed_asset_acquisition import create_fixed_asset_acquisition_fact

    with pytest.raises(TypeError):
        create_fixed_asset_acquisition_fact(object(), "computer_equipment", "bank")

    with pytest.raises((TypeError, ValueError)):
        create_fixed_asset_acquisition_fact(
            _asset(id=None),
            "computer_equipment",
            "bank",
        )


def test_asset_class_is_explicit_economic_classification_not_account_code_or_inference():
    from aqorath.fixed_asset_acquisition import create_fixed_asset_acquisition_fact

    allowed = (
        "furniture_equipment",
        "computer_equipment",
        "machinery_tools",
        "land_buildings",
    )
    for asset_class in allowed:
        fact = create_fixed_asset_acquisition_fact(_asset(), asset_class, "bank")
        assert fact.asset_class == asset_class

    for invalid in (
        "",
        " computer_equipment",
        "Computer_Equipment",
        "1201",
        "1202",
        "fixed_asset",
        None,
    ):
        with pytest.raises((TypeError, ValueError)):
            create_fixed_asset_acquisition_fact(_asset(), invalid, "bank")


def test_settlement_method_is_explicit_economic_fact_and_never_user_debit_credit_choice():
    from aqorath.fixed_asset_acquisition import create_fixed_asset_acquisition_fact

    for settlement_method in ("bank", "cash", "credit"):
        fact = create_fixed_asset_acquisition_fact(
            _asset(),
            "computer_equipment",
            settlement_method,
        )
        assert fact.settlement_method == settlement_method

    for invalid in ("", " bank", "Bank", "debit", "credit_side", "account_1101", None):
        with pytest.raises((TypeError, ValueError)):
            create_fixed_asset_acquisition_fact(
                _asset(),
                "computer_equipment",
                invalid,
            )

    signature = inspect.signature(create_fixed_asset_acquisition_fact)
    assert "side" not in signature.parameters
    assert "debit" not in signature.parameters
    assert "credit" not in signature.parameters
    assert "account_code" not in signature.parameters
    assert "account_id" not in signature.parameters


def test_acquisition_fact_does_not_infer_lifecycle_from_current_active_state():
    fact = _fact(is_active=False)
    assert fact.fixed_asset_id == 17
    assert fact.acquisition_date == date(2026, 3, 15)
    assert fact.acquisition_cost == Decimal("125000.0000")


def test_accounting_resolution_requires_nominal_acquisition_fact():
    from aqorath.fixed_asset_acquisition import resolve_fixed_asset_acquisition_accounting

    with pytest.raises(TypeError):
        resolve_fixed_asset_acquisition_accounting(object())


def test_each_asset_class_deterministically_selects_semantic_debit_role_without_codes():
    from aqorath.fixed_asset_acquisition import resolve_fixed_asset_acquisition_accounting

    expected = {
        "furniture_equipment": "fixed_asset_furniture_equipment",
        "computer_equipment": "fixed_asset_computer_equipment",
        "machinery_tools": "fixed_asset_machinery_tools",
        "land_buildings": "fixed_asset_land_buildings",
    }
    for asset_class, role in expected.items():
        resolution = resolve_fixed_asset_acquisition_accounting(_fact(asset_class=asset_class))
        assert resolution.outcome == "accounting_proposal"
        debit = resolution.proposal.lines[0]
        assert debit.account_role == role
        assert debit.side == "debit"


def test_each_settlement_method_deterministically_selects_semantic_credit_role():
    from aqorath.fixed_asset_acquisition import resolve_fixed_asset_acquisition_accounting

    expected = {
        "bank": "bank",
        "cash": "cash",
        "credit": "accounts_payable",
    }
    for settlement_method, role in expected.items():
        resolution = resolve_fixed_asset_acquisition_accounting(
            _fact(settlement_method=settlement_method)
        )
        credit = resolution.proposal.lines[1]
        assert credit.account_role == role
        assert credit.side == "credit"


def test_positive_acquisition_is_exact_balanced_two_line_accounting_proposal():
    from aqorath.economic_facts import AccountingProposal, ProposalLine
    from aqorath.fixed_asset_acquisition import resolve_fixed_asset_acquisition_accounting

    resolution = resolve_fixed_asset_acquisition_accounting(
        _fact(asset_overrides={}, acquisition_cost=Decimal("10.123400"))
    )
    assert isinstance(resolution.proposal, AccountingProposal)
    assert isinstance(resolution.proposal.lines, tuple)
    assert len(resolution.proposal.lines) == 2
    assert all(isinstance(line, ProposalLine) for line in resolution.proposal.lines)
    debit, credit = resolution.proposal.lines
    assert debit.amount.as_tuple() == Decimal("10.123400").as_tuple()
    assert credit.amount.as_tuple() == Decimal("10.123400").as_tuple()
    assert debit.amount == credit.amount


def test_zero_cost_acquisition_is_explicit_no_entry_outcome_not_zero_lines():
    from aqorath.fixed_asset_acquisition import resolve_fixed_asset_acquisition_accounting

    resolution = resolve_fixed_asset_acquisition_accounting(
        _fact(
            acquisition_cost=Decimal("0.0000"),
            residual_value=Decimal("0.0000"),
        )
    )
    assert resolution.outcome == "zero_cost_no_entry"
    assert resolution.proposal is None
    assert "zero" in resolution.explanation.lower()
    assert "no accounting entry" in resolution.explanation.lower()


def test_acquisition_explanation_is_deterministic_and_derived_from_same_truth():
    from aqorath.fixed_asset_acquisition import resolve_fixed_asset_acquisition_accounting

    first = resolve_fixed_asset_acquisition_accounting(
        _fact(asset_class="machinery_tools", settlement_method="credit")
    )
    second = resolve_fixed_asset_acquisition_accounting(
        _fact(asset_class="machinery_tools", settlement_method="credit")
    )
    assert first.explanation == second.explanation
    text = first.explanation.lower()
    assert "eq-017" in text
    assert "machinery_tools" in text
    assert "credit" in text
    assert "125000.0000" in text


def test_public_resolution_type_fails_closed_on_forged_outcome_or_accounting_lines():
    from aqorath.economic_facts import AccountingProposal, ProposalLine
    from aqorath.fixed_asset_acquisition import FixedAssetAcquisitionAccountingResolution

    fact = _fact()
    wrong = AccountingProposal(
        lines=(
            ProposalLine("cash", "debit", fact.acquisition_cost),
            ProposalLine("fixed_asset_computer_equipment", "credit", fact.acquisition_cost),
        ),
        explanation="forged",
    )
    with pytest.raises((TypeError, ValueError)):
        FixedAssetAcquisitionAccountingResolution(
            acquisition_fact=fact,
            outcome="accounting_proposal",
            proposal=wrong,
            explanation="forged",
        )

    with pytest.raises((TypeError, ValueError)):
        FixedAssetAcquisitionAccountingResolution(
            acquisition_fact=fact,
            outcome="zero_cost_no_entry",
            proposal=None,
            explanation="forged",
        )


def test_acquisition_accounting_contains_no_hardcoded_catalog_or_second_accounting_authority():
    import aqorath.fixed_asset_acquisition as acquisition

    source = inspect.getsource(acquisition).lower()
    for forbidden in (
        "1201",
        "1202",
        "1203",
        "1204",
        "sqlmodel",
        "sqlalchemy",
        "sqlite3",
        "get_session",
        "post_entry",
        "_stage_entry_in_session",
        "account_bindings",
        "resolve_account_by_code",
        "confirmation",
        "posting",
        "from .assets",
        "import aqorath.assets",
    ):
        assert forbidden not in source


def test_acquisition_accounting_is_pure_deterministic_and_does_not_mutate_fixed_asset():
    from aqorath.fixed_asset_acquisition import (
        create_fixed_asset_acquisition_fact,
        resolve_fixed_asset_acquisition_accounting,
    )

    source = _asset()
    before = source
    fact1 = create_fixed_asset_acquisition_fact(source, "computer_equipment", "bank")
    fact2 = create_fixed_asset_acquisition_fact(source, "computer_equipment", "bank")
    result1 = resolve_fixed_asset_acquisition_accounting(fact1)
    result2 = resolve_fixed_asset_acquisition_accounting(fact2)
    assert source == before
    assert fact1 == fact2
    assert result1 == result2


def test_application_exposes_acquisition_fact_and_accounting_as_thin_interface_agnostic_delegations(monkeypatch):
    import aqorath.application as application
    import aqorath.fixed_asset_acquisition as acquisition

    assert str(inspect.signature(application.create_fixed_asset_acquisition_fact)) == (
        "(fixed_asset, asset_class, settlement_method)"
    )
    assert str(inspect.signature(application.resolve_fixed_asset_acquisition_accounting)) == (
        "(acquisition_fact)"
    )

    asset = _asset()
    sentinel_fact = object()
    sentinel_resolution = object()
    calls = []

    def fake_create(fixed_asset, asset_class, settlement_method):
        calls.append(("create", fixed_asset, asset_class, settlement_method))
        return sentinel_fact

    def fake_resolve(acquisition_fact):
        calls.append(("resolve", acquisition_fact))
        return sentinel_resolution

    monkeypatch.setattr(acquisition, "create_fixed_asset_acquisition_fact", fake_create)
    monkeypatch.setattr(acquisition, "resolve_fixed_asset_acquisition_accounting", fake_resolve)

    assert application.create_fixed_asset_acquisition_fact(
        asset,
        "computer_equipment",
        "bank",
    ) is sentinel_fact
    assert application.resolve_fixed_asset_acquisition_accounting(
        sentinel_fact
    ) is sentinel_resolution
    assert calls == [
        ("create", asset, "computer_equipment", "bank"),
        ("resolve", sentinel_fact),
    ]
