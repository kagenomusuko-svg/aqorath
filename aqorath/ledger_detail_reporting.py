"""Professional journal and general-ledger views from the canonical SQLite ledger.

These are read-only projections over JournalEntry/JournalLine/Account. Running balances
are reconstructed from the existing canonical balance authority plus exact lines in the
requested range. No report balance is persisted.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
import sqlite3

from . import core as _core
from . import reporting_source as _reporting_source


@dataclass(frozen=True)
class JournalReportLine:
    line_id: int
    account_code: str
    account_name: str
    debit: Decimal
    credit: Decimal
    description: str


@dataclass(frozen=True)
class JournalReportEntry:
    entry_id: int
    posting_date: date
    concept: str
    state: str | None
    lines: tuple[JournalReportLine, ...]
    total_debit: Decimal
    total_credit: Decimal


@dataclass(frozen=True)
class JournalReportView:
    from_date: date
    to_date: date
    entries: tuple[JournalReportEntry, ...]


@dataclass(frozen=True)
class GeneralLedgerMovement:
    entry_id: int
    line_id: int
    posting_date: date
    concept: str
    description: str
    debit: Decimal
    credit: Decimal
    running_balance: Decimal


@dataclass(frozen=True)
class GeneralLedgerAccount:
    account_code: str
    account_name: str
    nature: str
    opening_balance: Decimal
    movements: tuple[GeneralLedgerMovement, ...]
    total_debit: Decimal
    total_credit: Decimal
    closing_balance: Decimal


@dataclass(frozen=True)
class GeneralLedgerView:
    from_date: date
    to_date: date
    accounts: tuple[GeneralLedgerAccount, ...]


def _require_range(from_date, to_date):
    if type(from_date) is not date or type(to_date) is not date:
        raise TypeError("from_date and to_date must be date")
    if to_date < from_date:
        raise ValueError("to_date cannot precede from_date")


def _open(path):
    return sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)


def _columns(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info('{table}')").fetchall()}


def _date_value(raw):
    return date.fromisoformat(str(raw)[:10])


def _read_rows(path, from_date, to_date):
    conn = _open(path)
    try:
        line_cols = _columns(conn, "journalline")
        entry_cols = _columns(conn, "journalentry")
        if not {"id", "entry_id", "debit", "credit"}.issubset(line_cols):
            raise RuntimeError("journalline schema cannot support professional reporting")
        if not {"id", "date"}.issubset(entry_cols):
            raise RuntimeError("journalentry schema cannot support professional reporting")

        if "account_code" in line_cols and "account_id" in line_cols:
            account_expr = "COALESCE(jl.account_code, a.code)"
        elif "account_code" in line_cols:
            account_expr = "jl.account_code"
        elif "account_id" in line_cols:
            account_expr = "a.code"
        else:
            raise RuntimeError("journalline has no account reference")

        state_expr = "je.state" if "state" in entry_cols else "NULL"
        line_description_expr = "COALESCE(jl.description, '')" if "description" in line_cols else "''"
        concept_expr = "COALESCE(je.concept, '')" if "concept" in entry_cols else "''"
        sql = f"""
            SELECT je.id, je.date, {concept_expr}, {state_expr},
                   jl.id, {account_expr}, a.name,
                   jl.debit, jl.credit, {line_description_expr}
            FROM journalentry je
            JOIN journalline jl ON jl.entry_id = je.id
            LEFT JOIN account a ON jl.account_id = a.id
            WHERE DATE(SUBSTR(je.date, 1, 10)) >= ?
              AND DATE(SUBSTR(je.date, 1, 10)) <= ?
            ORDER BY je.date, je.id, jl.id
        """
        return conn.execute(
            sql, (from_date.isoformat(), to_date.isoformat())
        ).fetchall()
    finally:
        conn.close()


def build_journal_report_from_sqlite(db_path, from_date, to_date):
    _require_range(from_date, to_date)
    path = _reporting_source._explicit_existing_db_path(db_path)
    identities = _reporting_source._load_account_identities_from_sqlite(path)
    rows = _read_rows(path, from_date, to_date)

    entries = []
    current_id = None
    current_header = None
    current_lines = []
    debit_total = Decimal("0")
    credit_total = Decimal("0")

    def flush():
        if current_id is None:
            return
        if debit_total != credit_total:
            raise RuntimeError(f"journal entry {current_id} is not balanced")
        entries.append(
            JournalReportEntry(
                entry_id=current_id,
                posting_date=current_header[0],
                concept=current_header[1],
                state=current_header[2],
                lines=tuple(current_lines),
                total_debit=debit_total,
                total_credit=credit_total,
            )
        )

    for entry_id, raw_date, concept, state, line_id, code, account_name, raw_debit, raw_credit, description in rows:
        if entry_id != current_id:
            flush()
            current_id = entry_id
            current_header = (_date_value(raw_date), str(concept or ""), state)
            current_lines = []
            debit_total = Decimal("0")
            credit_total = Decimal("0")
        if code is None or str(code) not in identities:
            raise LookupError(f"journal line {line_id} has no canonical account identity")
        code = str(code)
        identity = identities[code]
        debit = Decimal(str(raw_debit or 0))
        credit = Decimal(str(raw_credit or 0))
        debit_total += debit
        credit_total += credit
        current_lines.append(
            JournalReportLine(
                line_id=int(line_id),
                account_code=code,
                account_name=identity.name if identity.name else str(account_name or ""),
                debit=debit,
                credit=credit,
                description=str(description or ""),
            )
        )
    flush()
    return JournalReportView(from_date, to_date, tuple(entries))


def build_general_ledger_from_sqlite(db_path, from_date, to_date):
    _require_range(from_date, to_date)
    path = _reporting_source._explicit_existing_db_path(db_path)
    identities = _reporting_source._load_account_identities_from_sqlite(path)
    if from_date == date.min:
        opening = {}
    else:
        opening = _core._balances_from_sqlite(
            path, as_of=(from_date - timedelta(days=1)).isoformat()
        )
    closing = _core._balances_from_sqlite(path, as_of=to_date.isoformat())
    rows = _read_rows(path, from_date, to_date)

    movements_by_code = {}
    for entry_id, raw_date, concept, _state, line_id, code, _account_name, raw_debit, raw_credit, description in rows:
        if code is None or str(code) not in identities:
            raise LookupError(f"journal line {line_id} has no canonical account identity")
        code = str(code)
        movements_by_code.setdefault(code, []).append(
            (
                int(entry_id),
                int(line_id),
                _date_value(raw_date),
                str(concept or ""),
                str(description or ""),
                Decimal(str(raw_debit or 0)),
                Decimal(str(raw_credit or 0)),
            )
        )

    codes = sorted(set(identities) | set(opening) | set(closing) | set(movements_by_code))
    accounts = []
    for code in codes:
        identity = identities.get(code)
        if identity is None:
            raise LookupError(f"no account identity for ledger account {code!r}")
        running = opening.get(code, Decimal("0"))
        movements = []
        total_debit = Decimal("0")
        total_credit = Decimal("0")
        for entry_id, line_id, posting_date, concept, description, debit, credit in movements_by_code.get(code, ()):
            total_debit += debit
            total_credit += credit
            running += debit - credit
            movements.append(
                GeneralLedgerMovement(
                    entry_id,
                    line_id,
                    posting_date,
                    concept,
                    description,
                    debit,
                    credit,
                    running,
                )
            )
        authoritative_closing = closing.get(code, Decimal("0"))
        if running != authoritative_closing:
            raise RuntimeError(
                f"general ledger does not reconcile for account {code!r}: "
                f"{running} != {authoritative_closing}"
            )
        accounts.append(
            GeneralLedgerAccount(
                account_code=code,
                account_name=identity.name,
                nature=identity.nature,
                opening_balance=opening.get(code, Decimal("0")),
                movements=tuple(movements),
                total_debit=total_debit,
                total_credit=total_credit,
                closing_balance=authoritative_closing,
            )
        )
    return GeneralLedgerView(from_date, to_date, tuple(accounts))
