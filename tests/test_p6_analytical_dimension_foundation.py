"""Phase 6E.1 — AnalyticalDimension / OSC foundation contracts.

Contracts only. Analytical dimensions enrich existing JournalLine truth for reporting and
OSC traceability. They never create parallel accounting, duplicate debit/credit truth,
select accounts, or mutate an existing journal entry.
"""

from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timezone
import inspect
import sqlite3

import pytest
from sqlalchemy import create_engine
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
            modules_enabled=("banking",),
        ),
        is_active=True,
    )


def _fresh_db(tmp_path, filename="analytics.db"):
    from aqorath.migrations import migrate_database

    db_path = tmp_path / filename
    result = migrate_database(str(db_path))
    assert result["to_version"] == 5
    return db_path, create_engine(f"sqlite:///{db_path}")


def _create_entity(session):
    from aqorath.entity_repository import create_entity

    return create_entity(session, _entity())


def _dimension(entity_id, *, key="program", name="Programa"):
    from aqorath.analytical_dimension import AnalyticalDimension

    return AnalyticalDimension(
        id=None,
        entity_id=entity_id,
        key=key,
        name=name,
    )


def _dimension_value(dimension_id, *, code="education", name="Educación"):
    from aqorath.analytical_dimension import AnalyticalDimensionValue

    return AnalyticalDimensionValue(
        id=None,
        dimension_id=dimension_id,
        code=code,
        name=name,
    )


def _create_line(session):
    from aqorath.models import Account, JournalEntry, JournalLine

    debit_account = session.exec(select(Account).where(Account.code == "1101")).first()
    if debit_account is None:
        debit_account = Account(code="1101", name="Banco", nature="DEBIT")
        session.add(debit_account)
    credit_account = session.exec(select(Account).where(Account.code == "4201")).first()
    if credit_account is None:
        credit_account = Account(code="4201", name="Ingreso", nature="CREDIT")
        session.add(credit_account)
    session.flush()

    entry = JournalEntry(
        date=datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc),
        concept="Operación con dimensiones analíticas",
        state="posted",
    )
    session.add(entry)
    session.flush()
    line = JournalLine(
        entry_id=entry.id,
        account_code=debit_account.code,
        account_id=debit_account.id,
        debit="100.00",
        credit="0",
        description="Banco",
    )
    counterline = JournalLine(
        entry_id=entry.id,
        account_code=credit_account.code,
        account_id=credit_account.id,
        debit="0",
        credit="100.00",
        description="Ingreso",
    )
    session.add(line)
    session.add(counterline)
    session.commit()
    session.refresh(line)
    return entry, line


def test_analytical_dimension_domain_is_pure_frozen_metadata_not_accounting_truth():
    import aqorath.analytical_dimension as domain
    from aqorath.analytical_dimension import (
        AnalyticalDimension,
        AnalyticalDimensionAssignment,
        AnalyticalDimensionValue,
    )

    dimension = AnalyticalDimension(
        id=None,
        entity_id=1,
        key="program",
        name="Programa",
    )
    value = AnalyticalDimensionValue(
        id=None,
        dimension_id=2,
        code="education",
        name="Educación",
    )
    assignment = AnalyticalDimensionAssignment(
        journal_line_id=3,
        dimension_id=2,
        dimension_key="program",
        dimension_name="Programa",
        value_id=4,
        value_code="education",
        value_name="Educación",
    )

    assert [field.name for field in fields(AnalyticalDimension)] == [
        "id",
        "entity_id",
        "key",
        "name",
    ]
    assert [field.name for field in fields(AnalyticalDimensionValue)] == [
        "id",
        "dimension_id",
        "code",
        "name",
    ]
    assert [field.name for field in fields(AnalyticalDimensionAssignment)] == [
        "journal_line_id",
        "dimension_id",
        "dimension_key",
        "dimension_name",
        "value_id",
        "value_code",
        "value_name",
    ]

    with pytest.raises(FrozenInstanceError):
        dimension.name = "Otro"
    with pytest.raises(FrozenInstanceError):
        value.name = "Otro"
    with pytest.raises(FrozenInstanceError):
        assignment.value_name = "Otro"

    forbidden = {
        "account_id",
        "account_code",
        "debit",
        "credit",
        "amount",
        "entry_id",
        "fiscal_rule_set_id",
        "cfdi_uuid",
    }
    for cls in (AnalyticalDimension, AnalyticalDimensionValue, AnalyticalDimensionAssignment):
        assert forbidden.isdisjoint({field.name for field in fields(cls)})

    source = inspect.getsource(domain).lower()
    assert "sqlmodel" not in source
    assert "sqlalchemy" not in source
    assert "decimal" not in source


