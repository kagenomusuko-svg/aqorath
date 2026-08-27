"""Phase 6A.1 — Entity / EntityProfile / FiscalProfile foundation contracts.

Contracts only.  This phase establishes one active accounting entity per local
installation, keeps economic/legal identity separate from effective-dated fiscal
profile history, and exposes the capability through the canonical application
boundary.  It deliberately does not introduce ThirdParty, CFDI, UI modes, or
implicit fiscal-rule selection.
"""

from dataclasses import FrozenInstanceError, fields
from datetime import date
import inspect
import sqlite3

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select


def _entity_profile():
    from aqorath.entity import EntityProfile

    return EntityProfile(
        economic_purpose="no_lucrativo",
        is_donor_authorized=False,
        special_capabilities=("osc", "restricted_funds"),
        modules_enabled=("banking", "osc"),
    )


def _entity(*, name="Meriadock A.C.", active=True):
    from aqorath.entity import Entity

    return Entity(
        id=None,
        name=name,
        rfc=None,
        legal_personality="persona_moral",
        legal_form="A.C.",
        profile=_entity_profile(),
        is_active=active,
    )


def _fiscal_profile(
    entity_id,
    *,
    regime="TEST-REGIME-A",
    start=date(2024, 1, 1),
    end=None,
    characteristics=("cfdi", "iva"),
):
    from aqorath.entity import FiscalProfile

    return FiscalProfile(
        id=None,
        entity_id=entity_id,
        jurisdiction="MX",
        fiscal_regime_code=regime,
        tax_characteristics=characteristics,
        effective_from=start,
        effective_to=end,
    )


def _fresh_db(tmp_path, filename="entity-foundation.db"):
    from aqorath.migrations import migrate_database

    db_path = tmp_path / filename
    result = migrate_database(str(db_path))
    assert result["to_version"] == 5
    engine = create_engine(f"sqlite:///{db_path}")
    return db_path, engine


def test_entity_domain_is_pure_frozen_compositional_and_keeps_fiscal_history_outside_entity_profile():
    import aqorath.entity as domain
    from aqorath.entity import Entity, EntityProfile, FiscalProfile

    profile = _entity_profile()
    entity = _entity()

    assert entity.profile is profile or entity.profile == profile
    assert entity.name == "Meriadock A.C."
    assert entity.legal_personality == "persona_moral"
    assert entity.legal_form == "A.C."
    assert entity.is_active is True

    with pytest.raises(FrozenInstanceError):
        entity.name = "changed"
    with pytest.raises(FrozenInstanceError):
        profile.economic_purpose = "lucrativo"

    # Fiscal history is independent, not one mutable pointer inside EntityProfile.
    assert "fiscal_profile_id" not in {field.name for field in fields(EntityProfile)}
    assert {"Entity", "EntityProfile", "FiscalProfile"}.issubset(set(dir(domain)))

    source = inspect.getsource(domain).lower()
    assert "sqlmodel" not in source
    assert "sqlalchemy" not in source


def test_entity_and_entity_profile_validate_identity_and_immutable_collection_contracts_fail_closed():
    from aqorath.entity import Entity, EntityProfile

    valid_profile = _entity_profile()

    invalid_profiles = (
        dict(
            economic_purpose="unknown",
            is_donor_authorized=False,
            special_capabilities=(),
            modules_enabled=(),
        ),
        dict(
            economic_purpose="lucrativo",
            is_donor_authorized="no",
            special_capabilities=(),
            modules_enabled=(),
        ),
        dict(
            economic_purpose="lucrativo",
            is_donor_authorized=False,
            special_capabilities=["osc"],
            modules_enabled=(),
        ),
        dict(
            economic_purpose="lucrativo",
            is_donor_authorized=False,
            special_capabilities=("osc", "osc"),
            modules_enabled=(),
        ),
        dict(
            economic_purpose="lucrativo",
            is_donor_authorized=False,
            special_capabilities=("",),
            modules_enabled=(),
        ),
    )
    for kwargs in invalid_profiles:
        with pytest.raises((TypeError, ValueError)):
            EntityProfile(**kwargs)

    invalid_entities = (
        dict(name="", legal_personality="persona_moral", legal_form="A.C."),
        dict(name="X", legal_personality="unknown", legal_form="A.C."),
        dict(name="X", legal_personality="persona_moral", legal_form=""),
    )
    for invalid in invalid_entities:
        with pytest.raises((TypeError, ValueError)):
            Entity(
                id=None,
                name=invalid["name"],
                rfc=None,
                legal_personality=invalid["legal_personality"],
                legal_form=invalid["legal_form"],
                profile=valid_profile,
                is_active=True,
            )

    with pytest.raises((TypeError, ValueError)):
        Entity(
            id=None,
            name="X",
            rfc="",
            legal_personality="persona_moral",
            legal_form="A.C.",
            profile=valid_profile,
            is_active=True,
        )


