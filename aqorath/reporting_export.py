"""Canonical financial-report export orchestration.

This layer composes the canonical reporting runtime with presentation renderers.
It does not resolve storage/catalog authorities itself, recalculate accounting,
or write files.
"""

from . import financial_statements_xlsx as _financial_statements_xlsx
from . import reporting_csv as _reporting_csv
from . import reporting_runtime as _reporting_runtime
from . import reporting_xlsx as _reporting_xlsx


def get_financial_report_csv(as_of=None):
    """Return canonical financial-report CSV text for the requested cutoff."""
    snapshot = _reporting_runtime.get_financial_report_snapshot(as_of=as_of)
    return _reporting_csv.render_financial_report_csv(snapshot)


def get_financial_report_xlsx(as_of=None):
    """Return canonical raw financial-report XLSX bytes for the requested cutoff."""
    snapshot = _reporting_runtime.get_financial_report_snapshot(as_of=as_of)
    return _reporting_xlsx.render_financial_report_xlsx(snapshot)


def get_financial_statements_xlsx(as_of=None):
    """Return formal coherent financial-statements XLSX bytes."""
    bundle = _reporting_runtime.get_financial_statements_bundle(as_of=as_of)
    return _financial_statements_xlsx.render_financial_statements_xlsx(bundle)