def test_analytical_dimension_domain_validates_ids_and_text_fail_closed_without_normalization():
    from aqorath.analytical_dimension import (
        AnalyticalDimension,
        AnalyticalDimensionAssignment,
        AnalyticalDimensionValue,
    )

    dimension = AnalyticalDimension(
        id=9,
        entity_id=1,
        key="Program.Custom",
        name="Programa Especial",
    )
    assert dimension.key == "Program.Custom"
    assert dimension.name == "Programa Especial"

    value = AnalyticalDimensionValue(
        id=8,
        dimension_id=9,
        code="EDU-2026",
        name="Educación 2026",
    )
    assert value.code == "EDU-2026"

    for patch in (
        {"id": 0},
        {"id": True},
        {"entity_id": 0},
        {"entity_id": True},
        {"key": ""},
        {"key": "   "},
        {"name": ""},
        {"name": "   "},
    ):
        with pytest.raises((TypeError, ValueError)):
            AnalyticalDimension(**{
                "id": None,
                "entity_id": 1,
                "key": "program",
                "name": "Programa",
                **patch,
            })

    for patch in (
        {"id": 0},
        {"dimension_id": 0},
        {"dimension_id": False},
        {"code": ""},
        {"code": "   "},
        {"name": ""},
    ):
        with pytest.raises((TypeError, ValueError)):
            AnalyticalDimensionValue(**{
                "id": None,
                "dimension_id": 1,
                "code": "education",
                "name": "Educación",
                **patch,
            })

    baseline_assignment = dict(
        journal_line_id=1,
        dimension_id=2,
        dimension_key="program",
        dimension_name="Programa",
        value_id=3,
        value_code="education",
        value_name="Educación",
    )
    for patch in (
        {"journal_line_id": 0},
        {"journal_line_id": True},
        {"dimension_id": 0},
        {"value_id": 0},
        {"dimension_key": ""},
        {"dimension_name": "   "},
        {"value_code": ""},
        {"value_name": ""},
    ):
        with pytest.raises((TypeError, ValueError)):
            AnalyticalDimensionAssignment(**{**baseline_assignment, **patch})


def test_dimension_keys_are_explicit_extensible_and_osc_is_not_a_parallel_mode():
    from aqorath.analytical_dimension import AnalyticalDimension

    keys = ("program", "project", "fund", "resource_source", "cost_center", "custom_axis")
    built = tuple(
        AnalyticalDimension(id=None, entity_id=1, key=key, name=f"Dim {key}")
        for key in keys
    )
    assert tuple(item.key for item in built) == keys

    import aqorath.analytical_dimension as domain

    source = inspect.getsource(domain).lower()
    for forbidden in (
        "commercial_mode",
        "osc_mode",
        "modo_osc",
        "journalentry(",
        "journalline(",
        "account(",
    ):
        assert forbidden not in source


