"""Persistence authority for external bank evidence only."""

from dataclasses import replace
from hashlib import sha256
from sqlmodel import select

from .bank_import import parse_bank_csv
from .banking import BankAccount, BankTransaction
from .banking_models import BankAccountRecord, BankStatementRecord, BankTransactionRecord
from .models import Account, EntityRecord


def _stage_bank_account(session, account):
    """Stage one validated BankAccount without owning the caller transaction."""
    if not isinstance(account, BankAccount):
        raise TypeError("account must be BankAccount")
    if account.id is not None:
        raise ValueError("new bank account id must be None")
    if session.get(EntityRecord, account.entity_id) is None:
        raise LookupError("entity not found")
    if session.get(Account, account.ledger_account_id) is None:
        raise LookupError("ledger account not found")
    record = BankAccountRecord(**account.__dict__)
    session.add(record)
    session.flush()
    if record.id is None:
        raise RuntimeError("bank account identity was not assigned")
    return replace(account, id=record.id)


def create_bank_account(session, account):
    """Persist one BankAccount while preserving the historical public contract."""
    try:
        persisted = _stage_bank_account(session, account)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return persisted


def import_bank_csv(session, bank_account_id, source_name, content):
    if type(bank_account_id) is not int or bank_account_id <= 0:
        raise ValueError("bank_account_id must be positive int")
    if not isinstance(source_name, str) or not source_name.strip():
        raise ValueError("source_name must be non-empty")
    if not isinstance(content, str):
        raise TypeError("content must be str")
    account = session.get(BankAccountRecord, bank_account_id)
    if account is None:
        raise LookupError("bank account not found")
    source_hash = sha256(content.encode("utf-8")).hexdigest()
    existing = session.exec(select(BankStatementRecord).where(
        BankStatementRecord.bank_account_id == bank_account_id,
        BankStatementRecord.source_hash == source_hash,
    )).first()
    if existing is not None:
        return existing.id
    rows = parse_bank_csv(content)
    statement = BankStatementRecord(
        bank_account_id=bank_account_id,
        source_hash=source_hash,
        source_name=source_name,
        date_from=(min(r["transaction_date"] for r in rows).isoformat() if rows else None),
        date_to=(max(r["transaction_date"] for r in rows).isoformat() if rows else None),
        closing_balance=(str(rows[-1]["external_balance"]) if rows and rows[-1]["external_balance"] is not None else None),
    )
    try:
        session.add(statement)
        session.flush()
        for row in rows:
            session.add(BankTransactionRecord(
                bank_account_id=bank_account_id,
                statement_id=statement.id,
                transaction_date=row["transaction_date"].isoformat(),
                reference=row["reference"],
                amount=str(row["amount"]),
                fingerprint=row["fingerprint"],
                direction=row["direction"],
                external_balance=(str(row["external_balance"]) if row["external_balance"] is not None else None),
            ))
        session.commit()
    except Exception:
        session.rollback()
        raise
    return statement.id


__all__ = ["create_bank_account", "import_bank_csv"]
