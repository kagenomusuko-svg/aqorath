"""Pure formal Income Statement projection from a financial report snapshot.

Formal Income Statement totals are ledger-based net semantics. The historical
snapshot ``totals`` and ``result`` fields summarize normal balances and therefore
are not authoritative for contra-income or contra-expense presentation. This
module delegates net totals exactly once to ``financial_statement_semantics`` and
only structures the supplied profit-and-loss lines for presentation.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Tuple

from . import financial_statement_semantics as _semantics
from .reporting import FinancialReportLine


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


def _section(snapshot, account_type: str, total: Decimal) -> IncomeStatementSection:
    return IncomeStatementSection(
        account_type=account_type,
        lines=tuple(
            line for line in snapshot.lines
            if line.account_type == account_type
        ),
        total=total,
    )


def build_income_statement_view(snapshot):
    """Project one snapshot into a formal ledger-net Income Statement view."""
    totals = _semantics.compute_financial_statement_totals(snapshot)

    return IncomeStatementView(
        as_of=totals.as_of,
        income=_section(snapshot, "Ingreso", totals.income),
        costs=_section(snapshot, "Costo", totals.costs),
        expenses=_section(snapshot, "Gasto", totals.expenses),
        result=totals.result,
    )
