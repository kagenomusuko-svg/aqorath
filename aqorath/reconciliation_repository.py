"""One-to-one matching and derived reconciliation over bank evidence and ledger."""

from datetime import date
from decimal import Decimal

from sqlmodel import select

from .banking import ReconciliationDivergenceError, ReconciliationLine, ReconciliationView
from .banking_models import (
    BankAccountRecord, BankStatementRecord, BankTransactionRecord,
    ReconciliationMatchRecord, ReconciliationMatchRevocationRecord,
    ReconciliationRecord,
)
from .models import JournalEntry, JournalLine


def create_reconciliation(session, bank_account_id, statement_id, as_of):
    if type(as_of) is not date:
        raise TypeError("as_of must be date")
    account = session.get(BankAccountRecord, bank_account_id)
    statement = session.get(BankStatementRecord, statement_id)
    if account is None or statement is None or statement.bank_account_id != bank_account_id:
        raise LookupError("statement is not owned by bank account")
    record = ReconciliationRecord(
        bank_account_id=bank_account_id,
        statement_id=statement_id,
        as_of=as_of.isoformat(),
    )
    try:
        session.add(record)
        session.flush()
        session.commit()
    except Exception:
        session.rollback()
        raise
    return record.id


def match_transaction(session, reconciliation_id, bank_transaction_id, journal_line_id):
    reconciliation = session.get(ReconciliationRecord, reconciliation_id)
    bank = session.get(BankTransactionRecord, bank_transaction_id)
    line = session.get(JournalLine, journal_line_id)
    if reconciliation is None or bank is None or line is None:
        raise LookupError("reconciliation, bank transaction, and journal line are required")
    account = session.get(BankAccountRecord, reconciliation.bank_account_id)
    entry = session.get(JournalEntry, line.entry_id)
    if bank.bank_account_id != reconciliation.bank_account_id or account is None:
        raise ValueError("bank transaction is outside reconciliation account")
    if bank.transaction_date > reconciliation.as_of:
        raise ValueError("bank transaction is after reconciliation as_of")
    if line.account_id != account.ledger_account_id or entry is None:
        raise ValueError("journal line is outside linked bank ledger account")
    if entry.date.date() > date.fromisoformat(reconciliation.as_of):
        raise ValueError("journal line is after reconciliation as_of")
    external_signed = Decimal(bank.amount) * (Decimal("1") if bank.direction == "credit" else Decimal("-1"))
    ledger_signed = Decimal(line.debit) - Decimal(line.credit)
    if external_signed != ledger_signed:
        raise ValueError("bank and journal line amounts do not match exactly")
    if session.exec(select(ReconciliationMatchRecord).where(
        ReconciliationMatchRecord.bank_transaction_id == bank_transaction_id
    )).first() is not None:
        raise ValueError("bank transaction is already matched")
    if session.exec(select(ReconciliationMatchRecord).where(
        ReconciliationMatchRecord.journal_line_id == journal_line_id
    )).first() is not None:
        raise ValueError("journal line is already matched")
    record = ReconciliationMatchRecord(
        reconciliation_id=reconciliation_id,
        bank_transaction_id=bank_transaction_id,
        journal_line_id=journal_line_id,
    )
    try:
        session.add(record)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return record.id


def revoke_match(session, match_id, reason):
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("reason must be non-empty")
    match = session.get(ReconciliationMatchRecord, match_id)
    if match is None:
        raise LookupError("match not found")
    if session.exec(select(ReconciliationMatchRevocationRecord).where(
        ReconciliationMatchRevocationRecord.match_id == match_id
    )).first() is not None:
        raise ValueError("match already revoked")
    record = ReconciliationMatchRevocationRecord(match_id=match_id, reason=reason)
    try:
        session.add(record)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return record.id


def load_reconciliation(session, reconciliation_id):
    reconciliation = session.get(ReconciliationRecord, reconciliation_id)
    if reconciliation is None:
        raise LookupError("reconciliation not found")
    account = session.get(BankAccountRecord, reconciliation.bank_account_id)
    statement = session.get(BankStatementRecord, reconciliation.statement_id)
    if account is None or statement is None:
        raise RuntimeError("reconciliation provenance is incomplete")
    as_of = date.fromisoformat(reconciliation.as_of)
    revoked = {
        row.match_id for row in session.exec(select(ReconciliationMatchRevocationRecord)).all()
    }
    matches = [row for row in session.exec(select(ReconciliationMatchRecord).where(
        ReconciliationMatchRecord.reconciliation_id == reconciliation_id
    )).all() if row.id not in revoked]
    by_bank = {row.bank_transaction_id: row for row in matches}
    by_line = {row.journal_line_id: row for row in matches}
    transactions = session.exec(select(BankTransactionRecord).where(
        BankTransactionRecord.bank_account_id == account.id,
        BankTransactionRecord.transaction_date <= as_of.isoformat(),
    )).all()
    lines = session.exec(select(JournalLine).where(JournalLine.account_id == account.ledger_account_id)).all()
    entries = {entry.id: entry for entry in session.exec(select(JournalEntry)).all()}
    eligible_lines = [line for line in lines if line.entry_id in entries and entries[line.entry_id].date.date() <= as_of]
    statement_balance = Decimal(statement.closing_balance) if statement.closing_balance is not None else None
    ledger_balance = sum((Decimal(line.debit) - Decimal(line.credit) for line in eligible_lines), Decimal("0"))
    external_balance = sum((Decimal(row.amount) if row.direction == "credit" else -Decimal(row.amount) for row in transactions), Decimal("0"))
    result_lines = []
    for row in transactions:
        match = by_bank.get(row.id)
        result_lines.append(ReconciliationLine(
            row.id, match.journal_line_id if match else None,
            "matched" if match else "unmatched", Decimal("0") if match else Decimal(row.amount),
        ))
    missing_lines = tuple(line.id for line in eligible_lines if line.id not in by_line)
    difference = (ledger_balance - statement_balance) if statement_balance is not None else ledger_balance - external_balance
    return ReconciliationView(
        reconciliation.id, account.id, as_of, statement_balance, ledger_balance,
        tuple(result_lines), tuple(row.id for row in transactions if row.id not in by_bank),
        missing_lines, difference,
    )


__all__ = ["create_reconciliation", "match_transaction", "revoke_match", "load_reconciliation", "ReconciliationDivergenceError"]
