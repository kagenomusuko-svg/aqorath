"""Canonical persistence invariants for journal lines.

This module is deliberately small and side-effect free. It defines the monetary
and accounting checks that every ORM persistence path must satisfy before a journal
entry can become durable.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable

from aqorath.money import to_decimal_exact


class LedgerInvariantError(ValueError):
    """Raised when a journal entry violates a non-negotiable ledger invariant."""


def _field(line: Any, name: str) -> Any:
    if isinstance(line, dict):
        return line.get(name)
    return getattr(line, name, None)


def _exact_money(value: Any, *, field: str, index: int) -> Decimal:
    try:
        amount = to_decimal_exact(0 if value is None else value)
    except Exception as exc:
        raise LedgerInvariantError(
            f"JournalLine {index}: {field} must be an exact monetary value"
        ) from exc

    if not amount.is_finite():
        raise LedgerInvariantError(f"JournalLine {index}: {field} must be finite")
    return amount


def validate_journal_line_money(line: Any, *, index: int = 0) -> tuple[Decimal, Decimal]:
    """Validate invariants that are meaningful for one line in isolation."""

    debit = _exact_money(_field(line, "debit"), field="debit", index=index)
    credit = _exact_money(_field(line, "credit"), field="credit", index=index)

    if debit < 0 or credit < 0:
        raise LedgerInvariantError(
            f"JournalLine {index}: debit and credit must be non-negative"
        )

    debit_positive = debit > 0
    credit_positive = credit > 0
    if debit_positive == credit_positive:
        raise LedgerInvariantError(
            f"JournalLine {index}: exactly one of debit or credit must be positive"
        )

    return debit, credit


def validate_journal_lines(lines: Iterable[Any]) -> None:
    """Validate one complete persisted JournalEntry line set.

    Enforced invariants:
    - at least one line exists;
    - every line belongs to an entry and resolves an Account identity;
    - debit/credit are finite, exact and non-negative;
    - exactly one side of every line is strictly positive;
    - total debits equal total credits exactly (no tolerance/rounding authority).
    """

    materialized = list(lines)
    if not materialized:
        raise LedgerInvariantError("JournalEntry must contain at least one JournalLine")

    total_debit = Decimal("0")
    total_credit = Decimal("0")

    for index, line in enumerate(materialized):
        entry_id = _field(line, "entry_id")
        account_id = _field(line, "account_id")
        account_code = _field(line, "account_code")

        if entry_id is None:
            raise LedgerInvariantError(f"JournalLine {index}: entry_id is required")
        if account_id is None:
            raise LedgerInvariantError(f"JournalLine {index}: account_id is required")
        if account_code is None or not str(account_code).strip():
            raise LedgerInvariantError(f"JournalLine {index}: account_code is required")

        debit, credit = validate_journal_line_money(line, index=index)
        total_debit += debit
        total_credit += credit

    if total_debit != total_credit:
        raise LedgerInvariantError(
            "JournalEntry is unbalanced: "
            f"debit={total_debit} credit={total_credit}"
        )