def test_entity_profile_is_component_data_not_commercial_osc_mode_or_capability_inference():
    from aqorath.entity import EntityProfile

    neutral = EntityProfile(
        economic_purpose="no_lucrativo",
        is_donor_authorized=True,
        special_capabilities=(),
        modules_enabled=(),
    )
    assert neutral.special_capabilities == ()
    assert neutral.modules_enabled == ()
    assert not hasattr(neutral, "mode")
    assert not hasattr(neutral, "company_mode")
    assert not hasattr(neutral, "accounting_engine")


def test_fiscal_profile_is_frozen_explicit_effective_dated_and_does_not_infer_tax_characteristics():
    from aqorath.entity import FiscalProfile

    profile = FiscalProfile(
        id=None,
        entity_id=7,
        jurisdiction="MX",
        fiscal_regime_code="UNMAPPED-EXPLICIT",
        tax_characteristics=(),
        effective_from=date(2025, 1, 1),
        effective_to=None,
    )
    assert profile.tax_characteristics == ()
    assert profile.fiscal_regime_code == "UNMAPPED-EXPLICIT"
    with pytest.raises(FrozenInstanceError):
        profile.fiscal_regime_code = "changed"

    with pytest.raises((TypeError, ValueError)):
        FiscalProfile(
            id=None,
            entity_id=7,
            jurisdiction="MX",
            fiscal_regime_code="R",
            tax_characteristics=("iva",),
            effective_from=date(2025, 2, 1),
            effective_to=date(2025, 1, 31),
        )
    with pytest.raises((TypeError, ValueError)):
        FiscalProfile(
            id=None,
            entity_id=7,
            jurisdiction="MX",
            fiscal_regime_code="R",
            tax_characteristics=["iva"],
            effective_from=date(2025, 1, 1),
            effective_to=None,
        )


def test_entity_repository_public_contracts_have_exact_signatures():
    import aqorath.entity_repository as repository

    assert str(inspect.signature(repository.create_entity)) == "(session, entity)"
    assert str(inspect.signature(repository.load_active_entity)) == "(session)"
    assert str(inspect.signature(repository.register_fiscal_profile)) == "(session, profile)"
    assert str(inspect.signature(repository.resolve_fiscal_profile)) == "(session, entity_id, effective_date)"


def test_schema_v5_creates_canonical_entity_profile_tables_foreign_keys_and_single_active_constraint(tmp_path):
    from aqorath.migrations import CURRENT_SCHEMA_VERSION, MIGRATIONS

    assert CURRENT_SCHEMA_VERSION == 5
    assert 5 in MIGRATIONS

    db_path, engine = _fresh_db(tmp_path, "fresh-v5.db")
    engine.dispose()

    conn = sqlite3.connect(str(db_path))
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        assert {"entity", "entityprofile", "fiscalprofile"}.issubset(tables)

        entity_columns = {row[1] for row in conn.execute("PRAGMA table_info(entity)")}
        assert {
            "id",
            "name",
            "rfc",
            "legal_personality",
            "legal_form",
            "is_active",
            "created_at",
        }.issubset(entity_columns)

        profile_columns = {row[1] for row in conn.execute("PRAGMA table_info(entityprofile)")}
        assert {
            "id",
            "entity_id",
            "economic_purpose",
            "is_donor_authorized",
            "special_capabilities_json",
            "modules_enabled_json",
            "created_at",
        }.issubset(profile_columns)

        fiscal_columns = {row[1] for row in conn.execute("PRAGMA table_info(fiscalprofile)")}
        assert {
            "id",
            "entity_id",
            "jurisdiction",
            "fiscal_regime_code",
            "tax_characteristics_json",
            "effective_from",
            "effective_to",
            "created_at",
        }.issubset(fiscal_columns)

        entity_profile_fks = conn.execute("PRAGMA foreign_key_list(entityprofile)").fetchall()
        fiscal_profile_fks = conn.execute("PRAGMA foreign_key_list(fiscalprofile)").fetchall()
        assert any(row[2] == "entity" and row[3] == "entity_id" for row in entity_profile_fks)
        assert any(row[2] == "entity" and row[3] == "entity_id" for row in fiscal_profile_fks)

        indexes = conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='entity'"
        ).fetchall()
        assert any(
            name == "uq_entity_single_active"
            and sql is not None
            and "where is_active = 1" in sql.lower()
            for name, sql in indexes
        )
    finally:
        conn.close()


