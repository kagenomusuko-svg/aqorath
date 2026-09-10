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


def _schema8_snapshot(path):
    """Frozen schema 8 fixture: schema6.sql plus literal 7/8 DDL, no metadata."""
    snapshot = open(__import__("pathlib").Path(__file__).parent / "fixtures" / "schema6.sql", encoding="utf-8").read()
    additions = """
    CREATE TABLE openitem (id INTEGER PRIMARY KEY, entity_id INTEGER NOT NULL, third_party_id INTEGER NOT NULL, kind VARCHAR NOT NULL, source_entry_id INTEGER NOT NULL, source_line_id INTEGER NOT NULL UNIQUE, source_document_reference_id INTEGER NOT NULL, due_date DATE NOT NULL, created_at DATETIME NOT NULL, FOREIGN KEY(entity_id) REFERENCES entity(id), FOREIGN KEY(third_party_id) REFERENCES thirdparty(id), FOREIGN KEY(source_entry_id) REFERENCES journalentry(id), FOREIGN KEY(source_line_id) REFERENCES journalline(id), FOREIGN KEY(source_document_reference_id) REFERENCES documentreference(id));
    CREATE TABLE openitemapplication (id INTEGER PRIMARY KEY, open_item_id INTEGER NOT NULL, application_entry_id INTEGER NOT NULL, application_line_id INTEGER NOT NULL UNIQUE, application_document_reference_id INTEGER NOT NULL, created_at DATETIME NOT NULL, FOREIGN KEY(open_item_id) REFERENCES openitem(id), FOREIGN KEY(application_entry_id) REFERENCES journalentry(id), FOREIGN KEY(application_line_id) REFERENCES journalline(id), FOREIGN KEY(application_document_reference_id) REFERENCES documentreference(id));
    CREATE TABLE bankaccount (id INTEGER PRIMARY KEY, entity_id INTEGER NOT NULL, ledger_account_id INTEGER NOT NULL, institution_name VARCHAR NOT NULL, account_identifier VARCHAR NOT NULL, currency VARCHAR NOT NULL, is_active BOOLEAN NOT NULL, created_at DATETIME NOT NULL, UNIQUE(entity_id, account_identifier), FOREIGN KEY(entity_id) REFERENCES entity(id), FOREIGN KEY(ledger_account_id) REFERENCES account(id));
    CREATE TABLE bankstatement (id INTEGER PRIMARY KEY, bank_account_id INTEGER NOT NULL, source_hash VARCHAR NOT NULL, source_name VARCHAR NOT NULL, date_from VARCHAR, date_to VARCHAR, opening_balance TEXT, closing_balance TEXT, imported_at DATETIME NOT NULL, UNIQUE(bank_account_id, source_hash), FOREIGN KEY(bank_account_id) REFERENCES bankaccount(id));
    CREATE TABLE banktransaction (id INTEGER PRIMARY KEY, bank_account_id INTEGER NOT NULL, statement_id INTEGER NOT NULL, transaction_date VARCHAR NOT NULL, reference TEXT NOT NULL, amount TEXT NOT NULL, fingerprint VARCHAR NOT NULL, direction VARCHAR NOT NULL, external_balance TEXT, UNIQUE(bank_account_id, fingerprint), FOREIGN KEY(bank_account_id) REFERENCES bankaccount(id), FOREIGN KEY(statement_id) REFERENCES bankstatement(id));
    CREATE TABLE reconciliation (id INTEGER PRIMARY KEY, bank_account_id INTEGER NOT NULL, statement_id INTEGER NOT NULL, as_of VARCHAR NOT NULL, created_at DATETIME NOT NULL, FOREIGN KEY(bank_account_id) REFERENCES bankaccount(id), FOREIGN KEY(statement_id) REFERENCES bankstatement(id));
    CREATE TABLE reconciliationmatch (id INTEGER PRIMARY KEY, reconciliation_id INTEGER NOT NULL, bank_transaction_id INTEGER NOT NULL, journal_line_id INTEGER NOT NULL, matched_at DATETIME NOT NULL, UNIQUE(bank_transaction_id), UNIQUE(journal_line_id), FOREIGN KEY(reconciliation_id) REFERENCES reconciliation(id), FOREIGN KEY(bank_transaction_id) REFERENCES banktransaction(id), FOREIGN KEY(journal_line_id) REFERENCES journalline(id));
    CREATE TABLE reconciliationmatchrevocation (id INTEGER PRIMARY KEY, match_id INTEGER NOT NULL UNIQUE, reason TEXT NOT NULL, revoked_at DATETIME NOT NULL, FOREIGN KEY(match_id) REFERENCES reconciliationmatch(id));
    PRAGMA user_version=8;
    """
    with sqlite3.connect(path) as conn:
        conn.executescript(snapshot + additions)


