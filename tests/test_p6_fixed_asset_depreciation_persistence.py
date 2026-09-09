"""Phase 6M.1 — atomic fixed-asset depreciation persistence and period identity."""

from dataclasses import fields
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from inspect import Parameter, getsource, signature

import pytest
from sqlalchemy import inspect as sa_inspect, text
from sqlmodel import Session, select


def _initialize_canonical_db(tmp_path, monkeypatch):
    from aqorath import storage
    from aqorath.account_bindings import set_account_binding
    from aqorath.models import Account, EntityRecord, FixedAssetRecord

    db_path = tmp_path / "aqorath-6m.db"
    monkeypatch.setenv("AQORATH_DB", str(db_path))
    storage.init_db(str(db_path), create_tables=True)
    engine = storage.get_engine()

    with Session(engine) as session:
        entity = EntityRecord(
            name="Entidad 6M",
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
            acquisition_cost="100.00",
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
    return engine, db_path, entity_id, fixed_asset_id


def _domain_asset(
    *,
    fixed_asset_id,
    entity_id,
    code="EQ-001",
    acquisition_cost=Decimal("100.00"),
    residual_value=Decimal("0.00"),
    useful_life_months=3,
    is_active=True,
):
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


def _instruction(
    session,
    asset,
    *,
    period_number=1,
    recognition_date=date(2026, 2, 28),
    source_ref="EXPLICIT:6M",
):
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
    from aqorath.fixed_asset_depreciation_confirmation import (
        confirm_fixed_asset_depreciation,
        prepare_fixed_asset_depreciation_confirmation,
    )
    from aqorath.fixed_asset_depreciation_posting import (
        create_fixed_asset_depreciation_posting_instruction,
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
        source_ref,
    )
    accounting = resolve_fixed_asset_depreciation_accounting(recognition)
    prepared = prepare_fixed_asset_depreciation_confirmation(session, accounting)
    confirmed = confirm_fixed_asset_depreciation(prepared)
    return create_fixed_asset_depreciation_posting_instruction(confirmed)


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


def test_persisted_depreciation_record_schema_is_minimal_metadata_with_period_uniqueness():
    from aqorath.models import FixedAssetDepreciationPostingRecord

    table = FixedAssetDepreciationPostingRecord.__table__
    assert table.name == "fixedassetdepreciationpostingrecord"
    assert list(table.columns.keys()) == [
        "id",
        "fixed_asset_id",
        "period_number",
        "entry_id",
        "recognition_source_ref",
        "created_at",
    ]
    assert table.c.fixed_asset_id.nullable is False
    assert table.c.period_number.nullable is False
    assert table.c.entry_id.nullable is False
    assert table.c.recognition_source_ref.nullable is False

    foreign_keys = {
        (fk.parent.name, fk.target_fullname)
        for fk in table.foreign_keys
    }
    assert foreign_keys == {
        ("fixed_asset_id", "fixedasset.id"),
        ("entry_id", "journalentry.id"),
    }

    unique_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("fixed_asset_id", "period_number") in unique_columns


def test_persisted_depreciation_record_does_not_duplicate_ledger_money_accounts_or_posting_date():
    from aqorath.models import FixedAssetDepreciationPostingRecord

    names = set(FixedAssetDepreciationPostingRecord.__table__.columns.keys())
    forbidden = {
        "amount",
        "debit",
        "credit",
        "account_id",
        "account_code",
        "posting_date",
        "recognition_date",
        "description",
    }
    assert names.isdisjoint(forbidden)


def test_frozen_v4_additively_ensures_depreciation_period_registry_without_schema_bump(tmp_path, monkeypatch):
    from aqorath import migrations

    engine, db_path, _, _ = _initialize_canonical_db(tmp_path, monkeypatch)
    assert migrations.CURRENT_SCHEMA_VERSION == 5
    assert "fixedassetdepreciationpostingrecord" in sa_inspect(engine).get_table_names()

    with engine.begin() as connection:
        connection.execute(text("DROP TABLE fixedassetdepreciationpostingrecord"))
    assert "fixedassetdepreciationpostingrecord" not in sa_inspect(engine).get_table_names()

    migrations.migrate_database(str(db_path))
    engine.dispose()

    from sqlalchemy import create_engine

    verification_engine = create_engine(f"sqlite:///{db_path}")
    try:
        assert "fixedassetdepreciationpostingrecord" in sa_inspect(
            verification_engine
        ).get_table_names()
        with verification_engine.connect() as connection:
            version = connection.exec_driver_sql("PRAGMA user_version").scalar_one()
        assert version == 5
    finally:
        verification_engine.dispose()


def test_persisted_depreciation_snapshot_is_frozen_minimal_and_uses_entry_date_as_temporal_truth():
    from aqorath.fixed_asset_depreciation_persistence import (
        PersistedFixedAssetDepreciationPosting,
    )

    assert PersistedFixedAssetDepreciationPosting.__dataclass_params__.frozen
    assert [field.name for field in fields(PersistedFixedAssetDepreciationPosting)] == [
        "fixed_asset_id",
        "period_number",
        "entry_id",
        "posting_date",
        "recognition_source_ref",
    ]


def test_persistence_public_api_has_exact_signatures_without_user_period_or_date_overrides():
    from aqorath.fixed_asset_depreciation_persistence import (
        execute_fixed_asset_depreciation_posting_once,
        load_fixed_asset_depreciation_posting,
    )

    expected = {
        execute_fixed_asset_depreciation_posting_once: ["instruction"],
        load_fixed_asset_depreciation_posting: [
            "session",
            "fixed_asset_id",
            "period_number",
        ],
    }
    for function, names in expected.items():
        sig = signature(function)
        assert list(sig.parameters) == names
        for parameter in sig.parameters.values():
            assert parameter.default is Parameter.empty
            assert parameter.kind is Parameter.POSITIONAL_OR_KEYWORD


def test_executor_requires_nominal_6l_instruction_before_session_or_staging(monkeypatch):
    import aqorath.core
    import aqorath.storage
    from aqorath.fixed_asset_depreciation_persistence import (
        execute_fixed_asset_depreciation_posting_once,
    )

    calls = []

    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("executor crossed boundary before nominal validation")

    monkeypatch.setattr(aqorath.storage, "get_session", forbidden)
    monkeypatch.setattr(aqorath.core, "_stage_entry_in_session", forbidden)

    with pytest.raises(TypeError):
        execute_fixed_asset_depreciation_posting_once(object())
    assert calls == []


def test_unpersisted_asset_identity_fails_closed_before_accounting_staging(tmp_path, monkeypatch):
    import aqorath.core
    from aqorath.fixed_asset_depreciation_persistence import (
        execute_fixed_asset_depreciation_posting_once,
    )

    engine, _, entity_id, _ = _initialize_canonical_db(tmp_path, monkeypatch)
    unpersisted = _domain_asset(fixed_asset_id=None, entity_id=entity_id, code="NEW-001")
    with Session(engine) as session:
        instruction = _instruction(session, unpersisted)

    calls = []
    real_stage = aqorath.core._stage_entry_in_session

    def stage_spy(*args, **kwargs):
        calls.append((args, kwargs))
        return real_stage(*args, **kwargs)

    monkeypatch.setattr(aqorath.core, "_stage_entry_in_session", stage_spy)
    result = execute_fixed_asset_depreciation_posting_once(instruction)

    assert result["ok"] is False
    assert calls == []


def test_executor_validates_persisted_asset_identity_before_staging_forged_truth(tmp_path, monkeypatch):
    import aqorath.core
    from aqorath.fixed_asset_depreciation_persistence import (
        execute_fixed_asset_depreciation_posting_once,
    )

    engine, _, entity_id, fixed_asset_id = _initialize_canonical_db(tmp_path, monkeypatch)
    forged = _domain_asset(
        fixed_asset_id=fixed_asset_id,
        entity_id=entity_id,
        code="FORGED-CODE",
    )
    with Session(engine) as session:
        instruction = _instruction(session, forged)

    calls = []
    real_stage = aqorath.core._stage_entry_in_session

    def stage_spy(*args, **kwargs):
        calls.append((args, kwargs))
        return real_stage(*args, **kwargs)

    monkeypatch.setattr(aqorath.core, "_stage_entry_in_session", stage_spy)
    result = execute_fixed_asset_depreciation_posting_once(instruction)

    assert result["ok"] is False
    assert calls == []


def test_executor_uses_existing_core_staging_once_with_exact_6l_payload(tmp_path, monkeypatch):
    import aqorath.core
    from aqorath.fixed_asset_depreciation_persistence import (
        execute_fixed_asset_depreciation_posting_once,
    )

    engine, _, entity_id, fixed_asset_id = _initialize_canonical_db(tmp_path, monkeypatch)
    asset = _domain_asset(fixed_asset_id=fixed_asset_id, entity_id=entity_id)
    with Session(engine) as session:
        instruction = _instruction(
            session,
            asset,
            period_number=3,
            recognition_date=date(2026, 4, 30),
        )

    real_stage = aqorath.core._stage_entry_in_session
    calls = []

    def stage_once(session, payload):
        calls.append(payload)
        return real_stage(session, payload)

    monkeypatch.setattr(aqorath.core, "_stage_entry_in_session", stage_once)
    result = execute_fixed_asset_depreciation_posting_once(instruction)

    assert result["ok"] is True
    assert calls == [
        {
            "date": date(2026, 4, 30),
            "description": instruction.posting_instruction.description,
            "lines": [
                {
                    "account_id": instruction.posting_instruction.lines[0].account_id,
                    "account_code": "5106",
                    "debit": Decimal("33.34"),
                    "credit": Decimal("0"),
                },
                {
                    "account_id": instruction.posting_instruction.lines[1].account_id,
                    "account_code": "1205",
                    "debit": Decimal("0"),
                    "credit": Decimal("33.34"),
                },
            ],
        }
    ]


def test_real_atomic_persistence_writes_one_entry_two_lines_and_minimal_period_registry(tmp_path, monkeypatch):
    from aqorath.fixed_asset_depreciation_persistence import (
        execute_fixed_asset_depreciation_posting_once,
    )
    from aqorath.models import (
        FixedAssetDepreciationPostingRecord,
        JournalEntry,
        JournalLine,
    )

    engine, _, entity_id, fixed_asset_id = _initialize_canonical_db(tmp_path, monkeypatch)
    asset = _domain_asset(fixed_asset_id=fixed_asset_id, entity_id=entity_id)
    with Session(engine) as session:
        instruction = _instruction(session, asset)

    result = execute_fixed_asset_depreciation_posting_once(instruction)
    assert result["ok"] is True

    with Session(engine) as session:
        entries = session.exec(select(JournalEntry)).all()
        lines = session.exec(select(JournalLine)).all()
        records = session.exec(select(FixedAssetDepreciationPostingRecord)).all()

        assert len(entries) == 1
        assert len(lines) == 2
        assert len(records) == 1
        entry = entries[0]
        record = records[0]
        assert result["entry_id"] == entry.id == record.entry_id
        assert entry.date.date() == date(2026, 2, 28)
        assert record.fixed_asset_id == fixed_asset_id
        assert record.period_number == 1
        assert record.recognition_source_ref == "EXPLICIT:6M"
        assert [(line.account_code, line.debit, line.credit) for line in lines] == [
            ("5106", "33.33", "0"),
            ("1205", "0", "33.33"),
        ]


def test_same_asset_period_is_persistently_single_use_and_second_attempt_creates_nothing(tmp_path, monkeypatch):
    from aqorath.fixed_asset_depreciation_persistence import (
        execute_fixed_asset_depreciation_posting_once,
    )
    from aqorath.models import (
        FixedAssetDepreciationPostingRecord,
        JournalEntry,
        JournalLine,
    )

    engine, _, entity_id, fixed_asset_id = _initialize_canonical_db(tmp_path, monkeypatch)
    asset = _domain_asset(fixed_asset_id=fixed_asset_id, entity_id=entity_id)
    with Session(engine) as session:
        instruction = _instruction(session, asset)

    first = execute_fixed_asset_depreciation_posting_once(instruction)
    second = execute_fixed_asset_depreciation_posting_once(instruction)

    assert first["ok"] is True
    assert second["ok"] is False
    assert "period" in second["error"].lower()

    with Session(engine) as session:
        assert len(session.exec(select(JournalEntry)).all()) == 1
        assert len(session.exec(select(JournalLine)).all()) == 2
        assert len(session.exec(select(FixedAssetDepreciationPostingRecord)).all()) == 1


def test_same_asset_different_periods_are_distinct_allowed_persistent_truth(tmp_path, monkeypatch):
    from aqorath.fixed_asset_depreciation_persistence import (
        execute_fixed_asset_depreciation_posting_once,
    )
    from aqorath.models import FixedAssetDepreciationPostingRecord, JournalEntry

    engine, _, entity_id, fixed_asset_id = _initialize_canonical_db(tmp_path, monkeypatch)
    asset = _domain_asset(fixed_asset_id=fixed_asset_id, entity_id=entity_id)
    with Session(engine) as session:
        first_instruction = _instruction(session, asset, period_number=1)
        second_instruction = _instruction(
            session,
            asset,
            period_number=2,
            recognition_date=date(2026, 3, 31),
        )

    assert execute_fixed_asset_depreciation_posting_once(first_instruction)["ok"] is True
    assert execute_fixed_asset_depreciation_posting_once(second_instruction)["ok"] is True

    with Session(engine) as session:
        records = session.exec(
            select(FixedAssetDepreciationPostingRecord).order_by(
                FixedAssetDepreciationPostingRecord.period_number
            )
        ).all()
        assert [record.period_number for record in records] == [1, 2]
        assert len(session.exec(select(JournalEntry)).all()) == 2


def test_same_period_number_on_different_assets_is_allowed_without_cross_asset_collision(tmp_path, monkeypatch):
    from aqorath.fixed_asset_depreciation_persistence import (
        execute_fixed_asset_depreciation_posting_once,
    )
    from aqorath.models import FixedAssetDepreciationPostingRecord

    engine, _, entity_id, fixed_asset_id = _initialize_canonical_db(tmp_path, monkeypatch)
    first_asset = _domain_asset(fixed_asset_id=fixed_asset_id, entity_id=entity_id)
    with Session(engine) as session:
        second_asset = _persist_second_asset(session, entity_id)
        first_instruction = _instruction(session, first_asset, period_number=1)
        second_instruction = _instruction(session, second_asset, period_number=1)

    assert execute_fixed_asset_depreciation_posting_once(first_instruction)["ok"] is True
    assert execute_fixed_asset_depreciation_posting_once(second_instruction)["ok"] is True

    with Session(engine) as session:
        records = session.exec(select(FixedAssetDepreciationPostingRecord)).all()
        assert {(record.fixed_asset_id, record.period_number) for record in records} == {
            (first_asset.id, 1),
            (second_asset.id, 1),
        }


def test_period_uniqueness_is_enforced_by_sqlite_even_if_executor_guard_is_bypassed(tmp_path, monkeypatch):
    from sqlalchemy.exc import IntegrityError
    from aqorath.fixed_asset_depreciation_persistence import (
        execute_fixed_asset_depreciation_posting_once,
    )
    from aqorath.models import FixedAssetDepreciationPostingRecord

    engine, _, entity_id, fixed_asset_id = _initialize_canonical_db(tmp_path, monkeypatch)
    asset = _domain_asset(fixed_asset_id=fixed_asset_id, entity_id=entity_id)
    with Session(engine) as session:
        instruction = _instruction(session, asset)
    result = execute_fixed_asset_depreciation_posting_once(instruction)
    assert result["ok"] is True

    with Session(engine) as session:
        duplicate = FixedAssetDepreciationPostingRecord(
            fixed_asset_id=fixed_asset_id,
            period_number=1,
            entry_id=result["entry_id"],
            recognition_source_ref="FORGED:DUPLICATE",
        )
        session.add(duplicate)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_staging_failure_never_inserts_period_registry_or_commits_partial_entry(tmp_path, monkeypatch):
    import aqorath.core
    from aqorath.fixed_asset_depreciation_persistence import (
        execute_fixed_asset_depreciation_posting_once,
    )
    from aqorath.models import FixedAssetDepreciationPostingRecord, JournalEntry

    engine, _, entity_id, fixed_asset_id = _initialize_canonical_db(tmp_path, monkeypatch)
    asset = _domain_asset(fixed_asset_id=fixed_asset_id, entity_id=entity_id)
    with Session(engine) as session:
        instruction = _instruction(session, asset)

    monkeypatch.setattr(
        aqorath.core,
        "_stage_entry_in_session",
        lambda session, payload: (None, "explicit staging failure"),
    )
    result = execute_fixed_asset_depreciation_posting_once(instruction)

    assert result == {"ok": False, "error": "explicit staging failure"}
    with Session(engine) as session:
        assert session.exec(select(JournalEntry)).all() == []
        assert session.exec(select(FixedAssetDepreciationPostingRecord)).all() == []


def test_single_commit_failure_rolls_back_entry_lines_and_period_registry(tmp_path, monkeypatch):
    from sqlmodel import Session as SQLModelSession
    from aqorath.fixed_asset_depreciation_persistence import (
        execute_fixed_asset_depreciation_posting_once,
    )
    from aqorath.models import (
        FixedAssetDepreciationPostingRecord,
        JournalEntry,
        JournalLine,
    )

    engine, _, entity_id, fixed_asset_id = _initialize_canonical_db(tmp_path, monkeypatch)
    asset = _domain_asset(fixed_asset_id=fixed_asset_id, entity_id=entity_id)
    with Session(engine) as session:
        instruction = _instruction(session, asset)

    def fail_commit(self):
        raise RuntimeError("forced 6M commit failure")

    monkeypatch.setattr(SQLModelSession, "commit", fail_commit)
    result = execute_fixed_asset_depreciation_posting_once(instruction)
    assert result["ok"] is False
    assert "forced 6M commit failure" in result["error"]

    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM journalentry")).scalar_one() == 0
        assert connection.execute(text("SELECT COUNT(*) FROM journalline")).scalar_one() == 0
        assert connection.execute(
            text("SELECT COUNT(*) FROM fixedassetdepreciationpostingrecord")
        ).scalar_one() == 0


def test_loader_reconstructs_period_identity_and_uses_journal_entry_date_without_recalculation(tmp_path, monkeypatch):
    import aqorath.fixed_asset_depreciation
    import aqorath.fixed_asset_depreciation_allocation
    import aqorath.fixed_asset_depreciation_recognition
    from aqorath.fixed_asset_depreciation_persistence import (
        execute_fixed_asset_depreciation_posting_once,
        load_fixed_asset_depreciation_posting,
    )

    engine, _, entity_id, fixed_asset_id = _initialize_canonical_db(tmp_path, monkeypatch)
    asset = _domain_asset(fixed_asset_id=fixed_asset_id, entity_id=entity_id)
    with Session(engine) as session:
        instruction = _instruction(
            session,
            asset,
            period_number=2,
            recognition_date=date(2026, 3, 31),
            source_ref="EXPLICIT:6I-TRACE",
        )
    result = execute_fixed_asset_depreciation_posting_once(instruction)
    assert result["ok"] is True

    def forbidden(*args, **kwargs):
        raise AssertionError("loader recalculated depreciation truth")

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

    with Session(engine) as session:
        loaded = load_fixed_asset_depreciation_posting(session, fixed_asset_id, 2)

    assert loaded.fixed_asset_id == fixed_asset_id
    assert loaded.period_number == 2
    assert loaded.entry_id == result["entry_id"]
    assert loaded.posting_date == date(2026, 3, 31)
    assert loaded.recognition_source_ref == "EXPLICIT:6I-TRACE"


def test_loader_is_read_only_uses_only_supplied_session_and_missing_period_fails_closed(tmp_path, monkeypatch):
    import aqorath.storage
    from aqorath.fixed_asset_depreciation_persistence import (
        execute_fixed_asset_depreciation_posting_once,
        load_fixed_asset_depreciation_posting,
    )

    engine, _, entity_id, fixed_asset_id = _initialize_canonical_db(tmp_path, monkeypatch)
    asset = _domain_asset(fixed_asset_id=fixed_asset_id, entity_id=entity_id)
    with Session(engine) as session:
        instruction = _instruction(session, asset)
    assert execute_fixed_asset_depreciation_posting_once(instruction)["ok"] is True

    monkeypatch.setattr(
        aqorath.storage,
        "get_session",
        lambda: (_ for _ in ()).throw(AssertionError("hidden session used by read")),
    )

    with Session(engine) as session:
        def forbidden(*args, **kwargs):
            raise AssertionError("read attempted mutation")

        monkeypatch.setattr(session, "add", forbidden)
        monkeypatch.setattr(session, "commit", forbidden)
        monkeypatch.setattr(session, "delete", forbidden)
        loaded = load_fixed_asset_depreciation_posting(session, fixed_asset_id, 1)
        assert loaded.period_number == 1

        with pytest.raises(LookupError):
            load_fixed_asset_depreciation_posting(session, fixed_asset_id, 3)


def test_period_identity_does_not_impose_hidden_sequence_or_active_state_rules(tmp_path, monkeypatch):
    from aqorath.fixed_asset_depreciation_persistence import (
        execute_fixed_asset_depreciation_posting_once,
    )

    engine, _, entity_id, fixed_asset_id = _initialize_canonical_db(tmp_path, monkeypatch)
    inactive_asset = _domain_asset(
        fixed_asset_id=fixed_asset_id,
        entity_id=entity_id,
        is_active=False,
    )
    with Session(engine) as session:
        instruction = _instruction(
            session,
            inactive_asset,
            period_number=2,
            recognition_date=date(2026, 3, 31),
        )

    result = execute_fixed_asset_depreciation_posting_once(instruction)
    assert result["ok"] is True


def test_persistence_module_reuses_core_staging_and_contains_no_second_accounting_engine_or_recalculation():
    import aqorath.fixed_asset_depreciation_persistence as module

    source = getsource(module)
    assert "_core._stage_entry_in_session" in source
    assert "_storage.get_session" in source
    forbidden = (
        "_core.post_entry(",
        "execute_posting_instruction(",
        "execute_fixed_asset_depreciation_posting(",
        "calculate_monthly_straight_line_depreciation(",
        "allocate_monthly_depreciation(",
        "declare_fixed_asset_depreciation_recognition(",
        "resolve_fixed_asset_depreciation_accounting(",
        "prepare_fixed_asset_depreciation_confirmation(",
        "confirm_fixed_asset_depreciation(",
        "float(",
    )
    for token in forbidden:
        assert token not in source


def test_application_exposes_atomic_depreciation_persistence_and_read_as_thin_delegations(monkeypatch):
    import aqorath.application as application
    import aqorath.fixed_asset_depreciation_persistence as authority

    assert list(signature(application.execute_fixed_asset_depreciation_posting_once).parameters) == [
        "instruction"
    ]
    assert list(signature(application.load_fixed_asset_depreciation_posting).parameters) == [
        "session",
        "fixed_asset_id",
        "period_number",
    ]

    instruction = object()
    session = object()
    write_result = {"ok": True, "entry_id": 55}
    read_result = object()
    calls = []

    def write_once(supplied):
        calls.append(("write", supplied))
        return write_result

    def read_once(supplied_session, fixed_asset_id, period_number):
        calls.append(("read", supplied_session, fixed_asset_id, period_number))
        return read_result

    monkeypatch.setattr(
        authority,
        "execute_fixed_asset_depreciation_posting_once",
        write_once,
    )
    monkeypatch.setattr(
        authority,
        "load_fixed_asset_depreciation_posting",
        read_once,
    )

    assert application.execute_fixed_asset_depreciation_posting_once(instruction) is write_result
    assert application.load_fixed_asset_depreciation_posting(session, 41, 2) is read_result
    assert calls == [
        ("write", instruction),
        ("read", session, 41, 2),
    ]
