"""Deliberately narrow, deterministic CSV adapter for bank evidence."""

import csv
import hashlib
import io
from datetime import date
from decimal import Decimal, InvalidOperation


REQUIRED_COLUMNS = ("date", "reference", "amount")
OPTIONAL_COLUMNS = ("balance",)


def _decimal(raw, field, row_number):
    try:
        value = Decimal(raw.strip())
    except (AttributeError, InvalidOperation) as exc:
        raise ValueError(f"row {row_number}: invalid {field}") from exc
    if not value.is_finite() or value == 0:
        raise ValueError(f"row {row_number}: {field} must be finite and non-zero")
    return value


def parse_bank_csv(content):
    """Parse the explicit V1 CSV contract without guessing column meanings."""
    if not isinstance(content, str):
        raise TypeError("content must be str")
    reader = csv.DictReader(io.StringIO(content, newline=""))
    if reader.fieldnames is None or any(name not in reader.fieldnames for name in REQUIRED_COLUMNS):
        raise ValueError("CSV must contain date, reference, and amount columns")
    unexpected = set(reader.fieldnames) - set(REQUIRED_COLUMNS) - set(OPTIONAL_COLUMNS)
    if unexpected:
        raise ValueError(f"unsupported CSV columns: {', '.join(sorted(unexpected))}")
    result = []
    for row_number, row in enumerate(reader, 2):
        if None in row:
            raise ValueError(f"row {row_number}: too many CSV fields")
        try:
            movement_date = date.fromisoformat(row["date"].strip())
        except (AttributeError, ValueError) as exc:
            raise ValueError(f"row {row_number}: date must be ISO YYYY-MM-DD") from exc
        reference = row["reference"].strip()
        if not reference:
            raise ValueError(f"row {row_number}: reference must be non-empty")
        signed = _decimal(row["amount"], "amount", row_number)
        balance = None
        if "balance" in reader.fieldnames and row.get("balance", "").strip():
            try:
                balance = Decimal(row["balance"].strip())
            except (InvalidOperation, AttributeError) as exc:
                raise ValueError(f"row {row_number}: invalid balance") from exc
            if not balance.is_finite():
                raise ValueError(f"row {row_number}: balance must be finite")
        canonical = "|".join((movement_date.isoformat(), reference, str(signed), "" if balance is None else str(balance)))
        result.append({
            "transaction_date": movement_date,
            "reference": reference,
            "amount": abs(signed),
            "direction": "credit" if signed > 0 else "debit",
            "external_balance": balance,
            "fingerprint": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        })
    return tuple(result)


__all__ = ["parse_bank_csv", "REQUIRED_COLUMNS", "OPTIONAL_COLUMNS"]
