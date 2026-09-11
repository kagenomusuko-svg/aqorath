"""Canonical range reporting projection over the existing SQLite ledger.

This adapter reads only Account, JournalEntry and JournalLine from the same explicit
SQLite file used by the established reporting authority.  It never persists report
figures.  Opening and closing balances are delegated to ``core._balances_from_sqlite``;
period debit/credit movement is read exactly from JournalLine using Decimal and is
reconciled account-by-account to those canonical balances.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
import sqlite3

from . import core as _core
from . import reporting as _reporting
from . import reporting_source as _reporting_source


@dataclass(frozen=True)
class PeriodTrialBalanceLine:
    account_code: str
    account_name: str
    opening_balance: Decimal
    debits: Decimal
    credits: Decimal
    closing_balance: Decimal


@dataclass(frozen=True)
class PeriodTrialBalance:
    from_date: date
    to_date: date
    lines: tuple[PeriodTrialBalanceLine, ...]
    total_debits: Decimal
    total_credits: Decimal


@dataclass(frozen=True)
class PeriodReportingSnapshot:
    from_date: date
    to_date: date
    trial_balance: PeriodTrialBalance
    movement_snapshot: _reporting.FinancialReportSnapshot
    closing_snapshot: _reporting.FinancialReportSnapshot


def _require_exact_date(value, field_name):
    if type(value) is not date:
        raise TypeError(f"{field_name} must be date")


def _zero_balances(accounts_by_code):
    return {code: Decimal("0") for code in accounts_by_code}


def _canonical_balances(path, accounts_by_code, as_of):
    balances = dict(_core._balances_from_sqlite(path, as_of=as_of))
    for code in accounts_by_code:
        balances.setdefault(code, Decimal("0"))
    unknown = set(balances).difference(accounts_by_code)
    if unknown:
        raise ValueError(
            "canonical balances reference unknown Account codes: "
            + ", ".join(sorted(unknown))
        )
    return balances


def _period_movements(path, accounts_by_code, from_date, to_date):
    movements = {
        code: [Decimal("0"), Decimal("0")]
        for code in accounts_by_code
    }
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        rows = conn.execute(
            """
            SELECT COALESCE(jl.account_code, a.code), jl.debit, jl.credit
            FROM journalline jl
            JOIN journalentry je ON je.id = jl.entry_id
            LEFT JOIN account a ON a.id = jl.account_id
            WHERE DATE(SUBSTR(je.date, 1, 10)) >= ?
              AND DATE(SUBSTR(je.date, 1, 10)) <= ?
            ORDER BY je.date, je.id, jl.id
            """,
            (from_date.isoformat(), to_date.isoformat()),
        ).fetchall()
    finally:
        conn.close()

    for code, debit, credit in rows:
        if code is None or str(code) not in accounts_by_code:
            raise ValueError("JournalLine references no governed Account identity")
        key = str(code)
        movements[key][0] += Decimal(str(debit or 0))
        movements[key][1] += Decimal(str(credit or 0))
    return movements


def build_period_reporting_snapshot_from_sqlite(
    db_path,
    catalog,
    *,
    from_date,
    to_date,
):
    """Build one reconciled inclusive-range reporting snapshot from canonical truth."""
    _require_exact_date(from_date, "from_date")
    _require_exact_date(to_date, "to_date")
    if to_date < from_date:
        raise ValueError("to_date cannot precede from_date")

    path = _reporting_source._explicit_existing_db_path(db_path)
    accounts_by_code = _reporting_source._load_account_identities_from_sqlite(path)

    if from_date == date.min:
        opening = _zero_balances(accounts_by_code)
    else:
        opening = _canonical_balances(
            path,
            accounts_by_code,
            (from_date - timedelta(days=1)).isoformat(),
        )
    closing = _canonical_balances(
        path,
        accounts_by_code,
        to_date.isoformat(),
    )
    movements = _period_movements(path, accounts_by_code, from_date, to_date)

    lines = []
    movement_balances = {}
    total_debits = Decimal("0")
    total_credits = Decimal("0")
    for code in sorted(accounts_by_code):
        debits, credits = movements[code]
        expected_closing = opening[code] + debits - credits
        if expected_closing != closing[code]:
            raise RuntimeError(
                f"period reporting failed ledger reconciliation for Account {code}"
            )
        lines.append(
            PeriodTrialBalanceLine(
                account_code=code,
                account_name=accounts_by_code[code].name,
                opening_balance=opening[code],
                debits=debits,
                credits=credits,
                closing_balance=closing[code],
            )
        )
        movement_balances[code] = debits - credits
        total_debits += debits
        total_credits += credits

    if total_debits != total_credits:
        raise RuntimeError("period JournalLine movement violates double-entry balance")

    movement_snapshot = _reporting.build_financial_report_snapshot(
        movement_balances,
        accounts_by_code,
        catalog,
        as_of=to_date.isoformat(),
    )
    closing_snapshot = _reporting.build_financial_report_snapshot(
        closing,
        accounts_by_code,
        catalog,
        as_of=to_date.isoformat(),
    )
    return PeriodReportingSnapshot(
        from_date=from_date,
        to_date=to_date,
        trial_balance=PeriodTrialBalance(
            from_date=from_date,
            to_date=to_date,
            lines=tuple(lines),
            total_debits=total_debits,
            total_credits=total_credits,
        ),
        movement_snapshot=movement_snapshot,
        closing_snapshot=closing_snapshot,
    )
