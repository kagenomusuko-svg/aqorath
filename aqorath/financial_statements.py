"""Coherent immutable bundle of formal financial statements.

A bundle is built from exactly one supplied ``FinancialReportSnapshot``. The same
snapshot object is passed, once each and in deterministic order, to the formal
Income Statement and Balance Sheet projectors. No runtime, storage, catalog,
rendering, or alternate snapshot discovery belongs here.
"""

from dataclasses import dataclass

from . import balance_sheet as _balance_sheet
from . import income_statement as _income_statement
from .reporting import FinancialReportSnapshot


@dataclass(frozen=True)
class FinancialStatementsBundle:
    snapshot: FinancialReportSnapshot
    income_statement: _income_statement.IncomeStatementView
    balance_sheet: _balance_sheet.BalanceSheetView


def build_financial_statements_bundle(snapshot):
    """Build both formal statements from one exact immutable snapshot."""
    if not isinstance(snapshot, FinancialReportSnapshot):
        raise TypeError("snapshot must be a FinancialReportSnapshot")

    income_statement = _income_statement.build_income_statement_view(snapshot)
    balance_sheet = _balance_sheet.build_balance_sheet_view(snapshot)

    return FinancialStatementsBundle(
        snapshot=snapshot,
        income_statement=income_statement,
        balance_sheet=balance_sheet,
    )