def test_analytical_dimension_repository_public_contracts_are_minimal_exact_and_non_destructive():
    import aqorath.analytical_dimension_repository as repository

    assert str(inspect.signature(repository.create_analytical_dimension)) == (
        "(session, dimension)"
    )
    assert str(inspect.signature(repository.get_analytical_dimension)) == (
        "(session, entity_id, dimension_id)"
    )
    assert str(inspect.signature(repository.list_analytical_dimensions)) == (
        "(session, entity_id)"
    )
    assert str(inspect.signature(repository.create_analytical_dimension_value)) == (
        "(session, dimension_value)"
    )
    assert str(inspect.signature(repository.list_analytical_dimension_values)) == (
        "(session, dimension_id)"
    )
    assert str(inspect.signature(repository.assign_analytical_dimension_value)) == (
        "(session, journal_line_id, dimension_value_id)"
    )
    assert str(inspect.signature(repository.list_journal_line_analytics)) == (
        "(session, journal_line_id)"
    )
    for forbidden in (
        "delete_analytical_dimension",
        "delete_analytical_dimension_value",
        "delete_journal_line_analytics",
        "post_entry",
        "create_account",
        "calculate_tax",
    ):
        assert not hasattr(repository, forbidden)


def test_frozen_v4_additively_creates_normalized_analytical_schema_and_constraints(tmp_path):
    from aqorath.migrations import CURRENT_SCHEMA_VERSION
    from aqorath.models import (
        AnalyticalDimensionRecord,
        AnalyticalDimensionValueRecord,
        JournalLineAnalyticalDimensionRecord,
    )

    assert CURRENT_SCHEMA_VERSION == 5
    assert AnalyticalDimensionRecord.__tablename__ == "analyticaldimension"
    assert AnalyticalDimensionValueRecord.__tablename__ == "analyticaldimensionvalue"
    assert JournalLineAnalyticalDimensionRecord.__tablename__ == (
        "journallineanalyticaldimension"
    )

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
        assert {
            "analyticaldimension",
            "analyticaldimensionvalue",
            "journallineanalyticaldimension",
        }.issubset(tables)

        dimension_columns = {
            row[1]: row
            for row in conn.execute("PRAGMA table_info(analyticaldimension)")
        }
        assert set(dimension_columns) == {"id", "entity_id", "key", "name", "created_at"}
        for required in ("entity_id", "key", "name", "created_at"):
            assert dimension_columns[required][3] == 1, required

        value_columns = {
            row[1]: row
            for row in conn.execute("PRAGMA table_info(analyticaldimensionvalue)")
        }
        assert set(value_columns) == {
            "id",
            "dimension_id",
            "code",
            "name",
            "created_at",
        }
        for required in ("dimension_id", "code", "name", "created_at"):
            assert value_columns[required][3] == 1, required

        assignment_columns = {
            row[1]: row
            for row in conn.execute(
                "PRAGMA table_info(journallineanalyticaldimension)"
            )
        }
        assert set(assignment_columns) == {
            "id",
            "journal_line_id",
            "dimension_id",
            "dimension_value_id",
            "created_at",
        }
        for required in (
            "journal_line_id",
            "dimension_id",
            "dimension_value_id",
            "created_at",
        ):
            assert assignment_columns[required][3] == 1, required

        dimension_fks = conn.execute(
            "PRAGMA foreign_key_list(analyticaldimension)"
        ).fetchall()
        assert any(
            row[2] == "entity" and row[3] == "entity_id" and row[4] == "id"
            for row in dimension_fks
        )

        value_fks = conn.execute(
            "PRAGMA foreign_key_list(analyticaldimensionvalue)"
        ).fetchall()
        assert any(
            row[2] == "analyticaldimension"
            and row[3] == "dimension_id"
            and row[4] == "id"
            for row in value_fks
        )

        assignment_fks = conn.execute(
            "PRAGMA foreign_key_list(journallineanalyticaldimension)"
        ).fetchall()
        assert any(
            row[2] == "journalline"
            and row[3] == "journal_line_id"
            and row[4] == "id"
            for row in assignment_fks
        )
        assert any(
            row[2] == "analyticaldimension"
            and row[3] == "dimension_id"
            and row[4] == "id"
            for row in assignment_fks
        )
        assert any(
            row[2] == "analyticaldimensionvalue"
            and row[3] == "dimension_value_id"
            and row[4] == "id"
            for row in assignment_fks
        )

        def unique_sets(table):
            indexes = [
                row
                for row in conn.execute(f"PRAGMA index_list({table})").fetchall()
                if row[2] == 1
            ]
            return {
                tuple(
                    col[2]
                    for col in conn.execute(
                        f"PRAGMA index_info({row[1]})"
                    ).fetchall()
                )
                for row in indexes
            }

        assert ("entity_id", "key") in unique_sets("analyticaldimension")
        assert ("dimension_id", "code") in unique_sets("analyticaldimensionvalue")
        assert ("journal_line_id", "dimension_id") in unique_sets(
            "journallineanalyticaldimension"
        )
    finally:
        conn.close()


