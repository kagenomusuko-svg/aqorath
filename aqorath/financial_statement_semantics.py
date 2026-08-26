"""Pure net semantics for formal financial statements.

``FinancialReportSnapshot.totals`` intentionally summarizes balances by each
account's normal nature. Formal statements need a different projection: contra
accounts must net inside their statement class. This module therefore derives
formal statement totals from ``ledger_balance`` (debit minus credit) only.

No storage, catalog lookup, rendering, persistence, or silent balancing occurs
here. An unbalanced snapshot is rejected explicitly.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from .reporting import FinancialReportSnapshot


@dataclass(frozen=True)
class FinancialStatementTotals:
    as_of: Optional[str]
    assets: Decimal
    liabilities: Decimal
    recorded_equity: Decimal
    income: Decimal
    costs: Decimal
    expenses: Decimal
    result: Decimal
    total_equity: Decimal
    liabilities_and_equity: Decimal
    balance_difference: Decimal


def compute_financial_statement_totals(snapshot):
    """Derive exact net statement totals from one immutable report snapshot.

    ``ledger_balance`` is debit minus credit. Consequently:
    - assets, costs and expenses retain that sign;
    - liabilities, equity and income are sign-inverted for presentation;
    - contra accounts naturally reduce their enclosing statement class.

    The accounting equation must close exactly; no tolerance, rounding or repair
    is applied.
    """
    if not isinstance(snapshot, FinancialReportSnapshot):
        raise TypeError("snapshot must be a FinancialReportSnapshot")

    assets = Decimal("0")
    liabilities = Decimal("0")
    recorded_equity = Decimal("0")
    income = Decimal("0")
    costs = Decimal("0")
    expenses = Decimal("0")

    for line in snapshot.lines:
        ledger_balance = line.ledger_balance
        if not isinstance(ledger_balance, Decimal):
            raise TypeError(
                f"ledger_balance for account {line.account_code!r} must be Decimal"
            )

        account_type = line.account_type
        if account_type == "Activo":
            assets += ledger_balance
        elif account_type == "Pasivo":
            liabilities -= ledger_balance
        elif account_type == "Patrimonio":
            recorded_equity -= ledger_balance
        elif account_type == "Ingreso":
            income -= ledger_balance
        elif account_type == "Costo":
            costs += ledger_balance
        elif account_type == "Gasto":
            expenses += ledger_balance
        else:
            raise ValueError(
                f"Unknown financial statement classification {account_type!r} "
                f"for account {line.account_code!r}"
            )

    result = income - costs - expenses
    total_equity = recorded_equity + result
    liabilities_and_equity = liabilities + total_equity
    balance_difference = assets - liabilities_and_equity

    if balance_difference != Decimal("0"):
        raise ValueError(
            "Financial statement balance does not close exactly: "
            f"assets={assets}, liabilities_and_equity={liabilities_and_equity}, "
            f"difference={balance_difference}"
        )

    return FinancialStatementTotals(
        as_of=snapshot.as_of,
        assets=assets,
        liabilities=liabilities,
        recorded_equity=recorded_equity,
        income=income,
        costs=costs,
        expenses=expenses,
        result=result,
        total_equity=total_equity,
        liabilities_and_equity=liabilities_and_equity,
        balance_difference=balance_difference,
    )
