"""Phase 6AC.1 — frozen first-class OSC Donation foundation contracts.

Constitution anchors:
- R16 requires donors and donations to be first-class OSC concepts.
- R5 requires exact Decimal money for donation amounts.
- R9/R20 require explicit monoentity ownership and reuse of known counterparties.
- R17 forbids analytical dimensions from becoming parallel accounting truth.

Phase 6AC freezes only Donation identity, exact persistence, optional ThirdParty donor
reference, and thin application access. A Donation does not create accounts, entries,
programs, funds, analytical dimensions, fiscal truth, or reports by itself.
"""

from dataclasses import FrozenInstanceError, fields, replace
from datetime import datetime, timezone
from decimal import Decimal
import inspect
import sqlite3

import pytest
from sqlalchemy import create_engine
from sqlmodel import Session, select


DONATION_FIELDS = (
    "id",
    "entity_id",
    "date",
    "amount",
    "donor_third_party_id",
    "purpose",
    "is_restricted",
)


def _entity(*, osc=True, active=True, name="Meriadock A.C."):
    from aqorath.entity import Entity, EntityProfile

    return Entity(
        id=None,
        name=name,
        rfc=None,
        legal_personality="persona_moral",
        legal_form="A.C." if osc else "S.A. de C.V.",
        profile=EntityProfile(
            economic_purpose="no_lucrativo" if osc else "lucrativo",
            is_donor_authorized=False,
            special_capabilities=("osc",) if osc else (),
            modules_enabled=("banking",),
        ),
        is_active=active,
    )


def _fresh_db(tmp_path, filename="donation.db"):
    from aqorath.migrations import migrate_database

    db_path = tmp_path / filename
    result = migrate_database(str(db_path))
    assert result["to_version"] == 5
    return db_path, create_engine(f"sqlite:///{db_path}")


def _create_entity(session, *, osc=True, active=True, name="Meriadock A.C."):
    from aqorath.entity_repository import create_entity

    return create_entity(session, _entity(osc=osc, active=active, name=name))


def _create_donor(session, entity_id, *, name="Donante Uno", party_type="donor"):
    from aqorath.third_party import ThirdParty
    from aqorath.third_party_repository import create_third_party

    return create_third_party(
        session,
        ThirdParty(
            id=None,
            entity_id=entity_id,
            name=name,
            rfc=None,
            email=None,
            phone=None,
            party_type=party_type,
            address=None,
            contact_person=None,
            notes=None,
            is_active=True,
        ),
    )


def _donation(
    entity_id,
    *,
    donor_third_party_id=None,
    date=datetime(2026, 8, 27, 12, 34, 56, tzinfo=timezone.utc),
    amount=Decimal("1250.2300"),
    purpose="Educación comunitaria",
    is_restricted=True,
):
    from aqorath.donation import Donation

    return Donation(
        id=None,
        entity_id=entity_id,
        date=date,
        amount=amount,
        donor_third_party_id=donor_third_party_id,
        purpose=purpose,
        is_restricted=is_restricted,
    )


def test_donation_domain_is_pure_frozen_and_exactly_osc_resource_event_not_accounting_truth():
    import aqorath.donation as domain
    from aqorath.donation import Donation

    donation = Donation(
        id=None,
        entity_id=7,
        date=datetime(2026, 8, 27, tzinfo=timezone.utc),
        amount=Decimal("10.00"),
        donor_third_party_id=None,
        purpose=None,
        is_restricted=False,
    )
    assert tuple(field.name for field in fields(Donation)) == DONATION_FIELDS
    with pytest.raises(FrozenInstanceError):
        donation.amount = Decimal("11.00")

    forbidden = {
        "account_id", "account_code", "debit", "credit", "journal_entry_id",
        "journal_line_id", "dimension_id", "dimension_value_id", "program_id",
        "fund_id", "funding_source_id", "fiscal_rule_set_id",
    }
    assert forbidden.isdisjoint(DONATION_FIELDS)
    source = inspect.getsource(domain).lower()
    for forbidden_source in (
        "sqlmodel", "sqlalchemy", "sqlite3", "journalentry", "journalline",
        "analyticaldimension", "program", "funding",
    ):
        assert forbidden_source not in source


