"""Posting execution adapter — Phase 2C.6.

Adapts an immutable PostingInstruction to the canonical core.post_entry payload.
All persistence, transaction handling, account validation and SQLite authority remain
inside aqorath.core. This module does not recompute or resolve accounting semantics.
"""

from . import core as _core
from . import posting as _posting


__all__ = ["execute_posting_instruction"]


def execute_posting_instruction(instruction):
    """Persist exactly one PostingInstruction through the canonical core authority."""
    if not isinstance(instruction, _posting.PostingInstruction):
        raise TypeError("execute_posting_instruction requires PostingInstruction")

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
