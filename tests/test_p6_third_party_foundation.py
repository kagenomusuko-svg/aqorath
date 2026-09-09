"""Phase 6B.1 — ThirdParty foundation contracts.

Contracts only. A ThirdParty is a counterparty owned by the one accounting Entity;
it is not another accounting entity, account, balance, CFDI, or fiscal-rule authority.
"""

from dataclasses import FrozenInstanceError, fields
import inspect
import sqlite3

import pytest
from sqlalchemy import create_engine
from sqlmodel import Session, select


_ALLOWED_TYPES = (
    "customer",
    "supplier",
    "donor",
    "creditor",
    "debtor",
    "employee",
    "other",
)


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
            modules_enabled=("banking",),
        ),
        is_active=True,
    )


def _third_party(
    entity_id,
    *,
    name="Contraparte Uno",
    rfc="XAXX010101000",
    party_type="customer",
    active=True,
):
    from aqorath.third_party import ThirdParty

    return ThirdParty(
        id=None,
        entity_id=entity_id,
        name=name,
        rfc=rfc,
        email="contacto@example.test",
        phone="+52 55 0000 0000",
        party_type=party_type,
        address="Ciudad de México",
        contact_person="Persona Contacto",
        notes="Referencia interna",
        is_active=active,
    )


def _fresh_db(tmp_path, filename="third-party.db"):
    from aqorath.migrations import migrate_database

    db_path = tmp_path / filename
    result = migrate_database(str(db_path))
    assert result["to_version"] == 6
    return db_path, create_engine(f"sqlite:///{db_path}")


def _create_entity(session):
    from aqorath.entity_repository import create_entity

    return create_entity(session, _entity())


def test_third_party_domain_is_pure_frozen_and_exactly_counterparty_identity_not_accounting_truth():
    import aqorath.third_party as domain
    from aqorath.third_party import ThirdParty

    party = ThirdParty(
        id=None,
        entity_id=7,
        name="Proveedor Demo",
        rfc=None,
        email=None,
        phone=None,
        party_type="supplier",
        address=None,
        contact_person=None,
        notes=None,
        is_active=True,
    )
    assert [field.name for field in fields(ThirdParty)] == [
        "id",
        "entity_id",
        "name",
        "rfc",
        "email",
        "phone",
        "party_type",
        "address",
        "contact_person",
        "notes",
        "is_active",
    ]
    with pytest.raises(FrozenInstanceError):
        party.name = "changed"

    forbidden = {
        "account_id",
        "account_code",
        "balance",
        "debit",
        "credit",
        "entry_id",
        "document_id",
        "cfdi_uuid",
        "fiscal_profile_id",
        "fiscal_rule_set_id",
    }
    assert forbidden.isdisjoint({field.name for field in fields(ThirdParty)})
    source = inspect.getsource(domain).lower()
    assert "sqlmodel" not in source
    assert "sqlalchemy" not in source


def test_third_party_validates_identity_optional_text_boolean_and_explicit_type_fail_closed():
    from aqorath.third_party import ThirdParty

    for party_type in _ALLOWED_TYPES:
        party = ThirdParty(
            id=None,
            entity_id=1,
            name="X",
            rfc=None,
            email=None,
            phone=None,
            party_type=party_type,
            address=None,
            contact_person=None,
            notes=None,
            is_active=True,
        )
        assert party.party_type == party_type

    invalid = (
        dict(entity_id=0, name="X", party_type="customer", is_active=True),
        dict(entity_id=True, name="X", party_type="customer", is_active=True),
        dict(entity_id=1, name="", party_type="customer", is_active=True),
        dict(entity_id=1, name="X", party_type="unknown", is_active=True),
        dict(entity_id=1, name="X", party_type="customer", is_active="yes"),
    )
    for values in invalid:
        with pytest.raises((TypeError, ValueError)):
            ThirdParty(
                id=None,
                entity_id=values["entity_id"],
                name=values["name"],
                rfc=None,
                email=None,
                phone=None,
                party_type=values["party_type"],
                address=None,
                contact_person=None,
                notes=None,
                is_active=values["is_active"],
            )

    for field_name in ("rfc", "email", "phone", "address", "contact_person", "notes"):
        kwargs = dict(
            id=None,
            entity_id=1,
            name="X",
            rfc=None,
            email=None,
            phone=None,
            party_type="other",
            address=None,
            contact_person=None,
            notes=None,
            is_active=True,
        )
        kwargs[field_name] = ""
        with pytest.raises((TypeError, ValueError)):
            ThirdParty(**kwargs)