def test_schema_v4_migrates_to_v5_without_rewriting_existing_truth(tmp_path):
    from aqorath.migrations import get_schema_version, migrate_database

    db_path = tmp_path / "legacy-v4.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("CREATE TABLE fiscalpostingauditrecord (id INTEGER PRIMARY KEY)")
        conn.execute("CREATE TABLE preserved_truth (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO preserved_truth(id, value) VALUES (1, 'keep-me')")
        conn.execute("PRAGMA user_version = 4")
        conn.commit()
    finally:
        conn.close()

    result = migrate_database(str(db_path))
    assert result["from_version"] == 4
    assert result["to_version"] == 5
    assert result["migrated"] is True
    assert get_schema_version(str(db_path)) == 5

    conn = sqlite3.connect(str(db_path))
    try:
        assert conn.execute("SELECT value FROM preserved_truth WHERE id=1").fetchone()[0] == "keep-me"
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert {"entity", "entityprofile", "fiscalprofile"}.issubset(tables)
    finally:
        conn.close()


def test_sqlite_structurally_rejects_two_active_entities_even_if_repository_is_bypassed(tmp_path):
    from aqorath.models import EntityRecord

    _, engine = _fresh_db(tmp_path, "single-active.db")
    try:
        with Session(engine) as session:
            session.add(
                EntityRecord(
                    name="One",
                    rfc=None,
                    legal_personality="persona_moral",
                    legal_form="A.C.",
                    is_active=True,
                )
            )
            session.commit()
            session.add(
                EntityRecord(
                    name="Two",
                    rfc=None,
                    legal_personality="persona_moral",
                    legal_form="S.A.",
                    is_active=True,
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
    finally:
        engine.dispose()


def test_create_and_load_active_entity_round_trip_one_atomic_domain_aggregate(tmp_path):
    from aqorath.entity import Entity
    from aqorath.entity_repository import create_entity, load_active_entity
    from aqorath.models import EntityProfileRecord, EntityRecord

    _, engine = _fresh_db(tmp_path, "entity-round-trip.db")
    try:
        with Session(engine) as session:
            created = create_entity(session, _entity())
            assert isinstance(created, Entity)
            assert isinstance(created.id, int) and created.id > 0
            assert created.name == "Meriadock A.C."
            assert created.profile == _entity_profile()
            assert len(session.exec(select(EntityRecord)).all()) == 1
            assert len(session.exec(select(EntityProfileRecord)).all()) == 1

            loaded = load_active_entity(session)
            assert isinstance(loaded, Entity)
            assert loaded == created
            assert loaded.profile.special_capabilities == ("osc", "restricted_funds")
            assert loaded.profile.modules_enabled == ("banking", "osc")
    finally:
        engine.dispose()


def test_create_entity_rolls_back_header_and_profile_when_single_commit_fails(tmp_path, monkeypatch):
    from aqorath.entity_repository import create_entity
    from aqorath.models import EntityProfileRecord, EntityRecord

    _, engine = _fresh_db(tmp_path, "entity-rollback.db")
    try:
        with Session(engine) as session:
            def fail_commit():
                raise RuntimeError("commit failed")

            monkeypatch.setattr(session, "commit", fail_commit)
            with pytest.raises(RuntimeError, match="commit failed"):
                create_entity(session, _entity())

            assert session.exec(select(EntityRecord)).all() == []
            assert session.exec(select(EntityProfileRecord)).all() == []
    finally:
        engine.dispose()


def test_repository_rejects_second_active_entity_without_deactivating_or_replacing_first(tmp_path):
    from aqorath.entity_repository import create_entity, load_active_entity

    _, engine = _fresh_db(tmp_path, "repository-single-active.db")
    try:
        with Session(engine) as session:
            first = create_entity(session, _entity(name="First A.C."))
            with pytest.raises(ValueError, match="active entity"):
                create_entity(session, _entity(name="Second A.C."))
            loaded = load_active_entity(session)
            assert loaded.id == first.id
            assert loaded.name == "First A.C."
            assert loaded.is_active is True
    finally:
        engine.dispose()


def test_load_active_entity_uses_only_supplied_session_and_returns_none_before_setup(tmp_path, monkeypatch):
    import aqorath.storage as storage
    from aqorath.entity_repository import load_active_entity

    _, engine = _fresh_db(tmp_path, "supplied-session.db")
    try:
        with Session(engine) as session:
            monkeypatch.setattr(
                storage,
                "get_session",
                lambda *args, **kwargs: (_ for _ in ()).throw(
                    AssertionError("hidden session forbidden")
                ),
            )
            assert load_active_entity(session) is None
    finally:
        engine.dispose()


def test_fiscal_profile_history_registers_and_resolves_exact_inclusive_effective_intervals(tmp_path):
    from aqorath.entity import FiscalProfile
    from aqorath.entity_repository import (
        create_entity,
        register_fiscal_profile,
        resolve_fiscal_profile,
    )

    _, engine = _fresh_db(tmp_path, "fiscal-history.db")
    try:
        with Session(engine) as session:
            entity = create_entity(session, _entity())
            first = register_fiscal_profile(
                session,
                _fiscal_profile(
                    entity.id,
                    regime="REGIME-2024",
                    start=date(2024, 1, 1),
                    end=date(2024, 12, 31),
                    characteristics=("cfdi",),
                ),
            )
            second = register_fiscal_profile(
                session,
                _fiscal_profile(
                    entity.id,
                    regime="REGIME-2025",
                    start=date(2025, 1, 1),
                    end=None,
                    characteristics=("cfdi", "iva", "isr"),
                ),
            )

            assert isinstance(first, FiscalProfile)
            assert isinstance(second, FiscalProfile)
            assert resolve_fiscal_profile(session, entity.id, date(2024, 1, 1)) == first
            assert resolve_fiscal_profile(session, entity.id, date(2024, 12, 31)) == first
            assert resolve_fiscal_profile(session, entity.id, date(2025, 1, 1)) == second
            assert resolve_fiscal_profile(session, entity.id, date(2026, 8, 27)) == second
            assert second.tax_characteristics == ("cfdi", "iva", "isr")
    finally:
        engine.dispose()


def test_fiscal_profile_registration_rejects_overlap_without_closing_or_rewriting_existing_history(tmp_path):
    from aqorath.entity_repository import create_entity, register_fiscal_profile
    from aqorath.models import FiscalProfileRecord

    _, engine = _fresh_db(tmp_path, "fiscal-overlap.db")
    try:
        with Session(engine) as session:
            entity = create_entity(session, _entity())
            original = register_fiscal_profile(
                session,
                _fiscal_profile(
                    entity.id,
                    regime="ORIGINAL",
                    start=date(2024, 1, 1),
                    end=date(2025, 12, 31),
                ),
            )
            with pytest.raises(ValueError, match="overlap"):
                register_fiscal_profile(
                    session,
                    _fiscal_profile(
                        entity.id,
                        regime="OVERLAP",
                        start=date(2025, 1, 1),
                        end=None,
                    ),
                )

            rows = session.exec(select(FiscalProfileRecord)).all()
            assert len(rows) == 1
            assert rows[0].id == original.id
            assert rows[0].fiscal_regime_code == "ORIGINAL"
            assert rows[0].effective_to == date(2025, 12, 31)
    finally:
        engine.dispose()


def test_fiscal_profile_resolution_fails_closed_before_coverage_for_wrong_entity_and_for_invalid_inputs(tmp_path):
    from aqorath.entity_repository import (
        create_entity,
        register_fiscal_profile,
        resolve_fiscal_profile,
    )

    _, engine = _fresh_db(tmp_path, "fiscal-fail-closed.db")
    try:
        with Session(engine) as session:
            entity = create_entity(session, _entity())
            register_fiscal_profile(
                session,
                _fiscal_profile(entity.id, start=date(2025, 1, 1)),
            )

            with pytest.raises(LookupError):
                resolve_fiscal_profile(session, entity.id, date(2024, 12, 31))
            with pytest.raises(LookupError):
                resolve_fiscal_profile(session, entity.id + 999, date(2025, 1, 1))
            with pytest.raises((TypeError, ValueError)):
                resolve_fiscal_profile(session, entity.id, "2025-01-01")
    finally:
        engine.dispose()


def test_entity_fiscal_profile_authority_never_installs_resolves_or_infers_fiscal_rules(tmp_path, monkeypatch):
    import aqorath.fiscal_rule_install as fiscal_install
    import aqorath.fiscal_rules as fiscal_rules
    from aqorath.entity_repository import (
        create_entity,
        register_fiscal_profile,
        resolve_fiscal_profile,
    )

    _, engine = _fresh_db(tmp_path, "no-rule-inference.db")
    try:
        with Session(engine) as session:
            entity = create_entity(session, _entity())

            def forbidden(*args, **kwargs):
                raise AssertionError("entity profile authority must not own fiscal rules")

            monkeypatch.setattr(fiscal_install, "install_fiscal_rule_set", forbidden)
            monkeypatch.setattr(fiscal_rules, "resolve_fiscal_rule", forbidden)

            registered = register_fiscal_profile(
                session,
                _fiscal_profile(
                    entity.id,
                    regime="UNMAPPED-EXPLICIT",
                    characteristics=(),
                ),
            )
            resolved = resolve_fiscal_profile(
                session,
                entity.id,
                registered.effective_from,
            )
            assert resolved == registered
            assert resolved.tax_characteristics == ()
    finally:
        engine.dispose()


def test_application_exposes_entity_foundation_with_exact_signatures_and_delegates_only_to_repository(monkeypatch):
    import aqorath.application as application

    assert str(inspect.signature(application.create_entity)) == "(session, entity)"
    assert str(inspect.signature(application.get_active_entity)) == "(session)"
    assert str(inspect.signature(application.register_fiscal_profile)) == "(session, profile)"
    assert str(inspect.signature(application.get_fiscal_profile_for_date)) == "(session, entity_id, effective_date)"

    calls = []
    sent_entity = object()
    sent_profile = object()
    created = object()
    active = object()
    registered = object()
    resolved = object()
    effective_date = date(2026, 8, 27)

    monkeypatch.setattr(
        application._entity_repository,
        "create_entity",
        lambda session, entity: calls.append(("create", session, entity)) or created,
    )
    monkeypatch.setattr(
        application._entity_repository,
        "load_active_entity",
        lambda session: calls.append(("load", session)) or active,
    )
    monkeypatch.setattr(
        application._entity_repository,
        "register_fiscal_profile",
        lambda session, profile: calls.append(("register", session, profile)) or registered,
    )
    monkeypatch.setattr(
        application._entity_repository,
        "resolve_fiscal_profile",
        lambda session, entity_id, effective_date: calls.append(
            ("resolve", session, entity_id, effective_date)
        )
        or resolved,
    )

    session = object()
    assert application.create_entity(session, sent_entity) is created
    assert application.get_active_entity(session) is active
    assert application.register_fiscal_profile(session, sent_profile) is registered
    assert application.get_fiscal_profile_for_date(session, 42, effective_date) is resolved
    assert calls == [
        ("create", session, sent_entity),
        ("load", session),
        ("register", session, sent_profile),
        ("resolve", session, 42, effective_date),
    ]

    # Existing canonical boundaries remain present; Entity is additive, not a new app.
    assert callable(application.preview_economic_fact)
    assert callable(application.execute_fiscalized_posting_with_audit)
    assert callable(application.get_financial_statements_bundle)
