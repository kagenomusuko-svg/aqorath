"""Phase 6BP — persistence hardening after 6BO.2."""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlmodel import Session, select

from aqorath.ledger_invariants import LedgerInvariantError, validate_journal_lines


def _line(*, debit="0", credit="0", entry_id=1, account_id=1, account_code="1102"):
    return {
        "entry_id": entry_id,
        "account_id": account_id,
        "account_code": account_code,
        "debit": debit,
        "credit": credit,
    }


def _canonical_db(tmp_path, monkeypatch):
    import aqorath.storage as storage
    from aqorath.models import Account

    db = tmp_path / "p6bp-ledger-invariants.db"
    monkeypatch.setenv("AQORATH_DB", str(db))
    engine = storage.init_db(str(db), create_tables=True)
    from period_fixtures import seed_engine_calendar
    seed_engine_calendar(engine)

    with Session(engine) as session:
        accounts = (
            Account(code="1102", name="Caja chica", nature="DEBIT"),
            Account(code="4201", name="Venta de productos elaborados", nature="CREDIT"),
        )
        session.add_all(accounts)
        session.commit()
        for account in accounts:
            session.refresh(account)
        ids = tuple(account.id for account in accounts)

    return engine, ids


def _assert_ledger_empty(engine):
    from aqorath.models import JournalEntry, JournalLine

    with Session(engine) as session:
        assert session.exec(select(JournalEntry)).all() == []
        assert session.exec(select(JournalLine)).all() == []


def test_validator_accepts_exact_balanced_entry():
    assert validate_journal_lines(
        (
            _line(debit="100.00"),
            _line(credit="100.00", account_id=2, account_code="4201"),
        )
    ) is None


def test_validator_rejects_empty_unbalanced_and_invalid_money():
    with pytest.raises(LedgerInvariantError, match="at least one"):
        validate_journal_lines(())

    with pytest.raises(LedgerInvariantError, match="unbalanced"):
        validate_journal_lines(
            (
                _line(debit="100.00"),
                _line(credit="99.99", account_id=2, account_code="4201"),
            )
        )

    for debit, credit, message in (
        ("-1", "0", "non-negative"),
        ("1", "1", "exactly one"),
        ("0", "0", "exactly one"),
        ("NaN", "0", "finite"),
    ):
        with pytest.raises(LedgerInvariantError, match=message):
            validate_journal_lines(
                (
                    _line(debit=debit, credit=credit),
                    _line(credit="1", account_id=2, account_code="4201"),
                )
            )


def test_canonical_empty_journal_entry_cannot_commit(tmp_path, monkeypatch):
    from aqorath.models import JournalEntry

    engine, _ids = _canonical_db(tmp_path, monkeypatch)
    with Session(engine) as session:
        session.add(
            JournalEntry(
                date=datetime(2026, 9, 9, tzinfo=timezone.utc),
                concept="Empty entry must not become durable",
            )
        )
        with pytest.raises(LedgerInvariantError, match="at least one"):
            session.commit()
        session.rollback()

    _assert_ledger_empty(engine)


def test_direct_orm_unbalanced_entry_cannot_commit(tmp_path, monkeypatch):
    from aqorath.models import JournalEntry, JournalLine

    engine, ids = _canonical_db(tmp_path, monkeypatch)
    with Session(engine) as session:
        entry = JournalEntry(
            date=datetime(2026, 9, 9, tzinfo=timezone.utc),
            concept="Must roll back",
        )
        session.add(entry)
        session.flush()
        session.add_all(
            (
                JournalLine(
                    entry_id=entry.id,
                    account_id=ids[0],
                    account_code="1102",
                    debit="100.00",
                    credit="0",
                ),
                JournalLine(
                    entry_id=entry.id,
                    account_id=ids[1],
                    account_code="4201",
                    debit="0",
                    credit="99.00",
                ),
            )
        )
        with pytest.raises(LedgerInvariantError, match="unbalanced"):
            session.commit()
        session.rollback()

    _assert_ledger_empty(engine)


