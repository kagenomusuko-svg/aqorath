"""Phase 6AB.1 — frozen first-class OSC Program foundation contracts.

Constitution anchors:
- R16 requires OSC concepts such as programs to be first-class, not a renamed ERP mode.
- R17 allows analytical dimensions without duplicating accounting truth.
- R5 requires exact Decimal money wherever an optional program budget is present.

Phase 6AB freezes only Program identity, persistence, and thin application access. A
Program is management structure owned by the accounting Entity. It does not create
accounts, journal entries, analytical dimensions, donations, fiscal truth, or report
outputs by itself.
"""

from dataclasses import FrozenInstanceError, fields
from decimal import Decimal
import inspect
import sqlite3

import pytest
from sqlalchemy import create_engine
from sqlmodel import Session, select


PROGRAM_FIELDS = (
    "id",
    "entity_id",
    "name",
    "description",
    "budget",
)


def _entity(*, osc=True, active=True, name="Meriadock A.C."):
    from aqorath.entity import Entity, EntityProfile

    capabilities = ("osc",) if osc else ()
    return Entity(
        id=None,
        name=name,
        rfc=None,
        legal_personality="persona_moral",
        legal_form="A.C." if osc else "S.A. de C.V.",
        profile=EntityProfile(
            economic_purpose="no_lucrativo" if osc else "lucrativo",
            is_donor_authorized=False,
            special_capabilities=capabilities,
            modules_enabled=("banking",),
        ),
        is_active=active,
    )


def _program(
    entity_id,
    *,
    name="Educación Comunitaria",
    description="Programa anual de educación",
    budget=Decimal("125000.2300"),
):
    from aqorath.program import Program

    return Program(
        id=None,
        entity_id=entity_id,
        name=name,
        description=description,
        budget=budget,
    )


def _fresh_db(tmp_path, filename="program.db"):
    from aqorath.migrations import migrate_database

    db_path = tmp_path / filename
    result = migrate_database(str(db_path))
    assert result["to_version"] == 4
    return db_path, create_engine(f"sqlite:///{db_path}")


def _create_entity(session, *, osc=True, active=True, name="Meriadock A.C."):
    from aqorath.entity_repository import create_entity

    return create_entity(
        session,
        _entity(osc=osc, active=active, name=name),
    )


def test_program_domain_is_pure_frozen_and_exactly_osc_management_structure_not_accounting_truth():
    import aqorath.program as domain
    from aqorath.program import Program

    program = Program(
        id=None,
        entity_id=7,
        name="Salud Comunitaria",
        description=None,
        budget=Decimal("0.00"),
    )

    assert tuple(field.name for field in fields(Program)) == PROGRAM_FIELDS
    with pytest.raises(FrozenInstanceError):
        program.name = "changed"

    forbidden = {
        "account_id",
        "account_code",
        "debit",
        "credit",
        "journal_entry_id",
        "journal_line_id",
        "dimension_id",
        "dimension_value_id",
        "donation_id",
        "fiscal_profile_id",
        "fiscal_rule_set_id",
    }
    assert forbidden.isdisjoint(PROGRAM_FIELDS)

    source = inspect.getsource(domain).lower()
    for forbidden_source in (
        "sqlmodel",
        "sqlalchemy",
        "sqlite3",
        "journalentry",
        "journalline",
        "analyticaldimension",
        "donation",
    ):
        assert forbidden_source not in source


def test_program_domain_validates_identity_text_and_optional_exact_decimal_budget_fail_closed():
    from aqorath.program import Program

    exact = Decimal("123456.7800")
    program = Program(
        id=9,
        entity_id=1,
        name="Programa Especial",
        description="Descripción explícita",
        budget=exact,
    )
    assert program.budget is exact
    assert program.name == "Programa Especial"

    for patch in (
        {"id": 0},
        {"id": True},
        {"entity_id": 0},
        {"entity_id": True},
        {"name": ""},
        {"name": " Programa"},
        {"name": "Programa "},
        {"description": ""},
        {"description": " descripción"},
        {"description": "descripción "},
        {"budget": -Decimal("0.01")},
        {"budget": Decimal("NaN")},
        {"budget": Decimal("Infinity")},
        {"budget": 100},
        {"budget": 100.0},
    ):
        values = dict(
            id=None,
            entity_id=1,
            name="Programa",
            description=None,
            budget=None,
        )
        values.update(patch)
        with pytest.raises((TypeError, ValueError)):
            Program(**values)

    assert Program(None, 1, "Sin presupuesto", None, None).budget is None
    assert Program(None, 1, "Presupuesto cero", None, Decimal("0.000")).budget == Decimal("0.000")