def test_donation_domain_validates_identity_datetime_exact_positive_decimal_optional_donor_and_purpose():
    from aqorath.donation import Donation

    moment = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
    exact = Decimal("1234.5600")
    donation = Donation(9, 1, moment, exact, 4, "Destino explícito", True)
    assert donation.date is moment
    assert donation.amount is exact

    for patch in (
        {"id": 0}, {"id": True}, {"entity_id": 0}, {"entity_id": True},
        {"date": "2026-08-27"}, {"date": None}, {"amount": Decimal("0")},
        {"amount": -Decimal("0.01")}, {"amount": Decimal("NaN")},
        {"amount": Decimal("Infinity")}, {"amount": 100}, {"amount": 100.0},
        {"donor_third_party_id": 0}, {"donor_third_party_id": True},
        {"purpose": ""}, {"purpose": " destino"}, {"purpose": "destino "},
        {"is_restricted": 1}, {"is_restricted": "yes"},
    ):
        values = dict(
            id=None,
            entity_id=1,
            date=moment,
            amount=Decimal("1.00"),
            donor_third_party_id=None,
            purpose=None,
            is_restricted=False,
        )
        values.update(patch)
        with pytest.raises((TypeError, ValueError)):
            Donation(**values)


def test_donation_donor_reference_is_optional_identity_not_embedded_counterparty_snapshot_or_mode():
    from aqorath.donation import Donation

    anonymous = Donation(
        None, 1, datetime(2026, 8, 27, tzinfo=timezone.utc),
        Decimal("1.00"), None, None, False,
    )
    identified = replace(anonymous, donor_third_party_id=8)
    assert anonymous.donor_third_party_id is None
    assert identified.donor_third_party_id == 8
    for forbidden in (
        "donor_name", "donor_rfc", "donor_email", "party_type", "osc_mode",
        "commercial_mode", "special_capabilities",
    ):
        assert not hasattr(identified, forbidden)


def test_donation_repository_public_contracts_are_minimal_exact_and_non_destructive():
    import aqorath.donation_repository as repository

    assert str(inspect.signature(repository.create_donation)) == "(session, donation)"
    assert str(inspect.signature(repository.get_donation)) == "(session, entity_id, donation_id)"
    assert str(inspect.signature(repository.list_donations)) == "(session, entity_id)"
    for forbidden in (
        "delete_donation", "post_donation", "create_account", "create_program",
        "create_fund", "assign_analytical_dimension_value",
    ):
        assert not hasattr(repository, forbidden)


def test_frozen_v4_additively_creates_exact_donation_schema_with_entity_donor_fks_and_text_money(tmp_path):
    from aqorath.migrations import CURRENT_SCHEMA_VERSION
    from aqorath.models import DonationRecord

    assert CURRENT_SCHEMA_VERSION == 5
    assert DonationRecord.__tablename__ == "donation"
    db_path, engine = _fresh_db(tmp_path, "schema.db")
    engine.dispose()
    conn = sqlite3.connect(str(db_path))
    try:
        columns = {row[1]: row for row in conn.execute("PRAGMA table_info(donation)")}
        assert set(columns) == {
            "id", "entity_id", "date", "amount", "donor_third_party_id",
            "purpose", "is_restricted", "created_at",
        }
        for required in ("entity_id", "date", "amount", "is_restricted", "created_at"):
            assert columns[required][3] == 1, required
        for optional in ("donor_third_party_id", "purpose"):
            assert columns[optional][3] == 0, optional
        assert "TEXT" in columns["date"][2].upper()
        assert "TEXT" in columns["amount"][2].upper()
        fks = conn.execute("PRAGMA foreign_key_list(donation)").fetchall()
        assert any(row[2] == "entity" and row[3] == "entity_id" and row[4] == "id" for row in fks)
        assert any(
            row[2] == "thirdparty" and row[3] == "donor_third_party_id" and row[4] == "id"
            for row in fks
        )
    finally:
        conn.close()