def test_third_party_classification_is_explicit_and_not_inferred_from_name_rfc_or_entity_profile():
    from aqorath.third_party import ThirdParty

    donor_named_company = ThirdParty(
        id=None,
        entity_id=1,
        name="Comercializadora Ejemplo S.A. de C.V.",
        rfc="XAXX010101000",
        email=None,
        phone=None,
        party_type="donor",
        address=None,
        contact_person=None,
        notes=None,
        is_active=True,
    )
    customer_named_foundation = ThirdParty(
        id=None,
        entity_id=1,
        name="Fundación Ejemplo",
        rfc="XAXX010101000",
        email=None,
        phone=None,
        party_type="customer",
        address=None,
        contact_person=None,
        notes=None,
        is_active=True,
    )
    assert donor_named_company.party_type == "donor"
    assert customer_named_foundation.party_type == "customer"


def test_third_party_repository_public_contracts_have_exact_signatures():
    import aqorath.third_party_repository as repository

    assert str(inspect.signature(repository.create_third_party)) == "(session, third_party)"
    assert str(inspect.signature(repository.get_third_party)) == "(session, entity_id, third_party_id)"
    assert str(inspect.signature(repository.list_third_parties)) == "(session, entity_id, include_inactive=False)"
    assert str(inspect.signature(repository.set_third_party_active)) == "(session, entity_id, third_party_id, is_active)"
    assert not hasattr(repository, "delete_third_party")


def test_frozen_v4_additively_creates_third_party_table_columns_foreign_key_and_nonunique_rfc(tmp_path):
    from aqorath.migrations import CURRENT_SCHEMA_VERSION
    from aqorath.models import ThirdPartyRecord

    assert CURRENT_SCHEMA_VERSION == 6
    assert ThirdPartyRecord.__tablename__ == "thirdparty"

    db_path, engine = _fresh_db(tmp_path, "schema.db")
    engine.dispose()
    conn = sqlite3.connect(str(db_path))
    try:
        columns = {row[1]: row for row in conn.execute("PRAGMA table_info(thirdparty)")}
        assert set(columns) == {
            "id",
            "entity_id",
            "name",
            "rfc",
            "email",
            "phone",
            "party_type",
            "address",
            "contact_person",
            "notes",
            "is_active",
            "created_at",
        }
        for required in ("entity_id", "name", "party_type", "is_active", "created_at"):
            assert columns[required][3] == 1, required
        for optional in ("rfc", "email", "phone", "address", "contact_person", "notes"):
            assert columns[optional][3] == 0, optional

        fks = conn.execute("PRAGMA foreign_key_list(thirdparty)").fetchall()
        assert any(
            row[2] == "entity" and row[3] == "entity_id" and row[4] == "id"
            for row in fks
        )

        unique_indexes = [
            row for row in conn.execute("PRAGMA index_list(thirdparty)").fetchall()
            if row[2] == 1
        ]
        unique_column_sets = {
            tuple(
                col[2]
                for col in conn.execute(f"PRAGMA index_info({row[1]})").fetchall()
            )
            for row in unique_indexes
        }
        assert ("rfc",) not in unique_column_sets
        assert ("entity_id", "rfc") not in unique_column_sets
    finally:
        conn.close()


def test_current_v4_additive_ensure_adds_third_party_schema_without_rewriting_existing_truth(tmp_path):
    from aqorath.migrations import get_schema_version, migrate_database

    db_path = tmp_path / "existing-v4.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("CREATE TABLE fiscalpostingauditrecord (id INTEGER PRIMARY KEY)")
        conn.execute("CREATE TABLE preserved_truth (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO preserved_truth VALUES (1, 'keep-me')")
        conn.execute("PRAGMA user_version = 4")
        conn.commit()
    finally:
        conn.close()

    result = migrate_database(str(db_path))
    assert result == {
        "from_version": 4,
        "to_version": 6,
        "migrated": True,
        "backup_path": result["backup_path"],
    }
    assert __import__("pathlib").Path(result["backup_path"]).is_file()
    assert get_schema_version(str(db_path)) == 6
    conn = sqlite3.connect(str(db_path))
    try:
        assert conn.execute("SELECT value FROM preserved_truth WHERE id=1").fetchone() == ("keep-me",)
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"entity", "thirdparty"}.issubset(tables)
    finally:
        conn.close()


