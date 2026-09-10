"""Phase 6Q.1 — atomic fixed-asset acquisition persistence and one-use identity."""

from contextlib import contextmanager
from dataclasses import fields
from datetime import date, datetime
from decimal import Decimal
from inspect import Parameter, getsource, signature

import pytest
from sqlalchemy import inspect as sa_inspect, text
from sqlmodel import Session, select


def _initialize_canonical_db(tmp_path, monkeypatch):
    from aqorath import storage
    from aqorath.account_bindings import set_account_binding
    from aqorath.models import Account, EntityRecord, FixedAssetRecord

    db_path = tmp_path / "aqorath-6q.db"
    monkeypatch.setenv("AQORATH_DB", str(db_path))
    storage.init_db(str(db_path), create_tables=True)
    engine = storage.get_engine()

    with Session(engine) as session:
        entity = EntityRecord(
            name="Entidad 6Q",
            rfc="AAA010101AAA",
            legal_personality="persona_moral",
            legal_form="S.A. de C.V.",
            is_active=True,
        )
        session.add(entity)
        session.commit()
        session.refresh(entity)

        accounts = (
            Account(code="1203", name="Equipo de cómputo", nature="Deudora"),
            Account(code="1101", name="Bancos", nature="Deudora"),
            Account(code="1102", name="Caja", nature="Deudora"),
            Account(code="2101", name="Proveedores", nature="Acreedora"),
        )
        for account in accounts:
            session.add(account)
        session.commit()

        asset_record = FixedAssetRecord(
            entity_id=entity.id,
            code="EQ-ACQ-001",
            name="Equipo adquirido",
            acquisition_date=date(2026, 1, 15),
            in_service_date=date(2026, 2, 1),
            acquisition_cost="100.00",
            residual_value="0.00",
            useful_life_months=36,
            depreciation_method="straight_line",
            is_active=True,
        )
        session.add(asset_record)
        session.commit()
        session.refresh(asset_record)

        set_account_binding(session, "fixed_asset_computer_equipment", "1203")
        set_account_binding(session, "bank", "1101")
        set_account_binding(session, "cash", "1102")
        set_account_binding(session, "accounts_payable", "2101")

        entity_id = entity.id
        fixed_asset_id = asset_record.id

    from period_fixtures import seed_engine_calendar
    seed_engine_calendar(engine)
    return engine, db_path, entity_id, fixed_asset_id


def _domain_asset(
    *,
    fixed_asset_id,
    entity_id,
    code="EQ-ACQ-001",
    acquisition_date=date(2026, 1, 15),
    acquisition_cost=Decimal("100.00"),
    is_active=True,
):
    from aqorath.fixed_asset import FixedAsset

    return FixedAsset(
        id=fixed_asset_id,
        entity_id=entity_id,
        code=code,
        name="Equipo adquirido",
        acquisition_date=acquisition_date,
        in_service_date=date(2026, 2, 1),
        acquisition_cost=acquisition_cost,
        residual_value=Decimal("0.00"),
        useful_life_months=36,
        depreciation_method="straight_line",
        is_active=is_active,
    )


def _instruction(
    session,
    asset,
    *,
    asset_class="computer_equipment",
    settlement_method="bank",
):
    from aqorath.fixed_asset_acquisition import (
        create_fixed_asset_acquisition_fact,
        resolve_fixed_asset_acquisition_accounting,
    )
    from aqorath.fixed_asset_acquisition_confirmation import (
        confirm_fixed_asset_acquisition,
        prepare_fixed_asset_acquisition_confirmation,
    )
    from aqorath.fixed_asset_acquisition_posting import (
        create_fixed_asset_acquisition_posting_instruction,
    )

    fact = create_fixed_asset_acquisition_fact(
        asset,
        asset_class,
        settlement_method,
    )
    accounting = resolve_fixed_asset_acquisition_accounting(fact)
    prepared = prepare_fixed_asset_acquisition_confirmation(session, accounting)
    confirmed = confirm_fixed_asset_acquisition(prepared)
    return create_fixed_asset_acquisition_posting_instruction(confirmed)


