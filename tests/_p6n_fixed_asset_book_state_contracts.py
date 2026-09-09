"""Phase 6N.1 — canonical fixed-asset book-state read contracts.

Contracts only. Book state is a read-only projection of canonical SQLite truth:
FixedAsset acquisition metadata plus depreciation amounts actually persisted through
the Phase 6M asset-period registry and its linked JournalEntry/JournalLine rows.
It never recalculates a theoretical depreciation schedule, uses a global accumulated-
depreciation account balance, or persists carrying value as competing truth.
"""

from dataclasses import fields
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from inspect import Parameter, getsource, signature

import pytest
from sqlmodel import Session, select


def _initialize_canonical_db(tmp_path, monkeypatch):
    from aqorath import storage
    from aqorath.account_bindings import set_account_binding
    from aqorath.models import Account, EntityRecord, FixedAssetRecord

    tmp_path.mkdir(parents=True, exist_ok=True)
    db_path = tmp_path / "aqorath-6n.db"
    monkeypatch.setenv("AQORATH_DB", str(db_path))
    storage.init_db(str(db_path), create_tables=True)
    engine = storage.get_engine()

    with Session(engine) as session:
        entity = EntityRecord(
            name="Entidad 6N",
            rfc="AAA010101AAA",
            legal_personality="persona_moral",
            legal_form="A.C.",
            is_active=True,
        )
        session.add(entity)
        session.commit()
        session.refresh(entity)

        expense = Account(
            code="5106",
            name="Depreciación y amortización",
            nature="Deudora",
        )
        accumulated = Account(
            code="1205",
            name="Depreciación acumulada",
            nature="Acreedora",
        )
        session.add(expense)
        session.add(accumulated)
        session.commit()

        asset_record = FixedAssetRecord(
            entity_id=entity.id,
            code="EQ-001",
            name="Equipo de cómputo",
            acquisition_date=date(2026, 1, 15),
            in_service_date=date(2026, 2, 1),
            acquisition_cost="100.0000",
            residual_value="0.00",
            useful_life_months=3,
            depreciation_method="straight_line",
            is_active=True,
        )
        session.add(asset_record)
        session.commit()
        session.refresh(asset_record)

        set_account_binding(session, "depreciation_expense", "5106")
        set_account_binding(session, "accumulated_depreciation", "1205")

        entity_id = entity.id
        fixed_asset_id = asset_record.id

    from period_fixtures import seed_engine_calendar
    seed_engine_calendar(engine)
    return engine, entity_id, fixed_asset_id


def _domain_asset(*, fixed_asset_id, entity_id, code="EQ-001", acquisition_cost=Decimal("100.0000"), residual_value=Decimal("0.00"), useful_life_months=3, is_active=True):
    from aqorath.fixed_asset import FixedAsset

    return FixedAsset(
        id=fixed_asset_id,
        entity_id=entity_id,
        code=code,
        name="Equipo de cómputo",
        acquisition_date=date(2026, 1, 15),
        in_service_date=date(2026, 2, 1),
        acquisition_cost=acquisition_cost,
        residual_value=residual_value,
        useful_life_months=useful_life_months,
        depreciation_method="straight_line",
        is_active=is_active,
    )


def _instruction(session, asset, *, period_number, recognition_date, source_ref):
    from aqorath.fixed_asset_depreciation import calculate_monthly_straight_line_depreciation
    from aqorath.fixed_asset_depreciation_allocation import (
        FixedAssetDepreciationAllocationPolicy,
        allocate_monthly_depreciation,
    )
    from aqorath.fixed_asset_depreciation_recognition import declare_fixed_asset_depreciation_recognition
    from aqorath.fixed_asset_depreciation_accounting import resolve_fixed_asset_depreciation_accounting
    from aqorath.fixed_asset_depreciation_confirmation import (
        confirm_fixed_asset_depreciation,
        prepare_fixed_asset_depreciation_confirmation,
    )
    from aqorath.fixed_asset_depreciation_posting import create_fixed_asset_depreciation_posting_instruction

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
        source_ref,
    )
    accounting = resolve_fixed_asset_depreciation_accounting(recognition)
    prepared = prepare_fixed_asset_depreciation_confirmation(session, accounting)
    confirmed = confirm_fixed_asset_depreciation(prepared)
    return create_fixed_asset_depreciation_posting_instruction(confirmed)


