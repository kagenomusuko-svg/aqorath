"""Phase 6AD.1 — frozen general AuditEvent traceability foundation contracts.

Architecture anchors:
- ARCHITECTURE_BASELINE_V1 defines AuditEvent explicitly as entity-scoped traceability.
- AuditEvent is append-only evidence about an action; it is not accounting or fiscal truth.
- Existing fiscal posting audit remains its specialized provenance authority.
- R8 monouser forbids enterprise actor/RBAC semantics from entering this foundation.

Phase 6AD freezes only explicit AuditEvent identity, deterministic metadata persistence,
entity scoping, and thin application access. It does not generate timestamps, infer actors,
post accounting, reconstruct fiscal provenance, or mutate prior events.
"""

from dataclasses import FrozenInstanceError, fields, replace
from datetime import datetime, timezone
from decimal import Decimal
import inspect
import json
import sqlite3

import pytest
from sqlalchemy import create_engine
from sqlmodel import Session, select


AUDIT_EVENT_FIELDS = (
    "id",
    "entity_id",
    "event_type",
    "timestamp",
    "details",
)


def _entity(*, osc=False, active=True, name="Entidad Uno"):
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


def _fresh_db(tmp_path, filename="audit-event.db"):
    from aqorath.migrations import CURRENT_SCHEMA_VERSION, migrate_database

    db_path = tmp_path / filename
    result = migrate_database(str(db_path))
    assert result["to_version"] == CURRENT_SCHEMA_VERSION
    return db_path, create_engine(f"sqlite:///{db_path}")


def _create_entity(session, *, osc=False, active=True, name="Entidad Uno"):
    from aqorath.entity_repository import create_entity

    return create_entity(
        session,
        _entity(osc=osc, active=active, name=name),
    )


def _event(
    entity_id,
    *,
    event_type="export",
    timestamp=datetime(2026, 8, 27, 12, 34, 56, tzinfo=timezone.utc),
    details=None,
):
    from aqorath.audit_event import AuditEvent

    if details is None:
        details = {"entry_id": 7, "source": "ui"}
    return AuditEvent(
        id=None,
        entity_id=entity_id,
        event_type=event_type,
        timestamp=timestamp,
        details=details,
    )


def test_audit_event_domain_is_pure_frozen_exact_and_not_accounting_fiscal_or_actor_truth():
    import aqorath.audit_event as domain
    from aqorath.audit_event import AuditEvent

    event = AuditEvent(
        id=None,
        entity_id=7,
        event_type="entry_posted",
        timestamp=datetime(2026, 8, 27, tzinfo=timezone.utc),
        details={"entry_id": 11},
    )

    assert tuple(field.name for field in fields(AuditEvent)) == AUDIT_EVENT_FIELDS
    with pytest.raises(FrozenInstanceError):
        event.event_type = "changed"

    forbidden_fields = {
        "user_id",
        "actor_id",
        "role_id",
        "account_id",
        "debit",
        "credit",
        "journal_line_id",
        "fiscal_rule_set_id",
        "fiscal_amount",
        "donation_id",
    }
    assert forbidden_fields.isdisjoint(AUDIT_EVENT_FIELDS)

    source = inspect.getsource(domain).lower()
    for forbidden_source in (
        "sqlmodel",
        "sqlalchemy",
        "sqlite3",
        "journalentry",
        "journalline",
        "fiscalpostingaudit",
        "userknowledge",
    ):
        assert forbidden_source not in source


def test_audit_event_domain_validates_identity_event_type_timestamp_and_exact_details_container():
    from aqorath.audit_event import AuditEvent

    moment = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
    details = {"entry_id": 4, "source": "application", "ok": True, "note": None}
    event = AuditEvent(9, 1, "entry_posted", moment, details)
    assert event.timestamp is moment
    assert event.details is details

    for patch in (
        {"id": 0},
        {"id": True},
        {"entity_id": 0},
        {"entity_id": True},
        {"event_type": ""},
        {"event_type": " event"},
        {"event_type": "event "},
        {"event_type": 7},
        {"timestamp": "2026-08-27T12:00:00+00:00"},
        {"timestamp": None},
        {"details": ()},
        {"details": []},
        {"details": None},
    ):
        values = dict(
            id=None,
            entity_id=1,
            event_type="export",
            timestamp=moment,
            details={},
        )
        values.update(patch)
        with pytest.raises((TypeError, ValueError)):
            AuditEvent(**values)


