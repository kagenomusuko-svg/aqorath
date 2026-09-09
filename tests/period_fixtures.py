"""Explicit calendar setup for existing accounting integration fixtures.

Only test data: the pre-AQR-002 fixtures did not declare activity start or open
periods. This helper establishes those prerequisites through the real APIs;
it never mocks the temporal guard or modifies production default behavior.
"""
from datetime import date
from sqlalchemy import text
from aqorath.accounting_period_repository import configure_calendar, open_fiscal_year
from aqorath.entity import Entity, EntityProfile
from aqorath.entity_repository import create_entity


def seed_calendar(session):
    if session.execute(text('SELECT id FROM accountingcalendar')).first():
        return
    rows = session.execute(text('SELECT id FROM entity WHERE is_active=1')).all()
    if rows:
        entity_id = rows[0][0]
    else:
        entity = create_entity(session, Entity(None, 'Calendar test entity', None, 'persona_moral', 'A.C.',
            EntityProfile('no_lucrativo', False, (), ()), True))
        entity_id = entity.id
    from aqorath.accounting_period import accounting_date
    entries = session.execute(text('SELECT date FROM journalentry')).all()
    states = {d.year*100+d.month: 'open' for (value,) in entries for d in (accounting_date(value),)}
    from aqorath.accounting_period import FiscalYear
    years = {pid // 100 for pid in states}
    states = {p.id: 'open' for y in years for p in FiscalYear(y, date(2000,1,1)).periods()}
    configure_calendar(session, entity_id, date(2000, 1, 1), states, historical_year_states={y: 'open' for y in years})
    existing = {r[0] for r in session.execute(text('SELECT year FROM fiscalyear')).all()}
    for year in sorted({2000, 2010, 2025, 2026, 2027, date.today().year} - existing):
        open_fiscal_year(session, year)
    session.commit()


def seed_engine_calendar(engine):
    from sqlmodel import Session
    with Session(engine) as session:
        seed_calendar(session)
