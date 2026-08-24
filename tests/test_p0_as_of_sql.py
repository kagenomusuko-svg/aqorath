"""
P0-3 TEST: Behavioral test for as_of filtering with real data.

Crea datos reales en SQLite y verifica que as_of funciona correctamente.
NO inspecciona source code.
"""

import pytest
from decimal import Decimal
from datetime import datetime
from pathlib import Path
from sqlalchemy import create_engine
from sqlmodel import SQLModel, Session, select
from aqorath.core import _balances_from_sqlite
from aqorath.models import Account, JournalEntry, JournalLine


def test_as_of_boundary_with_real_data(tmp_path):
    """
    Real behavioral test with boundary timestamps.

    Entry A: 2026-03-31 23:59:59 (must be included in as_of="2026-03-31")
    Entry B: 2026-04-01 00:00:00 (must be excluded from as_of="2026-03-31")
    """
    # Create temporary database
    db_file = tmp_path / "as_of_test.db"
    db_url = f"sqlite:///{db_file}"
    engine = create_engine(db_url, echo=False)
    SQLModel.metadata.create_all(engine)

    # Create test data
    with Session(engine) as session:
        # Create account
        account = Account(code="1101", name="Bancos", nature="DEBIT")
        session.add(account)
        session.flush()

        # Entry A: 31 March 23:59:59
        entry_a = JournalEntry(date=datetime(2026, 3, 31, 23, 59, 59))
        session.add(entry_a)
        session.flush()

        line_a = JournalLine(
            entry_id=entry_a.id,
            account_code="1101",
            debit="100",
            credit="0"
        )
        session.add(line_a)

        # Entry B: 1 April 00:00:00
        entry_b = JournalEntry(date=datetime(2026, 4, 1, 0, 0, 0))
        session.add(entry_b)
        session.flush()

        line_b = JournalLine(
            entry_id=entry_b.id,
            account_code="1101",
            debit="0",
            credit="50"
        )
        session.add(line_b)
        session.commit()

    # Test 1: without as_of (include both)
    balances_all = _balances_from_sqlite(db_file)
    assert balances_all.get("1101") == Decimal("50"), (
        f"Sin as_of: esperado 50, actual {balances_all.get('1101')}"
    )

    # Test 2: with as_of="2026-03-31" (only entry A on 31st 23:59:59)
    balances_cutoff = _balances_from_sqlite(db_file, as_of="2026-03-31")
    assert balances_cutoff.get("1101") == Decimal("100"), (
        f"Con as_of='2026-03-31': esperado 100, actual {balances_cutoff.get('1101')}"
    )

    # Test 3: with as_of="2026-04-01" (both)
    balances_next = _balances_from_sqlite(db_file, as_of="2026-04-01")
    assert balances_next.get("1101") == Decimal("50"), (
        f"Con as_of='2026-04-01': esperado 50, actual {balances_next.get('1101')}"
    )


def test_as_of_invalid_format_raises_error(tmp_path):
    """
    Test that invalid as_of format raises ValueError.
    """
    # Create temporary database
    db_file = tmp_path / "as_of_invalid.db"
    db_url = f"sqlite:///{db_file}"
    engine = create_engine(db_url, echo=False)
    SQLModel.metadata.create_all(engine)

    # Add dummy data
    with Session(engine) as session:
        account = Account(code="1101", name="Bancos", nature="DEBIT")
        session.add(account)
        session.flush()

        entry = JournalEntry(date=datetime(2026, 3, 31))
        session.add(entry)
        session.flush()

        line = JournalLine(entry_id=entry.id, account_code="1101", debit="100", credit="0")
        session.add(line)
        session.commit()

    # Invalid formats must raise ValueError
    with pytest.raises(ValueError):
        _balances_from_sqlite(db_file, as_of="31/03/2026")

    with pytest.raises(ValueError):
        _balances_from_sqlite(db_file, as_of="Mar 31, 2026")
