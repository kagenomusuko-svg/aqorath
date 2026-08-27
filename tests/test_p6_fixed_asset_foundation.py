"""Phase 6F.1 — canonical FixedAsset foundation contracts.

Contracts only. A fixed asset is durable registry metadata owned by the one accounting
Entity. Registration preserves exact acquisition facts and depreciation inputs, but it
never calculates depreciation, selects accounts, derives carrying value, or posts entries.
The legacy aqorath.assets module and legacy Asset table are explicitly not canonical.
"""

from dataclasses import FrozenInstanceError, fields, replace
from datetime import date, datetime, timezone
from decimal import Decimal
import inspect
import sqlite3

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select


def _entity():
    from aqorath.entity import Entity, EntityProfile

    return Entity(
        id=None,
        name="Meriadock A.C.",
        rfc=None,
        legal_personality="persona_moral",
        legal_form="A.C.",
        profile=EntityProfile(
            economic_purpose="no_lucrativo",
            is_donor_authorized=False,
            special_capabilities=("osc",),
            modules_enabled=("fixed_assets",),
        ),
        is_active=True,
    )


def _fresh_db(tmp_path, filename="fixed-assets.db"):
    from aqorath.migrations import migrate_database

    db_path = tmp_path / filename
    result = migrate_database(str(db_path))
    assert result["to_version"] == 4
    return db_path, create_engine(f"sqlite:///{db_path}")


def _create_entity(session):
    from aqorath.entity_repository import create_entity

    return create_entity(session, _entity())


def _fixed_asset(entity_id, **overrides):
    from aqorath.fixed_asset import FixedAsset

    values = {
        "id": None,
        "entity_id": entity_id,
        "code": "EQ-001",
        "name": "Equipo de cómputo",
        "acquisition_date": date(2026, 1, 15),
        "in_service_date": date(2026, 2, 1),
        "acquisition_cost": Decimal("125000.0000"),
        "residual_value": Decimal("5000.00"),
        "useful_life_months": 60,
        "depreciation_method": "straight_line",
        "is_active": True,
    }
    values.update(overrides)
    return FixedAsset(**values)


def test_fixed_asset_domain_is_pure_frozen_registry_metadata_not_accounting_truth():
    import aqorath.fixed_asset as domain
    from aqorath.fixed_asset import FixedAsset

    asset = _fixed_asset(1)

    assert [field.name for field in fields(FixedAsset)] == [
        "id",
        "entity_id",
        "code",
        "name",
        "acquisition_date",
        "in_service_date",
        "acquisition_cost",
        "residual_value",
        "useful_life_months",
        "depreciation_method",
        "is_active",
    ]
    assert isinstance(asset.acquisition_cost, Decimal)
    assert isinstance(asset.residual_value, Decimal)
    with pytest.raises(FrozenInstanceError):
        asset.name = "Otro"

    forbidden = {
        "account_id",
        "account_code",
        "debit",
        "credit",
        "journal_entry_id",
        "accumulated_depreciation",
        "carrying_value",
        "book_value",
        "fiscal_rule_set_id",
        "document_reference_id",
    }
    assert forbidden.isdisjoint({field.name for field in fields(FixedAsset)})

    source = inspect.getsource(domain).lower()
    for forbidden_source in (
        "sqlmodel",
        "sqlalchemy",
        "get_session",
        "journalentry(",
        "journalline(",
        "from .assets",
        "import aqorath.assets",
    ):
        assert forbidden_source not in source


def test_fixed_asset_domain_validates_identity_dates_money_life_and_boolean_fail_closed():
    from aqorath.fixed_asset import FixedAsset

    asset = _fixed_asset(
        1,
        code="EQ.Custom-01",
        name="Servidor Ágora",
        depreciation_method="Custom.Method",
    )
    assert asset.code == "EQ.Custom-01"
    assert asset.name == "Servidor Ágora"
    assert asset.depreciation_method == "Custom.Method"

    for patch in (
        {"id": 0},
        {"id": True},
        {"entity_id": 0},
        {"entity_id": True},
        {"code": ""},
        {"code": "   "},
        {"name": ""},
        {"name": "   "},
        {"depreciation_method": ""},
        {"depreciation_method": "   "},
        {"useful_life_months": 0},
        {"useful_life_months": -1},
        {"useful_life_months": True},
        {"is_active": 1},
        {"acquisition_date": datetime(2026, 1, 15, tzinfo=timezone.utc)},
        {"in_service_date": "2026-02-01"},
    ):
        with pytest.raises((TypeError, ValueError)):
            _fixed_asset(1, **patch)

    for patch in (
        {"acquisition_cost": 125000.0},
        {"acquisition_cost": 125000},
        {"acquisition_cost": "125000.00"},
        {"acquisition_cost": Decimal("NaN")},
        {"acquisition_cost": Decimal("Infinity")},
        {"acquisition_cost": Decimal("-0.01")},
        {"residual_value": 0.0},
        {"residual_value": Decimal("NaN")},
        {"residual_value": Decimal("-0.01")},
        {"residual_value": Decimal("125000.0001")},
    ):
        with pytest.raises((TypeError, ValueError)):
            _fixed_asset(1, **patch)

    with pytest.raises(ValueError):
        _fixed_asset(
            1,
            acquisition_date=date(2026, 2, 2),
            in_service_date=date(2026, 2, 1),
        )


