"""Phase 6L.1 — explicit dated posting for confirmed fixed-asset depreciation."""

from dataclasses import fields, replace
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


def _confirmed_depreciation(
    monkeypatch,
    *,
    period_number=1,
    recognition_date=date(2026, 2, 28),
):
    import aqorath.account_bindings
    import aqorath.account_resolution
    from aqorath.account_resolution import (
        ResolvedAccountingProposal,
        ResolvedProposalLine,
    )
    from aqorath.fixed_asset_depreciation_confirmation import (
        confirm_fixed_asset_depreciation,
        prepare_fixed_asset_depreciation_confirmation,
    )

    accounting_resolution = _accounting_resolution(
        period_number=period_number,
        recognition_date=recognition_date,
    )
    amount = accounting_resolution.recognition_fact.amount
    resolved = ResolvedAccountingProposal(
        lines=[
            ResolvedProposalLine(
                account_role="depreciation_expense",
                account_id=11,
                account_code="5106",
                account_name="Depreciación y amortización",
                side="debit",
                amount=amount,
            ),
            ResolvedProposalLine(
                account_role="accumulated_depreciation",
                account_id=12,
                account_code="1205",
                account_name="Depreciación acumulada",
                side="credit",
                amount=amount,
            ),
        ],
        explanation=accounting_resolution.explanation,
    )
    monkeypatch.setattr(
        aqorath.account_bindings,
        "get_account_bindings",
        lambda session, roles: {
            "depreciation_expense": "5106",
            "accumulated_depreciation": "1205",
        },
    )
    monkeypatch.setattr(
        aqorath.account_resolution,
        "resolve_proposal_accounts",
        lambda session, proposal, bindings: resolved,
    )
    prepared = prepare_fixed_asset_depreciation_confirmation(
        object(),
        accounting_resolution,
    )
    return confirm_fixed_asset_depreciation(prepared)


def test_dated_posting_public_instruction_is_frozen_minimal_and_provenance_bearing():
    from aqorath.fixed_asset_depreciation_posting import (
        FixedAssetDepreciationPostingInstruction,
    )

    assert FixedAssetDepreciationPostingInstruction.__dataclass_params__.frozen
    assert [field.name for field in fields(FixedAssetDepreciationPostingInstruction)] == [
        "confirmed_depreciation",
        "posting_instruction",
        "posting_date",
    ]


def test_dated_posting_api_has_exact_signatures_and_no_user_date_parameter():
    from aqorath.fixed_asset_depreciation_posting import (
        create_fixed_asset_depreciation_posting_instruction,
        execute_fixed_asset_depreciation_posting,
    )

    expected = {
        create_fixed_asset_depreciation_posting_instruction: ["confirmed_depreciation"],
        execute_fixed_asset_depreciation_posting: ["instruction"],
    }
    for function, names in expected.items():
        sig = signature(function)
        assert list(sig.parameters) == names
        for parameter in sig.parameters.values():
            assert parameter.default is Parameter.empty
            assert parameter.kind is Parameter.POSITIONAL_OR_KEYWORD