def test_current_v4_additive_ensure_adds_donation_without_rewriting_existing_truth(tmp_path):
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
        "from_version": 4, "to_version": 5, "migrated": True, "backup_path": result["backup_path"],
    }
    assert __import__("pathlib").Path(result["backup_path"]).is_file()
    assert get_schema_version(str(db_path)) == 5
    conn = sqlite3.connect(str(db_path))
    try:
        assert conn.execute("SELECT value FROM preserved_truth WHERE id=1").fetchone() == ("keep-me",)
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"entity", "thirdparty", "donation"}.issubset(tables)
    finally:
        conn.close()


def test_create_donation_round_trip_preserves_exact_decimal_scale_datetime_and_restriction(tmp_path):
    from aqorath.models import DonationRecord
    from aqorath.donation import Donation
    from aqorath.donation_repository import create_donation, get_donation

    db_path, engine = _fresh_db(tmp_path, "round-trip.db")
    try:
        with Session(engine) as session:
            entity = _create_entity(session)
            donor = _create_donor(session, entity.id)
            source = _donation(entity.id, donor_third_party_id=donor.id)
            created = create_donation(session, source)
            assert isinstance(created, Donation)
            assert created.id is not None
            assert source.id is None
            assert created.amount.as_tuple() == Decimal("1250.2300").as_tuple()
            assert created.date == source.date
            assert created.donor_third_party_id == donor.id
            assert created.is_restricted is True
            assert get_donation(session, entity.id, created.id) == created
            record = session.exec(select(DonationRecord)).one()
            assert record.amount == "1250.2300"
            assert record.date == source.date.isoformat()

        conn = sqlite3.connect(str(db_path))
        try:
            assert conn.execute("SELECT amount, date FROM donation").fetchone() == (
                "1250.2300", source.date.isoformat(),
            )
        finally:
            conn.close()
    finally:
        engine.dispose()


def test_create_donation_accepts_anonymous_donor_and_none_purpose_without_inventing_defaults(tmp_path):
    from aqorath.donation_repository import create_donation

    _, engine = _fresh_db(tmp_path, "anonymous.db")
    try:
        with Session(engine) as session:
            entity = _create_entity(session)
            created = create_donation(
                session,
                _donation(entity.id, donor_third_party_id=None, purpose=None, is_restricted=False),
            )
            assert created.donor_third_party_id is None
            assert created.purpose is None
            assert created.is_restricted is False
    finally:
        engine.dispose()


def test_create_donation_requires_nominal_new_donation_and_explicit_existing_active_osc_owner(tmp_path):
    from aqorath.donation_repository import create_donation

    _, engine = _fresh_db(tmp_path, "owner.db")
    try:
        with Session(engine) as session:
            entity = _create_entity(session)
            with pytest.raises(TypeError):
                create_donation(session, object())
            with pytest.raises(ValueError):
                create_donation(session, replace(_donation(entity.id), id=99))
            with pytest.raises(LookupError):
                create_donation(session, _donation(entity.id + 999))
    finally:
        engine.dispose()

    _, nonosc_engine = _fresh_db(tmp_path, "nonosc.db")
    try:
        with Session(nonosc_engine) as session:
            entity = _create_entity(session, osc=False, name="Comercial Uno S.A. de C.V.")
            with pytest.raises(ValueError, match="osc"):
                create_donation(session, _donation(entity.id))
    finally:
        nonosc_engine.dispose()

    _, inactive_engine = _fresh_db(tmp_path, "inactive.db")
    try:
        with Session(inactive_engine) as session:
            entity = _create_entity(session, active=False, name="OSC Histórica A.C.")
            with pytest.raises(ValueError, match="active"):
                create_donation(session, _donation(entity.id))
    finally:
        inactive_engine.dispose()


