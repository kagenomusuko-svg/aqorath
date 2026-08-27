"""Pure formal Balance Sheet projection from a financial report snapshot.

This module owns presentation structure only. Net statement totals are delegated
exactly once to :mod:`aqorath.financial_statement_semantics`; account lines are
projected directly from ``ledger_balance`` so contra accounts retain their
reducing sign. No storage, catalog, runtime, export, rendering, or balancing
fallback lives here.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Tuple

from . import financial_statement_semantics as _semantics


@dataclass(frozen=True)
class BalanceSheetLine:
    account_code: str
    account_name: str
    account_subtype: str
    amount: Decimal


@dataclass(frozen=True)
class BalanceSheetSection:
    account_type: str
    lines: Tuple[BalanceSheetLine, ...]
    total: Decimal


@dataclass(frozen=True)
class BalanceSheetView:
    as_of: Optional[str]
    assets: BalanceSheetSection
    liabilities: BalanceSheetSection
    recorded_equity: BalanceSheetSection
    current_result: Decimal
    total_equity: Decimal
    liabilities_and_equity: Decimal
    balance_difference: Decimal


def build_balance_sheet_view(snapshot):
    """Project one immutable snapshot into a formal Balance Sheet view.

    Net totals and the accounting-equation check remain authoritative in
    ``financial_statement_semantics``. This function only selects Balance Sheet
    accounts, preserves their identity/order, and applies statement presentation
    signs to their exact ``ledger_balance`` values.
    """
    totals = _semantics.compute_financial_statement_totals(snapshot)

    asset_lines = []
    liability_lines = []
    equity_lines = []

    for line in snapshot.lines:
        if line.account_type == "Activo":
            asset_lines.append(
                BalanceSheetLine(
                    account_code=line.account_code,
                    account_name=line.account_name,
                    account_subtype=line.account_subtype,
                    amount=line.ledger_balance,
                )
            )
        elif line.account_type == "Pasivo":
            liability_lines.append(
                BalanceSheetLine(
                    account_code=line.account_code,
                    account_name=line.account_name,
                    account_subtype=line.account_subtype,
                    amount=-line.ledger_balance,
                )
            )
        elif line.account_type == "Patrimonio":
            equity_lines.append(
                BalanceSheetLine(
                    account_code=line.account_code,
                    account_name=line.account_name,
                    account_subtype=line.account_subtype,
                    amount=-line.ledger_balance,
                )
            )

    return BalanceSheetView(
        as_of=totals.as_of,
        assets=BalanceSheetSection(
            account_type="Activo",
            lines=tuple(asset_lines),
            total=totals.assets,
        ),
        liabilities=BalanceSheetSection(
            account_type="Pasivo",
            lines=tuple(liability_lines),
            total=totals.liabilities,
        ),
        recorded_equity=BalanceSheetSection(
            account_type="Patrimonio",
            lines=tuple(equity_lines),
            total=totals.recorded_equity,
        ),
        current_result=totals.result,
        total_equity=totals.total_equity,
        liabilities_and_equity=totals.liabilities_and_equity,
        balance_difference=totals.balance_difference,
    )