def test_program_identity_does_not_embed_entity_mode_or_duplicate_analytical_dimension_identity():
    from aqorath.program import Program

    program = Program(
        id=None,
        entity_id=1,
        name="Educación",
        description=None,
        budget=None,
    )

    for forbidden in (
        "osc_mode",
        "commercial_mode",
        "special_capabilities",
        "modules_enabled",
        "dimension_id",
        "dimension_value_id",
        "dimension_key",
        "value_code",
    ):
        assert not hasattr(program, forbidden)


def test_program_repository_public_contracts_are_minimal_exact_and_non_destructive():
    import aqorath.program_repository as repository

    assert str(inspect.signature(repository.create_program)) == "(session, program)"
    assert str(inspect.signature(repository.get_program)) == "(session, entity_id, program_id)"
    assert str(inspect.signature(repository.list_programs)) == "(session, entity_id)"

    for forbidden in (
        "delete_program",
        "post_program",
        "create_account",
        "assign_analytical_dimension_value",
        "create_donation",
    ):
        assert not hasattr(repository, forbidden)


def test_frozen_v4_additively_creates_exact_program_schema_with_entity_fk_and_text_decimal(tmp_path):
    from aqorath.migrations import CURRENT_SCHEMA_VERSION
    from aqorath.models import ProgramRecord

    assert CURRENT_SCHEMA_VERSION == 4
    assert ProgramRecord.__tablename__ == "program"

    db_path, engine = _fresh_db(tmp_path, "schema.db")
    engine.dispose()
    conn = sqlite3.connect(str(db_path))
    try:
        columns = {row[1]: row for row in conn.execute("PRAGMA table_info(program)")}
        assert set(columns) == {
            "id",
            "entity_id",
            "name",
            "description",
            "budget",
            "created_at",
        }
        for required in ("entity_id", "name", "created_at"):
            assert columns[required][3] == 1, required
        for optional in ("description", "budget"):
            assert columns[optional][3] == 0, optional
        assert "TEXT" in columns["budget"][2].upper()

        fks = conn.execute("PRAGMA foreign_key_list(program)").fetchall()
        assert any(
            row[2] == "entity" and row[3] == "entity_id" and row[4] == "id"
            for row in fks
        )
    finally:
        conn.close()


def test_current_v4_additive_ensure_adds_program_without_rewriting_existing_truth(tmp_path):
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
        assert conn.execute(
            "SELECT value FROM preserved_truth WHERE id=1"
        ).fetchone() == ("keep-me",)
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert {"entity", "program"}.issubset(tables)
    finally:
        conn.close()


def test_create_program_round_trip_preserves_optional_values_and_exact_decimal_scale(tmp_path):
    from aqorath.models import ProgramRecord
    from aqorath.program import Program
    from aqorath.program_repository import create_program, get_program

    db_path, engine = _fresh_db(tmp_path, "round-trip.db")
    try:
        with Session(engine) as session:
            entity = _create_entity(session)
            source = _program(entity.id, budget=Decimal("125000.2300"))
            created = create_program(session, source)

            assert isinstance(created, Program)
            assert created.id is not None
            assert source.id is None
            assert created.entity_id == entity.id
            assert created.budget == Decimal("125000.2300")
            assert created.budget.as_tuple() == Decimal("125000.2300").as_tuple()
            assert get_program(session, entity.id, created.id) == created

            record = session.exec(select(ProgramRecord)).one()
            assert record.budget == "125000.2300"

        conn = sqlite3.connect(str(db_path))
        try:
            assert conn.execute("SELECT budget FROM program").fetchone() == (
                "125000.2300",
            )
        finally:
            conn.close()
    finally:
        engine.dispose()