def _persist_second_asset(session, entity_id):
    from aqorath.fixed_asset import FixedAsset
    from aqorath.models import FixedAssetRecord

    record = FixedAssetRecord(
        entity_id=entity_id,
        code="EQ-ACQ-002",
        name="Segundo equipo adquirido",
        acquisition_date=date(2026, 3, 10),
        in_service_date=date(2026, 3, 15),
        acquisition_cost="60.00",
        residual_value="0.00",
        useful_life_months=24,
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


def test_acquisition_record_schema_is_minimal_semantic_provenance_with_one_use_uniqueness():
    from aqorath.models import FixedAssetAcquisitionPostingRecord

    table = FixedAssetAcquisitionPostingRecord.__table__
    assert table.name == "fixedassetacquisitionpostingrecord"
    assert list(table.columns.keys()) == [
        "id",
        "fixed_asset_id",
        "entry_id",
        "asset_class",
        "settlement_method",
        "created_at",
    ]
    assert table.c.fixed_asset_id.nullable is False
    assert table.c.entry_id.nullable is False
    assert table.c.asset_class.nullable is False
    assert table.c.settlement_method.nullable is False

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
    assert ("fixed_asset_id",) in unique_columns
    assert ("entry_id",) in unique_columns


def test_acquisition_record_does_not_duplicate_ledger_money_accounts_dates_or_asset_registry_identity():
    from aqorath.models import FixedAssetAcquisitionPostingRecord

    names = set(FixedAssetAcquisitionPostingRecord.__table__.columns.keys())
    forbidden = {
        "amount",
        "acquisition_cost",
        "debit",
        "credit",
        "account_id",
        "account_code",
        "account_role",
        "posting_date",
        "acquisition_date",
        "description",
        "fixed_asset_code",
        "entity_id",
    }
    assert names.isdisjoint(forbidden)


def test_frozen_v4_additively_ensures_acquisition_registry_without_schema_bump(tmp_path, monkeypatch):
    from aqorath import migrations

    engine, db_path, _, _ = _initialize_canonical_db(tmp_path, monkeypatch)
    assert migrations.get_schema_version(db_path) == migrations.CURRENT_SCHEMA_VERSION
    assert "fixedassetacquisitionpostingrecord" in sa_inspect(engine).get_table_names()

    with engine.begin() as connection:
        connection.execute(text("DROP TABLE fixedassetacquisitionpostingrecord"))
    assert "fixedassetacquisitionpostingrecord" not in sa_inspect(engine).get_table_names()

    migrations.migrate_database(str(db_path))
    engine.dispose()

    from sqlalchemy import create_engine

    verification_engine = create_engine(f"sqlite:///{db_path}")
    try:
        assert "fixedassetacquisitionpostingrecord" in sa_inspect(
            verification_engine
        ).get_table_names()
        with verification_engine.connect() as connection:
            version = connection.exec_driver_sql("PRAGMA user_version").scalar_one()
        assert version == migrations.CURRENT_SCHEMA_VERSION
    finally:
        verification_engine.dispose()


def test_persisted_acquisition_snapshot_is_frozen_minimal_and_keeps_semantic_provenance_structured():
    from aqorath.fixed_asset_acquisition_persistence import (
        PersistedFixedAssetAcquisitionPosting,
    )

    assert PersistedFixedAssetAcquisitionPosting.__dataclass_params__.frozen
    assert [field.name for field in fields(PersistedFixedAssetAcquisitionPosting)] == [
        "fixed_asset_id",
        "entry_id",
        "posting_date",
        "asset_class",
        "settlement_method",
    ]

    snapshot = PersistedFixedAssetAcquisitionPosting(
        fixed_asset_id=1,
        entry_id=2,
        posting_date=date(2026, 1, 15),
        asset_class="computer_equipment",
        settlement_method="credit",
    )
    assert snapshot.asset_class == "computer_equipment"
    assert snapshot.settlement_method == "credit"

    with pytest.raises(ValueError):
        PersistedFixedAssetAcquisitionPosting(
            fixed_asset_id=1,
            entry_id=2,
            posting_date=date(2026, 1, 15),
            asset_class="unknown_asset_class",
            settlement_method="credit",
        )
    with pytest.raises(ValueError):
        PersistedFixedAssetAcquisitionPosting(
            fixed_asset_id=1,
            entry_id=2,
            posting_date=date(2026, 1, 15),
            asset_class="computer_equipment",
            settlement_method="unknown_settlement",
        )


def test_acquisition_persistence_public_api_has_exact_signatures_without_user_identity_or_date_overrides():
    from aqorath.fixed_asset_acquisition_persistence import (
        execute_fixed_asset_acquisition_posting_once,
        load_fixed_asset_acquisition_posting,
    )

    expected = {
        execute_fixed_asset_acquisition_posting_once: ["instruction"],
        load_fixed_asset_acquisition_posting: ["session", "fixed_asset_id"],
    }
    for function, names in expected.items():
        sig = signature(function)
        assert list(sig.parameters) == names
        for parameter in sig.parameters.values():
            assert parameter.default is Parameter.empty
            assert parameter.kind is Parameter.POSITIONAL_OR_KEYWORD


def test_executor_requires_nominal_6p_instruction_before_session_or_staging(monkeypatch):
    import aqorath.core
    import aqorath.storage
    from aqorath.fixed_asset_acquisition_persistence import (
        execute_fixed_asset_acquisition_posting_once,
    )

    calls = []

    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("executor crossed boundary before nominal validation")

    monkeypatch.setattr(aqorath.storage, "get_session", forbidden)
    monkeypatch.setattr(aqorath.core, "_stage_entry_in_session", forbidden)

    with pytest.raises(TypeError):
        execute_fixed_asset_acquisition_posting_once(object())
    assert calls == []


def test_missing_persisted_asset_fails_closed_before_accounting_staging(tmp_path, monkeypatch):
    import aqorath.core
    from aqorath.fixed_asset_acquisition_persistence import (
        execute_fixed_asset_acquisition_posting_once,
    )

    engine, _, entity_id, _ = _initialize_canonical_db(tmp_path, monkeypatch)
    missing_asset = _domain_asset(fixed_asset_id=999999, entity_id=entity_id)
    with Session(engine) as session:
        instruction = _instruction(session, missing_asset)

    calls = []
    real_stage = aqorath.core._stage_entry_in_session

    def stage_spy(*args, **kwargs):
        calls.append((args, kwargs))
        return real_stage(*args, **kwargs)

    monkeypatch.setattr(aqorath.core, "_stage_entry_in_session", stage_spy)
    result = execute_fixed_asset_acquisition_posting_once(instruction)

    assert result["ok"] is False
    assert calls == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"entity_id": 999999},
        {"code": "FORGED-CODE"},
        {"acquisition_date": date(2026, 1, 16)},
        {"acquisition_cost": Decimal("100.0")},
    ],
)
def test_executor_validates_exact_persisted_asset_identity_before_staging(tmp_path, monkeypatch, overrides):
    import aqorath.core
    from aqorath.fixed_asset_acquisition_persistence import (
        execute_fixed_asset_acquisition_posting_once,
    )

    engine, _, entity_id, fixed_asset_id = _initialize_canonical_db(tmp_path, monkeypatch)
    values = {
        "fixed_asset_id": fixed_asset_id,
        "entity_id": entity_id,
    }
    values.update(overrides)
    forged = _domain_asset(**values)
    with Session(engine) as session:
        instruction = _instruction(session, forged)

    calls = []
    real_stage = aqorath.core._stage_entry_in_session

    def stage_spy(*args, **kwargs):
        calls.append((args, kwargs))
        return real_stage(*args, **kwargs)

    monkeypatch.setattr(aqorath.core, "_stage_entry_in_session", stage_spy)
    result = execute_fixed_asset_acquisition_posting_once(instruction)

    assert result["ok"] is False
    assert calls == []