def test_current_v4_additive_ensure_adds_analytics_without_rewriting_existing_truth(tmp_path):
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
        "to_version": 5,
        "migrated": True,
        "backup_path": result["backup_path"],
    }
    assert __import__("pathlib").Path(result["backup_path"]).is_file()
    assert get_schema_version(str(db_path)) == 5

    conn = sqlite3.connect(str(db_path))
    try:
        assert conn.execute(
            "SELECT value FROM preserved_truth WHERE id=1"
        ).fetchone() == ("keep-me",)
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {
            "analyticaldimension",
            "analyticaldimensionvalue",
            "journallineanalyticaldimension",
        }.issubset(tables)
    finally:
        conn.close()


def test_create_dimension_round_trip_requires_explicit_existing_active_entity_and_unique_key(tmp_path):
    from aqorath.analytical_dimension import AnalyticalDimension
    from aqorath.analytical_dimension_repository import (
        create_analytical_dimension,
        get_analytical_dimension,
        list_analytical_dimensions,
    )

    _, engine = _fresh_db(tmp_path, "dimensions.db")
    try:
        with Session(engine) as session:
            entity = _create_entity(session)
            program = create_analytical_dimension(
                session,
                _dimension(entity.id, key="program", name="Programa"),
            )
            fund = create_analytical_dimension(
                session,
                _dimension(entity.id, key="fund", name="Fondo"),
            )

            assert isinstance(program, AnalyticalDimension)
            assert program.id is not None
            assert program.entity_id == entity.id
            assert program.key == "program"
            assert get_analytical_dimension(session, entity.id, program.id) == program
            assert list_analytical_dimensions(session, entity.id) == (program, fund)

            with pytest.raises((ValueError, LookupError)):
                create_analytical_dimension(
                    session,
                    _dimension(entity.id, key="program", name="Programa duplicado"),
                )
            with pytest.raises(LookupError, match="Entity"):
                create_analytical_dimension(
                    session,
                    _dimension(entity.id + 999, key="project", name="Proyecto"),
                )
    finally:
        engine.dispose()


def test_dimension_value_round_trip_is_dimension_scoped_ordered_and_unique_by_code(tmp_path):
    from aqorath.analytical_dimension import AnalyticalDimensionValue
    from aqorath.analytical_dimension_repository import (
        create_analytical_dimension,
        create_analytical_dimension_value,
        list_analytical_dimension_values,
    )

    _, engine = _fresh_db(tmp_path, "values.db")
    try:
        with Session(engine) as session:
            entity = _create_entity(session)
            dimension = create_analytical_dimension(
                session,
                _dimension(entity.id),
            )
            education = create_analytical_dimension_value(
                session,
                _dimension_value(
                    dimension.id,
                    code="education",
                    name="Educación",
                ),
            )
            health = create_analytical_dimension_value(
                session,
                _dimension_value(
                    dimension.id,
                    code="health",
                    name="Salud",
                ),
            )

            assert isinstance(education, AnalyticalDimensionValue)
            assert education.id is not None
            assert list_analytical_dimension_values(session, dimension.id) == (
                education,
                health,
            )

            with pytest.raises((ValueError, LookupError)):
                create_analytical_dimension_value(
                    session,
                    _dimension_value(
                        dimension.id,
                        code="education",
                        name="Duplicado",
                    ),
                )
            with pytest.raises(LookupError, match="AnalyticalDimension"):
                create_analytical_dimension_value(
                    session,
                    _dimension_value(
                        dimension.id + 999,
                        code="x",
                        name="Inexistente",
                    ),
                )
    finally:
        engine.dispose()


