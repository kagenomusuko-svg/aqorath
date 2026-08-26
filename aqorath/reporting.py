"""Presentation-agnostic financial reporting snapshots.

This module transforms already-authoritative accounting balances plus supplied account
identity/classification data into an immutable reporting snapshot.  It does not read
SQLite, open sessions, load files, post entries, or render documents.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Optional, Tuple

from . import accounting_rules as _accounting_rules


_REPORT_TYPES = (
    "Activo",
    "Pasivo",
    "Patrimonio",
    "Ingreso",
    "Costo",
    "Gasto",
)


@dataclass(frozen=True)
class FinancialReportLine:
    account_code: str
    account_name: str
    account_type: str
    account_subtype: str
    nature: str
    ledger_balance: Decimal
    normal_balance: Decimal


@dataclass(frozen=True)
class FinancialReportTotal:
    account_type: str
    amount: Decimal


@dataclass(frozen=True)
class FinancialReportSnapshot:
    as_of: Optional[str]
    lines: Tuple[FinancialReportLine, ...]
    totals: Tuple[FinancialReportTotal, ...]
    result: Decimal


def _classification_for(code: str, catalog: Mapping[str, dict]) -> tuple[str, str]:
    entry = _accounting_rules.resolve_catalog_entry_for_account_code(code, catalog)
    if not entry:
        raise LookupError(f"No accounting classification found for account {code!r}")

    raw_type = (
        entry.get("tipo")
        or entry.get("Tipo")
        or entry.get("tipo_contable")
        or ""
    )
    account_type = str(raw_type).strip().capitalize()
    if account_type not in _REPORT_TYPES:
        raise ValueError(
            f"Unsupported accounting classification for account {code!r}: "
            f"{raw_type!r}"
        )

    raw_subtype = entry.get("subtipo")
    if raw_subtype is None:
        raw_subtype = entry.get("Subtipo")
    account_subtype = "" if raw_subtype is None else str(raw_subtype).strip()
    return account_type, account_subtype


def build_financial_report_snapshot(
    balances,
    accounts_by_code,
    catalog,
    as_of=None,
):
    """Build an immutable financial-report snapshot from supplied authoritative data.

    ``balances`` must contain exact ``Decimal`` ledger-signed balances (debit minus
    credit).  ``accounts_by_code`` supplies the real account identity/name/nature,
    while ``catalog`` supplies canonical reporting classification. Entity extension
    codes inherit classification from their canonical parent through Aqorath's
    governed catalog rules.
    """
    if not isinstance(balances, Mapping):
        raise TypeError("balances must be a mapping of account code to Decimal")
    if not isinstance(accounts_by_code, Mapping):
        raise TypeError("accounts_by_code must be a mapping")
    if not isinstance(catalog, Mapping):
        raise TypeError("catalog must be a mapping")
    if as_of is not None and not isinstance(as_of, str):
        raise TypeError("as_of must be a string or None")

    totals_by_type = {account_type: Decimal("0") for account_type in _REPORT_TYPES}
    lines = []

    for raw_code in sorted(balances, key=lambda value: str(value)):
        if not isinstance(raw_code, str) or not raw_code:
            raise TypeError("report account codes must be non-empty strings")
        code = raw_code
        ledger_balance = balances[raw_code]
        if not isinstance(ledger_balance, Decimal):
            raise TypeError(
                f"Balance for account {code!r} must be Decimal, "
                f"got {type(ledger_balance).__name__}"
            )

        try:
            account = accounts_by_code[code]
        except (KeyError, TypeError) as exc:
            raise LookupError(
                f"No account identity supplied for balance account {code!r}"
            ) from exc

        account_code = getattr(account, "code", None)
        if account_code != code:
            raise ValueError(
                f"Account identity mismatch for {code!r}: account.code={account_code!r}"
            )

        account_name = getattr(account, "name", None)
        nature = getattr(account, "nature", None)
        if not isinstance(account_name, str) or not account_name.strip():
            raise ValueError(f"Account {code!r} must have a non-empty name")
        if not isinstance(nature, str) or not nature.strip():
            raise ValueError(f"Account {code!r} must have a valid nature")

        account_type, account_subtype = _classification_for(code, catalog)
        normal_balance = _accounting_rules.normal_balance_amount(
            ledger_balance,
            nature,
        )

        line = FinancialReportLine(
            account_code=code,
            account_name=account_name,
            account_type=account_type,
            account_subtype=account_subtype,
            nature=nature,
            ledger_balance=ledger_balance,
            normal_balance=normal_balance,
        )
        lines.append(line)
        totals_by_type[account_type] += normal_balance

    totals = tuple(
        FinancialReportTotal(
            account_type=account_type,
            amount=totals_by_type[account_type],
        )
        for account_type in _REPORT_TYPES
    )
    result = (
        totals_by_type["Ingreso"]
        - totals_by_type["Costo"]
        - totals_by_type["Gasto"]
    )

    return FinancialReportSnapshot(
        as_of=as_of,
        lines=tuple(lines),
        totals=totals,
        result=result,
    )