def test_fixed_asset_money_and_depreciation_inputs_are_explicit_exact_and_not_calculated():
    import aqorath.fixed_asset as domain
    from aqorath.fixed_asset import FixedAsset

    asset = _fixed_asset(
        1,
        acquisition_cost=Decimal("10.123400"),
        residual_value=Decimal("0.0100"),
        useful_life_months=84,
        depreciation_method="units_of_production.future",
    )
    assert asset.acquisition_cost.as_tuple() == Decimal("10.123400").as_tuple()
    assert asset.residual_value.as_tuple() == Decimal("0.0100").as_tuple()
    assert asset.useful_life_months == 84
    assert asset.depreciation_method == "units_of_production.future"

    signature = inspect.signature(FixedAsset)
    for explicit in (
        "acquisition_date",
        "in_service_date",
        "acquisition_cost",
        "residual_value",
        "useful_life_months",
        "depreciation_method",
        "is_active",
    ):
        assert signature.parameters[explicit].default is inspect.Parameter.empty

    for forbidden in (
        "calculate_depreciation",
        "monthly_depreciation_straight",
        "annual_depreciation_straight",
        "generate_depreciation_entries_for_period",
        "post_depreciation",
    ):
        assert not hasattr(domain, forbidden)


def test_fixed_asset_repository_public_contracts_are_minimal_exact_and_non_destructive():
    import aqorath.fixed_asset_repository as repository

    assert str(inspect.signature(repository.create_fixed_asset)) == "(session, fixed_asset)"
    assert str(inspect.signature(repository.get_fixed_asset)) == (
        "(session, entity_id, fixed_asset_id)"
    )
    assert str(inspect.signature(repository.list_fixed_assets)) == (
        "(session, entity_id, include_inactive=False)"
    )
    assert str(inspect.signature(repository.set_fixed_asset_active)) == (
        "(session, entity_id, fixed_asset_id, is_active)"
    )

    for forbidden in (
        "delete_fixed_asset",
        "calculate_depreciation",
        "post_depreciation",
        "generate_depreciation_entries_for_period",
        "create_account",
        "post_entry",
    ):
        assert not hasattr(repository, forbidden)


def test_frozen_v4_additively_creates_exact_fixed_asset_schema_and_decimal_text_authority(tmp_path):
    from aqorath.migrations import CURRENT_SCHEMA_VERSION
    from aqorath.models import FixedAssetRecord

    assert CURRENT_SCHEMA_VERSION == 4
    assert FixedAssetRecord.__tablename__ == "fixedasset"

    db_path, engine = _fresh_db(tmp_path, "schema.db")
    engine.dispose()
    conn = sqlite3.connect(str(db_path))
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert "fixedasset" in tables

        columns = {
            row[1]: row
            for row in conn.execute("PRAGMA table_info(fixedasset)").fetchall()
        }
        assert set(columns) == {
            "id",
            "entity_id",
            "code",
            "name",
            "acquisition_date",
            "in_service_date",
            "acquisition_cost",
            "residual_value",
            "useful_life_months",
            "depreciation_method",
            "is_active",
            "created_at",
        }
        for required in (
            "entity_id",
            "code",
            "name",
            "acquisition_date",
            "in_service_date",
            "acquisition_cost",
            "residual_value",
            "useful_life_months",
            "depreciation_method",
            "is_active",
            "created_at",
        ):
            assert columns[required][3] == 1, required

        assert columns["acquisition_cost"][2].upper() == "TEXT"
        assert columns["residual_value"][2].upper() == "TEXT"
        assert "REAL" not in columns["acquisition_cost"][2].upper()
        assert "FLOAT" not in columns["acquisition_cost"][2].upper()

        fks = conn.execute("PRAGMA foreign_key_list(fixedasset)").fetchall()
        assert any(
            row[2] == "entity" and row[3] == "entity_id" and row[4] == "id"
            for row in fks
        )

        unique_sets = {
            tuple(
                col[2]
                for col in conn.execute(
                    f"PRAGMA index_info({index_row[1]})"
                ).fetchall()
            )
            for index_row in conn.execute("PRAGMA index_list(fixedasset)").fetchall()
            if index_row[2] == 1
        }
        assert ("entity_id", "code") in unique_sets

        for forbidden_column in (
            "account_id",
            "account_code",
            "debit",
            "credit",
            "accumulated_depreciation",
            "carrying_value",
            "book_value",
            "journal_entry_id",
        ):
            assert forbidden_column not in columns
    finally:
        conn.close()