def test_audit_event_details_are_explicit_json_object_metadata_with_str_keys_and_fail_closed_values():
    from aqorath.audit_event import AuditEvent

    moment = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
    valid = {
        "action": "export",
        "ids": [1, 2],
        "flags": {"professional": True},
        "none": None,
    }
    event = AuditEvent(None, 1, "export", moment, valid)
    assert event.details == valid

    for details in (
        {1: "non-string-key"},
        {"": "blank-key"},
        {" key": "leading-space-key"},
        {"key ": "trailing-space-key"},
        {"amount": Decimal("1.00")},
        {"nan": float("nan")},
        {"infinity": float("inf")},
        {"unsupported": object()},
    ):
        with pytest.raises((TypeError, ValueError)):
            AuditEvent(None, 1, "export", moment, details)


def test_audit_event_repository_public_contracts_are_minimal_append_only_and_exact():
    import aqorath.audit_event_repository as repository

    assert str(inspect.signature(repository.create_audit_event)) == "(session, event)"
    assert str(inspect.signature(repository.get_audit_event)) == "(session, entity_id, event_id)"
    assert str(inspect.signature(repository.list_audit_events)) == "(session, entity_id)"

    for forbidden in (
        "update_audit_event",
        "delete_audit_event",
        "set_audit_event_active",
        "post_audit_event",
        "create_journal_entry",
    ):
        assert not hasattr(repository, forbidden)


def test_frozen_v4_additively_creates_exact_audit_event_schema_with_entity_fk_and_text_metadata(tmp_path):
    from aqorath.migrations import CURRENT_SCHEMA_VERSION
    from aqorath.models import AuditEventRecord

    assert CURRENT_SCHEMA_VERSION >= 4
    assert AuditEventRecord.__tablename__ == "auditevent"

    db_path, engine = _fresh_db(tmp_path, "schema.db")
    engine.dispose()
    conn = sqlite3.connect(str(db_path))
    try:
        columns = {row[1]: row for row in conn.execute("PRAGMA table_info(auditevent)")}
        assert set(columns) == {
            "id",
            "entity_id",
            "event_type",
            "timestamp",
            "details_json",
            "created_at",
        }
        for required in (
            "entity_id",
            "event_type",
            "timestamp",
            "details_json",
            "created_at",
        ):
            assert columns[required][3] == 1, required
        assert "TEXT" in columns["timestamp"][2].upper()
        assert "TEXT" in columns["details_json"][2].upper()

        fks = conn.execute("PRAGMA foreign_key_list(auditevent)").fetchall()
        assert any(
            row[2] == "entity" and row[3] == "entity_id" and row[4] == "id"
            for row in fks
        )
    finally:
        conn.close()


def test_current_v4_additive_ensure_adds_audit_event_without_rewriting_existing_truth(tmp_path):
    from aqorath.migrations import CURRENT_SCHEMA_VERSION, get_schema_version, migrate_database

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
        "to_version": CURRENT_SCHEMA_VERSION,
        "migrated": True,
        "backup_path": result["backup_path"],
    }
    assert __import__("pathlib").Path(result["backup_path"]).is_file()
    assert get_schema_version(str(db_path)) == CURRENT_SCHEMA_VERSION

    conn = sqlite3.connect(str(db_path))
    try:
        assert conn.execute("SELECT value FROM preserved_truth WHERE id=1").fetchone() == ("keep-me",)
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert {"entity", "auditevent"}.issubset(tables)
    finally:
        conn.close()


def test_create_audit_event_round_trip_preserves_explicit_timestamp_and_canonical_json_details(tmp_path):
    from aqorath.audit_event import AuditEvent
    from aqorath.audit_event_repository import create_audit_event, get_audit_event
    from aqorath.models import AuditEventRecord

    db_path, engine = _fresh_db(tmp_path, "round-trip.db")
    try:
        with Session(engine) as session:
            entity = _create_entity(session)
            moment = datetime(2026, 8, 27, 12, 34, 56, 123456, tzinfo=timezone.utc)
            source = _event(
                entity.id,
                timestamp=moment,
                details={"source": "ui", "entry_id": 7},
            )
            created = create_audit_event(session, source)

            assert isinstance(created, AuditEvent)
            assert created.id is not None
            assert source.id is None
            assert created.timestamp == moment
            assert created.details == {"source": "ui", "entry_id": 7}
            assert get_audit_event(session, entity.id, created.id) == created

            record = session.exec(select(AuditEventRecord)).one()
            assert record.timestamp == moment.isoformat()
            assert record.details_json == '{"entry_id":7,"source":"ui"}'

        conn = sqlite3.connect(str(db_path))
        try:
            assert conn.execute(
                "SELECT timestamp, details_json FROM auditevent"
            ).fetchone() == (
                moment.isoformat(),
                '{"entry_id":7,"source":"ui"}',
            )
        finally:
            conn.close()
    finally:
        engine.dispose()