def test_one_journal_line_accepts_multiple_distinct_dimensions_without_parallel_entries_or_lines(tmp_path):
    from aqorath.analytical_dimension_repository import (
        assign_analytical_dimension_value,
        create_analytical_dimension,
        create_analytical_dimension_value,
        list_journal_line_analytics,
    )
    from aqorath.models import JournalEntry, JournalLine

    _, engine = _fresh_db(tmp_path, "multi-dimension.db")
    try:
        with Session(engine) as session:
            entity = _create_entity(session)
            entry, line = _create_line(session)
            entries_before = len(session.exec(select(JournalEntry)).all())
            lines_before = len(session.exec(select(JournalLine)).all())

            program = create_analytical_dimension(
                session,
                _dimension(entity.id, key="program", name="Programa"),
            )
            fund = create_analytical_dimension(
                session,
                _dimension(entity.id, key="fund", name="Fondo"),
            )
            education = create_analytical_dimension_value(
                session,
                _dimension_value(program.id, code="education", name="Educación"),
            )
            restricted = create_analytical_dimension_value(
                session,
                _dimension_value(fund.id, code="restricted", name="Restringido"),
            )

            first = assign_analytical_dimension_value(
                session,
                line.id,
                education.id,
            )
            second = assign_analytical_dimension_value(
                session,
                line.id,
                restricted.id,
            )
            assert first.dimension_key == "program"
            assert first.value_code == "education"
            assert second.dimension_key == "fund"
            assert second.value_code == "restricted"
            assert list_journal_line_analytics(session, line.id) == (first, second)

            assert len(session.exec(select(JournalEntry)).all()) == entries_before
            assert len(session.exec(select(JournalLine)).all()) == lines_before
            persisted_line = session.get(JournalLine, line.id)
            assert persisted_line.entry_id == entry.id
            assert persisted_line.account_code == "1101"
            assert persisted_line.debit == "100.00"
            assert persisted_line.credit == "0"
    finally:
        engine.dispose()


def test_same_dimension_cannot_assign_two_values_to_same_line_or_silently_replace_first(tmp_path):
    from aqorath.analytical_dimension_repository import (
        assign_analytical_dimension_value,
        create_analytical_dimension,
        create_analytical_dimension_value,
        list_journal_line_analytics,
    )

    _, engine = _fresh_db(tmp_path, "one-value-per-dimension.db")
    try:
        with Session(engine) as session:
            entity = _create_entity(session)
            _, line = _create_line(session)
            program = create_analytical_dimension(
                session,
                _dimension(entity.id),
            )
            education = create_analytical_dimension_value(
                session,
                _dimension_value(program.id, code="education", name="Educación"),
            )
            health = create_analytical_dimension_value(
                session,
                _dimension_value(program.id, code="health", name="Salud"),
            )
            first = assign_analytical_dimension_value(session, line.id, education.id)

            with pytest.raises((ValueError, LookupError)):
                assign_analytical_dimension_value(session, line.id, health.id)

            assert list_journal_line_analytics(session, line.id) == (first,)
    finally:
        engine.dispose()


def test_assignment_requires_existing_line_and_value_and_never_guesses_dimension(tmp_path):
    from aqorath.analytical_dimension_repository import (
        assign_analytical_dimension_value,
        create_analytical_dimension,
        create_analytical_dimension_value,
    )

    _, engine = _fresh_db(tmp_path, "assignment-validation.db")
    try:
        with Session(engine) as session:
            entity = _create_entity(session)
            _, line = _create_line(session)
            dimension = create_analytical_dimension(
                session,
                _dimension(entity.id),
            )
            value = create_analytical_dimension_value(
                session,
                _dimension_value(dimension.id),
            )

            with pytest.raises(LookupError, match="JournalLine"):
                assign_analytical_dimension_value(
                    session,
                    line.id + 999,
                    value.id,
                )
            with pytest.raises(LookupError, match="AnalyticalDimensionValue"):
                assign_analytical_dimension_value(
                    session,
                    line.id,
                    value.id + 999,
                )
            for invalid_line, invalid_value in (
                (0, value.id),
                (True, value.id),
                (line.id, 0),
                (line.id, False),
            ):
                with pytest.raises((TypeError, ValueError)):
                    assign_analytical_dimension_value(
                        session,
                        invalid_line,
                        invalid_value,
                    )
    finally:
        engine.dispose()


