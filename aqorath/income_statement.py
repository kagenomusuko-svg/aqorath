"""Pure formal Income Statement view derived from a financial report snapshot.

This module is presentation-structuring only. It selects the income-statement
portion of an already-authoritative ``FinancialReportSnapshot`` and preserves the
snapshot's supplied totals and result verbatim. It does not recalculate accounting,
query storage, load catalog data, or render files.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Tuple

from .reporting import FinancialReportLine, FinancialReportSnapshot


@dataclass(frozen=True)
class IncomeStatementSection:
    account_type: str
    lines: Tuple[FinancialReportLine, ...]
    total: Decimal


@dataclass(frozen=True)
class IncomeStatementView:
    as_of: Optional[str]
    income: IncomeStatementSection
    costs: IncomeStatementSection
    expenses: IncomeStatementSection
    result: Decimal


def _required_total(snapshot: FinancialReportSnapshot, account_type: str) -> Decimal:
    matches = tuple(
        total for total in snapshot.totals
        if total.account_type == account_type
    )
    if len(matches) != 1:
        raise ValueError(
            f"Income statement requires exactly one {account_type!r} total, "
            f"found {len(matches)}"
        )

    amount = matches[0].amount
    if not isinstance(amount, Decimal):
        raise TypeError(
            f"Income statement total for {account_type!r} must be Decimal"
        )
    return amount


def _section(snapshot: FinancialReportSnapshot, account_type: str) -> IncomeStatementSection:
    lines = tuple(
        line for line in snapshot.lines
        if line.account_type == account_type
    )
    return IncomeStatementSection(
        account_type=account_type,
        lines=lines,
        total=_required_total(snapshot, account_type),
    )


def build_income_statement_view(snapshot):
    """Project one immutable financial snapshot into a formal income statement view."""
    if not isinstance(snapshot, FinancialReportSnapshot):
        raise TypeError("snapshot must be a FinancialReportSnapshot")
    if not isinstance(snapshot.result, Decimal):
        raise TypeError("snapshot.result must be Decimal")

    return IncomeStatementView(
        as_of=snapshot.as_of,
        income=_section(snapshot, "Ingreso"),
        costs=_section(snapshot, "Costo"),
        expenses=_section(snapshot, "Gasto"),
        result=snapshot.result,
    )
