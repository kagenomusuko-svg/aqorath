"""
P1-1 REGRESSION TESTS: ORM must be able to persist without raw SQLite fallback.

P1-1: Persistencia mediante ORM compatible. NO fallback silencioso a sqlite directo.
P1-1: Atomicidad de póliza: JournalEntry + JournalLines = UNA transacción.
"""

import pytest
from decimal import Decimal
from datetime import datetime
from pathlib import Path
from sqlalchemy import create_engine
from sqlmodel import SQLModel, Session, select
import aqorath.core as core
from aqorath.models import Account, JournalEntry, JournalLine


def test_persist_entry_works_through_orm_without_raw_sqlite_fallback(tmp_path, monkeypatch):
    """
    P1-1: post_entry debe persistir mediante ORM sin depender de SQLite directo.

    ESTADO ACTUAL: EXPECTED FAIL
    - JournalEntry(description=...) falla: modelo usa 'concept' + 'date'
    - Intento de fallback SQLite directo
    - Sin fallback, la operación no persiste

    CONTRATO FUTURO:
    - JournalEntry y JournalLine creados correctamente
    - Verificables mediante ORM
    """
    # Setup temporary database (aislado del engine global en conftest)
    db_file = tmp_path / "orm_test.db"
    db_url = f"sqlite:///{db_file}"
    engine = create_engine(db_url, echo=False)
    SQLModel.metadata.create_all(engine)
    from period_fixtures import seed_engine_calendar
    seed_engine_calendar(engine)

    # Create canonical accounts via ORM and store their IDs
    with Session(engine) as session:
        acc_1101 = Account(code="1101", name="Bancos", nature="DEBIT")
        acc_4101 = Account(code="4101", name="Ventas", nature="CREDIT")
        session.add(acc_1101)
        session.add(acc_4101)
        session.commit()
        session.refresh(acc_1101)
        session.refresh(acc_4101)
        id_1101 = acc_1101.id
        id_4101 = acc_4101.id

    # Monkeypatch core.get_session to use isolated engine
    def isolated_get_session():
        return Session(engine)

    monkeypatch.setattr(core, "get_session", isolated_get_session)

    # Disable raw SQLite fallback
    monkeypatch.setattr(core, "_find_db_path", lambda: None)

    # Try to persist via ORM using account_id (not account_code) to isolate ORM persistence
    result = core.post_entry({
        "description": "Venta prueba ORM",
        "lines": [
            {
                "account_id": id_1101,
                "debit": Decimal("100"),
                "credit": Decimal("0")
            },
            {
                "account_id": id_4101,
                "debit": Decimal("0"),
                "credit": Decimal("100")
            }
        ]
    })

    # CURRENT STATE: This fails because of JournalEntry signature mismatch
    # Error should be about ORM/model incompatibility, NOT about account validation
    # FUTURE CONTRACT: Should succeed with correct ORM persistence
    assert isinstance(result, dict) and result.get("ok"), (
        f"P1-1 ORM persistence failed: {result}"
    )

    # Verify via ORM if it persisted
    with Session(engine) as session:
        entries = session.exec(select(JournalEntry)).all()
        assert len(entries) > 0, "No JournalEntry persisted"

        lines = session.exec(select(JournalLine)).all()
        assert len(lines) == 2, f"Expected 2 JournalLine, got {len(lines)}"

        # Verify entry structure
        entry = entries[0]
        assert entry.date is not None, "JournalEntry.date is None"
        assert entry.concept == "Venta prueba ORM", f"JournalEntry.concept mismatch: {entry.concept}"

        # Verify lines reference the entry
        for line in lines:
            assert line.entry_id == entry.id, "JournalLine.entry_id mismatch"


def test_orm_persistence_rolls_back_header_if_line_creation_fails(tmp_path, monkeypatch):
    """
    P1-1: Atomicidad de póliza.

    JournalEntry + JournalLines DEBEN ser UNA transacción.
    Si falla alguna línea, la cabecera debe ser rolled back.

    ESTADO ACTUAL: EXPECTED FAIL
    - add JournalEntry + commit
    - luego add JournalLines + commit
    - Si falla en JournalLine, la cabecera queda huérfana

    CONTRATO FUTURO:
    - add JournalEntry
    - add JournalLines
    - commit UNA SOLA VEZ
    - Si error: rollback TODO

    Estrategia: Usar cuentas válidas, forzar fallo en JournalLine, verificar atomicidad.
    """
    # Setup temporary database
    db_file = tmp_path / "atomicity_test.db"
    db_url = f"sqlite:///{db_file}"
    engine = create_engine(db_url, echo=False)
    SQLModel.metadata.create_all(engine)
    from period_fixtures import seed_engine_calendar
    seed_engine_calendar(engine)

    # Create accounts and get their IDs
    with Session(engine) as session:
        acc_1101 = Account(code="1101", name="Bancos", nature="DEBIT")
        acc_4101 = Account(code="4101", name="Ventas", nature="CREDIT")
        session.add(acc_1101)
        session.add(acc_4101)
        session.commit()
        session.refresh(acc_1101)
        session.refresh(acc_4101)
        id_1101 = acc_1101.id
        id_4101 = acc_4101.id

    # Monkeypatch to use isolated engine
    def isolated_get_session():
        return Session(engine)

    monkeypatch.setattr(core, "get_session", isolated_get_session)
    monkeypatch.setattr(core, "_find_db_path", lambda: None)

    # Neutralize JournalEntry description/date/concept mismatch artificially
    # to isolate the atomicity defect
    from datetime import datetime, timezone
    RealJournalEntry = core.JournalEntry

    def compatible_journal_entry(*args, **kwargs):
        if "description" in kwargs and "concept" not in kwargs:
            kwargs["concept"] = kwargs.pop("description")
        kwargs.setdefault("date", datetime.now(timezone.utc))
        return RealJournalEntry(*args, **kwargs)

    monkeypatch.setattr(core, "JournalEntry", compatible_journal_entry)

    # Force JournalLine creation to fail
    def failing_journal_line(*args, **kwargs):
        raise RuntimeError("Forced JournalLine creation failure")

    monkeypatch.setattr(core, "JournalLine", failing_journal_line)

    # Try to post with valid account_ids
    try:
        result = core.post_entry({
            "description": "Venta atomicity test",
            "lines": [
                {
                    "account_id": id_1101,
                    "debit": Decimal("100"),
                    "credit": Decimal("0")
                },
                {
                    "account_id": id_4101,
                    "debit": Decimal("0"),
                    "credit": Decimal("100")
                }
            ]
        })
    except Exception:
        pass

    # FUTURE CONTRACT: No orphaned entries (either 0 or complete entry+lines)
    # CURRENT STATE: May have orphaned JournalEntry without all JournalLines
    with Session(engine) as session:
        entries = session.exec(select(JournalEntry)).all()
        lines = session.exec(select(JournalLine)).all()

        # If atomicity is broken: entries > 0 but lines == 0
        # This demonstrates the P1-1 atomicity defect
        if len(entries) > 0 and len(lines) == 0:
            pytest.fail(
                f"P1-1 Atomicity broken: {len(entries)} JournalEntry (orphaned), {len(lines)} JournalLine"
            )
        elif len(entries) > 0 or len(lines) > 0:
            pytest.fail(
                f"P1-1 Atomicity broken: {len(entries)} JournalEntry, {len(lines)} JournalLine"
            )
