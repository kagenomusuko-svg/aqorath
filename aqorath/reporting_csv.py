"""Deterministic CSV renderer for immutable financial-report snapshots.

This module is presentation-only. It consumes an already-built
``FinancialReportSnapshot`` and serializes it without recalculating accounting,
querying storage, loading catalog data, or writing files.
"""

import csv
from io import StringIO

from .reporting import FinancialReportSnapshot


_HEADER = (
    "record_type",
    "account_code",
    "account_name",
    "account_type",
    "account_subtype",
    "nature",
    "ledger_balance",
    "normal_balance",
    "amount",
    "as_of",
)


def render_financial_report_csv(snapshot):
    """Serialize one ``FinancialReportSnapshot`` to deterministic CSV text."""
    if not isinstance(snapshot, FinancialReportSnapshot):
        raise TypeError("snapshot must be a FinancialReportSnapshot")

    as_of = "" if snapshot.as_of is None else snapshot.as_of
    output = StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(_HEADER)

    for line in snapshot.lines:
        writer.writerow(
            (
                "ACCOUNT",
                line.account_code,
                line.account_name,
                line.account_type,
                line.account_subtype,
                line.nature,
                str(line.ledger_balance),
                str(line.normal_balance),
                "",
                as_of,
            )
        )

    for total in snapshot.totals:
        writer.writerow(
            (
                "TOTAL",
                "",
                "",
                total.account_type,
                "",
                "",
                "",
                "",
                str(total.amount),
                as_of,
            )
        )

    writer.writerow(
        (
            "RESULT",
            "",
            "Resultado del ejercicio",
            "",
            "",
            "",
            "",
            "",
            str(snapshot.result),
            as_of,
        )
    )

    return output.getvalue()
