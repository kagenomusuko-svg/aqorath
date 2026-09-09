"""Canonical, atomic correction by reversal of a posted journal entry."""
from datetime import date, datetime, timezone
from sqlalchemy import text
from .accounting_period_repository import require_open_period
from .core import _stage_entry_in_session
from .accounting_period import PeriodError


def reverse_posted_entry(session, entry_id, reason, reversal_date=None):
    if type(entry_id) is not int or entry_id <= 0:
        raise ValueError("entry_id must be a positive integer")
    if type(reason) is not str or not reason.strip():
        raise ValueError("A nonblank reversal reason is required")
    row = session.execute(text("SELECT id,date,concept,state,period_id FROM journalentry WHERE id=:id"), {"id": entry_id}).mappings().one_or_none()
    if row is None:
        raise LookupError("Journal entry not found")
    if row["state"] != "posted":
        raise PeriodError("Only a posted entry can be reversed")
    if session.execute(text("SELECT id FROM journalentryreversal WHERE original_entry_id=:id"), {"id": entry_id}).first():
        raise PeriodError("Journal entry already has a reversal")
    lines = session.execute(text("SELECT account_code,debit,credit,description FROM journalline WHERE entry_id=:id ORDER BY id"), {"id": entry_id}).mappings().all()
    if not lines:
        raise ValueError("Posted entry has no lines")
    day = reversal_date or date.today()
    if isinstance(day, datetime):
        day = day.date()
    payload = {"date": day, "concept": f"Reversión: {row['concept'] or entry_id}", "state": "posted",
               "lines": [{"account_code": l["account_code"], "debit": l["credit"], "credit": l["debit"], "description": l["description"]} for l in lines]}
    reversal, error = _stage_entry_in_session(session, payload)
    if error:
        raise PeriodError(error)
    session.flush()
    session.execute(text("UPDATE journalentry SET state='reversed' WHERE id=:id"), {"id": entry_id})
    session.execute(text("INSERT INTO journalentryreversal(original_entry_id,reversal_entry_id,reason,created_at) VALUES (:o,:r,:reason,:created)"), {"o": entry_id, "r": reversal.id, "reason": reason, "created": datetime.now(timezone.utc).isoformat()})
    return {"original_entry_id": entry_id, "reversal_entry_id": reversal.id, "reason": reason}