def test_current_v4_additive_ensure_adds_fixed_assets_without_rewriting_existing_truth(tmp_path):
    from aqorath.migrations import get_schema_version, migrate_database

    db_path = tmp_path / "existing-v4.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("CREATE TABLE fiscalpostingauditrecord (id INTEGER PRIMARY KEY)")
        conn.execute(
            "CREATE TABLE preserved_truth (id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
        )
        conn.execute("INSERT INTO preserved_truth VALUES (1, 'keep-me')")
        conn.execute("PRAGMA user_version = 4")
        conn.commit()
    finally:
        conn.close()

    result = migrate_database(str(db_path))
    assert result == {
        "from_version": 4,
        "to_version": 4,
        "migrated": False,
        "backup_path": None,
    }
    assert get_schema_version(str(db_path)) == 4

    conn = sqlite3.connect(str(db_path))
    try:
        assert conn.execute("SELECT value FROM preserved_truth WHERE id = 1").fetchone() == (
            "keep-me",
        )
        assert conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='fixedasset'"
        ).fetchone() == ("fixedasset",)
    finally:
        conn.close()


def test_legacy_asset_table_remains_separate_and_is_never_auto_promoted_to_canonical_fixed_asset(tmp_path):
    from aqorath.migrations import migrate_database

    db_path = tmp_path / "legacy-asset-v4.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("CREATE TABLE fiscalpostingauditrecord (id INTEGER PRIMARY KEY)")
        conn.execute(
            """
            CREATE TABLE asset (
                id INTEGER PRIMARY KEY,
                name VARCHAR,
                value TEXT NOT NULL,
                created_at DATETIME
            )
            """
        )
        conn.execute(
            "INSERT INTO asset (id, name, value, created_at) VALUES (1, 'Legacy', '99.9900', '2026-01-01')"
        )
        conn.execute("PRAGMA user_version = 4")
        conn.commit()
    finally:
        conn.close()

    migrate_database(str(db_path))

    conn = sqlite3.connect(str(db_path))
    try:
        assert conn.execute(
            "SELECT id, name, value, created_at FROM asset"
        ).fetchall() == [(1, "Legacy", "99.9900", "2026-01-01")]
        assert conn.execute("SELECT COUNT(*) FROM fixedasset").fetchone() == (0,)
    finally:
        conn.close()


def test_create_fixed_asset_round_trip_preserves_every_explicit_value_and_decimal_scale(tmp_path):
    from aqorath.fixed_asset_repository import create_fixed_asset, get_fixed_asset
    from aqorath.models import FixedAssetRecord

    _, engine = _fresh_db(tmp_path, "round-trip.db")
    with Session(engine) as session:
        entity = _create_entity(session)
        source = _fixed_asset(entity.id)
        created = create_fixed_asset(session, source)

        assert created.id is not None
        assert created == replace(source, id=created.id)
        assert created.acquisition_cost.as_tuple() == Decimal("125000.0000").as_tuple()
        assert created.residual_value.as_tuple() == Decimal("5000.00").as_tuple()

        loaded = get_fixed_asset(session, entity.id, created.id)
        assert loaded == created
        assert loaded.acquisition_cost.as_tuple() == source.acquisition_cost.as_tuple()
        assert loaded.residual_value.as_tuple() == source.residual_value.as_tuple()

        record = session.exec(select(FixedAssetRecord)).one()
        assert record.acquisition_cost == "125000.0000"
        assert record.residual_value == "5000.00"
        assert record.acquisition_date == date(2026, 1, 15)
        assert record.in_service_date == date(2026, 2, 1)
    engine.dispose()


