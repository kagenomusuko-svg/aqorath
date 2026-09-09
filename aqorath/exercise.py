"""Retired compatibility surface for legacy exercise closing.

The historical implementation in this module owned a parallel accounting write path:
it could construct JournalEntry/JournalLine rows itself and fall back to direct SQLite
writes.  That violates Aqorath's canonical persistence authority and is intentionally
removed.

The module remains importable because runtime-consolidation contracts still include
``aqorath.exercise``.  ``close_exercise`` is preserved only as an explicit fail-closed
compatibility boundary until a canonical year-end closing workflow is introduced.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional


LEGACY_EXERCISE_RETIRED = "LEGACY_EXERCISE_RETIRED"


def close_exercise(
    carry_over: bool = True,
    out_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Reject use of the retired parallel year-end persistence path.

    No backup, account resolution, JournalEntry construction, ORM write, direct SQLite
    access, or monetary transformation occurs here.  Callers must use a future
    canonical closing workflow that delegates to Aqorath's governed posting authority.
    """

    del carry_over, out_root
    return {
        "ok": False,
        "code": LEGACY_EXERCISE_RETIRED,
        "error": (
            "Legacy exercise closing is retired because it bypassed canonical ledger "
            "persistence. Use the governed Aqorath closing workflow when available."
        ),
    }