def test_reads_fail_closed_are_scoped_and_deterministic(tmp_path):
    from aqorath.analytical_dimension_repository import (
        create_analytical_dimension,
        create_analytical_dimension_value,
        get_analytical_dimension,
        list_analytical_dimension_values,
        list_analytical_dimensions,
        list_journal_line_analytics,
    )

    _, engine = _fresh_db(tmp_path, "reads.db")
    try:
        with Session(engine) as session:
            entity = _create_entity(session)
            dimension = create_analytical_dimension(
                session,
                _dimension(entity.id),
            )
            create_analytical_dimension_value(
                session,
                _dimension_value(dimension.id),
            )
            _, line = _create_line(session)

            with pytest.raises(LookupError, match="AnalyticalDimension"):
                get_analytical_dimension(session, entity.id, dimension.id + 999)
            with pytest.raises(LookupError, match="Entity"):
                list_analytical_dimensions(session, entity.id + 999)
            with pytest.raises(LookupError, match="AnalyticalDimension"):
                list_analytical_dimension_values(session, dimension.id + 999)
            with pytest.raises(LookupError, match="JournalLine"):
                list_journal_line_analytics(session, line.id + 999)

            assert list_journal_line_analytics(session, line.id) == ()
    finally:
        engine.dispose()


def test_dimension_and_assignment_writes_roll_back_on_single_commit_failure(tmp_path, monkeypatch):
    from aqorath.analytical_dimension_repository import (
        assign_analytical_dimension_value,
        create_analytical_dimension,
        create_analytical_dimension_value,
    )
    from aqorath.models import (
        AnalyticalDimensionRecord,
        JournalLineAnalyticalDimensionRecord,
    )

    _, engine = _fresh_db(tmp_path, "rollback.db")
    try:
        with Session(engine) as session:
            entity = _create_entity(session)

            real_commit = session.commit

            def fail_commit():
                raise RuntimeError("commit failed")

            monkeypatch.setattr(session, "commit", fail_commit)
            with pytest.raises(RuntimeError, match="commit failed"):
                create_analytical_dimension(session, _dimension(entity.id))
            assert session.exec(select(AnalyticalDimensionRecord)).all() == []

            monkeypatch.setattr(session, "commit", real_commit)
            dimension = create_analytical_dimension(session, _dimension(entity.id))
            value = create_analytical_dimension_value(
                session,
                _dimension_value(dimension.id),
            )
            _, line = _create_line(session)

            monkeypatch.setattr(session, "commit", fail_commit)
            with pytest.raises(RuntimeError, match="commit failed"):
                assign_analytical_dimension_value(session, line.id, value.id)
            assert session.exec(select(JournalLineAnalyticalDimensionRecord)).all() == []
    finally:
        engine.dispose()


def test_analytics_repository_uses_only_supplied_session_and_never_becomes_accounting_reporting_or_osc_engine():
    import aqorath.analytical_dimension_repository as repository

    source = inspect.getsource(repository).lower()
    for forbidden in (
        "create_engine",
        "sessionlocal",
        "get_db_path",
        "sqlite3",
        "core.",
        "post_entry",
        "trial_balance",
        "reporting",
        "economic_facts",
        "fiscal_",
        "cfdi",
        "assets",
        "exercise",
        "pandas",
        "open(",
    ):
        assert forbidden not in source


