"""Canonical reporting runtime orchestration.

This layer resolves Aqorath's canonical local SQLite path and canonical reporting
catalog once, then delegates all accounting/report construction to the explicit
same-SQLite reporting source.  It owns orchestration only: no accounting math,
rendering, posting, or fallback authority lives here.
"""

from . import accounting_rules as _accounting_rules
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
