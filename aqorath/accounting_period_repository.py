"""Temporal persistence composes the pure calendar authority and the caller's transaction."""
import json
from datetime import date
from sqlalchemy import text
from .accounting_period import FiscalYear, AccountingPeriod, PeriodError, accounting_date, resolve_posting_period


def _rows(session, sql, **params):
    return session.execute(text(sql), params).mappings().all()


def load_fiscal_year(session, year):
    calendar = _rows(session, 'SELECT * FROM accountingcalendar WHERE id=1')
    if not calendar:
        raise PeriodError('Declare entity activity_start before posting')
    if not _rows(session, 'SELECT id FROM entity WHERE id=:id AND is_active=1', id=calendar[0]['entity_id']):
        raise PeriodError('Calendar owner is not the active entity')
    rows = _rows(session, 'SELECT * FROM fiscalyear WHERE year=:year', year=year)
    if not rows:
        raise PeriodError('Fiscal year is not open/configured')
    row = rows[0]
    if row['calendar_id'] != 1:
        raise PeriodError('Invalid fiscal calendar reference')
    fy = FiscalYear(year, date.fromisoformat(calendar[0]['activity_start']), row['state'])
    if (row['start_date'], row['end_date']) != (fy.start.isoformat(), fy.end.isoformat()):
        raise PeriodError('Stored fiscal year boundaries contradict calendar authority')
    return fy


def load_periods(session, fy):
    rows = _rows(session, 'SELECT * FROM accountingperiod WHERE year=:year ORDER BY month', year=fy.year)
    result = []
    for row in rows:
        p = AccountingPeriod(fy, row['month'], row['state'])
        if (row['id'], row['start_date'], row['end_date']) != (p.id, p.start.isoformat(), p.end.isoformat()):
            raise PeriodError('Stored period contradicts calendar authority')
        result.append(p)
    return tuple(result)


def require_open_period(session, value, supplied_id=None):
    day = accounting_date(value)
    fy = load_fiscal_year(session, day.year)
    return resolve_posting_period(day, fy, load_periods(session, fy), supplied_id)