def test_executor_does_not_impose_current_active_state_rule_on_confirmed_historical_acquisition(tmp_path, monkeypatch):
    from aqorath.fixed_asset_acquisition_persistence import (
        execute_fixed_asset_acquisition_posting_once,
    )
    from aqorath.models import FixedAssetRecord

    engine, _, entity_id, fixed_asset_id = _initialize_canonical_db(tmp_path, monkeypatch)
    with Session(engine) as session:
        record = session.get(FixedAssetRecord, fixed_asset_id)
        record.is_active = False
        session.add(record)
        session.commit()

        asset = _domain_asset(
            fixed_asset_id=fixed_asset_id,
            entity_id=entity_id,
            is_active=False,
        )
        instruction = _instruction(session, asset)

    result = execute_fixed_asset_acquisition_posting_once(instruction)
    assert result["ok"] is True


def test_executor_uses_existing_core_staging_once_with_exact_6p_payload(tmp_path, monkeypatch):
    import aqorath.core
    from aqorath.fixed_asset_acquisition_persistence import (
        execute_fixed_asset_acquisition_posting_once,
    )

    engine, _, entity_id, fixed_asset_id = _initialize_canonical_db(tmp_path, monkeypatch)
    asset = _domain_asset(fixed_asset_id=fixed_asset_id, entity_id=entity_id)
    with Session(engine) as session:
        instruction = _instruction(
            session,
            asset,
            settlement_method="credit",
        )

    real_stage = aqorath.core._stage_entry_in_session
    calls = []

    def stage_once(session, payload):
        calls.append(payload)
        return real_stage(session, payload)

    monkeypatch.setattr(aqorath.core, "_stage_entry_in_session", stage_once)
    result = execute_fixed_asset_acquisition_posting_once(instruction)

    assert result["ok"] is True
    assert calls == [
        {
            "date": date(2026, 1, 15),
            "description": instruction.posting_instruction.description,
            "lines": [
                {
                    "account_id": instruction.posting_instruction.lines[0].account_id,
                    "account_code": "1203",
                    "debit": Decimal("100.00"),
                    "credit": Decimal("0"),
                },
                {
                    "account_id": instruction.posting_instruction.lines[1].account_id,
                    "account_code": "2101",
                    "debit": Decimal("0"),
                    "credit": Decimal("100.00"),
                },
            ],
        }
    ]