def test_create_fixed_asset_requires_explicit_existing_active_owner_and_never_defaults_entity(tmp_path):
    from aqorath.fixed_asset_repository import create_fixed_asset
    from aqorath.models import EntityRecord

    _, engine = _fresh_db(tmp_path, "owner.db")
    with Session(engine) as session:
        entity = _create_entity(session)

        with pytest.raises(LookupError):
            create_fixed_asset(session, _fixed_asset(entity.id + 999))

        owner = session.get(EntityRecord, entity.id)
        owner.is_active = False
        session.add(owner)
        session.commit()
        with pytest.raises(ValueError):
            create_fixed_asset(session, _fixed_asset(entity.id))
    engine.dispose()


def test_fixed_asset_code_is_unique_per_entity_in_repository_and_sqlite(tmp_path):
    from aqorath.fixed_asset_repository import create_fixed_asset
    from aqorath.models import FixedAssetRecord

    _, engine = _fresh_db(tmp_path, "unique-code.db")
    with Session(engine) as session:
        entity = _create_entity(session)
        create_fixed_asset(session, _fixed_asset(entity.id, code="FA-001"))

        with pytest.raises(ValueError):
            create_fixed_asset(
                session,
                _fixed_asset(entity.id, code="FA-001", name="Duplicado"),
            )

        session.add(
            FixedAssetRecord(
                entity_id=entity.id,
                code="FA-001",
                name="Bypass repository",
                acquisition_date=date(2026, 1, 1),
                in_service_date=date(2026, 1, 1),
                acquisition_cost="1.00",
                residual_value="0.00",
                useful_life_months=12,
                depreciation_method="straight_line",
                is_active=True,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
    engine.dispose()


def test_get_and_list_fixed_assets_are_entity_scoped_deterministic_and_exclude_inactive_by_default(tmp_path):
    from aqorath.fixed_asset_repository import (
        create_fixed_asset,
        get_fixed_asset,
        list_fixed_assets,
        set_fixed_asset_active,
    )

    _, engine = _fresh_db(tmp_path, "reads.db")
    with Session(engine) as session:
        entity = _create_entity(session)
        first = create_fixed_asset(session, _fixed_asset(entity.id, code="FA-B"))
        second = create_fixed_asset(
            session,
            _fixed_asset(entity.id, code="FA-A", name="Segundo"),
        )
        set_fixed_asset_active(session, entity.id, second.id, False)

        assert get_fixed_asset(session, entity.id, first.id) == first
        with pytest.raises(LookupError):
            get_fixed_asset(session, entity.id + 1, first.id)
        with pytest.raises((TypeError, ValueError)):
            get_fixed_asset(session, True, first.id)
        with pytest.raises((TypeError, ValueError)):
            get_fixed_asset(session, entity.id, 0)

        assert list_fixed_assets(session, entity.id) == (first,)
        assert tuple(item.id for item in list_fixed_assets(session, entity.id, True)) == (
            first.id,
            second.id,
        )
        assert list_fixed_assets(session, entity.id + 1) == ()
        with pytest.raises(TypeError):
            list_fixed_assets(session, entity.id, include_inactive=1)
    engine.dispose()


def test_fixed_asset_deactivation_and_reactivation_preserve_identity_without_delete_or_recreation(tmp_path):
    from aqorath.fixed_asset_repository import (
        create_fixed_asset,
        get_fixed_asset,
        set_fixed_asset_active,
    )
    from aqorath.models import FixedAssetRecord

    _, engine = _fresh_db(tmp_path, "active-state.db")
    with Session(engine) as session:
        entity = _create_entity(session)
        created = create_fixed_asset(session, _fixed_asset(entity.id))

        inactive = set_fixed_asset_active(session, entity.id, created.id, False)
        assert inactive.id == created.id
        assert inactive.is_active is False
        assert get_fixed_asset(session, entity.id, created.id) == inactive

        active = set_fixed_asset_active(session, entity.id, created.id, True)
        assert active.id == created.id
        assert active.is_active is True
        assert session.exec(select(FixedAssetRecord)).all().__len__() == 1

        with pytest.raises(TypeError):
            set_fixed_asset_active(session, entity.id, created.id, 1)
    engine.dispose()


def test_fixed_asset_write_rolls_back_when_single_commit_fails(tmp_path, monkeypatch):
    from aqorath.fixed_asset_repository import create_fixed_asset
    from aqorath.models import FixedAssetRecord

    _, engine = _fresh_db(tmp_path, "rollback.db")
    with Session(engine) as session:
        entity = _create_entity(session)
        original_commit = session.commit
        original_rollback = session.rollback
        calls = {"rollback": 0}

        def fail_commit():
            raise RuntimeError("simulated commit failure")

        def track_rollback():
            calls["rollback"] += 1
            return original_rollback()

        monkeypatch.setattr(session, "commit", fail_commit)
        monkeypatch.setattr(session, "rollback", track_rollback)
        with pytest.raises(RuntimeError, match="simulated commit failure"):
            create_fixed_asset(session, _fixed_asset(entity.id))
        assert calls["rollback"] == 1

        monkeypatch.setattr(session, "commit", original_commit)
        assert session.exec(select(FixedAssetRecord)).all() == []
    engine.dispose()


def test_fixed_asset_repository_uses_only_supplied_session_and_never_calls_legacy_or_accounting_engines():
    import aqorath.fixed_asset_repository as repository

    source = inspect.getsource(repository).lower()
    for forbidden in (
        "get_session",
        "sqlite3",
        "create_engine",
        "from .assets",
        "import aqorath.assets",
        "monthly_depreciation",
        "annual_depreciation",
        "generate_depreciation_entries_for_period",
        "post_entry",
        "journalentry",
        "journalline",
        "accountrolebinding",
        '"6000"',
        '"1700"',
    ):
        assert forbidden not in source


def test_fixed_asset_persistence_does_not_create_accounting_fiscal_document_or_analytical_truth(tmp_path):
    from aqorath.fixed_asset_repository import create_fixed_asset
    from aqorath.models import (
        AnalyticalDimensionRecord,
        Asset,
        DocumentReferenceRecord,
        FiscalPostingAuditRecord,
        JournalEntry,
        JournalLine,
    )

    _, engine = _fresh_db(tmp_path, "non-accounting.db")
    with Session(engine) as session:
        entity = _create_entity(session)
        before = {
            JournalEntry: len(session.exec(select(JournalEntry)).all()),
            JournalLine: len(session.exec(select(JournalLine)).all()),
            FiscalPostingAuditRecord: len(
                session.exec(select(FiscalPostingAuditRecord)).all()
            ),
            DocumentReferenceRecord: len(
                session.exec(select(DocumentReferenceRecord)).all()
            ),
            AnalyticalDimensionRecord: len(
                session.exec(select(AnalyticalDimensionRecord)).all()
            ),
            Asset: len(session.exec(select(Asset)).all()),
        }

        create_fixed_asset(session, _fixed_asset(entity.id))

        after = {
            model: len(session.exec(select(model)).all())
            for model in before
        }
        assert after == before
    engine.dispose()


def test_application_exposes_fixed_asset_foundation_with_exact_signatures_and_delegates_only_to_repository(monkeypatch):
    import aqorath.application as application
    import aqorath.fixed_asset_repository as repository

    assert str(inspect.signature(application.create_fixed_asset)) == "(session, fixed_asset)"
    assert str(inspect.signature(application.get_fixed_asset)) == (
        "(session, entity_id, fixed_asset_id)"
    )
    assert str(inspect.signature(application.list_fixed_assets)) == (
        "(session, entity_id, include_inactive=False)"
    )
    assert str(inspect.signature(application.set_fixed_asset_active)) == (
        "(session, entity_id, fixed_asset_id, is_active)"
    )

    calls = []
    sentinels = [object(), object(), object(), object()]

    def create(session, fixed_asset):
        calls.append(("create", session, fixed_asset))
        return sentinels[0]

    def get(session, entity_id, fixed_asset_id):
        calls.append(("get", session, entity_id, fixed_asset_id))
        return sentinels[1]

    def list_(session, entity_id, include_inactive=False):
        calls.append(("list", session, entity_id, include_inactive))
        return sentinels[2]

    def active(session, entity_id, fixed_asset_id, is_active):
        calls.append(("active", session, entity_id, fixed_asset_id, is_active))
        return sentinels[3]

    monkeypatch.setattr(repository, "create_fixed_asset", create)
    monkeypatch.setattr(repository, "get_fixed_asset", get)
    monkeypatch.setattr(repository, "list_fixed_assets", list_)
    monkeypatch.setattr(repository, "set_fixed_asset_active", active)

    session = object()
    fixed_asset = object()
    assert application.create_fixed_asset(session, fixed_asset) is sentinels[0]
    assert application.get_fixed_asset(session, 11, 22) is sentinels[1]
    assert application.list_fixed_assets(session, 11, True) is sentinels[2]
    assert application.set_fixed_asset_active(session, 11, 22, False) is sentinels[3]
    assert calls == [
        ("create", session, fixed_asset),
        ("get", session, 11, 22),
        ("list", session, 11, True),
        ("active", session, 11, 22, False),
    ]

    source = inspect.getsource(application).lower()
    assert "from .assets" not in source
    assert "import aqorath.assets" not in source
