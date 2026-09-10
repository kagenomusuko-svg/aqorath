"""Pure value contracts for external bank evidence and reconciliation."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value

def _id(value, name):
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive int")

def _money(value, name):
    if not isinstance(value, Decimal) or not value.is_finite() or value == 0:
        raise ValueError(f"{name} must be a finite non-zero Decimal")

@dataclass(frozen=True)
class BankAccount:
    id: Optional[int]
    entity_id: int
    ledger_account_id: int
    institution_name: str
    account_identifier: str
    currency: str
    is_active: bool = True
    def __post_init__(self):
        if self.id is not None: _id(self.id, "id")
        _id(self.entity_id, "entity_id"); _id(self.ledger_account_id, "ledger_account_id")
        _text(self.institution_name, "institution_name"); _text(self.account_identifier, "account_identifier")
        _text(self.currency, "currency")
        if type(self.is_active) is not bool: raise TypeError("is_active must be bool")

@dataclass(frozen=True)
class BankTransaction:
    id: Optional[int]
    bank_account_id: int
    statement_id: int
    transaction_date: date
    reference: str
    amount: Decimal
    fingerprint: str
    direction: str
    external_balance: Optional[Decimal]
    def __post_init__(self):
        if self.id is not None: _id(self.id, "id")
        _id(self.bank_account_id, "bank_account_id"); _id(self.statement_id, "statement_id")
        if type(self.transaction_date) is not date: raise TypeError("transaction_date must be date")
        _text(self.reference, "reference"); _money(self.amount, "amount"); _text(self.fingerprint, "fingerprint")
        if self.direction not in {"credit", "debit"}: raise ValueError("direction must be credit or debit")
        if self.external_balance is not None and (not isinstance(self.external_balance, Decimal) or not self.external_balance.is_finite()):
            raise ValueError("external_balance must be a finite Decimal")

@dataclass(frozen=True)
class ReconciliationLine:
    bank_transaction_id: int
    journal_line_id: Optional[int]
    state: str
    difference: Decimal

@dataclass(frozen=True)
class ReconciliationView:
    reconciliation_id: int
    bank_account_id: int
    as_of: date
    bank_balance: Optional[Decimal]
    ledger_balance: Decimal
    lines: tuple[ReconciliationLine, ...]
    missing_bank_transaction_ids: tuple[int, ...]
    missing_journal_line_ids: tuple[int, ...]
    difference: Decimal

class ReconciliationDivergenceError(RuntimeError):
    """External evidence and canonical ledger cannot be reconciled exactly."""

__all__ = ["BankAccount", "BankTransaction", "ReconciliationLine", "ReconciliationView", "ReconciliationDivergenceError"]
