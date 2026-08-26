"""Canonical financial-report export orchestration.

This layer composes the canonical reporting runtime with presentation renderers.
It does not resolve storage/catalog authorities itself, recalculate accounting,
or write files.
"""

from . import reporting_csv as _reporting_csv
from . import reporting_runtime as _reporting_runtime


def get_financial_report_csv(as_of=None):
    """Return canonical financial-report CSV text for the requested cutoff."""
    snapshot = _reporting_runtime.get_financial_report_snapshot(as_of=as_of)
    return _reporting_csv.render_financial_report_csv(snapshot)
