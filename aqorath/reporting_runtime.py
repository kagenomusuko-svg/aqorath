"""Canonical reporting runtime orchestration.

This layer resolves Aqorath's canonical local SQLite path and canonical reporting
catalog once, then delegates all accounting/report construction to the explicit
same-SQLite reporting source. It also composes formal statement views and coherent
statement bundles from the canonical immutable snapshot. It owns orchestration
only: no accounting math, rendering, posting, or fallback authority lives here.
"""

from . import accounting_rules as _accounting_rules
from . import balance_sheet as _balance_sheet
from . import financial_statements as _financial_statements
from . import income_statement as _income_statement
from . import reporting_source as _reporting_source
from . import storage as _storage


def get_financial_report_snapshot(as_of=None):
    """Return the canonical immutable financial report snapshot."""
    db_path = _storage.get_db_path()
    catalog = _accounting_rules.load_catalog()
    return _reporting_source.build_financial_report_snapshot_from_sqlite(
        db_path,
        catalog,
        as_of=as_of,
    )


def get_income_statement_view(as_of=None):
    """Return the formal Income Statement view of one canonical snapshot."""
    snapshot = get_financial_report_snapshot(as_of=as_of)
    return _income_statement.build_income_statement_view(snapshot)


def get_balance_sheet_view(as_of=None):
    """Return the formal Balance Sheet view of one canonical snapshot."""
    snapshot = get_financial_report_snapshot(as_of=as_of)
    return _balance_sheet.build_balance_sheet_view(snapshot)


def get_financial_statements_bundle(as_of=None):
    """Return coherent formal statements built from one canonical snapshot."""
    snapshot = get_financial_report_snapshot(as_of=as_of)
    return _financial_statements.build_financial_statements_bundle(snapshot)
