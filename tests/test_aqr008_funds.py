"""AQR-008: fund/source traceability remains a projection over JournalLine."""
from dataclasses import FrozenInstanceError
from datetime import date, datetime, timezone
from decimal import Decimal
import sqlite3

import pytest
from sqlalchemy import create_engine
from sqlmodel import Session, select


def _db(tmp_path):
    from aqorath.migrations import migrate_database
    path = tmp_path / "funds.db"
    migrate_database(path)
    return path, create_engine(f"sqlite:///{path}")


def _entity(session):
    from aqorath.entity import Entity, EntityProfile
    from aqorath.entity_repository import create_entity
    return create_entity(session, Entity(
        id=None, name="Meriadock A.C.", rfc=None, legal_personality="persona_moral",
        legal_form="A.C.", is_active=True,
        profile=EntityProfile(economic_purpose="no_lucrativo", is_donor_authorized=False,
                              special_capabilities=("osc",), modules_enabled=("banking",)),
    ))


def test_schema9_is_additive_and_does_not_add_parallel_money_tables(tmp_path):
    path, _ = _db(tmp_path)
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 9
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"fund", "fundingsource", "fundreceipt", "fundapplication"}.issubset(tables)
        assert "fundbalance" not in tables
        assert {row[1] for row in conn.execute("PRAGMA table_info(fundapplication)")} >= {
            "fund_id", "program_id", "journal_line_id", "amount"
        }


def test_fund_domain_is_frozen_and_has_no_debit_credit_authority():
    from aqorath.fund import Fund, FundingSource, FundReceipt, FundApplication
    fund = Fund(None, 1, "EDU", "Educación", "restricted", "becas", 4,
                date(2026, 1, 1), date(2026, 12, 31))
    assert fund.restriction == "restricted"
    with pytest.raises(FrozenInstanceError):
        fund.name = "changed"
    for cls in (Fund, FundingSource, FundReceipt, FundApplication):
        assert not {field for field in cls.__dataclass_fields__ if field in {"debit", "credit", "balance"}}


def test_fund_receipt_and_application_require_exact_canonical_line_amount(tmp_path):
    from aqorath.fund import Fund, FundingSource, FundReceipt, FundApplication
    from aqorath.fund_repository import (
        create_fund, create_funding_source, record_fund_application, record_fund_receipt,
    )
    from aqorath.models import Account, JournalEntry, JournalLine
    from aqorath.program import Program
    from aqorath.program_repository import create_program

    _, engine = _db(tmp_path)
    with Session(engine) as session:
        entity = _entity(session)
        program = create_program(session, Program(None, entity.id, "Salud", None, None))
        fund = create_fund(session, Fund(None, entity.id, "RESTRICTED", "Restricted", "restricted", program_id=program.id))
        source = create_funding_source(session, FundingSource(None, entity.id, "Grant source"))
        debit = Account(code="5101", name="Program expense", nature="DEBIT")
        session.add(debit); session.flush()
        entry = JournalEntry(date=datetime(2026, 5, 1, tzinfo=timezone.utc), concept="expense", state="posted")
        session.add(entry); session.flush()
        line = JournalLine(entry_id=entry.id, account_id=debit.id, account_code=debit.code, debit="100.00", credit="0")
        session.add(line); session.commit()
        with pytest.raises(ValueError, match="equal"):
            record_fund_receipt(session, FundReceipt(None, entity.id, fund.id, source.id, line.id, Decimal("99.99"), entry.date))
        application = record_fund_application(session, FundApplication(None, entity.id, fund.id, program.id, line.id, Decimal("100.00"), entry.date))
        assert application.id is not None
        assert session.exec(select(JournalLine)).one().debit == "100.00"
