"""Phase 6K.1 — configured depreciation confirmation with dated provenance."""

from dataclasses import FrozenInstanceError, fields, replace
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from inspect import Parameter, getsource, signature

import pytest


def _accounting_resolution(
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
    from aqorath.fixed_asset_depreciation_accounting import (
        resolve_fixed_asset_depreciation_accounting,
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
    recognition = declare_fixed_asset_depreciation_recognition(
        allocation,
        period_number,
        recognition_date,
        "EXPLICIT:6I",
    )
    return resolve_fixed_asset_depreciation_accounting(recognition)


def _resolved_positive_proposal(accounting_resolution, *, debit_id=11, credit_id=12):
    from aqorath.account_resolution import (
        ResolvedAccountingProposal,
        ResolvedProposalLine,
    )

    amount = accounting_resolution.recognition_fact.amount
    return ResolvedAccountingProposal(
        lines=[
            ResolvedProposalLine(
                account_role="depreciation_expense",
                account_id=debit_id,
                account_code="DEP-EXP",
                account_name="Depreciation expense",
                side="debit",
                amount=amount,
            ),
            ResolvedProposalLine(
                account_role="accumulated_depreciation",
                account_id=credit_id,
                account_code="ACC-DEP",
                account_name="Accumulated depreciation",
                side="credit",
                amount=amount,
            ),
        ],
        explanation=accounting_resolution.explanation,
    )


def test_confirmation_public_types_are_frozen_minimal_provenance_bearing_truth():
    from aqorath.fixed_asset_depreciation_confirmation import (
        ConfirmedFixedAssetDepreciation,
        FixedAssetDepreciationConfirmationSnapshot,
    )

    assert FixedAssetDepreciationConfirmationSnapshot.__dataclass_params__.frozen
    assert ConfirmedFixedAssetDepreciation.__dataclass_params__.frozen
    assert [field.name for field in fields(FixedAssetDepreciationConfirmationSnapshot)] == [
        "accounting_resolution",
        "confirmation_snapshot",
    ]
    assert [field.name for field in fields(ConfirmedFixedAssetDepreciation)] == [
        "snapshot",
        "confirmed_proposal",
    ]


def test_confirmation_api_has_exact_explicit_signatures_without_defaults():
    from aqorath.fixed_asset_depreciation_confirmation import (
        confirm_fixed_asset_depreciation,
        prepare_fixed_asset_depreciation_confirmation,
    )

    expected = {
        prepare_fixed_asset_depreciation_confirmation: ["session", "accounting_resolution"],
        confirm_fixed_asset_depreciation: ["snapshot"],
    }
    for function, names in expected.items():
        sig = signature(function)
        assert list(sig.parameters) == names
        for parameter in sig.parameters.values():
            assert parameter.default is Parameter.empty
            assert parameter.kind is Parameter.POSITIONAL_OR_KEYWORD


def test_preparation_requires_nominal_phase_6j_resolution_before_binding_lookup(monkeypatch):
    import aqorath.account_bindings
    from aqorath.fixed_asset_depreciation_confirmation import (
        prepare_fixed_asset_depreciation_confirmation,
    )

    calls = []
    monkeypatch.setattr(
        aqorath.account_bindings,
        "get_account_bindings",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    with pytest.raises(TypeError):
        prepare_fixed_asset_depreciation_confirmation(object(), object())
    assert calls == []


def test_positive_preparation_reuses_existing_binding_resolution_and_confirmation_authorities_once(monkeypatch):
    import aqorath.account_bindings
    import aqorath.account_resolution
    import aqorath.confirmation
    from aqorath.fixed_asset_depreciation_confirmation import (
        FixedAssetDepreciationConfirmationSnapshot,
        prepare_fixed_asset_depreciation_confirmation,
    )

    accounting_resolution = _accounting_resolution()
    resolved = _resolved_positive_proposal(accounting_resolution)
    real_create_snapshot = aqorath.confirmation.create_confirmation_snapshot
    session = object()
    events = []

    def load_bindings(supplied_session, roles):
        events.append(("bindings", supplied_session, roles))
        return {
            "depreciation_expense": "DEP-EXP",
            "accumulated_depreciation": "ACC-DEP",
        }

    def resolve_accounts(supplied_session, proposal, bindings):
        events.append(("accounts", supplied_session, proposal, bindings))
        return resolved

    def create_snapshot(supplied_resolved):
        events.append(("snapshot", supplied_resolved))
        return real_create_snapshot(supplied_resolved)

    monkeypatch.setattr(aqorath.account_bindings, "get_account_bindings", load_bindings)
    monkeypatch.setattr(aqorath.account_resolution, "resolve_proposal_accounts", resolve_accounts)
    monkeypatch.setattr(aqorath.confirmation, "create_confirmation_snapshot", create_snapshot)

    prepared = prepare_fixed_asset_depreciation_confirmation(
        session,
        accounting_resolution,
    )

    assert isinstance(prepared, FixedAssetDepreciationConfirmationSnapshot)
    assert prepared.accounting_resolution is accounting_resolution
    assert events == [
        (
            "bindings",
            session,
            ("depreciation_expense", "accumulated_depreciation"),
        ),
        (
            "accounts",
            session,
            accounting_resolution.proposal,
            {
                "depreciation_expense": "DEP-EXP",
                "accumulated_depreciation": "ACC-DEP",
            },
        ),
        ("snapshot", resolved),
    ]


def test_positive_snapshot_preserves_concrete_lines_exact_amount_scale_explanation_and_recognition_date(monkeypatch):
    import aqorath.account_bindings
    import aqorath.account_resolution
    from aqorath.fixed_asset_depreciation_confirmation import (
        prepare_fixed_asset_depreciation_confirmation,
    )

    accounting_resolution = _accounting_resolution(period_number=3, recognition_date=date(2026, 4, 30))
    resolved = _resolved_positive_proposal(accounting_resolution)
    monkeypatch.setattr(
        aqorath.account_bindings,
        "get_account_bindings",
        lambda session, roles: {
            "depreciation_expense": "DEP-EXP",
            "accumulated_depreciation": "ACC-DEP",
        },
    )
    monkeypatch.setattr(
        aqorath.account_resolution,
        "resolve_proposal_accounts",
        lambda session, proposal, bindings: resolved,
    )

    prepared = prepare_fixed_asset_depreciation_confirmation(object(), accounting_resolution)
    snapshot = prepared.confirmation_snapshot

    assert snapshot is not None
    assert tuple(line.account_role for line in snapshot.lines) == (
        "depreciation_expense",
        "accumulated_depreciation",
    )
    assert tuple(line.side for line in snapshot.lines) == ("debit", "credit")
    assert snapshot.lines[0].amount.as_tuple() == Decimal("33.34").as_tuple()
    assert snapshot.lines[1].amount.as_tuple() == Decimal("33.34").as_tuple()
    assert snapshot.explanation == accounting_resolution.explanation
    assert (
        prepared.accounting_resolution.recognition_fact.recognition_date
        == date(2026, 4, 30)
    )


def test_real_configured_preparation_uses_persisted_bindings_and_supplied_session(monkeypatch):
    from sqlalchemy import create_engine
    from sqlmodel import Session, SQLModel
    import aqorath.catalog
    from aqorath.fixed_asset_depreciation_confirmation import (
        prepare_fixed_asset_depreciation_confirmation,
    )
    from aqorath.models import Account, AccountRoleBinding

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    accounting_resolution = _accounting_resolution()

    with Session(engine) as session:
        expense = Account(code="5106", name="Depreciación y amortización", nature="Deudora")
        accumulated = Account(code="1205", name="Depreciación acumulada", nature="Acreedora")
        session.add(expense)
        session.add(accumulated)
        session.commit()
        session.refresh(expense)
        session.refresh(accumulated)
        session.add(AccountRoleBinding(role="depreciation_expense", account_id=expense.id))
        session.add(AccountRoleBinding(role="accumulated_depreciation", account_id=accumulated.id))
        session.commit()

        account_map = {"5106": expense, "1205": accumulated}
        monkeypatch.setattr(
            aqorath.catalog,
            "resolve_account_by_code",
            lambda supplied_session, code: account_map.get(code),
        )

        prepared = prepare_fixed_asset_depreciation_confirmation(
            session,
            accounting_resolution,
        )

    lines = prepared.confirmation_snapshot.lines
    assert lines[0].account_id == expense.id
    assert lines[0].account_code == "5106"
    assert lines[0].side == "debit"
    assert lines[1].account_id == accumulated.id
    assert lines[1].account_code == "1205"
    assert lines[1].side == "credit"
    assert lines[0].amount.as_tuple() == Decimal("33.33").as_tuple()
    assert lines[1].amount.as_tuple() == Decimal("33.33").as_tuple()


def test_missing_binding_fails_closed_before_account_resolution_or_snapshot(monkeypatch):
    import aqorath.account_bindings
    import aqorath.account_resolution
    import aqorath.confirmation
    from aqorath.fixed_asset_depreciation_confirmation import (
        prepare_fixed_asset_depreciation_confirmation,
    )

    accounting_resolution = _accounting_resolution()
    monkeypatch.setattr(
        aqorath.account_bindings,
        "get_account_bindings",
        lambda *args: (_ for _ in ()).throw(KeyError("missing depreciation binding")),
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("downstream authority must not run")

    monkeypatch.setattr(aqorath.account_resolution, "resolve_proposal_accounts", forbidden)
    monkeypatch.setattr(aqorath.confirmation, "create_confirmation_snapshot", forbidden)

    with pytest.raises(KeyError, match="missing depreciation binding"):
        prepare_fixed_asset_depreciation_confirmation(object(), accounting_resolution)


def test_account_resolution_failure_propagates_without_snapshot_retry(monkeypatch):
    import aqorath.account_bindings
    import aqorath.account_resolution
    import aqorath.confirmation
    from aqorath.fixed_asset_depreciation_confirmation import (
        prepare_fixed_asset_depreciation_confirmation,
    )

    accounting_resolution = _accounting_resolution()
    monkeypatch.setattr(
        aqorath.account_bindings,
        "get_account_bindings",
        lambda *args: {
            "depreciation_expense": "DEP-EXP",
            "accumulated_depreciation": "ACC-DEP",
        },
    )
    monkeypatch.setattr(
        aqorath.account_resolution,
        "resolve_proposal_accounts",
        lambda *args: (_ for _ in ()).throw(LookupError("account resolution sentinel")),
    )
    monkeypatch.setattr(
        aqorath.confirmation,
        "create_confirmation_snapshot",
        lambda *args: (_ for _ in ()).throw(AssertionError("snapshot must not run")),
    )

    with pytest.raises(LookupError, match="account resolution sentinel"):
        prepare_fixed_asset_depreciation_confirmation(object(), accounting_resolution)


def test_preparation_never_confirms_posts_persists_or_rebuilds_depreciation(monkeypatch):
    import aqorath.account_bindings
    import aqorath.account_resolution
    import aqorath.confirmation
    import aqorath.posting
    import aqorath.posting_execution
    import aqorath.core
    import aqorath.fixed_asset_depreciation_accounting
    from aqorath.fixed_asset_depreciation_confirmation import (
        prepare_fixed_asset_depreciation_confirmation,
    )

    accounting_resolution = _accounting_resolution()
    resolved = _resolved_positive_proposal(accounting_resolution)
    monkeypatch.setattr(
        aqorath.account_bindings,
        "get_account_bindings",
        lambda *args: {
            "depreciation_expense": "DEP-EXP",
            "accumulated_depreciation": "ACC-DEP",
        },
    )
    monkeypatch.setattr(
        aqorath.account_resolution,
        "resolve_proposal_accounts",
        lambda *args: resolved,
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("preparation crossed its authority boundary")

    monkeypatch.setattr(aqorath.confirmation, "confirm_snapshot", forbidden)
    monkeypatch.setattr(aqorath.posting, "create_posting_instruction", forbidden)
    monkeypatch.setattr(aqorath.posting_execution, "execute_posting_instruction", forbidden)
    monkeypatch.setattr(aqorath.core, "post_entry", forbidden)
    monkeypatch.setattr(
        aqorath.fixed_asset_depreciation_accounting,
        "resolve_fixed_asset_depreciation_accounting",
        forbidden,
    )

    prepared = prepare_fixed_asset_depreciation_confirmation(object(), accounting_resolution)
    assert prepared.confirmation_snapshot is not None


def test_zero_no_entry_preparation_short_circuits_bindings_resolution_and_generic_snapshot(monkeypatch):
    import aqorath.account_bindings
    import aqorath.account_resolution
    import aqorath.confirmation
    from aqorath.fixed_asset_depreciation_confirmation import (
        FixedAssetDepreciationConfirmationSnapshot,
        prepare_fixed_asset_depreciation_confirmation,
    )

    accounting_resolution = _accounting_resolution(
        acquisition_cost=Decimal("100.00"),
        residual_value=Decimal("100.00"),
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("zero no-entry must not resolve accounts or confirmation")

    monkeypatch.setattr(aqorath.account_bindings, "get_account_bindings", forbidden)
    monkeypatch.setattr(aqorath.account_resolution, "resolve_proposal_accounts", forbidden)
    monkeypatch.setattr(aqorath.confirmation, "create_confirmation_snapshot", forbidden)

    prepared = prepare_fixed_asset_depreciation_confirmation(object(), accounting_resolution)
    assert isinstance(prepared, FixedAssetDepreciationConfirmationSnapshot)
    assert prepared.accounting_resolution is accounting_resolution
    assert prepared.accounting_resolution.outcome == "zero_amount_no_entry"
    assert prepared.confirmation_snapshot is None


def test_positive_confirmation_delegates_exact_generic_snapshot_once_and_preserves_dated_provenance(monkeypatch):
    import aqorath.account_bindings
    import aqorath.account_resolution
    import aqorath.confirmation
    from aqorath.fixed_asset_depreciation_confirmation import (
        ConfirmedFixedAssetDepreciation,
        confirm_fixed_asset_depreciation,
        prepare_fixed_asset_depreciation_confirmation,
    )

    accounting_resolution = _accounting_resolution(recognition_date=date(2026, 2, 17))
    resolved = _resolved_positive_proposal(accounting_resolution)
    monkeypatch.setattr(
        aqorath.account_bindings,
        "get_account_bindings",
        lambda *args: {
            "depreciation_expense": "DEP-EXP",
            "accumulated_depreciation": "ACC-DEP",
        },
    )
    monkeypatch.setattr(
        aqorath.account_resolution,
        "resolve_proposal_accounts",
        lambda *args: resolved,
    )
    prepared = prepare_fixed_asset_depreciation_confirmation(object(), accounting_resolution)
    real_confirm = aqorath.confirmation.confirm_snapshot
    calls = []

    def confirm_once(snapshot):
        calls.append(snapshot)
        return real_confirm(snapshot)

    monkeypatch.setattr(aqorath.confirmation, "confirm_snapshot", confirm_once)
    confirmed = confirm_fixed_asset_depreciation(prepared)

    assert isinstance(confirmed, ConfirmedFixedAssetDepreciation)
    assert confirmed.snapshot is prepared
    assert confirmed.confirmed_proposal.snapshot is prepared.confirmation_snapshot
    assert calls == [prepared.confirmation_snapshot]
    assert (
        confirmed.snapshot.accounting_resolution.recognition_fact.recognition_date
        == date(2026, 2, 17)
    )


def test_zero_no_entry_cannot_be_confirmed_and_never_calls_generic_confirmation(monkeypatch):
    import aqorath.confirmation
    from aqorath.fixed_asset_depreciation_confirmation import (
        confirm_fixed_asset_depreciation,
        prepare_fixed_asset_depreciation_confirmation,
    )

    accounting_resolution = _accounting_resolution(
        acquisition_cost=Decimal("100.00"),
        residual_value=Decimal("100.00"),
    )
    prepared = prepare_fixed_asset_depreciation_confirmation(object(), accounting_resolution)
    monkeypatch.setattr(
        aqorath.confirmation,
        "confirm_snapshot",
        lambda *args: (_ for _ in ()).throw(AssertionError("zero no-entry must not confirm")),
    )

    with pytest.raises(ValueError, match="zero_amount_no_entry|no entry|no-entry"):
        confirm_fixed_asset_depreciation(prepared)


def test_public_confirmation_types_fail_closed_on_forged_cross_stage_content(monkeypatch):
    import aqorath.account_bindings
    import aqorath.account_resolution
    from aqorath.fixed_asset_depreciation_confirmation import (
        confirm_fixed_asset_depreciation,
        prepare_fixed_asset_depreciation_confirmation,
    )

    accounting_resolution = _accounting_resolution()
    resolved = _resolved_positive_proposal(accounting_resolution)
    monkeypatch.setattr(
        aqorath.account_bindings,
        "get_account_bindings",
        lambda *args: {
            "depreciation_expense": "DEP-EXP",
            "accumulated_depreciation": "ACC-DEP",
        },
    )
    monkeypatch.setattr(
        aqorath.account_resolution,
        "resolve_proposal_accounts",
        lambda *args: resolved,
    )
    prepared = prepare_fixed_asset_depreciation_confirmation(object(), accounting_resolution)
    confirmed = confirm_fixed_asset_depreciation(prepared)

    with pytest.raises((TypeError, ValueError)):
        replace(prepared, confirmation_snapshot=None)
    with pytest.raises((TypeError, ValueError)):
        replace(
            prepared,
            accounting_resolution=_accounting_resolution(
                period_number=2,
                recognition_date=date(2026, 3, 31),
            ),
        )
    with pytest.raises((TypeError, ValueError)):
        replace(confirmed, confirmed_proposal=None)


def test_confirmation_module_preserves_stage_boundaries_and_never_owns_posting_or_date_defaulting():
    import aqorath.fixed_asset_depreciation_confirmation as module

    source = getsource(module).lower()
    forbidden = (
        "from . import core",
        "from . import posting",
        "posting_execution",
        "post_entry",
        "journalentry",
        "journalline",
        "get_session",
        "datetime.now",
        "date.today",
        "calculate_monthly_straight_line_depreciation",
        "allocate_monthly_depreciation(",
        "declare_fixed_asset_depreciation_recognition(",
        "resolve_fixed_asset_depreciation_accounting(",
        "from .assets",
        "import aqorath.assets",
        "float(",
        "commit(",
        "rollback(",
    )
    for text in forbidden:
        assert text not in source


def test_confirmation_is_deterministic_and_keeps_recognition_date_structural(monkeypatch):
    import aqorath.account_bindings
    import aqorath.account_resolution
    from aqorath.fixed_asset_depreciation_confirmation import (
        prepare_fixed_asset_depreciation_confirmation,
    )

    accounting_resolution = _accounting_resolution(recognition_date=date(2026, 2, 19))
    resolved = _resolved_positive_proposal(accounting_resolution)
    monkeypatch.setattr(
        aqorath.account_bindings,
        "get_account_bindings",
        lambda *args: {
            "depreciation_expense": "DEP-EXP",
            "accumulated_depreciation": "ACC-DEP",
        },
    )
    monkeypatch.setattr(
        aqorath.account_resolution,
        "resolve_proposal_accounts",
        lambda *args: resolved,
    )

    first = prepare_fixed_asset_depreciation_confirmation(object(), accounting_resolution)
    second = prepare_fixed_asset_depreciation_confirmation(object(), accounting_resolution)
    assert first == second
    assert first is not second
    assert first.confirmation_snapshot is not second.confirmation_snapshot
    assert first.accounting_resolution is accounting_resolution
    assert second.accounting_resolution is accounting_resolution
    assert first.accounting_resolution.recognition_fact.recognition_date == date(2026, 2, 19)


def test_application_exposes_prepare_and_confirm_as_thin_interface_agnostic_delegations(monkeypatch):
    import aqorath.application as application
    import aqorath.fixed_asset_depreciation_confirmation as authority

    assert list(signature(application.prepare_fixed_asset_depreciation_confirmation).parameters) == [
        "session",
        "accounting_resolution",
    ]
    assert list(signature(application.confirm_fixed_asset_depreciation).parameters) == ["snapshot"]

    session = object()
    accounting_resolution = object()
    snapshot = object()
    prepared_sentinel = object()
    confirmed_sentinel = object()
    calls = []

    def prepare(supplied_session, supplied_resolution):
        calls.append(("prepare", supplied_session, supplied_resolution))
        return prepared_sentinel

    def confirm(supplied_snapshot):
        calls.append(("confirm", supplied_snapshot))
        return confirmed_sentinel

    monkeypatch.setattr(authority, "prepare_fixed_asset_depreciation_confirmation", prepare)
    monkeypatch.setattr(authority, "confirm_fixed_asset_depreciation", confirm)

    assert application.prepare_fixed_asset_depreciation_confirmation(
        session,
        accounting_resolution,
    ) is prepared_sentinel
    assert application.confirm_fixed_asset_depreciation(snapshot) is confirmed_sentinel
    assert calls == [
        ("prepare", session, accounting_resolution),
        ("confirm", snapshot),
    ]

    for function in (
        application.prepare_fixed_asset_depreciation_confirmation,
        application.confirm_fixed_asset_depreciation,
    ):
        source = getsource(function).lower()
        for forbidden in (
            "get_session",
            "account_bindings",
            "resolve_proposal_accounts",
            "create_confirmation_snapshot",
            "post_entry",
            "recognition_date",
        ):
            assert forbidden not in source
