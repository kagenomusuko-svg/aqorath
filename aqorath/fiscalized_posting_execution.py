"""Fiscalized posting execution adapter — Phase 5AA.2.

Adapts one immutable FiscalizedPostingInstruction to the canonical
``core.post_entry`` dictionary payload. All persistence, transaction handling,
account validation, and SQLite authority remain inside ``aqorath.core``.

This module does not rebuild the instruction, inspect fiscal provenance, resolve
accounts, recalculate fiscal amounts, open sessions, or use the historical
posting-execution adapter.
"""

from . import core as _core
from . import fiscalized_posting as _posting


__all__ = ["execute_fiscalized_posting_instruction"]


def execute_fiscalized_posting_instruction(instruction):
    """Persist exactly one fiscalized posting instruction through core.post_entry."""
    if not isinstance(instruction, _posting.FiscalizedPostingInstruction):
        raise TypeError(
            "execute_fiscalized_posting_instruction requires "
            "FiscalizedPostingInstruction"
        )

    payload = {
        "description": instruction.description,
        "lines": [
            {
                "account_id": line.account_id,
                "account_code": line.account_code,
                "debit": line.debit,
                "credit": line.credit,
            }
            for line in instruction.lines
        ],
    }

    return _core.post_entry(payload)