def test_real_atomic_persistence_writes_one_entry_two_lines_and_structured_acquisition_provenance(tmp_path, monkeypatch):
    from aqorath.fixed_asset_acquisition_persistence import (
        execute_fixed_asset_acquisition_posting_once,
    )
    from aqorath.models import (
        FixedAssetAcquisitionPostingRecord,
        JournalEntry,
        JournalLine,
    )

    engine, _, entity_id, fixed_asset_id = _initialize_canonical_db(tmp_path, monkeypatch)
    asset = _domain_asset(fixed_asset_id=fixed_asset_id, entity_id=entity_id)
    with Session(engine) as session:
        instruction = _instruction(
            session,
            asset,
            asset_class="computer_equipment",
            settlement_method="cash",
        )

    result = execute_fixed_asset_acquisition_posting_once(instruction)
    assert result["ok"] is True

    with Session(engine) as session:
        entries = session.exec(select(JournalEntry)).all()
        lines = session.exec(select(JournalLine)).all()
        records = session.exec(select(FixedAssetAcquisitionPostingRecord)).all()

        assert len(entries) == 1
        assert len(lines) == 2
        assert len(records) == 1
        entry = entries[0]
        record = records[0]
        assert result["entry_id"] == entry.id == record.entry_id
        assert entry.date.date() == date(2026, 1, 15)
        assert record.fixed_asset_id == fixed_asset_id
        assert record.asset_class == "computer_equipment"
        assert record.settlement_method == "cash"
        assert [(line.account_code, line.debit, line.credit) for line in lines] == [
            ("1203", "100.00", "0"),
            ("1102", "0", "100.00"),
        ]


def test_same_asset_acquisition_is_persistently_single_use_and_second_attempt_creates_nothing(tmp_path, monkeypatch):
    from aqorath.fixed_asset_acquisition_persistence import (
        execute_fixed_asset_acquisition_posting_once,
    )
    from aqorath.models import FixedAssetAcquisitionPostingRecord, JournalEntry, JournalLine

    engine, _, entity_id, fixed_asset_id = _initialize_canonical_db(tmp_path, monkeypatch)
    asset = _domain_asset(fixed_asset_id=fixed_asset_id, entity_id=entity_id)
    with Session(engine) as session:
        instruction = _instruction(session, asset)

    first = execute_fixed_asset_acquisition_posting_once(instruction)
    second = execute_fixed_asset_acquisition_posting_once(instruction)
    assert first["ok"] is True
    assert second["ok"] is False
    assert "already" in second["error"].lower()

    with Session(engine) as session:
        assert len(session.exec(select(JournalEntry)).all()) == 1
        assert len(session.exec(select(JournalLine)).all()) == 2
        assert len(session.exec(select(FixedAssetAcquisitionPostingRecord)).all()) == 1