def test_create_audit_event_requires_nominal_new_event_and_existing_active_owner(tmp_path):
    from aqorath.audit_event_repository import create_audit_event

    _, engine = _fresh_db(tmp_path, "owner.db")
    try:
        with Session(engine) as session:
            entity = _create_entity(session)
            with pytest.raises(TypeError):
                create_audit_event(session, object())
            with pytest.raises(ValueError):
                create_audit_event(session, replace(_event(entity.id), id=99))
            with pytest.raises(LookupError):
                create_audit_event(session, _event(entity.id + 999))
    finally:
        engine.dispose()

    _, inactive_engine = _fresh_db(tmp_path, "inactive.db")
    try:
        with Session(inactive_engine) as session:
            entity = _create_entity(session, active=False, name="Entidad Histórica")
            with pytest.raises(ValueError, match="active"):
                create_audit_event(session, _event(entity.id))
    finally:
        inactive_engine.dispose()


def test_audit_event_is_general_entity_traceability_and_does_not_require_osc_capability(tmp_path):
    from aqorath.audit_event_repository import create_audit_event

    _, commercial_engine = _fresh_db(tmp_path, "commercial.db")
    try:
        with Session(commercial_engine) as session:
            entity = _create_entity(session, osc=False, name="Comercial Uno")
            created = create_audit_event(session, _event(entity.id))
            assert created.entity_id == entity.id
    finally:
        commercial_engine.dispose()

    _, osc_engine = _fresh_db(tmp_path, "osc.db")
    try:
        with Session(osc_engine) as session:
            entity = _create_entity(session, osc=True, name="OSC Uno A.C.")
            created = create_audit_event(session, _event(entity.id))
            assert created.entity_id == entity.id
    finally:
        osc_engine.dispose()


def test_create_audit_event_rolls_back_when_single_commit_fails(tmp_path, monkeypatch):
    from aqorath.audit_event_repository import create_audit_event
    from aqorath.models import AuditEventRecord

    _, engine = _fresh_db(tmp_path, "rollback.db")
    try:
        with Session(engine) as session:
            entity = _create_entity(session)

            def fail_commit():
                raise RuntimeError("commit failed")

            monkeypatch.setattr(session, "commit", fail_commit)
            with pytest.raises(RuntimeError, match="commit failed"):
                create_audit_event(session, _event(entity.id))
            assert session.exec(select(AuditEventRecord)).all() == []
    finally:
        engine.dispose()


def test_get_audit_event_is_entity_scoped_and_fails_closed_for_missing_or_invalid_identity(tmp_path):
    from aqorath.audit_event_repository import create_audit_event, get_audit_event

    _, engine = _fresh_db(tmp_path, "scoped-read.db")
    try:
        with Session(engine) as session:
            entity = _create_entity(session)
            event = create_audit_event(session, _event(entity.id))
            assert get_audit_event(session, entity.id, event.id) == event

            with pytest.raises(LookupError):
                get_audit_event(session, entity.id + 1, event.id)
            with pytest.raises(LookupError):
                get_audit_event(session, entity.id, event.id + 999)

            for bad in (0, True, "1"):
                with pytest.raises((TypeError, ValueError)):
                    get_audit_event(session, bad, event.id)
                with pytest.raises((TypeError, ValueError)):
                    get_audit_event(session, entity.id, bad)
    finally:
        engine.dispose()


def test_list_audit_events_is_entity_scoped_deterministic_tuple_ordered_by_identity(tmp_path):
    from aqorath.audit_event_repository import create_audit_event, list_audit_events

    _, engine = _fresh_db(tmp_path, "list.db")
    try:
        with Session(engine) as session:
            entity = _create_entity(session)
            one = create_audit_event(session, _event(entity.id, event_type="one"))
            two = create_audit_event(session, _event(entity.id, event_type="two"))
            three = create_audit_event(session, _event(entity.id, event_type="three"))

            listed = list_audit_events(session, entity.id)
            assert isinstance(listed, tuple)
            assert [item.id for item in listed] == [one.id, two.id, three.id]

            for bad in (0, True, "1"):
                with pytest.raises((TypeError, ValueError)):
                    list_audit_events(session, bad)
    finally:
        engine.dispose()


