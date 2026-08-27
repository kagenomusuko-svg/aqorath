"""Phase 6P.1 — configured confirmation and dated posting contracts for asset acquisition."""

from datetime import date
from decimal import Decimal
import inspect

import pytest


def _asset(**overrides):
    from aqorath.fixed_asset import FixedAsset

    values = {
        "id": 21,
        "entity_id": 4,
        "code": "FA-021",
        "name": "Equipo de laboratorio",
        "acquisition_date": date(2026, 5, 20),
        "in_service_date": date(2026, 6, 1),
        "acquisition_cost": Decimal("48000.0000"),
        "residual_value": Decimal("3000.00"),
        "useful_life_months": 48,
        "depreciation_method": "straight_line",
        "is_active": True,
    }
    values.update(overrides)
    return FixedAsset(**values)


def _accounting_resolution(
    *,
    asset_class="computer_equipment",
    settlement_method="bank",
    **asset_overrides,
):
    from aqorath.fixed_asset_acquisition import (
        create_fixed_asset_acquisition_fact,
        resolve_fixed_asset_acquisition_accounting,
    )

    fact = create_fixed_asset_acquisition_fact(
        _asset(**asset_overrides),
        asset_class,
        settlement_method,
    )
    return resolve_fixed_asset_acquisition_accounting(fact)


def _resolved_proposal(accounting_resolution):
    from aqorath.account_resolution import ResolvedAccountingProposal, ResolvedProposalLine

    proposal = accounting_resolution.proposal
    lines = tuple(
        ResolvedProposalLine(
            account_role=line.account_role,
            side=line.side,
            amount=line.amount,
            account_id=index + 100,
            account_code=f"TEST-{index + 1}",
        )
        for index, line in enumerate(proposal.lines)
    )
    return ResolvedAccountingProposal(
        lines=lines,
        explanation=proposal.explanation,
    )


def _prepared_positive(monkeypatch=None):
    from aqorath import fixed_asset_acquisition_confirmation as confirmation

    accounting_resolution = _accounting_resolution()
    resolved = _resolved_proposal(accounting_resolution)
    if monkeypatch is not None:
        monkeypatch.setattr(
            confirmation._account_bindings,
            "get_account_bindings",
            lambda session, roles: {
                role: f"TEST-{index + 1}" for index, role in enumerate(roles)
            },
        )
        monkeypatch.setattr(
            confirmation._account_resolution,
            "resolve_proposal_accounts",
            lambda session, proposal, bindings: resolved,
        )
    else:
        pytest.skip("helper requires monkeypatch")
    return confirmation.prepare_fixed_asset_acquisition_confirmation(
        object(), accounting_resolution
    )


def test_confirmation_and_posting_public_contracts_have_exact_signatures():
    import aqorath.fixed_asset_acquisition_confirmation as confirmation
    import aqorath.fixed_asset_acquisition_posting as posting

    assert confirmation.FixedAssetAcquisitionConfirmationSnapshot is not None
    assert confirmation.ConfirmedFixedAssetAcquisition is not None
    assert posting.FixedAssetAcquisitionPostingInstruction is not None
    assert str(inspect.signature(confirmation.prepare_fixed_asset_acquisition_confirmation)) == (
        "(session, accounting_resolution)"
    )
    assert str(inspect.signature(confirmation.confirm_fixed_asset_acquisition)) == "(snapshot)"
    assert str(inspect.signature(posting.create_fixed_asset_acquisition_posting_instruction)) == (
        "(confirmed_acquisition)"
    )
    assert str(inspect.signature(posting.execute_fixed_asset_acquisition_posting)) == "(instruction)"


def test_preparation_requires_nominal_6o_resolution_before_binding_lookup(monkeypatch):
    import aqorath.fixed_asset_acquisition_confirmation as confirmation

    called = []
    monkeypatch.setattr(
        confirmation._account_bindings,
        "get_account_bindings",
        lambda *args: called.append(args),
    )
    with pytest.raises(TypeError):
        confirmation.prepare_fixed_asset_acquisition_confirmation(object(), object())
    assert called == []