def test_distinct_assets_can_each_persist_one_acquisition_without_cross_asset_collision(tmp_path, monkeypatch):
    from aqorath.fixed_asset_acquisition_persistence import (
        execute_fixed_asset_acquisition_posting_once,
    )
    from aqorath.models import FixedAssetAcquisitionPostingRecord, JournalEntry

    engine, _, entity_id, fixed_asset_id = _initialize_canonical_db(tmp_path, monkeypatch)
    first_asset = _domain_asset(fixed_asset_id=fixed_asset_id, entity_id=entity_id)
    with Session(engine) as session:
        second_asset = _persist_second_asset(session, entity_id)
        first_instruction = _instruction(session, first_asset)
        second_instruction = _instruction(session, second_asset)

    first = execute_fixed_asset_acquisition_posting_once(first_instruction)
    second = execute_fixed_asset_acquisition_posting_once(second_instruction)
    assert first["ok"] is True
    assert second["ok"] is True

    with Session(engine) as session:
        records = session.exec(select(FixedAssetAcquisitionPostingRecord)).all()
        assert len(records) == 2
        assert len(session.exec(select(JournalEntry)).all()) == 2
        assert {record.fixed_asset_id for record in records} == {
            first_asset.id,
            second_asset.id,
        }


def test_sqlite_enforces_one_acquisition_record_per_asset_even_if_executor_guard_is_bypassed(tmp_path, monkeypatch):
    from aqorath.models import FixedAssetAcquisitionPostingRecord, JournalEntry

    engine, _, _, fixed_asset_id = _initialize_canonical_db(tmp_path, monkeypatch)
    with Session(engine) as session:
        first_entry = JournalEntry(date=datetime(2026, 1, 15), concept="first")
        second_entry = JournalEntry(date=datetime(2026, 1, 16), concept="second")
        session.add(first_entry)
        session.add(second_entry)
        session.commit()
        session.refresh(first_entry)
        session.refresh(second_entry)

        session.add(
            FixedAssetAcquisitionPostingRecord(
                fixed_asset_id=fixed_asset_id,
                entry_id=first_entry.id,
                asset_class="computer_equipment",
                settlement_method="bank",
            )
        )
        session.commit()

        session.add(
            FixedAssetAcquisitionPostingRecord(
                fixed_asset_id=fixed_asset_id,
                entry_id=second_entry.id,
                asset_class="computer_equipment",
                settlement_method="cash",
            )
        )
        with pytest.raises(Exception):
            session.commit()
        session.rollback()


def test_sqlite_enforces_one_acquisition_identity_per_journal_entry(tmp_path, monkeypatch):
    from aqorath.models import FixedAssetAcquisitionPostingRecord, JournalEntry

    engine, _, entity_id, fixed_asset_id = _initialize_canonical_db(tmp_path, monkeypatch)
    with Session(engine) as session:
        second_asset = _persist_second_asset(session, entity_id)
        entry = JournalEntry(date=datetime(2026, 1, 15), concept="shared")
        session.add(entry)
        session.commit()
        session.refresh(entry)

        session.add(
            FixedAssetAcquisitionPostingRecord(
                fixed_asset_id=fixed_asset_id,
                entry_id=entry.id,
                asset_class="computer_equipment",
                settlement_method="bank",
            )
        )
        session.commit()

        session.add(
            FixedAssetAcquisitionPostingRecord(
                fixed_asset_id=second_asset.id,
                entry_id=entry.id,
                asset_class="computer_equipment",
                settlement_method="bank",
            )
        )
        with pytest.raises(Exception):
            session.commit()
        session.rollback()