def test_create_donation_validates_optional_donor_reference_exists_and_is_owned_by_same_entity(tmp_path):
    from aqorath.models import EntityRecord, ThirdPartyRecord
    from aqorath.donation_repository import create_donation

    _, engine = _fresh_db(tmp_path, "donor-scope.db")
    try:
        with Session(engine) as session:
            entity = _create_entity(session)
            donor = _create_donor(session, entity.id)
            assert create_donation(
                session, _donation(entity.id, donor_third_party_id=donor.id),
            ).donor_third_party_id == donor.id
            with pytest.raises(LookupError):
                create_donation(
                    session, _donation(entity.id, donor_third_party_id=donor.id + 999),
                )

            other_entity = EntityRecord(
                name="Otra entidad histórica", rfc=None,
                legal_personality="persona_moral", legal_form="A.C.", is_active=False,
            )
            session.add(other_entity)
            session.flush()
            foreign_donor = ThirdPartyRecord(
                entity_id=other_entity.id, name="Donante ajeno", rfc=None, email=None,
                phone=None, party_type="donor", address=None, contact_person=None,
                notes=None, is_active=True,
            )
            session.add(foreign_donor)
            session.commit()
            with pytest.raises(ValueError, match="same Entity"):
                create_donation(
                    session, _donation(entity.id, donor_third_party_id=foreign_donor.id),
                )
    finally:
        engine.dispose()


def test_create_donation_rolls_back_when_single_commit_fails(tmp_path, monkeypatch):
    from aqorath.models import DonationRecord
    from aqorath.donation_repository import create_donation

    _, engine = _fresh_db(tmp_path, "rollback.db")
    try:
        with Session(engine) as session:
            entity = _create_entity(session)

            def fail_commit():
                raise RuntimeError("commit failed")

            monkeypatch.setattr(session, "commit", fail_commit)
            with pytest.raises(RuntimeError, match="commit failed"):
                create_donation(session, _donation(entity.id))
            assert session.exec(select(DonationRecord)).all() == []
    finally:
        engine.dispose()


def test_get_donation_is_entity_scoped_and_fails_closed_for_missing_or_invalid_identity(tmp_path):
    from aqorath.donation_repository import create_donation, get_donation

    _, engine = _fresh_db(tmp_path, "scoped-read.db")
    try:
        with Session(engine) as session:
            entity = _create_entity(session)
            donation = create_donation(session, _donation(entity.id))
            assert get_donation(session, entity.id, donation.id) == donation
            with pytest.raises(LookupError):
                get_donation(session, entity.id + 1, donation.id)
            with pytest.raises(LookupError):
                get_donation(session, entity.id, donation.id + 999)
            for bad in (0, True, "1"):
                with pytest.raises((TypeError, ValueError)):
                    get_donation(session, bad, donation.id)
                with pytest.raises((TypeError, ValueError)):
                    get_donation(session, entity.id, bad)
    finally:
        engine.dispose()


def test_list_donations_is_entity_scoped_deterministic_tuple_ordered_by_identity(tmp_path):
    from aqorath.donation_repository import create_donation, list_donations

    _, engine = _fresh_db(tmp_path, "list.db")
    try:
        with Session(engine) as session:
            entity = _create_entity(session)
            one = create_donation(session, _donation(entity.id, amount=Decimal("1.00")))
            two = create_donation(session, _donation(entity.id, amount=Decimal("2.00")))
            three = create_donation(session, _donation(entity.id, amount=Decimal("3.00")))
            listed = list_donations(session, entity.id)
            assert isinstance(listed, tuple)
            assert [item.id for item in listed] == [one.id, two.id, three.id]
            for bad in (0, True, "1"):
                with pytest.raises((TypeError, ValueError)):
                    list_donations(session, bad)
    finally:
        engine.dispose()


