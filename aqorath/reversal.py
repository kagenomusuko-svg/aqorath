"""Canonical, atomic correction by reversal of a posted journal entry."""
from datetime import date, datetime, timezone
from sqlalchemy import text
from .accounting_period_repository import require_open_period
from .core import _stage_entry_in_session
from .accounting_period import PeriodError


def correct_posted_entry(session, entry_id, reason, instruction, correction_date):
    """Compose reversal and an already confirmed replacement in one transaction."""
    # A generic replacement cannot manufacture the open-item/application metadata
    # required by AQR-006. Those entries must be reversed and re-entered through
    # their dedicated use case so ledger and subledger remain one transaction.
    try:
        from .open_item_repository import assert_entry_correctable
        assert_entry_correctable(session, entry_id)
    except ImportError:
        # Schema/module may be absent only while migrating from a pre-AQR-006 build.
        pass

    from .posting_execution import build_posting_payload
    from .audit_event import AuditEvent
    from .audit_event_repository import stage_audit_event
    payload = build_posting_payload(instruction)
    payload.update(date=correction_date, state='posted')
    try:
        with session.begin_nested():
            reversal = reverse_posted_entry(session, entry_id, reason, correction_date)
            replacement, error = _stage_entry_in_session(session, payload)
            if error:
                raise PeriodError(error)
            session.flush()
            owner = session.execute(text('SELECT entity_id FROM accountingcalendar WHERE id=1')).scalar_one()
            details = {**reversal, 'replacement_entry_id': replacement.id}
            stage_audit_event(session, AuditEvent(None, owner, 'entry_corrected', datetime.now(timezone.utc), details))
            return details
    except Exception:
        # A failed compound correction may not be committed by its caller.
        session.rollback()
        raise


def reverse_posted_entry(session, entry_id, reason, reversal_date=None):
    """Keep the caller's commit authority; roll back the whole operation on error."""
    try:
        from .open_item_repository import assert_entry_reversible
        assert_entry_reversible(session, entry_id)
    except ImportError:
        pass

    keys = ('_aqorath_new_journal_entries', '_aqorath_affected_journal_entry_ids', '_aqorath_deleted_journal_entry_ids')
    saved = None
    try:
        with session.begin_nested():
            saved = {key: session.info[key].copy() for key in keys if key in session.info}
            return _stage_reversal(session, entry_id, reason, reversal_date)
    except Exception:
        if saved is not None:
            for key in keys:
                session.info.pop(key, None)
            session.info.update(saved)
        raise


def _stage_reversal(session, entry_id, reason, reversal_date):
    if type(entry_id) is not int or entry_id <= 0:
        raise ValueError("entry_id must be a positive integer")
    if type(reason) is not str or not reason.strip():
        raise ValueError("A nonblank reversal reason is required")
    # Serialize the original-state read and the reversal in SQLite.
    session.execute(text('UPDATE accountingcalendar SET id=id WHERE id=1'))
    row = session.execute(text("SELECT id,date,concept,state,period_id FROM journalentry WHERE id=:id"), {"id": entry_id}).mappings().one_or_none()
    if row is None:
        raise LookupError("Journal entry not found")
    if row["state"] != "posted":
        raise PeriodError("Only a posted entry can be reversed")
    from .accounting_period import accounting_date
    from .accounting_period_repository import load_fiscal_year
    source_year = load_fiscal_year(session, accounting_date(row['date']).year)
    if source_year.state == 'closed':
        raise PeriodError('Correction of a closed fiscal year requires an explicit accounting policy')
    if session.execute(text("SELECT id FROM journalentryreversal WHERE original_entry_id=:id"), {"id": entry_id}).first():
        raise PeriodError("Journal entry already has a reversal")
    lines = session.execute(text("SELECT account_code,debit,credit,description FROM journalline WHERE entry_id=:id ORDER BY id"), {"id": entry_id}).mappings().all()
    if not lines:
        raise ValueError("Posted entry has no lines")
    day = reversal_date or date.today()
    if isinstance(day, datetime):
        day = day.date()
    payload = {"date": day, "description": f"Reversión: {row['concept'] or entry_id}", "state": "posted",
               "lines": [{"account_code": l["account_code"], "debit": l["credit"], "credit": l["debit"], "description": l["description"]} for l in lines]}
    reversal, error = _stage_entry_in_session(session, payload)
    if error:
        raise PeriodError(error)
    session.flush()
    session.execute(text("UPDATE journalentry SET state='reversed' WHERE id=:id"), {"id": entry_id})
    session.execute(text("INSERT INTO journalentryreversal(original_entry_id,reversal_entry_id,reason,created_at) VALUES (:o,:r,:reason,:created)"), {"o": entry_id, "r": reversal.id, "reason": reason, "created": datetime.now(timezone.utc).isoformat()})
    from .audit_event import AuditEvent
    from .audit_event_repository import stage_audit_event
    owner = session.execute(text('SELECT entity_id FROM accountingcalendar WHERE id=1')).scalar_one()
    details = {"original_entry_id": entry_id, "reversal_entry_id": reversal.id, "reason": reason}
    event = stage_audit_event(session, AuditEvent(None, owner, 'entry_reversed', datetime.now(timezone.utc), details))
    return {**details, 'audit_event_id': event.id}