def test_analytics_schema_does_not_duplicate_accounting_money_or_create_dimension_columns_on_journal_line():
    from aqorath.models import (
        AnalyticalDimensionRecord,
        AnalyticalDimensionValueRecord,
        JournalLine,
        JournalLineAnalyticalDimensionRecord,
    )

    assert {"debit", "credit", "account_code", "account_id"}.isdisjoint(
        AnalyticalDimensionRecord.model_fields
    )
    assert {"debit", "credit", "amount", "account_id"}.isdisjoint(
        AnalyticalDimensionValueRecord.model_fields
    )
    assert {"debit", "credit", "amount", "account_code", "account_id"}.isdisjoint(
        JournalLineAnalyticalDimensionRecord.model_fields
    )
    assert {
        "program_id",
        "project_id",
        "fund_id",
        "resource_source_id",
        "cost_center_id",
        "analytics_json",
    }.isdisjoint(JournalLine.model_fields)


def test_application_exposes_analytics_foundation_with_exact_signatures_and_delegates_only_to_repository(monkeypatch):
    from aqorath import application

    assert str(inspect.signature(application.create_analytical_dimension)) == (
        "(session, dimension)"
    )
    assert str(inspect.signature(application.get_analytical_dimension)) == (
        "(session, entity_id, dimension_id)"
    )
    assert str(inspect.signature(application.list_analytical_dimensions)) == (
        "(session, entity_id)"
    )
    assert str(inspect.signature(application.create_analytical_dimension_value)) == (
        "(session, dimension_value)"
    )
    assert str(inspect.signature(application.list_analytical_dimension_values)) == (
        "(session, dimension_id)"
    )
    assert str(inspect.signature(application.assign_analytical_dimension_value)) == (
        "(session, journal_line_id, dimension_value_id)"
    )
    assert str(inspect.signature(application.list_journal_line_analytics)) == (
        "(session, journal_line_id)"
    )

    calls = []

    monkeypatch.setattr(
        application._analytical_dimension_repository,
        "create_analytical_dimension",
        lambda *args: calls.append(("create_dimension", args)) or "d",
    )
    monkeypatch.setattr(
        application._analytical_dimension_repository,
        "get_analytical_dimension",
        lambda *args: calls.append(("get_dimension", args)) or "g",
    )
    monkeypatch.setattr(
        application._analytical_dimension_repository,
        "list_analytical_dimensions",
        lambda *args: calls.append(("list_dimensions", args)) or ("d1",),
    )
    monkeypatch.setattr(
        application._analytical_dimension_repository,
        "create_analytical_dimension_value",
        lambda *args: calls.append(("create_value", args)) or "v",
    )
    monkeypatch.setattr(
        application._analytical_dimension_repository,
        "list_analytical_dimension_values",
        lambda *args: calls.append(("list_values", args)) or ("v1",),
    )
    monkeypatch.setattr(
        application._analytical_dimension_repository,
        "assign_analytical_dimension_value",
        lambda *args: calls.append(("assign", args)) or "a",
    )
    monkeypatch.setattr(
        application._analytical_dimension_repository,
        "list_journal_line_analytics",
        lambda *args: calls.append(("list_line", args)) or ("a1",),
    )

    session = object()
    dimension = object()
    value = object()

    assert application.create_analytical_dimension(session, dimension) == "d"
    assert application.get_analytical_dimension(session, 1, 2) == "g"
    assert application.list_analytical_dimensions(session, 1) == ("d1",)
    assert application.create_analytical_dimension_value(session, value) == "v"
    assert application.list_analytical_dimension_values(session, 2) == ("v1",)
    assert application.assign_analytical_dimension_value(session, 3, 4) == "a"
    assert application.list_journal_line_analytics(session, 3) == ("a1",)

    assert calls == [
        ("create_dimension", (session, dimension)),
        ("get_dimension", (session, 1, 2)),
        ("list_dimensions", (session, 1)),
        ("create_value", (session, value)),
        ("list_values", (session, 2)),
        ("assign", (session, 3, 4)),
        ("list_line", (session, 3)),
    ]

    source = inspect.getsource(application.create_analytical_dimension)
    source += inspect.getsource(application.assign_analytical_dimension_value)
    for forbidden in ("JournalLine(", "Account(", "post_entry", "trial_balance"):
        assert forbidden not in source