def test_positive_preparation_reuses_binding_resolution_and_confirmation_once_in_order(monkeypatch):
    import aqorath.fixed_asset_acquisition_confirmation as confirmation

    accounting_resolution = _accounting_resolution(
        asset_class="machinery_tools",
        settlement_method="credit",
    )
    resolved = _resolved_proposal(accounting_resolution)
    sentinel_snapshot = object()
    calls = []

    def get_bindings(session, roles):
        calls.append(("bindings", session, roles))
        return {roles[0]: "A", roles[1]: "B"}

    def resolve(session, proposal, bindings):
        calls.append(("resolve", session, proposal, bindings))
        return resolved

    def freeze(resolved_proposal):
        calls.append(("snapshot", resolved_proposal))
        return sentinel_snapshot

    session = object()
    monkeypatch.setattr(confirmation._account_bindings, "get_account_bindings", get_bindings)
    monkeypatch.setattr(confirmation._account_resolution, "resolve_proposal_accounts", resolve)
    monkeypatch.setattr(confirmation._confirmation, "create_confirmation_snapshot", freeze)

    prepared = confirmation.prepare_fixed_asset_acquisition_confirmation(
        session, accounting_resolution
    )
    expected_roles = tuple(line.account_role for line in accounting_resolution.proposal.lines)
    assert prepared.accounting_resolution is accounting_resolution
    assert prepared.confirmation_snapshot is sentinel_snapshot
    assert calls == [
        ("bindings", session, expected_roles),
        ("resolve", session, accounting_resolution.proposal, {expected_roles[0]: "A", expected_roles[1]: "B"}),
        ("snapshot", resolved),
    ]


def test_prepared_positive_snapshot_preserves_exact_concrete_truth_and_acquisition_provenance(monkeypatch):
    from aqorath import fixed_asset_acquisition_confirmation as confirmation

    accounting_resolution = _accounting_resolution(
        asset_class="computer_equipment",
        settlement_method="bank",
        acquisition_cost=Decimal("48000.0000"),
    )
    resolved = _resolved_proposal(accounting_resolution)
    monkeypatch.setattr(
        confirmation._account_bindings,
        "get_account_bindings",
        lambda session, roles: {role: f"TEST-{i + 1}" for i, role in enumerate(roles)},
    )
    monkeypatch.setattr(
        confirmation._account_resolution,
        "resolve_proposal_accounts",
        lambda session, proposal, bindings: resolved,
    )

    prepared = confirmation.prepare_fixed_asset_acquisition_confirmation(
        object(), accounting_resolution
    )
    assert prepared.accounting_resolution is accounting_resolution
    assert prepared.accounting_resolution.acquisition_fact.acquisition_date == date(2026, 5, 20)
    assert prepared.accounting_resolution.acquisition_fact.acquisition_cost.as_tuple() == Decimal(
        "48000.0000"
    ).as_tuple()
    assert prepared.confirmation_snapshot.explanation == accounting_resolution.explanation
    assert tuple(line.account_role for line in prepared.confirmation_snapshot.lines) == (
        "fixed_asset_computer_equipment",
        "bank",
    )
    assert tuple(line.side for line in prepared.confirmation_snapshot.lines) == (
        "debit",
        "credit",
    )
    assert all(line.account_id is not None for line in prepared.confirmation_snapshot.lines)
    assert all(line.account_code for line in prepared.confirmation_snapshot.lines)


def test_missing_binding_fails_closed_without_resolution_snapshot_or_retry(monkeypatch):
    import aqorath.fixed_asset_acquisition_confirmation as confirmation

    accounting_resolution = _accounting_resolution()
    calls = []

    def missing(session, roles):
        calls.append("bindings")
        raise KeyError("missing acquisition role")

    monkeypatch.setattr(confirmation._account_bindings, "get_account_bindings", missing)
    monkeypatch.setattr(
        confirmation._account_resolution,
        "resolve_proposal_accounts",
        lambda *args: calls.append("resolve"),
    )
    monkeypatch.setattr(
        confirmation._confirmation,
        "create_confirmation_snapshot",
        lambda *args: calls.append("snapshot"),
    )

    with pytest.raises(KeyError):
        confirmation.prepare_fixed_asset_acquisition_confirmation(
            object(), accounting_resolution
        )
    assert calls == ["bindings"]


def test_zero_cost_preparation_short_circuits_bindings_resolution_and_generic_confirmation(monkeypatch):
    import aqorath.fixed_asset_acquisition_confirmation as confirmation

    accounting_resolution = _accounting_resolution(
        acquisition_cost=Decimal("0.0000"),
        residual_value=Decimal("0.0000"),
    )
    calls = []
    monkeypatch.setattr(
        confirmation._account_bindings,
        "get_account_bindings",
        lambda *args: calls.append("bindings"),
    )
    monkeypatch.setattr(
        confirmation._account_resolution,
        "resolve_proposal_accounts",
        lambda *args: calls.append("resolve"),
    )
    monkeypatch.setattr(
        confirmation._confirmation,
        "create_confirmation_snapshot",
        lambda *args: calls.append("snapshot"),
    )

    prepared = confirmation.prepare_fixed_asset_acquisition_confirmation(
        object(), accounting_resolution
    )
    assert prepared.accounting_resolution is accounting_resolution
    assert prepared.confirmation_snapshot is None
    assert calls == []