def configure_calendar(session, entity_id, activity_start, historical_states=None, legacy_period_assignments=None, historical_year_states=None):
    """Declare start, and explicitly classify legacy months before linking old rows.

    Does not commit. Historical states are {YYYYMM: 'open'|'closed'} for every
    usable month of each historical year. Unknown old period IDs are rejected, not reinterpreted.
    """
    if type(activity_start) is not date:
        raise PeriodError('activity_start must be an explicit date')
    if _rows(session, 'SELECT id FROM accountingcalendar'):
        raise PeriodError('Calendar already declared; historical start is immutable')
    entity = _rows(session, 'SELECT id FROM entity WHERE id=:id AND is_active=1', id=entity_id)
    if not entity:
        raise PeriodError('Calendar requires the active entity')
    entries = _rows(session, 'SELECT id,date,period_id FROM journalentry')
    explicit = {} if legacy_period_assignments is None else legacy_period_assignments
    assignments = []
    old_ids = []
    for row in entries:
        day = accounting_date(row['date'])
        fy = FiscalYear(day.year, activity_start)
        p = resolve_posting_period(day, fy, fy.periods())
        if row['period_id'] not in (None, p.id) and explicit.get(row['id']) != p.id:
            raise PeriodError('Legacy period_id needs explicit reconciliation before calendar setup')
        if row['id'] in explicit and explicit[row['id']] != p.id:
            raise PeriodError('Explicit legacy assignment contradicts declared calendar')
        old_ids.append({'entry_id': row['id'], 'old_period_id': row['period_id'], 'period_id': p.id})
        assignments.append((row['id'], p.id))
    if set(explicit) - {eid for eid, _ in assignments}:
        raise PeriodError('Unknown entry in explicit legacy assignments')
    years = {pid // 100 for _, pid in assignments}
    required = {p.id for y in years for p in FiscalYear(y, activity_start).periods()}
    year_states = {} if historical_year_states is None else historical_year_states
    if set(year_states) != years or any(v not in ('open', 'closed') for v in year_states.values()):
        raise PeriodError('Explicit historical fiscal-year states required')
    states = {} if historical_states is None else historical_states
    if set(states) != required or any(s not in ('open', 'closed') for s in states.values()):
        raise PeriodError('Explicit historical state required for each usable historical month, without extra months')
    with session.begin_nested():
        session.execute(text('INSERT INTO accountingcalendar(id,entity_id,activity_start,declaration_json) VALUES (1,:id,:start,:evidence)'),
                        {'id': entity_id, 'start': activity_start.isoformat(), 'evidence': json.dumps({'historical_states': states, 'legacy_assignments': old_ids, 'historical_year_states': year_states}, sort_keys=True)})
        for year in sorted({pid // 100 for pid in required}):
            open_fiscal_year(session, year)
        for entry_id, period_id in assignments:
            session.execute(text('UPDATE journalentry SET period_id=:p WHERE id=:id'), {'p': period_id, 'id': entry_id})
        for pid, state in states.items():
            session.execute(text('UPDATE accountingperiod SET state=:s WHERE id=:id'), {'s': state, 'id': pid})
        for y, state in year_states.items():
            if state == 'closed' and any(states[p.id] != 'closed' for p in FiscalYear(y, activity_start).periods()):
                raise PeriodError('Closed historical year cannot contain open periods')
            session.execute(text('UPDATE fiscalyear SET state=:s WHERE year=:y'), {'s': state, 'y': y})


def open_fiscal_year(session, year):
    calendars = _rows(session, 'SELECT activity_start FROM accountingcalendar WHERE id=1')
    if not calendars:
        raise PeriodError('Declare activity_start first')
    fy = FiscalYear(year, date.fromisoformat(calendars[0]['activity_start']))
    if _rows(session, 'SELECT year FROM fiscalyear WHERE year=:year', year=year):
        raise PeriodError('Fiscal year already exists; reopening is not implicit')
    with session.begin_nested():
        session.execute(text('INSERT INTO fiscalyear(year,calendar_id,start_date,end_date,state) VALUES (:y,1,:s,:e,\'open\')'),
                        {'y': year, 's': fy.start.isoformat(), 'e': fy.end.isoformat()})
        for p in fy.periods():
            session.execute(text('INSERT INTO accountingperiod(id,year,month,start_date,end_date,state) VALUES (:id,:y,:m,:s,:e,\'open\')'),
                            {'id': p.id, 'y': year, 'm': p.month, 's': p.start.isoformat(), 'e': p.end.isoformat()})
    return fy


def close_period(session, period_id):
    if type(period_id) is not int:
        raise PeriodError('period_id must be an integer')
    fy = load_fiscal_year(session, period_id // 100)
    periods = load_periods(session, fy)
    if not any(p.id == period_id for p in periods):
        raise PeriodError('Unknown accounting period')
    session.execute(text("UPDATE accountingperiod SET state='closed' WHERE id=:id"), {'id': period_id})


def validate_persisted_period(session, entry_id):
    rows = _rows(session, 'SELECT date,period_id FROM journalentry WHERE id=:id', id=entry_id)
    if not rows:
        raise PeriodError('Missing journal entry')
    row = rows[0]
    if row['period_id'] is None:
        raise PeriodError('Persisted journal entry requires a period')
    day = accounting_date(row['date'])
    fy = load_fiscal_year(session, day.year)
    closing = _rows(session, 'SELECT closing_entry_id FROM fiscalyear WHERE year=:y', y=day.year)[0]['closing_entry_id']
    annual_closing = closing == entry_id and session.info.get('_aqorath_annual_closing') == entry_id
    resolve_posting_period(day, fy, load_periods(session, fy), row['period_id'], annual_closing=annual_closing)


def get_period_balances(session, period_id):
    """Read through the existing balance engine; no independent aggregation."""
    fy = load_fiscal_year(session, period_id // 100)
    found = [p for p in load_periods(session, fy) if p.id == period_id]
    if len(found) != 1:
        raise PeriodError('Unknown accounting period')
    p = found[0]
    return {'period': p, **get_date_range_balances(session, p.start, p.end)}


def get_date_range_balances(session, start, end):
    """Arbitrary civil-date comparisons do not create posting periods."""
    from datetime import timedelta
    from .core import _balances_from_sqlite
    from .account_balance import _exact_decimal_sum
    from decimal import Decimal
    from pathlib import Path
    start, end = accounting_date(start), accounting_date(end)
    if end < start:
        raise PeriodError('Report range is inverted')
    path = session.get_bind().url.database
    if not path or path == ':memory:':
        raise PeriodError('Reports require the local SQLite database')
    closing = _balances_from_sqlite(Path(path), end.isoformat())
    opening = {} if start == date.min else _balances_from_sqlite(Path(path), (start - timedelta(days=1)).isoformat())
    return {'opening': opening, 'closing': closing,
            'movement': {code: _exact_decimal_sum([closing.get(code, Decimal(0)), opening.get(code, Decimal(0)).copy_negate()]) for code in closing.keys() | opening.keys()}}