def _entity(session):
    from aqorath.entity import Entity, EntityProfile
    from aqorath.entity_repository import create_entity
    return create_entity(session, Entity(
        id=None, name="Meriadock A.C.", rfc=None, legal_personality="persona_moral",
        legal_form="A.C.", is_active=True,
        profile=EntityProfile(economic_purpose="no_lucrativo", is_donor_authorized=False,
                              special_capabilities=("osc",), modules_enabled=("banking",)),
    ))


def test_current_schema_is_additive_and_does_not_add_parallel_money_tables(tmp_path):
    path, _ = _db(tmp_path)
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 10
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"fund", "fundingsource", "fundreceipt", "fundapplication"}.issubset(tables)
        assert "fundbalance" not in tables
        assert {row[1] for row in conn.execute("PRAGMA table_info(fundapplication)")} >= {
            "fund_id", "program_id", "journal_line_id", "amount"
        }


def test_schema8_to_9_uses_frozen_snapshot_and_preserves_history(tmp_path):
    from aqorath.migrations import migrate_database
    path = tmp_path / "historical-v8.db"
    _schema8_snapshot(path)
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 8
        assert not {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")} & {"fund", "fundingsource", "fundreceipt", "fundapplication"}
        conn.execute("INSERT INTO account(code,name,nature,vat_flag,origin,created_at) VALUES ('4201','Grant income','CREDIT',0,'canonical','2026-01-01')")
        account_id = conn.execute("SELECT id FROM account WHERE code='4201'").fetchone()[0]
        conn.execute("INSERT INTO journalentry(id,date,concept,state,created_at) VALUES (7,'2026-01-10T00:00:00+00:00','historic grant','posted','2026-01-10')")
        conn.execute("INSERT INTO journalline(id,entry_id,account_code,account_id,debit,credit,created_at) VALUES (8,7,'4201',?,'0','1000.00','2026-01-10')", (account_id,))
        conn.commit()
    assert migrate_database(path)["to_version"] == 10
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 10
        assert conn.execute("SELECT credit FROM journalline WHERE id=8").fetchone()[0] == "1000.00"
        assert conn.execute("SELECT count(*) FROM fund").fetchone()[0] == 0
        assert any("journal_line_id" in {r[2] for r in conn.execute(f"PRAGMA index_info('{row[1]}')")} for row in conn.execute("PRAGMA index_list(fundreceipt)"))


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
    from aqorath.models import Account, AuditEventRecord, JournalEntry, JournalLine
    from aqorath.donation import Donation
    from aqorath.donation_repository import create_donation
    from aqorath.program import Program
    from aqorath.program_repository import create_program

    _, engine = _db(tmp_path)
    with Session(engine) as session:
        entity = _entity(session)
        program = create_program(session, Program(None, entity.id, "Salud", None, None))
        fund = create_fund(session, Fund(None, entity.id, "RESTRICTED", "Restricted", "restricted", program_id=program.id))
        source = create_funding_source(session, FundingSource(None, entity.id, "Grant source"))
        debit = Account(code="5101", name="Program expense", nature="DEBIT")
        credit = Account(code="4201", name="Grant income", nature="CREDIT")
        session.add(debit); session.add(credit); session.flush()
        entry = JournalEntry(date=datetime(2026, 5, 1, tzinfo=timezone.utc), concept="receipt", state="posted")
        session.add(entry); session.flush()
        receipt_line = JournalLine(entry_id=entry.id, account_id=credit.id, account_code=credit.code, debit="0", credit="1000.00")
        session.add(receipt_line); session.commit()
        session.add(AuditEventRecord(entity_id=entity.id, event_type="entry_posted", timestamp=entry.date.isoformat(), details_json='{"decision":{"fact":{"type":"donation"}},"entry_id":%d}' % entry.id))
        donation = create_donation(session, Donation(None, entity.id, entry.date, Decimal("1000.00"), None, "Grant", True))
        with pytest.raises(ValueError, match="equal"):
            record_fund_receipt(session, FundReceipt(None, entity.id, fund.id, source.id, receipt_line.id, Decimal("99.99"), entry.date, donation.id))
        receipt = record_fund_receipt(session, FundReceipt(None, entity.id, fund.id, source.id, receipt_line.id, Decimal("1000.00"), entry.date, donation.id))
        expense_entry = JournalEntry(date=datetime(2026, 5, 2, tzinfo=timezone.utc), concept="expense", state="posted")
        session.add(expense_entry); session.flush()
        expense_line = JournalLine(entry_id=expense_entry.id, account_id=debit.id, account_code=debit.code, debit="300.00", credit="0")
        session.add(expense_line); session.commit()
        session.add(AuditEventRecord(entity_id=entity.id, event_type="entry_posted", timestamp=expense_entry.date.isoformat(), details_json='{"decision":{"fact":{"type":"utility_expense"},"explanation":{"effects":[{"account_role":"utilities_expense","side":"debit"}]}},"entry_id":%d}' % expense_entry.id)); session.commit()
        application = record_fund_application(session, FundApplication(None, entity.id, fund.id, program.id, expense_line.id, Decimal("300.00"), expense_entry.date, receipt_id=receipt.id))
        assert application.id is not None
        from aqorath.fund_repository import load_fund_balance, load_fund_traceability
        balance = load_fund_balance(session, entity.id, fund.id, date(2026, 5, 31))
        assert (balance.received, balance.applied, balance.available) == (Decimal("1000.00"), Decimal("300.00"), Decimal("700.00"))
        trace = load_fund_traceability(session, entity.id, fund.id, date(2026, 5, 31))
        assert trace["receipts"][0]["ledger"]["line_id"] == receipt_line.id
        assert trace["applications"][0]["ledger"]["line_id"] == expense_line.id
        assert session.get(JournalLine, expense_line.id).debit == "300.00"


def test_surface_exposes_human_fund_flow_and_professional_traceability(monkeypatch):
    from aqorath.web_assets import APP_HTML
    from aqorath.presentation_controller import LocalPresentationController
    import aqorath.presentation_controller as controller_module

    for endpoint in ("/api/osc/funds", "/api/osc/funding-sources", "/api/osc/fund-candidates?kind=receipt", "/api/osc/fund-receipts", "/api/osc/fund-applications"):
        assert endpoint in APP_HTML
    for element in ("oscFundSelect", "oscSourceSelect", "receiptCandidate", "applicationCandidate", "applicationAmount", "fundTraceOutput"):
        assert f'id="{element}"' in APP_HTML
    monkeypatch.setattr(controller_module._application, "list_surface_funds", lambda: [{"id": 1}])
    monkeypatch.setattr(controller_module._application, "list_surface_funding_sources", lambda: [{"id": 2}])
    controller = LocalPresentationController()
    assert controller.funds() == [{"id": 1}]
    assert controller.funding_sources() == [{"id": 2}]