def _post_period(engine, asset, period_number, recognition_date, source_ref=None):
    from aqorath.fixed_asset_depreciation_persistence import execute_fixed_asset_depreciation_posting_once

    source_ref = source_ref or f"EXPLICIT:6N:P{period_number}"
    with Session(engine) as session:
        instruction = _instruction(
            session,
            asset,
            period_number=period_number,
            recognition_date=recognition_date,
            source_ref=source_ref,
        )
    result = execute_fixed_asset_depreciation_posting_once(instruction)
    assert result["ok"] is True
    return result["entry_id"]


def _persist_second_asset(session, entity_id):
    from aqorath.fixed_asset import FixedAsset
    from aqorath.models import FixedAssetRecord

    record = FixedAssetRecord(
        entity_id=entity_id,
        code="EQ-002",
        name="Segundo equipo",
        acquisition_date=date(2026, 1, 20),
        in_service_date=date(2026, 2, 1),
        acquisition_cost="60.00",
        residual_value="0.00",
        useful_life_months=3,
        depreciation_method="straight_line",
        is_active=True,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return FixedAsset(
        id=record.id,
        entity_id=entity_id,
        code=record.code,
        name=record.name,
        acquisition_date=record.acquisition_date,
        in_service_date=record.in_service_date,
        acquisition_cost=Decimal(record.acquisition_cost),
        residual_value=Decimal(record.residual_value),
        useful_life_months=record.useful_life_months,
        depreciation_method=record.depreciation_method,
        is_active=record.is_active,
    )


def _load(session, entity_id, fixed_asset_id, as_of=None):
    from aqorath.fixed_asset_book_state import load_fixed_asset_book_state

    return load_fixed_asset_book_state(session, entity_id, fixed_asset_id, as_of)


def test_book_state_public_contract_is_frozen_exact_and_projection_only():
    from aqorath.fixed_asset_book_state import (
        FixedAssetBookState,
        FixedAssetRecognizedDepreciationPeriod,
        load_fixed_asset_book_state,
    )

    assert FixedAssetRecognizedDepreciationPeriod.__dataclass_params__.frozen
    assert [field.name for field in fields(FixedAssetRecognizedDepreciationPeriod)] == [
        "period_number",
        "entry_id",
        "posting_date",
        "recognition_source_ref",
        "amount",
    ]
    assert FixedAssetBookState.__dataclass_params__.frozen
    assert [field.name for field in fields(FixedAssetBookState)] == [
        "fixed_asset_id",
        "entity_id",
        "code",
        "as_of",
        "acquisition_cost",
        "residual_value",
        "accumulated_depreciation",
        "carrying_value",
        "recognized_periods",
    ]

    sig = signature(load_fixed_asset_book_state)
    assert list(sig.parameters) == ["session", "entity_id", "fixed_asset_id", "as_of"]
    assert sig.parameters["session"].default is Parameter.empty
    assert sig.parameters["entity_id"].default is Parameter.empty
    assert sig.parameters["fixed_asset_id"].default is Parameter.empty
    assert sig.parameters["as_of"].default is None


def test_asset_without_recognized_depreciation_has_zero_accumulated_and_cost_carrying_value(tmp_path, monkeypatch):
    engine, entity_id, fixed_asset_id = _initialize_canonical_db(tmp_path, monkeypatch)
    with Session(engine) as session:
        state = _load(session, entity_id, fixed_asset_id)

    assert state.fixed_asset_id == fixed_asset_id
    assert state.entity_id == entity_id
    assert state.code == "EQ-001"
    assert state.as_of is None
    assert state.acquisition_cost.as_tuple() == Decimal("100.0000").as_tuple()
    assert state.residual_value.as_tuple() == Decimal("0.00").as_tuple()
    assert state.accumulated_depreciation == Decimal("0")
    assert state.carrying_value.as_tuple() == Decimal("100.0000").as_tuple()
    assert state.recognized_periods == ()


def test_one_real_persisted_period_drives_accumulated_depreciation_and_carrying_value_exactly(tmp_path, monkeypatch):
    engine, entity_id, fixed_asset_id = _initialize_canonical_db(tmp_path, monkeypatch)
    asset = _domain_asset(fixed_asset_id=fixed_asset_id, entity_id=entity_id)
    entry_id = _post_period(engine, asset, 1, date(2026, 2, 28))

    with Session(engine) as session:
        state = _load(session, entity_id, fixed_asset_id)

    assert state.accumulated_depreciation.as_tuple() == Decimal("33.33").as_tuple()
    assert state.carrying_value.as_tuple() == Decimal("66.6700").as_tuple()
    assert len(state.recognized_periods) == 1
    period = state.recognized_periods[0]
    assert period.period_number == 1
    assert period.entry_id == entry_id
    assert period.posting_date == date(2026, 2, 28)
    assert period.recognition_source_ref == "EXPLICIT:6N:P1"
    assert period.amount.as_tuple() == Decimal("33.33").as_tuple()


def test_multiple_posted_periods_sum_actual_ledger_amounts_and_preserve_final_remainder(tmp_path, monkeypatch):
    engine, entity_id, fixed_asset_id = _initialize_canonical_db(tmp_path, monkeypatch)
    asset = _domain_asset(fixed_asset_id=fixed_asset_id, entity_id=entity_id)
    _post_period(engine, asset, 3, date(2026, 4, 30))
    _post_period(engine, asset, 1, date(2026, 2, 28))
    _post_period(engine, asset, 2, date(2026, 3, 31))

    with Session(engine) as session:
        state = _load(session, entity_id, fixed_asset_id)

    assert [period.period_number for period in state.recognized_periods] == [1, 2, 3]
    assert [period.amount.as_tuple() for period in state.recognized_periods] == [
        Decimal("33.33").as_tuple(),
        Decimal("33.33").as_tuple(),
        Decimal("33.34").as_tuple(),
    ]
    assert state.accumulated_depreciation.as_tuple() == Decimal("100.00").as_tuple()
    assert state.carrying_value.as_tuple() == Decimal("0.0000").as_tuple()


def test_as_of_filters_by_authoritative_journal_entry_date_not_period_number_or_registry_creation(tmp_path, monkeypatch):
    engine, entity_id, fixed_asset_id = _initialize_canonical_db(tmp_path, monkeypatch)
    asset = _domain_asset(fixed_asset_id=fixed_asset_id, entity_id=entity_id)
    _post_period(engine, asset, 2, date(2026, 3, 31))
    _post_period(engine, asset, 1, date(2026, 5, 31))

    with Session(engine) as session:
        state = _load(session, entity_id, fixed_asset_id, date(2026, 4, 30))

    assert state.as_of == date(2026, 4, 30)
    assert [period.period_number for period in state.recognized_periods] == [2]
    assert state.accumulated_depreciation.as_tuple() == Decimal("33.33").as_tuple()
    assert state.carrying_value.as_tuple() == Decimal("66.6700").as_tuple()


def test_book_state_is_asset_scoped_and_never_uses_global_accumulated_depreciation_balance(tmp_path, monkeypatch):
    engine, entity_id, fixed_asset_id = _initialize_canonical_db(tmp_path, monkeypatch)
    first = _domain_asset(fixed_asset_id=fixed_asset_id, entity_id=entity_id)
    with Session(engine) as session:
        second = _persist_second_asset(session, entity_id)

    _post_period(engine, first, 1, date(2026, 2, 28), "EXPLICIT:6N:FIRST")
    _post_period(engine, second, 1, date(2026, 2, 28), "EXPLICIT:6N:SECOND")

    with Session(engine) as session:
        first_state = _load(session, entity_id, first.id)
        second_state = _load(session, entity_id, second.id)

    assert first_state.accumulated_depreciation.as_tuple() == Decimal("33.33").as_tuple()
    assert second_state.accumulated_depreciation.as_tuple() == Decimal("20.00").as_tuple()
    assert first_state.carrying_value.as_tuple() == Decimal("66.6700").as_tuple()
    assert second_state.carrying_value.as_tuple() == Decimal("40.00").as_tuple()


def test_historical_book_state_remains_available_for_inactive_asset(tmp_path, monkeypatch):
    from aqorath.models import FixedAssetRecord

    engine, entity_id, fixed_asset_id = _initialize_canonical_db(tmp_path, monkeypatch)
    asset = _domain_asset(fixed_asset_id=fixed_asset_id, entity_id=entity_id)
    _post_period(engine, asset, 1, date(2026, 2, 28))

    with Session(engine) as session:
        record = session.get(FixedAssetRecord, fixed_asset_id)
        record.is_active = False
        session.add(record)
        session.commit()
        state = _load(session, entity_id, fixed_asset_id)

    assert state.fixed_asset_id == fixed_asset_id
    assert state.accumulated_depreciation.as_tuple() == Decimal("33.33").as_tuple()


def test_book_state_validates_scope_identity_and_as_of_fail_closed(tmp_path, monkeypatch):
    engine, entity_id, fixed_asset_id = _initialize_canonical_db(tmp_path, monkeypatch)
    with Session(engine) as session:
        for bad_entity in (0, -1, True, "1"):
            with pytest.raises((TypeError, ValueError)):
                _load(session, bad_entity, fixed_asset_id)
        for bad_asset in (0, -1, True, "1"):
            with pytest.raises((TypeError, ValueError)):
                _load(session, entity_id, bad_asset)
        for bad_as_of in (datetime(2026, 2, 28), "2026-02-28", 20260228):
            with pytest.raises((TypeError, ValueError)):
                _load(session, entity_id, fixed_asset_id, bad_as_of)
        with pytest.raises(LookupError):
            _load(session, entity_id + 999, fixed_asset_id)
        with pytest.raises(LookupError):
            _load(session, entity_id, fixed_asset_id + 999)


def test_corrupt_fixed_asset_decimal_text_fails_closed_without_float_or_silent_coercion(tmp_path, monkeypatch):
    from aqorath.models import FixedAssetRecord

    engine, entity_id, fixed_asset_id = _initialize_canonical_db(tmp_path, monkeypatch)
    with Session(engine) as session:
        record = session.get(FixedAssetRecord, fixed_asset_id)
        record.acquisition_cost = "not-a-decimal"
        session.add(record)
        session.commit()
        with pytest.raises(ValueError):
            _load(session, entity_id, fixed_asset_id)


def test_missing_or_wrongly_scoped_linked_journal_entry_fails_closed(tmp_path, monkeypatch):
    from aqorath.models import FixedAssetDepreciationPostingRecord, JournalEntry

    engine, entity_id, fixed_asset_id = _initialize_canonical_db(tmp_path, monkeypatch)
    asset = _domain_asset(fixed_asset_id=fixed_asset_id, entity_id=entity_id)
    entry_id = _post_period(engine, asset, 1, date(2026, 2, 28))

    with Session(engine) as session:
        entry = session.get(JournalEntry, entry_id)
        session.delete(entry)
        session.commit()
        with pytest.raises(LookupError):
            _load(session, entity_id, fixed_asset_id)

        record = session.exec(select(FixedAssetDepreciationPostingRecord)).one()
        assert record.entry_id == entry_id


def test_linked_depreciation_entry_must_be_exact_two_line_balanced_positive_truth(tmp_path, monkeypatch):
    from aqorath.models import JournalLine

    engine, entity_id, fixed_asset_id = _initialize_canonical_db(tmp_path, monkeypatch)
    asset = _domain_asset(fixed_asset_id=fixed_asset_id, entity_id=entity_id)
    entry_id = _post_period(engine, asset, 1, date(2026, 2, 28))

    with Session(engine) as session:
        lines = session.exec(select(JournalLine).where(JournalLine.entry_id == entry_id)).all()
        assert len(lines) == 2
        lines[0].debit = "33.32"
        session.add(lines[0])
        session.commit()
        with pytest.raises(ValueError):
            _load(session, entity_id, fixed_asset_id)


def test_linked_depreciation_entry_rejects_corrupt_money_and_extra_lines(tmp_path, monkeypatch):
    from aqorath.models import JournalLine

    engine, entity_id, fixed_asset_id = _initialize_canonical_db(tmp_path, monkeypatch)
    asset = _domain_asset(fixed_asset_id=fixed_asset_id, entity_id=entity_id)
    entry_id = _post_period(engine, asset, 1, date(2026, 2, 28))

    with Session(engine) as session:
        lines = session.exec(select(JournalLine).where(JournalLine.entry_id == entry_id)).all()
        lines[0].debit = "NaN"
        session.add(lines[0])
        session.commit()
        with pytest.raises(ValueError):
            _load(session, entity_id, fixed_asset_id)

    engine2, entity_id2, fixed_asset_id2 = _initialize_canonical_db(tmp_path / "second", monkeypatch)
    asset2 = _domain_asset(fixed_asset_id=fixed_asset_id2, entity_id=entity_id2)
    entry_id2 = _post_period(engine2, asset2, 1, date(2026, 2, 28))
    with Session(engine2) as session:
        source = session.exec(select(JournalLine).where(JournalLine.entry_id == entry_id2)).first()
        session.add(
            JournalLine(
                entry_id=entry_id2,
                account_code=source.account_code,
                account_id=source.account_id,
                debit="0",
                credit="1.00",
            )
        )
        session.commit()
        with pytest.raises(ValueError):
            _load(session, entity_id2, fixed_asset_id2)


def test_projection_fails_closed_if_recognized_depreciation_would_breach_residual_value(tmp_path, monkeypatch):
    from aqorath.models import JournalLine

    engine, entity_id, fixed_asset_id = _initialize_canonical_db(tmp_path, monkeypatch)
    asset = _domain_asset(fixed_asset_id=fixed_asset_id, entity_id=entity_id)
    entry_id = _post_period(engine, asset, 1, date(2026, 2, 28))

    with Session(engine) as session:
        lines = session.exec(select(JournalLine).where(JournalLine.entry_id == entry_id)).all()
        for line in lines:
            if Decimal(line.debit) > 0:
                line.debit = "100.01"
            if Decimal(line.credit) > 0:
                line.credit = "100.01"
            session.add(line)
        session.commit()
        with pytest.raises(ValueError):
            _load(session, entity_id, fixed_asset_id)


def test_book_state_read_is_read_only_uses_supplied_session_and_does_not_open_hidden_storage(tmp_path, monkeypatch):
    import aqorath.storage

    engine, entity_id, fixed_asset_id = _initialize_canonical_db(tmp_path, monkeypatch)

    def forbidden_session():
        raise AssertionError("book-state read opened hidden storage")

    monkeypatch.setattr(aqorath.storage, "get_session", forbidden_session)
    with Session(engine) as session:
        calls = []
        for name in ("add", "delete", "commit", "rollback"):
            original = getattr(session, name)

            def make_spy(method_name, method):
                def spy(*args, **kwargs):
                    calls.append(method_name)
                    return method(*args, **kwargs)
                return spy

            monkeypatch.setattr(session, name, make_spy(name, original))
        state = _load(session, entity_id, fixed_asset_id)

    assert state.fixed_asset_id == fixed_asset_id
    assert calls == []


def test_book_state_never_recalculates_schedule_reallocates_rounds_or_resolves_current_account_bindings(tmp_path, monkeypatch):
    import aqorath.account_bindings
    import aqorath.fixed_asset_depreciation
    import aqorath.fixed_asset_depreciation_allocation

    engine, entity_id, fixed_asset_id = _initialize_canonical_db(tmp_path, monkeypatch)
    asset = _domain_asset(fixed_asset_id=fixed_asset_id, entity_id=entity_id)
    _post_period(engine, asset, 1, date(2026, 2, 28))

    def forbidden(*args, **kwargs):
        raise AssertionError("book-state read entered a forbidden authority")

    monkeypatch.setattr(aqorath.fixed_asset_depreciation, "calculate_monthly_straight_line_depreciation", forbidden)
    monkeypatch.setattr(aqorath.fixed_asset_depreciation_allocation, "allocate_monthly_depreciation", forbidden)
    monkeypatch.setattr(aqorath.account_bindings, "get_account_binding", forbidden)
    monkeypatch.setattr(aqorath.account_bindings, "get_account_bindings", forbidden)

    with Session(engine) as session:
        state = _load(session, entity_id, fixed_asset_id)

    assert state.accumulated_depreciation.as_tuple() == Decimal("33.33").as_tuple()


def test_book_state_module_contains_no_persistence_schedule_or_global_account_authority():
    import aqorath.fixed_asset_book_state as module

    source = getsource(module).lower()
    for forbidden in (
        "get_session",
        "session.commit",
        "session.add",
        "session.delete",
        "calculate_monthly_straight_line_depreciation",
        "allocate_monthly_depreciation",
        "get_account_binding",
        "trial_balance",
        "accountrolebinding",
        "from .assets",
        "import aqorath.assets",
        "float(",
    ):
        assert forbidden not in source


def test_application_exposes_book_state_as_exact_thin_interface_agnostic_delegation(monkeypatch):
    import aqorath.application as application
    import aqorath.fixed_asset_book_state as authority

    assert str(signature(application.get_fixed_asset_book_state)) == "(session, entity_id, fixed_asset_id, as_of=None)"
    sentinel = object()
    calls = []

    def delegate(session, entity_id, fixed_asset_id, as_of=None):
        calls.append((session, entity_id, fixed_asset_id, as_of))
        return sentinel

    monkeypatch.setattr(authority, "load_fixed_asset_book_state", delegate)
    session = object()
    result = application.get_fixed_asset_book_state(session, 7, 11, date(2026, 6, 30))
    assert result is sentinel
    assert calls == [(session, 7, 11, date(2026, 6, 30))]


def test_application_real_book_state_matches_authority_without_recalculation(tmp_path, monkeypatch):
    import aqorath.application as application

    engine, entity_id, fixed_asset_id = _initialize_canonical_db(tmp_path, monkeypatch)
    asset = _domain_asset(fixed_asset_id=fixed_asset_id, entity_id=entity_id)
    _post_period(engine, asset, 1, date(2026, 2, 28))
    _post_period(engine, asset, 2, date(2026, 3, 31))

    with Session(engine) as session:
        state = application.get_fixed_asset_book_state(
            session,
            entity_id,
            fixed_asset_id,
            date(2026, 3, 31),
        )

    assert [period.period_number for period in state.recognized_periods] == [1, 2]
    assert state.accumulated_depreciation.as_tuple() == Decimal("66.66").as_tuple()
    assert state.carrying_value.as_tuple() == Decimal("33.3400").as_tuple()