def test_donation_repository_uses_supplied_session_and_never_resolves_hidden_storage_session(tmp_path, monkeypatch):
    import aqorath.storage as storage
    from aqorath.donation_repository import create_donation, list_donations

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
            created = create_donation(session, _donation(entity.id))
            assert list_donations(session, entity.id) == (created,)
    finally:
        engine.dispose()


def test_donation_persistence_has_no_parallel_truth_and_foundation_has_no_time_or_external_generation_authority(tmp_path):
    import aqorath.donation as domain
    import aqorath.donation_repository as repository
    from aqorath.models import (
        Account, AnalyticalDimensionRecord, AnalyticalDimensionValueRecord,
        FiscalProfileRecord, FiscalRuleVersion, JournalEntry, JournalLine, ProgramRecord,
    )
    from aqorath.donation_repository import create_donation

    _, engine = _fresh_db(tmp_path, "no-parallel-truth.db")
    try:
        with Session(engine) as session:
            entity = _create_entity(session)
            create_donation(session, _donation(entity.id))
            assert session.exec(select(Account)).all() == []
            assert session.exec(select(JournalEntry)).all() == []
            assert session.exec(select(JournalLine)).all() == []
            assert session.exec(select(ProgramRecord)).all() == []
            assert session.exec(select(AnalyticalDimensionRecord)).all() == []
            assert session.exec(select(AnalyticalDimensionValueRecord)).all() == []
            assert session.exec(select(FiscalProfileRecord)).all() == []
            assert session.exec(select(FiscalRuleVersion)).all() == []
    finally:
        engine.dispose()

    source = (inspect.getsource(domain) + inspect.getsource(repository)).lower()
    for forbidden in (
        "datetime.now", "datetime.utcnow", "time.time", "random", "requests",
        "openai", "llm", "render", "generate_report", "resolve_economic_fact", "post_entry",
    ):
        assert forbidden not in source


def test_application_exposes_exact_thin_donation_foundation_delegations(monkeypatch):
    import aqorath.application as application

    assert str(inspect.signature(application.create_donation)) == "(session, donation)"
    assert str(inspect.signature(application.get_donation)) == "(session, entity_id, donation_id)"
    assert str(inspect.signature(application.list_donations)) == "(session, entity_id)"
    assert not hasattr(application, "delete_donation")

    calls = []
    session = object()
    sent = object()
    created = object()
    loaded = object()
    listed = object()
    monkeypatch.setattr(
        application._donation_repository,
        "create_donation",
        lambda s, d: calls.append(("create", s, d)) or created,
    )
    monkeypatch.setattr(
        application._donation_repository,
        "get_donation",
        lambda s, entity_id, donation_id: calls.append(("get", s, entity_id, donation_id)) or loaded,
    )
    monkeypatch.setattr(
        application._donation_repository,
        "list_donations",
        lambda s, entity_id: calls.append(("list", s, entity_id)) or listed,
    )
    assert application.create_donation(session, sent) is created
    assert application.get_donation(session, 7, 8) is loaded
    assert application.list_donations(session, 7) is listed
    assert calls == [
        ("create", session, sent),
        ("get", session, 7, 8),
        ("list", session, 7),
    ]

    create_source = inspect.getsource(application.create_donation).lower()
    get_source = inspect.getsource(application.get_donation).lower()
    list_source = inspect.getsource(application.list_donations).lower()
    assert "_donation_repository.create_donation" in create_source
    assert "_donation_repository.get_donation" in get_source
    assert "_donation_repository.list_donations" in list_source
    for source in (create_source, get_source, list_source):
        for forbidden in (
            "storage", "get_session", "journalentry", "analyticaldimension",
            "program", "report",
        ):
            assert forbidden not in source