def test_positive_confirmation_delegates_exact_generic_snapshot_once(monkeypatch):
    import aqorath.fixed_asset_acquisition_confirmation as confirmation

    prepared = _prepared_positive(monkeypatch)
    sentinel_confirmed = object()
    calls = []

    def confirm(snapshot):
        calls.append(snapshot)
        return sentinel_confirmed

    monkeypatch.setattr(confirmation._confirmation, "confirm_snapshot", confirm)
    confirmed = confirmation.confirm_fixed_asset_acquisition(prepared)
    assert confirmed.snapshot is prepared
    assert confirmed.confirmed_proposal is sentinel_confirmed
    assert calls == [prepared.confirmation_snapshot]


def test_zero_cost_no_entry_cannot_be_confirmed(monkeypatch):
    import aqorath.fixed_asset_acquisition_confirmation as confirmation

    prepared = confirmation.prepare_fixed_asset_acquisition_confirmation(
        object(),
        _accounting_resolution(
            acquisition_cost=Decimal("0.00"),
            residual_value=Decimal("0.00"),
        ),
    )
    calls = []
    monkeypatch.setattr(
        confirmation._confirmation,
        "confirm_snapshot",
        lambda *args: calls.append(args),
    )
    with pytest.raises(ValueError):
        confirmation.confirm_fixed_asset_acquisition(prepared)
    assert calls == []


def test_confirmation_public_types_are_frozen_factory_only_and_reject_cross_stage_forgery(monkeypatch):
    import aqorath.fixed_asset_acquisition_confirmation as confirmation

    accounting_resolution = _accounting_resolution()
    with pytest.raises(TypeError):
        confirmation.FixedAssetAcquisitionConfirmationSnapshot(
            accounting_resolution,
            None,
        )

    prepared = _prepared_positive(monkeypatch)
    with pytest.raises(TypeError):
        confirmation.ConfirmedFixedAssetAcquisition(prepared, object())


def test_posting_factory_requires_nominal_confirmed_acquisition_before_generic_posting(monkeypatch):
    import aqorath.fixed_asset_acquisition_posting as posting

    calls = []
    monkeypatch.setattr(
        posting._posting,
        "create_posting_instruction",
        lambda *args: calls.append(args),
    )
    with pytest.raises(TypeError):
        posting.create_fixed_asset_acquisition_posting_instruction(object())
    assert calls == []


def test_posting_factory_delegates_confirmed_proposal_once_and_uses_exact_acquisition_date(monkeypatch):
    import aqorath.fixed_asset_acquisition_confirmation as confirmation
    import aqorath.fixed_asset_acquisition_posting as posting

    prepared = _prepared_positive(monkeypatch)
    generic_confirmed = object()
    monkeypatch.setattr(
        confirmation._confirmation,
        "confirm_snapshot",
        lambda snapshot: generic_confirmed,
    )
    confirmed = confirmation.confirm_fixed_asset_acquisition(prepared)
    generic_instruction = object()
    calls = []

    def make_instruction(value):
        calls.append(value)
        return generic_instruction

    monkeypatch.setattr(posting._posting, "create_posting_instruction", make_instruction)
    instruction = posting.create_fixed_asset_acquisition_posting_instruction(confirmed)
    assert instruction.confirmed_acquisition is confirmed
    assert instruction.posting_instruction is generic_instruction
    assert instruction.posting_date == date(2026, 5, 20)
    assert calls == [generic_confirmed]


def test_posting_api_has_no_user_date_override_and_date_comes_only_from_6o_truth():
    import aqorath.fixed_asset_acquisition_posting as posting

    factory_signature = inspect.signature(
        posting.create_fixed_asset_acquisition_posting_instruction
    )
    execute_signature = inspect.signature(posting.execute_fixed_asset_acquisition_posting)
    assert tuple(factory_signature.parameters) == ("confirmed_acquisition",)
    assert tuple(execute_signature.parameters) == ("instruction",)
    for forbidden in ("date", "posting_date", "effective_date", "as_of"):
        assert forbidden not in factory_signature.parameters
        assert forbidden not in execute_signature.parameters


