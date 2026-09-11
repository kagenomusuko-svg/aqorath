"""Professional journal/general-ledger projections for AQR-013.

The detail layer reads the same JournalEntry/JournalLine SQLite truth as the existing
financial reports and reconciles its movement totals to ``report_period_source``.
It persists nothing and owns no alternative balance semantics.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import sqlite3

from . import report_period_source as _period
from . import reporting_source as _reporting_source


@dataclass(frozen=True)
class JournalDetailLine:
    entry_id: int
    line_id: int
    posting_date: date
    concept: str
    account_code: str
    account_name: str
    debit: Decimal
    credit: Decimal
    description: str


@dataclass(frozen=True)
class JournalDetailReport:
    from_date: date
    to_date: date
    lines: tuple[JournalDetailLine, ...]
    total_debits: Decimal
    total_credits: Decimal


@dataclass(frozen=True)
class GeneralLedgerAccount:
    account_code: str
    account_name: str
    opening_balance: Decimal
    debits: Decimal
    credits: Decimal
    closing_balance: Decimal
    lines: tuple[JournalDetailLine, ...]


@dataclass(frozen=True)
class GeneralLedgerReport:
    from_date: date
    to_date: date
    accounts: tuple[GeneralLedgerAccount, ...]
    total_debits: Decimal
    total_credits: Decimal


def _require_date(value, name):
    if type(value) is not date:
        raise TypeError(f"{name} must be date")


def _read_journal(path, from_date, to_date):
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        rows = conn.execute(
            """
            SELECT je.id, jl.id, je.date, COALESCE(je.concept, ''),
                   COALESCE(jl.account_code, a.code), a.name,
                   jl.debit, jl.credit, COALESCE(jl.description, '')
            FROM journalentry je
            JOIN journalline jl ON jl.entry_id = je.id
            LEFT JOIN account a ON a.id = jl.account_id
            WHERE DATE(SUBSTR(je.date, 1, 10)) >= ?
              AND DATE(SUBSTR(je.date, 1, 10)) <= ?
            ORDER BY je.date, je.id, jl.id
            """,
            (from_date.isoformat(), to_date.isoformat()),
        ).fetchall()
    finally:
        conn.close()

    result = []
    total_debits = Decimal("0")
    total_credits = Decimal("0")
    for entry_id, line_id, raw_date, concept, code, name, debit, credit, description in rows:
        if code is None or name is None:
            raise ValueError("JournalLine cannot be projected without governed Account identity")
        posting_date = datetime.fromisoformat(str(raw_date)).date()
        debit_dec = Decimal(str(debit or 0))
        credit_dec = Decimal(str(credit or 0))
        total_debits += debit_dec
        total_credits += credit_dec
        result.append(
            JournalDetailLine(
                entry_id=int(entry_id),
                line_id=int(line_id),
                posting_date=posting_date,
                concept=str(concept),
                account_code=str(code),
                account_name=str(name),
                debit=debit_dec,
                credit=credit_dec,
                description=str(description),
            )
        )
    if total_debits != total_credits:
        raise RuntimeError("journal detail violates canonical double-entry balance")
    return tuple(result), total_debits, total_credits


def build_journal_and_ledger_from_sqlite(db_path, catalog, *, from_date, to_date):
    """Build journal and mayor together and reconcile them to the period trial balance."""
    _require_date(from_date, "from_date")
    _require_date(to_date, "to_date")
    if to_date < from_date:
        raise ValueError("to_date cannot precede from_date")

    path = _reporting_source._explicit_existing_db_path(db_path)
    period = _period.build_period_reporting_snapshot_from_sqlite(
        path,
        catalog,
        from_date=from_date,
        to_date=to_date,
    )
    lines, total_debits, total_credits = _read_journal(path, from_date, to_date)
    if (
        total_debits != period.trial_balance.total_debits
        or total_credits != period.trial_balance.total_credits
    ):
        raise RuntimeError("journal detail does not reconcile to period trial balance")

    trial_by_code = {
        line.account_code: line
        for line in period.trial_balance.lines
    }
    journal_by_code = {code: [] for code in trial_by_code}
    for line in lines:
        if line.account_code not in journal_by_code:
            raise RuntimeError("journal detail references Account absent from trial balance")
        journal_by_code[line.account_code].append(line)

    accounts = []
    for code in sorted(trial_by_code):
        trial = trial_by_code[code]
        detail = tuple(journal_by_code[code])
        detail_debits = sum((line.debit for line in detail), Decimal("0"))
        detail_credits = sum((line.credit for line in detail), Decimal("0"))
        if detail_debits != trial.debits or detail_credits != trial.credits:
            raise RuntimeError(f"mayor detail failed reconciliation for Account {code}")
        accounts.append(
            GeneralLedgerAccount(
                account_code=code,
                account_name=trial.account_name,
                opening_balance=trial.opening_balance,
                debits=trial.debits,
                credits=trial.credits,
                closing_balance=trial.closing_balance,
                lines=detail,
            )
        )

    return (
        JournalDetailReport(
            from_date=from_date,
            to_date=to_date,
            lines=lines,
            total_debits=total_debits,
            total_credits=total_credits,
        ),
        GeneralLedgerReport(
            from_date=from_date,
            to_date=to_date,
            accounts=tuple(accounts),
            total_debits=total_debits,
            total_credits=total_credits,
        ),
    )