def test_create_third_party_round_trip_preserves_every_value_and_allows_many_counterparties(tmp_path):
    from aqorath.models import ThirdPartyRecord
    from aqorath.third_party import ThirdParty
    from aqorath.third_party_repository import create_third_party, get_third_party

    _, engine = _fresh_db(tmp_path, "round-trip.db")
    try:
        with Session(engine) as session:
            entity = _create_entity(session)
            first = create_third_party(session, _third_party(entity.id, name="Uno", party_type="customer"))
            second = create_third_party(session, _third_party(entity.id, name="Dos", party_type="supplier"))

            assert isinstance(first, ThirdParty)
            assert isinstance(second, ThirdParty)
            assert first.id != second.id
            assert first.rfc == second.rfc == "XAXX010101000"
            assert len(session.exec(select(ThirdPartyRecord)).all()) == 2
            assert get_third_party(session, entity.id, first.id) == first
            assert get_third_party(session, entity.id, second.id) == second
    finally:
        engine.dispose()


def test_create_third_party_requires_explicit_existing_active_owner_and_never_defaults_to_active_entity(tmp_path):
    from aqorath.entity import Entity
    from aqorath.entity_repository import create_entity
    from aqorath.third_party_repository import create_third_party

    _, engine = _fresh_db(tmp_path, "owner.db")
    try:
        with Session(engine) as session:
            active = _create_entity(session)
            with pytest.raises(LookupError):
                create_third_party(session, _third_party(active.id + 999))

            inactive_source = _entity()
            inactive = Entity(
                id=None,
                name="Entidad histórica",
                rfc=None,
                legal_personality=inactive_source.legal_personality,
                legal_form=inactive_source.legal_form,
                profile=inactive_source.profile,
                is_active=False,
            )
            inactive = create_entity(session, inactive)
            with pytest.raises(ValueError, match="active entity"):
                create_third_party(session, _third_party(inactive.id))
    finally:
        engine.dispose()


def test_create_third_party_rolls_back_when_single_commit_fails(tmp_path, monkeypatch):
    from aqorath.models import ThirdPartyRecord
    from aqorath.third_party_repository import create_third_party

    _, engine = _fresh_db(tmp_path, "rollback.db")
    try:
        with Session(engine) as session:
            entity = _create_entity(session)

            def fail_commit():
                raise RuntimeError("commit failed")

            monkeypatch.setattr(session, "commit", fail_commit)
            with pytest.raises(RuntimeError, match="commit failed"):
                create_third_party(session, _third_party(entity.id))
            assert session.exec(select(ThirdPartyRecord)).all() == []
    finally:
        engine.dispose()


def test_get_third_party_is_entity_scoped_and_fails_closed_for_missing_or_invalid_identity(tmp_path):
    from aqorath.third_party_repository import create_third_party, get_third_party

    _, engine = _fresh_db(tmp_path, "scoped-read.db")
    try:
        with Session(engine) as session:
            entity = _create_entity(session)
            party = create_third_party(session, _third_party(entity.id))
            assert get_third_party(session, entity.id, party.id) == party
            with pytest.raises(LookupError):
                get_third_party(session, entity.id + 1, party.id)
            with pytest.raises(LookupError):
                get_third_party(session, entity.id, party.id + 999)
            for bad in (0, True, "1"):
                with pytest.raises((TypeError, ValueError)):
                    get_third_party(session, bad, party.id)
                with pytest.raises((TypeError, ValueError)):
                    get_third_party(session, entity.id, bad)
    finally:
        engine.dispose()


def test_list_third_parties_is_entity_scoped_deterministic_and_excludes_inactive_by_default(tmp_path):
    from aqorath.third_party_repository import (
        create_third_party,
        list_third_parties,
        set_third_party_active,
    )

    _, engine = _fresh_db(tmp_path, "list.db")
    try:
        with Session(engine) as session:
            entity = _create_entity(session)
            one = create_third_party(session, _third_party(entity.id, name="Uno"))
            two = create_third_party(session, _third_party(entity.id, name="Dos"))
            three = create_third_party(session, _third_party(entity.id, name="Tres"))
            set_third_party_active(session, entity.id, two.id, False)

            active = list_third_parties(session, entity.id)
            all_rows = list_third_parties(session, entity.id, include_inactive=True)
            assert isinstance(active, tuple)
            assert [row.id for row in active] == [one.id, three.id]
            assert [row.id for row in all_rows] == [one.id, two.id, three.id]
            with pytest.raises((TypeError, ValueError)):
                list_third_parties(session, entity.id, include_inactive="yes")
    finally:
        engine.dispose()