def test_create_program_accepts_none_budget_and_description_without_inventing_defaults(tmp_path):
    from aqorath.program_repository import create_program

    _, engine = _fresh_db(tmp_path, "nullable.db")
    try:
        with Session(engine) as session:
            entity = _create_entity(session)
            created = create_program(
                session,
                _program(entity.id, description=None, budget=None),
            )
            assert created.description is None
            assert created.budget is None
    finally:
        engine.dispose()


def test_create_program_requires_nominal_new_program_and_explicit_existing_active_osc_owner(tmp_path):
    from dataclasses import replace
    from aqorath.program_repository import create_program

    _, engine = _fresh_db(tmp_path, "owner.db")
    try:
        with Session(engine) as session:
            entity = _create_entity(session)

            with pytest.raises(TypeError):
                create_program(session, object())
            with pytest.raises(ValueError):
                create_program(session, replace(_program(entity.id), id=99))
            with pytest.raises(LookupError):
                create_program(session, _program(entity.id + 999))
    finally:
        engine.dispose()

    _, nonosc_engine = _fresh_db(tmp_path, "nonosc.db")
    try:
        with Session(nonosc_engine) as session:
            nonosc = _create_entity(session, osc=False, name="Comercial Uno S.A. de C.V.")
            with pytest.raises(ValueError, match="osc"):
                create_program(session, _program(nonosc.id))
    finally:
        nonosc_engine.dispose()

    _, inactive_engine = _fresh_db(tmp_path, "inactive.db")
    try:
        with Session(inactive_engine) as session:
            inactive = _create_entity(
                session,
                active=False,
                name="OSC Histórica A.C.",
            )
            with pytest.raises(ValueError, match="active"):
                create_program(session, _program(inactive.id))
    finally:
        inactive_engine.dispose()


def test_create_program_rolls_back_when_single_commit_fails(tmp_path, monkeypatch):
    from aqorath.models import ProgramRecord
    from aqorath.program_repository import create_program

    _, engine = _fresh_db(tmp_path, "rollback.db")
    try:
        with Session(engine) as session:
            entity = _create_entity(session)

            def fail_commit():
                raise RuntimeError("commit failed")

            monkeypatch.setattr(session, "commit", fail_commit)
            with pytest.raises(RuntimeError, match="commit failed"):
                create_program(session, _program(entity.id))
            assert session.exec(select(ProgramRecord)).all() == []
    finally:
        engine.dispose()


def test_get_program_is_entity_scoped_and_fails_closed_for_missing_or_invalid_identity(tmp_path):
    from aqorath.program_repository import create_program, get_program

    _, engine = _fresh_db(tmp_path, "scoped-read.db")
    try:
        with Session(engine) as session:
            entity = _create_entity(session)
            program = create_program(session, _program(entity.id))
            assert get_program(session, entity.id, program.id) == program

            with pytest.raises(LookupError):
                get_program(session, entity.id + 1, program.id)
            with pytest.raises(LookupError):
                get_program(session, entity.id, program.id + 999)

            for bad in (0, True, "1"):
                with pytest.raises((TypeError, ValueError)):
                    get_program(session, bad, program.id)
                with pytest.raises((TypeError, ValueError)):
                    get_program(session, entity.id, bad)
    finally:
        engine.dispose()


def test_list_programs_is_entity_scoped_deterministic_tuple_ordered_by_identity(tmp_path):
    from aqorath.program_repository import create_program, list_programs

    _, engine = _fresh_db(tmp_path, "list.db")
    try:
        with Session(engine) as session:
            entity = _create_entity(session)
            one = create_program(session, _program(entity.id, name="Uno"))
            two = create_program(session, _program(entity.id, name="Dos"))
            three = create_program(session, _program(entity.id, name="Tres"))

            listed = list_programs(session, entity.id)
            assert isinstance(listed, tuple)
            assert [item.id for item in listed] == [one.id, two.id, three.id]

            for bad in (0, True, "1"):
                with pytest.raises((TypeError, ValueError)):
                    list_programs(session, bad)
    finally:
        engine.dispose()