def test_staging_failure_never_inserts_acquisition_registry_or_commits_partial_entry(tmp_path, monkeypatch):
    import aqorath.core
    from aqorath.fixed_asset_acquisition_persistence import (
        execute_fixed_asset_acquisition_posting_once,
    )
    from aqorath.models import FixedAssetAcquisitionPostingRecord, JournalEntry, JournalLine

    engine, _, entity_id, fixed_asset_id = _initialize_canonical_db(tmp_path, monkeypatch)
    asset = _domain_asset(fixed_asset_id=fixed_asset_id, entity_id=entity_id)
    with Session(engine) as session:
        instruction = _instruction(session, asset)

    monkeypatch.setattr(
        aqorath.core,
        "_stage_entry_in_session",
        lambda session, payload: (None, "forced staging failure"),
    )
    result = execute_fixed_asset_acquisition_posting_once(instruction)
    assert result == {"ok": False, "error": "forced staging failure"}

    with Session(engine) as session:
        assert session.exec(select(JournalEntry)).all() == []
        assert session.exec(select(JournalLine)).all() == []
        assert session.exec(select(FixedAssetAcquisitionPostingRecord)).all() == []


def test_single_commit_failure_rolls_back_entry_lines_and_acquisition_registry(tmp_path, monkeypatch):
    import aqorath.fixed_asset_acquisition_persistence as persistence
    from aqorath.models import FixedAssetAcquisitionPostingRecord, JournalEntry, JournalLine

    engine, _, entity_id, fixed_asset_id = _initialize_canonical_db(tmp_path, monkeypatch)
    asset = _domain_asset(fixed_asset_id=fixed_asset_id, entity_id=entity_id)
    with Session(engine) as session:
        instruction = _instruction(session, asset)

    @contextmanager
    def failing_session():
        with Session(engine) as session:
            def fail_commit():
                raise RuntimeError("forced acquisition commit failure")

            monkeypatch.setattr(session, "commit", fail_commit)
            yield session

    monkeypatch.setattr(persistence._storage, "get_session", failing_session)
    result = persistence.execute_fixed_asset_acquisition_posting_once(instruction)
    assert result["ok"] is False
    assert "forced acquisition commit failure" in result["error"]

    with Session(engine) as session:
        assert session.exec(select(JournalEntry)).all() == []
        assert session.exec(select(JournalLine)).all() == []
        assert session.exec(select(FixedAssetAcquisitionPostingRecord)).all() == []


def test_loader_reconstructs_identity_date_and_structured_provenance_without_parsing_description(tmp_path, monkeypatch):
    from aqorath.fixed_asset_acquisition_persistence import (
        execute_fixed_asset_acquisition_posting_once,
        load_fixed_asset_acquisition_posting,
    )
    from aqorath.models import JournalEntry

    engine, _, entity_id, fixed_asset_id = _initialize_canonical_db(tmp_path, monkeypatch)
    asset = _domain_asset(fixed_asset_id=fixed_asset_id, entity_id=entity_id)
    with Session(engine) as session:
        instruction = _instruction(
            session,
            asset,
            settlement_method="credit",
        )

    result = execute_fixed_asset_acquisition_posting_once(instruction)
    assert result["ok"] is True

    with Session(engine) as session:
        entry = session.get(JournalEntry, result["entry_id"])
        entry.concept = "POISONED HUMAN DESCRIPTION — DO NOT PARSE"
        session.add(entry)
        session.commit()

        loaded = load_fixed_asset_acquisition_posting(session, fixed_asset_id)
        assert loaded.fixed_asset_id == fixed_asset_id
        assert loaded.entry_id == result["entry_id"]
        assert loaded.posting_date == date(2026, 1, 15)
        assert loaded.asset_class == "computer_equipment"
        assert loaded.settlement_method == "credit"


