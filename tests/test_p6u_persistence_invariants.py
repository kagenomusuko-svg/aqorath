"""Phase 6U.1 — canonical persistence invariant contracts."""

from datetime import datetime, timezone

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


def _balanced_lines():
    return (
        _line(debit="100.00", account_id=1, account_code="1102"),
        _line(credit="100.00", account_id=2, account_code="4201"),
    )


def _canonical_db(tmp_path, monkeypatch):
    import aqorath.storage as storage
    from aqorath.models import Account

    db = tmp_path / "p6u-ledger-invariants.db"
    monkeypatch.setenv("AQORATH_DB", str(db))
    engine = storage.init_db(str(db), create_tables=True)

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
    assert validate_journal_lines(_balanced_lines()) is None


def test_validator_rejects_empty_entry():
    with pytest.raises(LedgerInvariantError, match="at least one"):
        validate_journal_lines(())


def test_validator_rejects_unbalanced_entry_exactly():
    with pytest.raises(LedgerInvariantError, match="unbalanced"):
        validate_journal_lines(
            (
                _line(debit="100.00"),
                _line(credit="99.99", account_id=2, account_code="4201"),
            )
        )


@pytest.mark.parametrize(
    ("debit", "credit", "message"),
    [
        ("-1", "0", "non-negative"),
        ("0", "-1", "non-negative"),
        ("1", "1", "exactly one"),
        ("0", "0", "exactly one"),
        ("NaN", "0", "finite"),
        ("Infinity", "0", "finite"),
    ],
)
def test_validator_rejects_invalid_line_money(debit, credit, message):
    with pytest.raises(LedgerInvariantError, match=message):
        validate_journal_lines(
            (
                _line(debit=debit, credit=credit),
                _line(credit="1", account_id=2, account_code="4201"),
            )
        )


def test_validator_requires_account_identity():
    with pytest.raises(LedgerInvariantError, match="account_id"):
        validate_journal_lines(
            (
                _line(debit="1", account_id=None),
                _line(credit="1", account_id=2, account_code="4201"),
            )
        )


def test_direct_orm_unbalanced_entry_cannot_commit(tmp_path, monkeypatch):
    from aqorath.models import JournalEntry, JournalLine

    engine, ids = _canonical_db(tmp_path, monkeypatch)

    with Session(engine) as session:
        entry = JournalEntry(
            date=datetime(2026, 9, 8, tzinfo=timezone.utc),
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
            date=datetime(2026, 9, 8, tzinfo=timezone.utc),
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


def test_public_post_entry_dict_cannot_bypass_balance_guard(tmp_path, monkeypatch):
    import aqorath.core as core

    engine, ids = _canonical_db(tmp_path, monkeypatch)
    result = core.post_entry(
        {
            "description": "Public unbalanced payload",
            "date": "2026-09-08",
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


def test_public_post_entry_balanced_dict_still_persists(tmp_path, monkeypatch):
    import aqorath.core as core
    from aqorath.models import JournalEntry, JournalLine

    engine, ids = _canonical_db(tmp_path, monkeypatch)
    result = core.post_entry(
        {
            "description": "Balanced payload",
            "date": "2026-09-08",
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
        entries = session.exec(select(JournalEntry)).all()
        lines = session.exec(select(JournalLine)).all()
    assert len(entries) == 1
    assert len(lines) == 2
