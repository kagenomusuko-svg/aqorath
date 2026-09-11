"""Exact period reporting derived from the canonical SQLite ledger.

AQR-013 needs a professional trial balance for an explicit range. This module does
not persist balances and does not create another ledger. Opening/closing balances
are delegated to the existing canonical SQLite balance authority; period debits and
credits are read from the same JournalLine/JournalEntry truth and reconciled back to
those balances before a view is returned.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
import sqlite3

from . import core as _core
from . import reporting_source as _reporting_source


@dataclass(frozen=True)
class PeriodTrialBalanceLine:
    account_code: str
    account_name: str
    nature: str
    opening_balance: Decimal
    debit: Decimal
    credit: Decimal
    closing_balance: Decimal


@dataclass(frozen=True)
class PeriodTrialBalanceView:
    from_date: date
    to_date: date
    lines: tuple[PeriodTrialBalanceLine, ...]
    total_debit: Decimal
    total_credit: Decimal


def _require_date(value, name):
    if type(value) is not date:
        raise TypeError(f"{name} must be date")


def _opening_balances(path, from_date):
    if from_date == date.min:
        return {}
    prior = from_date - timedelta(days=1)
    return _core._balances_from_sqlite(path, as_of=prior.isoformat())


def _movement_rows(path, from_date, to_date):
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info('journalline')")
        columns = {row[1] for row in cur.fetchall()}
        if "debit" not in columns or "credit" not in columns:
            raise RuntimeError("journalline must expose debit and credit")
        has_code = "account_code" in columns
        has_id = "account_id" in columns
        if not has_code and not has_id:
            raise RuntimeError("journalline must reference an account")

        if has_code and has_id:
            account_expr = "COALESCE(jl.account_code, a.code)"
        elif has_code:
            account_expr = "jl.account_code"
        else:
            account_expr = "a.code"

        sql = f"""
            SELECT {account_expr} AS account_code, jl.debit, jl.credit
            FROM journalline jl
            LEFT JOIN account a ON jl.account_id = a.id
            JOIN journalentry je ON jl.entry_id = je.id
            WHERE DATE(SUBSTR(je.date, 1, 10)) >= ?
              AND DATE(SUBSTR(je.date, 1, 10)) <= ?
            ORDER BY je.date, je.id, jl.id
        """
        cur.execute(sql, (from_date.isoformat(), to_date.isoformat()))
        return cur.fetchall()
    finally:
        conn.close()


def build_period_trial_balance_from_sqlite(db_path, from_date, to_date):
    """Return a reconciled range trial balance from one explicit SQLite authority."""
    _require_date(from_date, "from_date")
    _require_date(to_date, "to_date")
    if to_date < from_date:
        raise ValueError("to_date cannot precede from_date")

    path = _reporting_source._explicit_existing_db_path(db_path)
    identities = _reporting_source._load_account_identities_from_sqlite(path)
    opening = _opening_balances(path, from_date)
    closing = _core._balances_from_sqlite(path, as_of=to_date.isoformat())

    debits = {}
    credits = {}
    for account_code, raw_debit, raw_credit in _movement_rows(path, from_date, to_date):
        if account_code is None or str(account_code) == "":
            raise RuntimeError("period movement references an account without code")
        code = str(account_code)
        if code not in identities:
            raise LookupError(f"period movement account is not present in Account: {code!r}")
        debits[code] = debits.get(code, Decimal("0")) + Decimal(str(raw_debit or 0))
        credits[code] = credits.get(code, Decimal("0")) + Decimal(str(raw_credit or 0))

    codes = sorted(
        set(identities) | set(opening) | set(closing) | set(debits) | set(credits)
    )
    lines = []
    total_debit = Decimal("0")
    total_credit = Decimal("0")

    for code in codes:
        identity = identities.get(code)
        if identity is None:
            raise LookupError(f"no account identity for report account {code!r}")
        opening_balance = opening.get(code, Decimal("0"))
        debit = debits.get(code, Decimal("0"))
        credit = credits.get(code, Decimal("0"))
        closing_balance = closing.get(code, Decimal("0"))
        expected_closing = opening_balance + debit - credit
        if expected_closing != closing_balance:
            raise RuntimeError(
                f"period trial balance does not reconcile for account {code!r}: "
                f"expected {expected_closing}, got {closing_balance}"
            )
        total_debit += debit
        total_credit += credit
        lines.append(
            PeriodTrialBalanceLine(
                account_code=code,
                account_name=identity.name,
                nature=identity.nature,
                opening_balance=opening_balance,
                debit=debit,
                credit=credit,
                closing_balance=closing_balance,
            )
        )

    if total_debit != total_credit:
        raise RuntimeError(
            f"period debits and credits do not balance: {total_debit} != {total_credit}"
        )

    return PeriodTrialBalanceView(
        from_date=from_date,
        to_date=to_date,
        lines=tuple(lines),
        total_debit=total_debit,
        total_credit=total_credit,
    )