def test_factory_requires_nominal_confirmed_depreciation_before_generic_posting(monkeypatch):
    import aqorath.posting
    from aqorath.fixed_asset_depreciation_posting import (
        create_fixed_asset_depreciation_posting_instruction,
    )

    calls = []
    monkeypatch.setattr(
        aqorath.posting,
        "create_posting_instruction",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    with pytest.raises(TypeError):
        create_fixed_asset_depreciation_posting_instruction(object())
    assert calls == []


def test_factory_delegates_exact_confirmed_proposal_once_to_existing_posting_authority(monkeypatch):
    import aqorath.posting
    from aqorath.fixed_asset_depreciation_posting import (
        create_fixed_asset_depreciation_posting_instruction,
    )

    confirmed = _confirmed_depreciation(monkeypatch)
    real_factory = aqorath.posting.create_posting_instruction
    expected_instruction = real_factory(confirmed.confirmed_proposal)
    calls = []

    def create_once(supplied_confirmed):
        calls.append(supplied_confirmed)
        return expected_instruction

    monkeypatch.setattr(aqorath.posting, "create_posting_instruction", create_once)
    instruction = create_fixed_asset_depreciation_posting_instruction(confirmed)

    assert calls == [confirmed.confirmed_proposal]
    assert instruction.confirmed_depreciation is confirmed
    assert instruction.posting_instruction is expected_instruction


def test_posting_date_is_exact_structured_recognition_date_not_ambient_or_user_supplied(monkeypatch):
    from aqorath.fixed_asset_depreciation_posting import (
        create_fixed_asset_depreciation_posting_instruction,
    )

    confirmed = _confirmed_depreciation(
        monkeypatch,
        period_number=2,
        recognition_date=date(2026, 3, 31),
    )
    instruction = create_fixed_asset_depreciation_posting_instruction(confirmed)

    assert instruction.posting_date == date(2026, 3, 31)
    assert (
        instruction.posting_date
        == confirmed.snapshot.accounting_resolution.recognition_fact.recognition_date
    )
    assert instruction.posting_date != date(2026, 8, 27)


def test_recognition_date_changes_only_temporal_posting_truth_not_accounting_lines(monkeypatch):
    from aqorath.fixed_asset_depreciation_posting import (
        create_fixed_asset_depreciation_posting_instruction,
    )

    first = create_fixed_asset_depreciation_posting_instruction(
        _confirmed_depreciation(
            monkeypatch,
            recognition_date=date(2026, 2, 28),
        )
    )
    second = create_fixed_asset_depreciation_posting_instruction(
        _confirmed_depreciation(
            monkeypatch,
            recognition_date=date(2026, 2, 27),
        )
    )

    assert first.posting_date == date(2026, 2, 28)
    assert second.posting_date == date(2026, 2, 27)
    assert first.posting_instruction.lines == second.posting_instruction.lines


def test_factory_preserves_line_order_roles_balance_and_exact_decimal_scale(monkeypatch):
    from aqorath.fixed_asset_depreciation_posting import (
        create_fixed_asset_depreciation_posting_instruction,
    )

    instruction = create_fixed_asset_depreciation_posting_instruction(
        _confirmed_depreciation(
            monkeypatch,
            period_number=3,
            recognition_date=date(2026, 4, 30),
        )
    )
    lines = instruction.posting_instruction.lines

    assert tuple(line.account_role for line in lines) == (
        "depreciation_expense",
        "accumulated_depreciation",
    )
    assert tuple(line.account_code for line in lines) == ("5106", "1205")
    assert lines[0].debit.as_tuple() == Decimal("33.34").as_tuple()
    assert lines[0].credit == Decimal("0")
    assert lines[1].debit == Decimal("0")
    assert lines[1].credit.as_tuple() == Decimal("33.34").as_tuple()
    assert sum((line.debit for line in lines), Decimal("0")) == sum(
        (line.credit for line in lines),
        Decimal("0"),
    )


def test_public_dated_instruction_cannot_be_directly_constructed_or_replaced_with_forged_date(monkeypatch):
    from aqorath.fixed_asset_depreciation_posting import (
        FixedAssetDepreciationPostingInstruction,
        create_fixed_asset_depreciation_posting_instruction,
    )

    confirmed = _confirmed_depreciation(monkeypatch)
    valid = create_fixed_asset_depreciation_posting_instruction(confirmed)

    with pytest.raises((TypeError, ValueError)):
        FixedAssetDepreciationPostingInstruction(
            confirmed,
            valid.posting_instruction,
            date(2026, 2, 28),
        )
    with pytest.raises((TypeError, ValueError)):
        replace(valid, posting_date=date(2026, 8, 27))


def test_factory_is_pure_and_never_executes_or_reenters_prior_depreciation_stages(monkeypatch):
    import aqorath.core
    import aqorath.posting_execution
    import aqorath.fixed_asset_depreciation
    import aqorath.fixed_asset_depreciation_allocation
    import aqorath.fixed_asset_depreciation_recognition
    import aqorath.fixed_asset_depreciation_accounting
    import aqorath.fixed_asset_depreciation_confirmation
    from aqorath.fixed_asset_depreciation_posting import (
        create_fixed_asset_depreciation_posting_instruction,
    )

    confirmed = _confirmed_depreciation(monkeypatch)

    def forbidden(*args, **kwargs):
        raise AssertionError("posting factory crossed its authority boundary")

    monkeypatch.setattr(aqorath.core, "post_entry", forbidden)
    monkeypatch.setattr(aqorath.posting_execution, "execute_posting_instruction", forbidden)
    monkeypatch.setattr(
        aqorath.fixed_asset_depreciation,
        "calculate_monthly_straight_line_depreciation",
        forbidden,
    )
    monkeypatch.setattr(
        aqorath.fixed_asset_depreciation_allocation,
        "allocate_monthly_depreciation",
        forbidden,
    )
    monkeypatch.setattr(
        aqorath.fixed_asset_depreciation_recognition,
        "declare_fixed_asset_depreciation_recognition",
        forbidden,
    )
    monkeypatch.setattr(
        aqorath.fixed_asset_depreciation_accounting,
        "resolve_fixed_asset_depreciation_accounting",
        forbidden,
    )
    monkeypatch.setattr(
        aqorath.fixed_asset_depreciation_confirmation,
        "confirm_fixed_asset_depreciation",
        forbidden,
    )

    instruction = create_fixed_asset_depreciation_posting_instruction(confirmed)
    assert instruction.confirmed_depreciation is confirmed


def test_execution_builds_exact_core_payload_with_explicit_recognition_date(monkeypatch):
    import aqorath.core
    from aqorath.fixed_asset_depreciation_posting import (
        create_fixed_asset_depreciation_posting_instruction,
        execute_fixed_asset_depreciation_posting,
    )

    instruction = create_fixed_asset_depreciation_posting_instruction(
        _confirmed_depreciation(
            monkeypatch,
            period_number=3,
            recognition_date=date(2026, 4, 30),
        )
    )
    calls = []
    sentinel = {"ok": True, "entry_id": 991}

    def post_once(payload):
        calls.append(payload)
        return sentinel

    monkeypatch.setattr(aqorath.core, "post_entry", post_once)
    result = execute_fixed_asset_depreciation_posting(instruction)

    assert result is sentinel
    assert calls == [
        {
            "date": date(2026, 4, 30),
            "description": instruction.posting_instruction.description,
            "lines": [
                {
                    "account_id": 11,
                    "account_code": "5106",
                    "debit": Decimal("33.34"),
                    "credit": Decimal("0"),
                },
                {
                    "account_id": 12,
                    "account_code": "1205",
                    "debit": Decimal("0"),
                    "credit": Decimal("33.34"),
                },
            ],
        }
    ]


def test_execution_requires_nominal_specific_instruction_before_core_call(monkeypatch):
    import aqorath.core
    from aqorath.fixed_asset_depreciation_posting import (
        execute_fixed_asset_depreciation_posting,
    )

    calls = []
    monkeypatch.setattr(
        aqorath.core,
        "post_entry",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    with pytest.raises(TypeError):
        execute_fixed_asset_depreciation_posting(object())
    assert calls == []


def test_execution_does_not_use_generic_executor_or_reconfirm_recalculate_or_resolve(monkeypatch):
    import aqorath.core
    import aqorath.posting_execution
    import aqorath.confirmation
    import aqorath.account_resolution
    import aqorath.fixed_asset_depreciation
    from aqorath.fixed_asset_depreciation_posting import (
        create_fixed_asset_depreciation_posting_instruction,
        execute_fixed_asset_depreciation_posting,
    )

    instruction = create_fixed_asset_depreciation_posting_instruction(
        _confirmed_depreciation(monkeypatch)
    )
    sentinel = {"ok": True, "entry_id": 12}

    def forbidden(*args, **kwargs):
        raise AssertionError("dated execution must not re-enter prior authorities")

    monkeypatch.setattr(aqorath.posting_execution, "execute_posting_instruction", forbidden)
    monkeypatch.setattr(aqorath.confirmation, "confirm_snapshot", forbidden)
    monkeypatch.setattr(aqorath.account_resolution, "resolve_proposal_accounts", forbidden)
    monkeypatch.setattr(
        aqorath.fixed_asset_depreciation,
        "calculate_monthly_straight_line_depreciation",
        forbidden,
    )
    monkeypatch.setattr(aqorath.core, "post_entry", lambda payload: sentinel)

    assert execute_fixed_asset_depreciation_posting(instruction) is sentinel


def test_execution_propagates_core_failure_once_without_retry(monkeypatch):
    import aqorath.core
    from aqorath.fixed_asset_depreciation_posting import (
        create_fixed_asset_depreciation_posting_instruction,
        execute_fixed_asset_depreciation_posting,
    )

    instruction = create_fixed_asset_depreciation_posting_instruction(
        _confirmed_depreciation(monkeypatch)
    )
    calls = []

    def fail(payload):
        calls.append(payload)
        raise LookupError("posting sentinel")

    monkeypatch.setattr(aqorath.core, "post_entry", fail)
    with pytest.raises(LookupError, match="posting sentinel"):
        execute_fixed_asset_depreciation_posting(instruction)
    assert len(calls) == 1


def test_zero_amount_no_entry_cannot_create_or_execute_a_posting(monkeypatch):
    import aqorath.core
    from aqorath.fixed_asset_depreciation_confirmation import (
        prepare_fixed_asset_depreciation_confirmation,
    )
    from aqorath.fixed_asset_depreciation_posting import (
        create_fixed_asset_depreciation_posting_instruction,
    )

    accounting_resolution = _accounting_resolution(
        acquisition_cost=Decimal("100.00"),
        residual_value=Decimal("100.00"),
    )
    prepared = prepare_fixed_asset_depreciation_confirmation(
        object(),
        accounting_resolution,
    )
    assert prepared.accounting_resolution.outcome == "zero_amount_no_entry"
    assert prepared.confirmation_snapshot is None

    monkeypatch.setattr(
        aqorath.core,
        "post_entry",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("zero no-entry must never reach persistence")
        ),
    )
    with pytest.raises(TypeError):
        create_fixed_asset_depreciation_posting_instruction(prepared)


def test_real_sqlite_round_trip_persists_exact_recognition_date_and_two_exact_lines(tmp_path, monkeypatch):
    from sqlmodel import select
    from aqorath.fixed_asset_depreciation_posting import (
        create_fixed_asset_depreciation_posting_instruction,
        execute_fixed_asset_depreciation_posting,
    )
    from aqorath import account_bindings, storage
    from aqorath.fixed_asset_depreciation_confirmation import (
        confirm_fixed_asset_depreciation,
        prepare_fixed_asset_depreciation_confirmation,
    )
    from aqorath.models import Account, JournalEntry, JournalLine

    db_file = tmp_path / "dated_depreciation.db"
    monkeypatch.setenv("AQORATH_DB", str(db_file))
    storage.init_db(str(db_file), create_tables=True)
    recognition_date = date(2026, 2, 28)
    accounting_resolution = _accounting_resolution(
        recognition_date=recognition_date,
    )

    with storage.get_session() as session:
        expense = session.exec(select(Account).where(Account.code == "5106")).one_or_none()
        if expense is None:
            expense = Account(
                code="5106",
                name="Depreciación y amortización",
                nature="Deudora",
            )
            session.add(expense)
        accumulated = session.exec(select(Account).where(Account.code == "1205")).one_or_none()
        if accumulated is None:
            accumulated = Account(
                code="1205",
                name="Depreciación acumulada",
                nature="Acreedora",
            )
            session.add(accumulated)
        session.commit()

        account_bindings.set_account_binding(session, "depreciation_expense", "5106")
        account_bindings.set_account_binding(session, "accumulated_depreciation", "1205")
        prepared = prepare_fixed_asset_depreciation_confirmation(
            session,
            accounting_resolution,
        )
        confirmed = confirm_fixed_asset_depreciation(prepared)

    instruction = create_fixed_asset_depreciation_posting_instruction(confirmed)
    result = execute_fixed_asset_depreciation_posting(instruction)
    assert result["ok"] is True

    with storage.get_session() as session:
        entry = session.get(JournalEntry, result["entry_id"])
        lines = session.exec(
            select(JournalLine)
            .where(JournalLine.entry_id == result["entry_id"])
            .order_by(JournalLine.id)
        ).all()

    assert entry is not None
    assert entry.date.date() == recognition_date
    assert entry.date.date() != date(2026, 8, 27)
    assert entry.concept == instruction.posting_instruction.description
    assert len(lines) == 2
    assert tuple(line.account_code for line in lines) == ("5106", "1205")
    assert (lines[0].debit, lines[0].credit) == ("33.33", "0")
    assert (lines[1].debit, lines[1].credit) == ("0", "33.33")


def test_posting_module_contains_no_ambient_date_recalculation_hidden_session_or_generic_executor():
    import aqorath.fixed_asset_depreciation_posting as module

    source = getsource(module).lower()
    for forbidden in (
        "datetime.now",
        "date.today",
        "posting_execution",
        "get_session",
        "calculate_monthly_straight_line_depreciation",
        "allocate_monthly_depreciation",
        "declare_fixed_asset_depreciation_recognition",
        "resolve_fixed_asset_depreciation_accounting",
        "prepare_fixed_asset_depreciation_confirmation",
        "confirm_fixed_asset_depreciation(",
        "float(",
        "commit(",
        "rollback(",
    ):
        assert forbidden not in source


def test_application_exposes_dated_posting_as_thin_interface_agnostic_delegations(monkeypatch):
    import aqorath.fixed_asset_depreciation_posting as authority
    import aqorath.application as application

    assert list(
        signature(application.create_fixed_asset_depreciation_posting_instruction).parameters
    ) == ["confirmed_depreciation"]
    assert list(
        signature(application.execute_fixed_asset_depreciation_posting).parameters
    ) == ["instruction"]

    confirmed = object()
    instruction = object()
    created = object()
    executed = object()
    calls = []

    def create_once(supplied_confirmed):
        calls.append(("create", supplied_confirmed))
        return created

    def execute_once(supplied_instruction):
        calls.append(("execute", supplied_instruction))
        return executed

    monkeypatch.setattr(
        authority,
        "create_fixed_asset_depreciation_posting_instruction",
        create_once,
    )
    monkeypatch.setattr(
        authority,
        "execute_fixed_asset_depreciation_posting",
        execute_once,
    )

    assert application.create_fixed_asset_depreciation_posting_instruction(confirmed) is created
    assert application.execute_fixed_asset_depreciation_posting(instruction) is executed
    assert calls == [("create", confirmed), ("execute", instruction)]

    for function in (
        application.create_fixed_asset_depreciation_posting_instruction,
        application.execute_fixed_asset_depreciation_posting,
    ):
        source = getsource(function).lower()
        for forbidden in (
            "core.",
            "post_entry",
            "create_posting_instruction",
            "execute_posting_instruction",
            "recognition_date",
            "date.today",
            "datetime.now",
            "get_session",
        ):
            assert forbidden not in source