def test_deactivation_and_reactivation_preserve_same_third_party_identity_and_never_delete_history(tmp_path):
    from aqorath.models import ThirdPartyRecord
    from aqorath.third_party_repository import (
        create_third_party,
        get_third_party,
        set_third_party_active,
    )

    _, engine = _fresh_db(tmp_path, "lifecycle.db")
    try:
        with Session(engine) as session:
            entity = _create_entity(session)
            original = create_third_party(session, _third_party(entity.id, name="Histórico"))
            inactive = set_third_party_active(session, entity.id, original.id, False)
            assert inactive.id == original.id
            assert inactive.name == original.name
            assert inactive.rfc == original.rfc
            assert inactive.is_active is False
            assert len(session.exec(select(ThirdPartyRecord)).all()) == 1
            assert get_third_party(session, entity.id, original.id) == inactive

            active = set_third_party_active(session, entity.id, original.id, True)
            assert active.id == original.id
            assert active.is_active is True
            assert len(session.exec(select(ThirdPartyRecord)).all()) == 1
    finally:
        engine.dispose()


def test_third_party_repository_uses_only_supplied_session_without_hidden_storage(tmp_path, monkeypatch):
    import aqorath.storage as storage
    from aqorath.third_party_repository import create_third_party, list_third_parties

    _, engine = _fresh_db(tmp_path, "supplied-session.db")
    try:
        with Session(engine) as session:
            entity = _create_entity(session)
            monkeypatch.setattr(
                storage,
                "get_session",
                lambda *args, **kwargs: (_ for _ in ()).throw(
                    AssertionError("hidden session forbidden")
                ),
            )
            created = create_third_party(session, _third_party(entity.id))
            assert list_third_parties(session, entity.id) == (created,)
    finally:
        engine.dispose()


def test_third_party_persistence_does_not_create_accounts_bindings_entries_or_fiscal_truth(tmp_path):
    from aqorath.models import (
        Account,
        AccountRoleBinding,
        FiscalProfileRecord,
        FiscalRuleVersion,
        JournalEntry,
        JournalLine,
    )
    from aqorath.third_party_repository import create_third_party

    _, engine = _fresh_db(tmp_path, "no-parallel-truth.db")
    try:
        with Session(engine) as session:
            entity = _create_entity(session)
            create_third_party(session, _third_party(entity.id, party_type="donor"))
            assert session.exec(select(Account)).all() == []
            assert session.exec(select(AccountRoleBinding)).all() == []
            assert session.exec(select(JournalEntry)).all() == []
            assert session.exec(select(JournalLine)).all() == []
            assert session.exec(select(FiscalProfileRecord)).all() == []
            assert session.exec(select(FiscalRuleVersion)).all() == []
    finally:
        engine.dispose()


def test_application_exposes_third_party_foundation_with_exact_signatures_and_delegates_only_to_repository(monkeypatch):
    import aqorath.application as application

    assert str(inspect.signature(application.create_third_party)) == "(session, third_party)"
    assert str(inspect.signature(application.get_third_party)) == "(session, entity_id, third_party_id)"
    assert str(inspect.signature(application.list_third_parties)) == "(session, entity_id, include_inactive=False)"
    assert str(inspect.signature(application.set_third_party_active)) == "(session, entity_id, third_party_id, is_active)"
    assert not hasattr(application, "delete_third_party")

    calls = []
    sent = object()
    created = object()
    loaded = object()
    listed = object()
    toggled = object()
    session = object()

    monkeypatch.setattr(
        application._third_party_repository,
        "create_third_party",
        lambda s, p: calls.append(("create", s, p)) or created,
    )
    monkeypatch.setattr(
        application._third_party_repository,
        "get_third_party",
        lambda s, entity_id, party_id: calls.append(("get", s, entity_id, party_id)) or loaded,
    )
    monkeypatch.setattr(
        application._third_party_repository,
        "list_third_parties",
        lambda s, entity_id, include_inactive=False: calls.append(("list", s, entity_id, include_inactive)) or listed,
    )
    monkeypatch.setattr(
        application._third_party_repository,
        "set_third_party_active",
        lambda s, entity_id, party_id, is_active: calls.append(("active", s, entity_id, party_id, is_active)) or toggled,
    )

    assert application.create_third_party(session, sent) is created
    assert application.get_third_party(session, 7, 8) is loaded
    assert application.list_third_parties(session, 7, include_inactive=True) is listed
    assert application.set_third_party_active(session, 7, 8, False) is toggled
    assert calls == [
        ("create", session, sent),
        ("get", session, 7, 8),
        ("list", session, 7, True),
        ("active", session, 7, 8, False),
    ]

    assert callable(application.create_entity)
    assert callable(application.get_active_entity)
    assert callable(application.execute_fiscalized_posting_with_audit)
    assert callable(application.get_financial_statements_bundle)