def test_execution_builds_exact_core_payload_with_acquisition_date_and_confirmed_lines(monkeypatch):
    import aqorath.fixed_asset_acquisition_confirmation as confirmation
    import aqorath.fixed_asset_acquisition_posting as posting
    from aqorath.posting import create_posting_instruction

    prepared = _prepared_positive(monkeypatch)
    generic_confirmed = confirmation._confirmation.confirm_snapshot(
        prepared.confirmation_snapshot
    )
    confirmed = object.__new__(confirmation.ConfirmedFixedAssetAcquisition)
    object.__setattr__(confirmed, "snapshot", prepared)
    object.__setattr__(confirmed, "confirmed_proposal", generic_confirmed)
    generic_instruction = create_posting_instruction(generic_confirmed)
    instruction = object.__new__(posting.FixedAssetAcquisitionPostingInstruction)
    object.__setattr__(instruction, "confirmed_acquisition", confirmed)
    object.__setattr__(instruction, "posting_instruction", generic_instruction)
    object.__setattr__(instruction, "posting_date", date(2026, 5, 20))

    calls = []
    sentinel = {"ok": True, "entry_id": 777}

    def post_entry(payload):
        calls.append(payload)
        return sentinel

    monkeypatch.setattr(posting._core, "post_entry", post_entry)
    result = posting.execute_fixed_asset_acquisition_posting(instruction)
    assert result is sentinel
    assert calls == [
        {
            "date": date(2026, 5, 20),
            "description": generic_instruction.description,
            "lines": [
                {
                    "account_id": line.account_id,
                    "account_code": line.account_code,
                    "debit": line.debit,
                    "credit": line.credit,
                }
                for line in generic_instruction.lines
            ],
        }
    ]


def test_execution_requires_nominal_specific_instruction_before_core(monkeypatch):
    import aqorath.fixed_asset_acquisition_posting as posting

    calls = []
    monkeypatch.setattr(posting._core, "post_entry", lambda *args: calls.append(args))
    with pytest.raises(TypeError):
        posting.execute_fixed_asset_acquisition_posting(object())
    assert calls == []


def test_confirmation_and_posting_do_not_rebuild_6o_truth_or_open_hidden_storage():
    import aqorath.fixed_asset_acquisition_confirmation as confirmation
    import aqorath.fixed_asset_acquisition_posting as posting

    confirmation_source = inspect.getsource(confirmation).lower()
    posting_source = inspect.getsource(posting).lower()

    for forbidden in (
        "create_fixed_asset_acquisition_fact",
        "resolve_fixed_asset_acquisition_accounting",
        "get_session",
        "sqlite3",
        "from .assets",
        "import aqorath.assets",
    ):
        assert forbidden not in confirmation_source
        assert forbidden not in posting_source

    for forbidden in (
        "get_account_bindings",
        "resolve_proposal_accounts",
        "create_confirmation_snapshot",
        "confirm_snapshot",
    ):
        assert forbidden not in posting_source


def test_application_exposes_6p_boundaries_as_exact_thin_delegations(monkeypatch):
    import aqorath.application as application
    import aqorath.fixed_asset_acquisition_confirmation as confirmation
    import aqorath.fixed_asset_acquisition_posting as posting

    assert str(inspect.signature(application.prepare_fixed_asset_acquisition_confirmation)) == (
        "(session, accounting_resolution)"
    )
    assert str(inspect.signature(application.confirm_fixed_asset_acquisition)) == "(snapshot)"
    assert str(inspect.signature(application.create_fixed_asset_acquisition_posting_instruction)) == (
        "(confirmed_acquisition)"
    )
    assert str(inspect.signature(application.execute_fixed_asset_acquisition_posting)) == "(instruction)"

    sentinels = [object(), object(), object(), object()]
    calls = []
    monkeypatch.setattr(
        confirmation,
        "prepare_fixed_asset_acquisition_confirmation",
        lambda session, resolution: calls.append(("prepare", session, resolution)) or sentinels[0],
    )
    monkeypatch.setattr(
        confirmation,
        "confirm_fixed_asset_acquisition",
        lambda snapshot: calls.append(("confirm", snapshot)) or sentinels[1],
    )
    monkeypatch.setattr(
        posting,
        "create_fixed_asset_acquisition_posting_instruction",
        lambda confirmed: calls.append(("instruction", confirmed)) or sentinels[2],
    )
    monkeypatch.setattr(
        posting,
        "execute_fixed_asset_acquisition_posting",
        lambda instruction: calls.append(("execute", instruction)) or sentinels[3],
    )

    session = object()
    resolution = object()
    assert application.prepare_fixed_asset_acquisition_confirmation(session, resolution) is sentinels[0]
    assert application.confirm_fixed_asset_acquisition(sentinels[0]) is sentinels[1]
    assert application.create_fixed_asset_acquisition_posting_instruction(sentinels[1]) is sentinels[2]
    assert application.execute_fixed_asset_acquisition_posting(sentinels[2]) is sentinels[3]
    assert calls == [
        ("prepare", session, resolution),
        ("confirm", sentinels[0]),
        ("instruction", sentinels[1]),
        ("execute", sentinels[2]),
    ]
