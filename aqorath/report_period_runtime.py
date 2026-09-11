"""Application-facing composition for period financial report products.

One canonical period source snapshot feeds the trial balance, period income statement
and closing balance sheet.  This module owns orchestration only; statement semantics
remain in the existing reporting authorities.
"""

from dataclasses import dataclass

from . import accounting_rules as _accounting_rules
from . import balance_sheet as _balance_sheet
from . import income_statement as _income_statement
from . import report_period_source as _period_source
from . import storage as _storage


@dataclass(frozen=True)
class PeriodFinancialBundle:
    source: _period_source.PeriodReportingSnapshot
    trial_balance: _period_source.PeriodTrialBalance
    income_statement: _income_statement.IncomeStatementView
    balance_sheet: _balance_sheet.BalanceSheetView


def get_period_financial_bundle(from_date, to_date):
    """Build all first-vertical products from one canonical SQLite source snapshot."""
    snapshot = _period_source.build_period_reporting_snapshot_from_sqlite(
        _storage.get_db_path(),
        _accounting_rules.load_catalog(),
        from_date=from_date,
        to_date=to_date,
    )
    return PeriodFinancialBundle(
        source=snapshot,
        trial_balance=snapshot.trial_balance,
        income_statement=_income_statement.build_income_statement_view(
            snapshot.movement_snapshot
        ),
        balance_sheet=_balance_sheet.build_balance_sheet_view(
            snapshot.closing_snapshot
        ),
    )


def get_period_trial_balance(from_date, to_date):
    return get_period_financial_bundle(from_date, to_date).trial_balance


def get_period_income_statement(from_date, to_date):
    return get_period_financial_bundle(from_date, to_date).income_statement


def get_period_balance_sheet(from_date, to_date):
    return get_period_financial_bundle(from_date, to_date).balance_sheet
