"""Pure value projections for AQR-006 receivable/payable subledgers."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class OpenItemApplicationView:
    id: int
    entry_id: int
    line_id: int
    document_reference_id: int
    posting_date: date
    amount: Decimal
    is_effective: bool


@dataclass(frozen=True)
class OpenItemView:
    id: int
    entity_id: int
    third_party_id: int
    third_party_name: str
    kind: str
    source_entry_id: int
    source_line_id: int
    source_document_reference_id: int
    document_type: str
    document_number: str
    posting_date: date
    due_date: date
    original_amount: Decimal
    applied_amount: Decimal
    open_balance: Decimal
    status: str
    aging_bucket: str
    applications: tuple[OpenItemApplicationView, ...]


@dataclass(frozen=True)
class SubledgerReconciliation:
    kind: str
    as_of: date
    ledger_balance: Decimal
    subledger_balance: Decimal
    difference: Decimal
    control_account_ids: tuple[int, ...]
    unassigned_line_ids: tuple[int, ...]

    @property
    def is_reconciled(self):
        return (
            self.difference == Decimal("0")
            and not self.unassigned_line_ids
        )


class SubledgerDivergenceError(RuntimeError):
    """Canonical ledger and operational subledger cannot be reconciled exactly."""


__all__ = [
    "OpenItemApplicationView",
    "OpenItemView",
    "SubledgerReconciliation",
    "SubledgerDivergenceError",
]
