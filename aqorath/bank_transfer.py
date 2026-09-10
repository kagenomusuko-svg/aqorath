"""Canonical two-bank-account transfer composition for AQR-007."""

from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation
import json

from sqlmodel import select

from . import core
from .banking_models import BankAccountRecord
from .entity_repository import load_active_entity
from .models import Account, AuditEventRecord


def execute_bank_transfer(session, source_bank_account_id, destination_bank_account_id, amount, posting_date, description):
    if type(posting_date) is not date:
        raise TypeError("posting_date must be date")
    try:
        amount = amount if isinstance(amount, Decimal) else Decimal(amount)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("amount must be exact Decimal text") from exc
    if not amount.is_finite() or amount <= 0:
        raise ValueError("amount must be finite and greater than zero")
    if source_bank_account_id == destination_bank_account_id:
        raise ValueError("source and destination bank accounts must differ")
    source = session.get(BankAccountRecord, source_bank_account_id)
    destination = session.get(BankAccountRecord, destination_bank_account_id)
    if source is None or destination is None or source.entity_id != destination.entity_id:
        raise LookupError("bank accounts must belong to the same entity")
    source_account = session.get(Account, source.ledger_account_id)
    destination_account = session.get(Account, destination.ledger_account_id)
    entity = load_active_entity(session)
    if source_account is None or destination_account is None or entity is None or entity.id != source.entity_id:
        raise LookupError("bank account ledger authority is incomplete")
    entry, error = core._stage_entry_in_session(session, {
        "date": datetime.combine(posting_date, time.min, tzinfo=timezone.utc),
        "description": description,
        "state": "posted",
        "lines": [
            {"account_id": destination_account.id, "account_code": destination_account.code, "debit": amount, "credit": Decimal("0")},
            {"account_id": source_account.id, "account_code": source_account.code, "debit": Decimal("0"), "credit": amount},
        ],
    })
    if error is not None:
        raise RuntimeError(error)
    audit = AuditEventRecord(
        entity_id=entity.id,
        event_type="bank_transfer_posted",
        timestamp=datetime.now(timezone.utc).isoformat(),
        details_json=json.dumps({"entry_id": entry.id, "source_bank_account_id": source.id, "destination_bank_account_id": destination.id, "amount": str(amount)}, sort_keys=True),
    )
    try:
        session.add(audit)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return {"entry_id": entry.id, "audit_event_id": audit.id}


__all__ = ["execute_bank_transfer"]