def test_loader_fails_closed_for_invalid_missing_or_corrupt_semantic_identity(tmp_path, monkeypatch):
    from aqorath.fixed_asset_acquisition_persistence import (
        execute_fixed_asset_acquisition_posting_once,
        load_fixed_asset_acquisition_posting,
    )
    from aqorath.models import FixedAssetAcquisitionPostingRecord

    engine, _, entity_id, fixed_asset_id = _initialize_canonical_db(tmp_path, monkeypatch)
    with Session(engine) as session:
        with pytest.raises(ValueError):
            load_fixed_asset_acquisition_posting(session, 0)
        with pytest.raises(LookupError):
            load_fixed_asset_acquisition_posting(session, fixed_asset_id)

        asset = _domain_asset(fixed_asset_id=fixed_asset_id, entity_id=entity_id)
        instruction = _instruction(session, asset)

    result = execute_fixed_asset_acquisition_posting_once(instruction)
    assert result["ok"] is True

    with Session(engine) as session:
        record = session.exec(
            select(FixedAssetAcquisitionPostingRecord).where(
                FixedAssetAcquisitionPostingRecord.fixed_asset_id == fixed_asset_id
            )
        ).one()
        record.asset_class = "corrupt"
        session.add(record)
        session.commit()

        with pytest.raises(ValueError):
            load_fixed_asset_acquisition_posting(session, fixed_asset_id)


def test_loader_is_read_only_uses_supplied_session_and_never_opens_hidden_storage(tmp_path, monkeypatch):
    import aqorath.fixed_asset_acquisition_persistence as persistence

    engine, _, entity_id, fixed_asset_id = _initialize_canonical_db(tmp_path, monkeypatch)
    asset = _domain_asset(fixed_asset_id=fixed_asset_id, entity_id=entity_id)
    with Session(engine) as session:
        instruction = _instruction(session, asset)
    result = persistence.execute_fixed_asset_acquisition_posting_once(instruction)
    assert result["ok"] is True

    hidden_calls = []
    monkeypatch.setattr(
        persistence._storage,
        "get_session",
        lambda: hidden_calls.append(True),
    )

    with Session(engine) as session:
        write_calls = []
        monkeypatch.setattr(session, "commit", lambda: write_calls.append("commit"))
        monkeypatch.setattr(session, "rollback", lambda: write_calls.append("rollback"))
        monkeypatch.setattr(session, "add", lambda *args: write_calls.append("add"))
        monkeypatch.setattr(session, "delete", lambda *args: write_calls.append("delete"))

        loaded = persistence.load_fixed_asset_acquisition_posting(
            session,
            fixed_asset_id,
        )
        assert loaded.entry_id == result["entry_id"]
        assert hidden_calls == []
        assert write_calls == []


def test_acquisition_persistence_reuses_staging_and_contains_no_second_accounting_or_reconstruction_engine():
    import aqorath.fixed_asset_acquisition_persistence as persistence

    source = getsource(persistence)
    assert "_stage_entry_in_session" in source
    forbidden = (
        "_core.post_entry(",
        "execute_fixed_asset_acquisition_posting(",
        "create_fixed_asset_acquisition_fact(",
        "resolve_fixed_asset_acquisition_accounting(",
        "prepare_fixed_asset_acquisition_confirmation(",
        "confirm_fixed_asset_acquisition(",
        "get_account_bindings(",
        "resolve_proposal_accounts(",
        "float(",
    )
    for token in forbidden:
        assert token not in source


def test_application_exposes_atomic_acquisition_persistence_and_read_as_thin_delegations(monkeypatch):
    import aqorath.application as application
    import aqorath.fixed_asset_acquisition_persistence as persistence

    assert str(signature(application.execute_fixed_asset_acquisition_posting_once)) == (
        "(instruction)"
    )
    assert str(signature(application.load_fixed_asset_acquisition_posting)) == (
        "(session, fixed_asset_id)"
    )

    calls = []
    execute_result = {"ok": True, "entry_id": 321}
    read_result = object()
    monkeypatch.setattr(
        persistence,
        "execute_fixed_asset_acquisition_posting_once",
        lambda instruction: calls.append(("execute", instruction)) or execute_result,
    )
    monkeypatch.setattr(
        persistence,
        "load_fixed_asset_acquisition_posting",
        lambda session, fixed_asset_id: calls.append(
            ("load", session, fixed_asset_id)
        ) or read_result,
    )

    instruction = object()
    session = object()
    assert application.execute_fixed_asset_acquisition_posting_once(instruction) is execute_result
    assert application.load_fixed_asset_acquisition_posting(session, 44) is read_result
    assert calls == [
        ("execute", instruction),
        ("load", session, 44),
    ]