def test_direct_orm_account_identity_mismatch_cannot_commit(tmp_path, monkeypatch):
    from aqorath.models import JournalEntry, JournalLine

    engine, ids = _canonical_db(tmp_path, monkeypatch)
    with Session(engine) as session:
        entry = JournalEntry(
            date=datetime(2026, 9, 9, tzinfo=timezone.utc),
            concept="Identity mismatch",
        )
        session.add(entry)
        session.flush()
        session.add_all(
            (
                JournalLine(
                    entry_id=entry.id,
                    account_id=ids[0],
                    account_code="4201",
                    debit="10.00",
                    credit="0",
                ),
                JournalLine(
                    entry_id=entry.id,
                    account_id=ids[1],
                    account_code="4201",
                    debit="0",
                    credit="10.00",
                ),
            )
        )
        with pytest.raises(LedgerInvariantError, match="identity mismatch"):
            session.commit()
        session.rollback()

    _assert_ledger_empty(engine)


def test_public_post_entry_cannot_bypass_guard(tmp_path, monkeypatch):
    import aqorath.core as core

    engine, ids = _canonical_db(tmp_path, monkeypatch)
    result = core.post_entry(
        {
            "description": "Public unbalanced payload",
            "date": "2026-09-09",
            "lines": [
                {
                    "account_id": ids[0],
                    "account_code": "1102",
                    "debit": "100.00",
                    "credit": "0",
                },
                {
                    "account_id": ids[1],
                    "account_code": "4201",
                    "debit": "0",
                    "credit": "99.00",
                },
            ],
        }
    )

    assert result["ok"] is False
    assert "unbalanced" in result["error"]
    _assert_ledger_empty(engine)


def test_public_post_entry_balanced_payload_still_persists(tmp_path, monkeypatch):
    import aqorath.core as core
    from aqorath.models import JournalEntry, JournalLine

    engine, ids = _canonical_db(tmp_path, monkeypatch)
    result = core.post_entry(
        {
            "description": "Balanced payload",
            "date": "2026-09-09",
            "lines": [
                {
                    "account_id": ids[0],
                    "account_code": "1102",
                    "debit": "100.00",
                    "credit": "0",
                },
                {
                    "account_id": ids[1],
                    "account_code": "4201",
                    "debit": "0",
                    "credit": "100.00",
                },
            ],
        }
    )

    assert result["ok"] is True
    with Session(engine) as session:
        assert len(session.exec(select(JournalEntry)).all()) == 1
        assert len(session.exec(select(JournalLine)).all()) == 2


def test_close_exercise_delegates_accounting_write_to_canonical_staging(monkeypatch, tmp_path):
    import aqorath.core as core
    import aqorath.exercise as exercise
    from aqorath.models import Account
    engine, _ = _canonical_db(tmp_path, monkeypatch)
    with Session(engine) as session:
        session.add(Account(code="3104",name="Resultado acumulado",nature="CREDIT"))
        session.commit()
    assert core.post_entry({"date":"2026-05-01","state":"posted","lines":[
        {"account_code":"1102","debit":"100","credit":"0"},
        {"account_code":"4201","debit":"0","credit":"100"},
    ]})["ok"]
    calls=[]
    real_stage=core._stage_entry_in_session
    def tracked_stage(session,payload):
        calls.append(payload)
        return real_stage(session,payload)
    monkeypatch.setattr(core,"_stage_entry_in_session",tracked_stage)
    result=exercise.close_exercise(year=2026,out_root=tmp_path/"backups")
    assert result["ok"],result
    assert len(calls)==1
    assert calls[0]["state"]=="posted"
    assert [(l["account_code"],l["debit"],l["credit"]) for l in calls[0]["lines"]]==[
        ("4201","100","0"),("3104","0","100")]
