from datetime import date
from decimal import Decimal

import pytest


def test_bank_csv_has_explicit_columns_exact_decimals_and_stable_fingerprints():
    from aqorath.bank_import import parse_bank_csv

    rows = parse_bank_csv(
        "date,reference,amount,balance\n"
        "2026-01-31,DEP-1000,1000.00,1000.00\n"
        "2026-02-01,FEE-1,-0.10,999.90\n"
    )
    assert rows[0]["transaction_date"] == date(2026, 1, 31)
    assert rows[0]["amount"] == Decimal("1000.00")
    assert rows[0]["direction"] == "credit"
    assert rows[1]["amount"] == Decimal("0.10")
    assert rows[1]["direction"] == "debit"
    assert rows == parse_bank_csv(
        "date,reference,amount,balance\n"
        "2026-01-31,DEP-1000,1000.00,1000.00\n"
        "2026-02-01,FEE-1,-0.10,999.90\n"
    )


@pytest.mark.parametrize("content", [
    "date,reference,amount\n2026/01/31,x,1\n",
    "date,reference,amount\n2026-01-31,x,abc\n",
    "date,reference,amount\n2026-01-31,x,1,unexpected\n",
])
def test_bank_csv_rejects_ambiguous_or_invalid_input(content):
    from aqorath.bank_import import parse_bank_csv
    with pytest.raises(ValueError):
        parse_bank_csv(content)


def test_bank_schema_is_evidence_and_relation_only(tmp_path):
    import sqlite3
    from aqorath.migrations import CURRENT_SCHEMA_VERSION, migrate_database
    db = tmp_path / "bank.db"
    assert migrate_database(db)["to_version"] == CURRENT_SCHEMA_VERSION
    with sqlite3.connect(db) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"bankaccount", "bankstatement", "banktransaction", "reconciliation", "reconciliationmatch"} <= tables
        assert {row[1] for row in conn.execute("PRAGMA table_info(banktransaction)")} == {
            "id", "bank_account_id", "statement_id", "transaction_date", "reference",
            "amount", "fingerprint", "direction", "external_balance",
        }
        assert "ledger_balance" not in {row[1] for row in conn.execute("PRAGMA table_info(reconciliation)")}


def test_bank_import_is_idempotent_and_does_not_create_ledger_rows(tmp_path, monkeypatch):
    from sqlmodel import Session, select
    from aqorath import bank_repository
    from aqorath.models import Account, JournalEntry, JournalLine
    from test_aqr006_subledger import _seed_runtime
    engine, _, entity_id, _, _ = _seed_runtime(tmp_path, monkeypatch, "bank-import.db")
    with Session(engine) as session:
        ledger = session.exec(select(Account).where(Account.code == "1101")).one()
        from aqorath.banking import BankAccount
        bank = bank_repository.create_bank_account(session, BankAccount(
            None, entity_id, ledger.id, "Banco V1", "CLABE-1", "MXN",
        ))
        csv = "date,reference,amount,balance\n2026-01-31,DEP-1000,1000.00,1000.00\n"
        first = bank_repository.import_bank_csv(session, bank.id, "enero.csv", csv)
        second = bank_repository.import_bank_csv(session, bank.id, "enero.csv", csv)
        assert first == second
        assert session.exec(select(JournalEntry)).all() == []
        assert session.exec(select(JournalLine)).all() == []


def test_matching_is_one_to_one_and_never_rewrites_ledger(tmp_path, monkeypatch):
    from sqlmodel import Session, select
    from aqorath import bank_repository, reconciliation_repository
    from aqorath.banking import BankAccount
    from aqorath.models import Account, JournalEntry, JournalLine
    from test_aqr006_subledger import _seed_runtime
    engine, _, entity_id, _, _ = _seed_runtime(tmp_path, monkeypatch, "bank-match.db")
    with Session(engine) as session:
        bank_account = session.exec(select(Account).where(Account.code == "1101")).one()
        revenue = session.exec(select(Account).where(Account.code == "4201")).one()
        bank = bank_repository.create_bank_account(session, BankAccount(None, entity_id, bank_account.id, "Banco V1", "CLABE-2", "MXN"))
        csv = "date,reference,amount,balance\n2026-01-31,DEP-1000,1000.00,1000.00\n"
        statement_id = bank_repository.import_bank_csv(session, bank.id, "enero.csv", csv)
        entry = JournalEntry(date=__import__("datetime").datetime(2026, 1, 31), concept="sale", period_id=1, state="posted")
        session.add(entry); session.flush()
        debit = JournalLine(entry_id=entry.id, account_code="1101", account_id=bank_account.id, debit="1000.00", credit="0")
        credit = JournalLine(entry_id=entry.id, account_code="4201", account_id=revenue.id, debit="0", credit="1000.00")
        session.add(debit); session.add(credit); session.commit(); session.refresh(debit)
        reconciliation_id = reconciliation_repository.create_reconciliation(session, bank.id, statement_id, date(2026, 1, 31))
        match_id = reconciliation_repository.match_transaction(session, reconciliation_id, 1, debit.id)
        with pytest.raises(ValueError, match="already matched"):
            reconciliation_repository.match_transaction(session, reconciliation_id, 1, debit.id)
        view = reconciliation_repository.load_reconciliation(session, reconciliation_id)
        assert match_id > 0
        assert view.lines[0].state == "matched"
        assert view.ledger_balance == Decimal("1000.00")
        assert session.get(JournalLine, debit.id).debit == "1000.00"
        reconciliation_repository.revoke_match(session, match_id, "corrección documental")
        reopened = reconciliation_repository.load_reconciliation(session, reconciliation_id)
        assert reopened.lines[0].state == "unmatched"
        assert reopened.missing_journal_line_ids == (debit.id,)