def test_program_repository_uses_supplied_session_and_never_resolves_hidden_storage_session(tmp_path, monkeypatch):
    import aqorath.storage as storage
    from aqorath.program_repository import create_program, list_programs

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
            created = create_program(session, _program(entity.id))
            assert list_programs(session, entity.id) == (created,)
    finally:
        engine.dispose()


def test_program_persistence_does_not_create_accounting_analytical_donation_or_fiscal_truth(tmp_path):
    from aqorath.models import (
        Account,
        AnalyticalDimensionRecord,
        AnalyticalDimensionValueRecord,
        FiscalProfileRecord,
        FiscalRuleVersion,
        JournalEntry,
        JournalLine,
    )
    from aqorath.program_repository import create_program

    _, engine = _fresh_db(tmp_path, "no-parallel-truth.db")
    try:
        with Session(engine) as session:
            entity = _create_entity(session)
            create_program(session, _program(entity.id))

            assert session.exec(select(Account)).all() == []
            assert session.exec(select(JournalEntry)).all() == []
            assert session.exec(select(JournalLine)).all() == []
            assert session.exec(select(AnalyticalDimensionRecord)).all() == []
            assert session.exec(select(AnalyticalDimensionValueRecord)).all() == []
            assert session.exec(select(FiscalProfileRecord)).all() == []
            assert session.exec(select(FiscalRuleVersion)).all() == []
    finally:
        engine.dispose()


def test_program_foundation_is_deterministic_and_contains_no_time_or_external_generation_authority():
    import aqorath.program as domain
    import aqorath.program_repository as repository

    source = (inspect.getsource(domain) + inspect.getsource(repository)).lower()
    for forbidden in (
        "datetime.now",
        "datetime.utcnow",
        "time.time",
        "random",
        "requests",
        "openai",
        "llm",
        "render",
        "generate_report",
    ):
        assert forbidden not in source


def test_application_exposes_exact_thin_program_foundation_delegations(monkeypatch):
    import aqorath.application as application

    assert str(inspect.signature(application.create_program)) == "(session, program)"
    assert str(inspect.signature(application.get_program)) == "(session, entity_id, program_id)"
    assert str(inspect.signature(application.list_programs)) == "(session, entity_id)"
    assert not hasattr(application, "delete_program")

    calls = []
    session = object()
    sent = object()
    created = object()
    loaded = object()
    listed = object()

    monkeypatch.setattr(
        application._program_repository,
        "create_program",
        lambda s, p: calls.append(("create", s, p)) or created,
    )
    monkeypatch.setattr(
        application._program_repository,
        "get_program",
        lambda s, entity_id, program_id: calls.append(
            ("get", s, entity_id, program_id)
        ) or loaded,
    )
    monkeypatch.setattr(
        application._program_repository,
        "list_programs",
        lambda s, entity_id: calls.append(("list", s, entity_id)) or listed,
    )

    assert application.create_program(session, sent) is created
    assert application.get_program(session, 7, 8) is loaded
    assert application.list_programs(session, 7) is listed
    assert calls == [
        ("create", session, sent),
        ("get", session, 7, 8),
        ("list", session, 7),
    ]

    create_source = inspect.getsource(application.create_program).lower()
    get_source = inspect.getsource(application.get_program).lower()
    list_source = inspect.getsource(application.list_programs).lower()
    assert "_program_repository.create_program" in create_source
    assert "_program_repository.get_program" in get_source
    assert "_program_repository.list_programs" in list_source
    for source in (create_source, get_source, list_source):
        for forbidden in (
            "storage",
            "get_session",
            "journalentry",
            "analyticaldimension",
            "donation",
            "report",
        ):
            assert forbidden not in source