def test_audit_event_repository_uses_supplied_session_and_never_resolves_hidden_storage_session(tmp_path, monkeypatch):
    import aqorath.storage as storage
    from aqorath.audit_event_repository import create_audit_event, list_audit_events

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
            created = create_audit_event(session, _event(entity.id))
            assert list_audit_events(session, entity.id) == (created,)
    finally:
        engine.dispose()


def test_audit_event_persistence_does_not_create_or_duplicate_accounting_fiscal_or_business_truth(tmp_path):
    from aqorath.audit_event_repository import create_audit_event
    from aqorath.models import (
        Account,
        DonationRecord,
        FiscalPostingAuditRecord,
        FiscalProfileRecord,
        FiscalRuleVersion,
        JournalEntry,
        JournalLine,
        ProgramRecord,
    )

    _, engine = _fresh_db(tmp_path, "no-parallel-truth.db")
    try:
        with Session(engine) as session:
            entity = _create_entity(session)
            create_audit_event(session, _event(entity.id))

            assert session.exec(select(Account)).all() == []
            assert session.exec(select(JournalEntry)).all() == []
            assert session.exec(select(JournalLine)).all() == []
            assert session.exec(select(FiscalPostingAuditRecord)).all() == []
            assert session.exec(select(FiscalProfileRecord)).all() == []
            assert session.exec(select(FiscalRuleVersion)).all() == []
            assert session.exec(select(ProgramRecord)).all() == []
            assert session.exec(select(DonationRecord)).all() == []
    finally:
        engine.dispose()


def test_audit_event_foundation_is_deterministic_and_never_generates_time_actor_or_external_truth():
    import aqorath.audit_event as domain
    import aqorath.audit_event_repository as repository

    source = (inspect.getsource(domain) + inspect.getsource(repository)).lower()
    for forbidden in (
        "datetime.now",
        "datetime.utcnow",
        "time.time",
        "random",
        "requests",
        "openai",
        "llm",
        "current_user",
        "user_id",
        "actor_id",
        "resolve_economic_fact",
        "post_entry",
        "fiscal_posting_audit",
    ):
        assert forbidden not in source


def test_application_exposes_exact_thin_audit_event_foundation_delegations(monkeypatch):
    import aqorath.application as application

    assert str(inspect.signature(application.create_audit_event)) == "(session, event)"
    assert str(inspect.signature(application.get_audit_event)) == "(session, entity_id, event_id)"
    assert str(inspect.signature(application.list_audit_events)) == "(session, entity_id)"
    assert not hasattr(application, "update_audit_event")
    assert not hasattr(application, "delete_audit_event")

    calls = []
    session = object()
    sent = object()
    created = object()
    loaded = object()
    listed = object()

    monkeypatch.setattr(
        application._audit_event_repository,
        "create_audit_event",
        lambda s, event: calls.append(("create", s, event)) or created,
    )
    monkeypatch.setattr(
        application._audit_event_repository,
        "get_audit_event",
        lambda s, entity_id, event_id: calls.append(
            ("get", s, entity_id, event_id)
        ) or loaded,
    )
    monkeypatch.setattr(
        application._audit_event_repository,
        "list_audit_events",
        lambda s, entity_id: calls.append(("list", s, entity_id)) or listed,
    )

    assert application.create_audit_event(session, sent) is created
    assert application.get_audit_event(session, 7, 8) is loaded
    assert application.list_audit_events(session, 7) is listed
    assert calls == [
        ("create", session, sent),
        ("get", session, 7, 8),
        ("list", session, 7),
    ]

    create_source = inspect.getsource(application.create_audit_event).lower()
    get_source = inspect.getsource(application.get_audit_event).lower()
    list_source = inspect.getsource(application.list_audit_events).lower()
    assert "_audit_event_repository.create_audit_event" in create_source
    assert "_audit_event_repository.get_audit_event" in get_source
    assert "_audit_event_repository.list_audit_events" in list_source
    for source in (create_source, get_source, list_source):
        for forbidden in (
            "storage",
            "get_session",
            "journalentry",
            "fiscal",
            "donation",
            "program",
            "report",
        ):
            assert forbidden not in source