def test_deposit_in_transit_remains_explicit_difference(tmp_path, monkeypatch):
    from datetime import datetime
    from sqlmodel import Session, select
    from aqorath import bank_repository, reconciliation_repository
    from aqorath.banking import BankAccount
    from aqorath.models import Account, JournalEntry, JournalLine
    from test_aqr006_subledger import _seed_runtime
    engine, _, entity_id, _, _ = _seed_runtime(tmp_path, monkeypatch, "transit.db")
    with Session(engine) as session:
        bank_account = session.exec(select(Account).where(Account.code == "1101")).one()
        revenue = session.exec(select(Account).where(Account.code == "4201")).one()
        bank = bank_repository.create_bank_account(session, BankAccount(None, entity_id, bank_account.id, "Banco V1", "CLABE-3", "MXN"))
        statement_id = bank_repository.import_bank_csv(session, bank.id, "enero.csv", "date,reference,amount,balance\n2026-01-31,BANK-900,900.00,900.00\n")
        entry = JournalEntry(date=datetime(2026, 1, 31), concept="deposit in transit", period_id=1, state="posted")
        session.add(entry); session.flush()
        line = JournalLine(entry_id=entry.id, account_code="1101", account_id=bank_account.id, debit="1000.00", credit="0")
        session.add(line); session.add(JournalLine(entry_id=entry.id, account_code="4201", account_id=revenue.id, debit="0", credit="1000.00")); session.commit()
        session.refresh(line)
        reconciliation_id = reconciliation_repository.create_reconciliation(session, bank.id, statement_id, date(2026, 1, 31))
        view = reconciliation_repository.load_reconciliation(session, reconciliation_id)
        assert view.bank_balance == Decimal("900.00")
        assert view.ledger_balance == Decimal("1000.00")
        assert view.difference == Decimal("100.00")
        assert view.missing_journal_line_ids == (line.id,)


def test_common_and_professional_banking_surface_share_reconciliation_truth(tmp_path, monkeypatch):
    from aqorath.presentation_controller import LocalPresentationController
    from test_aqr006_subledger import _seed_runtime
    _, _, _, _, _ = _seed_runtime(tmp_path, monkeypatch, "bank-surface.db")
    controller = LocalPresentationController()
    bank = controller.create_bank_account({
        "institution_name": "Banco V1", "account_identifier": "CLABE-SURFACE", "currency": "MXN",
    })
    imported = controller.import_bank_csv({
        "bank_account_id": bank["id"], "source_name": "enero.csv",
        "content": "date,reference,amount,balance\n2026-01-31,DEP-1,100.00,100.00\n",
    })
    created = controller.create_reconciliation({
        "bank_account_id": bank["id"], "statement_id": imported["statement_id"], "as_of": "2026-01-31",
    })
    professional = controller.reconciliation(created["reconciliation_id"])
    assert professional["bank_account_id"] == bank["id"]
    assert professional["lines"][0]["state"] == "unmatched"


def test_transfer_between_bank_accounts_uses_canonical_posting(tmp_path, monkeypatch):
    from sqlmodel import Session, select
    from aqorath import bank_repository, bank_transfer
    from aqorath.banking import BankAccount
    from aqorath.models import Account, JournalEntry, JournalLine
    from test_aqr006_subledger import _seed_runtime
    engine, _, entity_id, _, _ = _seed_runtime(tmp_path, monkeypatch, "bank-transfer.db")
    with Session(engine) as session:
        source_account = session.exec(select(Account).where(Account.code == "1101")).one()
        destination_account = Account(code="1102", name="Banco secundario", nature="DEBIT")
        session.add(destination_account); session.commit(); session.refresh(destination_account)
        source = bank_repository.create_bank_account(session, BankAccount(None, entity_id, source_account.id, "Banco V1", "SOURCE", "MXN"))
        destination = bank_repository.create_bank_account(session, BankAccount(None, entity_id, destination_account.id, "Banco V1", "DEST", "MXN"))
        result = bank_transfer.execute_bank_transfer(session, source.id, destination.id, Decimal("300.00"), date(2026, 1, 31), "Transferencia entre cuentas propias")
        lines = session.exec(select(JournalLine).where(JournalLine.entry_id == result["entry_id"]).order_by(JournalLine.id)).all()
        assert [(line.account_id, line.debit, line.credit) for line in lines] == [(destination_account.id, "300.00", "0"), (source_account.id, "0", "300.00")]
        assert session.get(JournalEntry, result["entry_id"]).state == "posted"
