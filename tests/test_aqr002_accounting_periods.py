from dataclasses import FrozenInstanceError
from datetime import date, datetime, timezone
from decimal import Decimal
import sqlite3
import pytest
from sqlmodel import Session
from sqlalchemy import text
from aqorath.accounting_period import FiscalYear, AccountingPeriod, PeriodError, resolve_posting_period
from aqorath.accounting_period_repository import configure_calendar, open_fiscal_year, close_period, require_open_period, get_period_balances


def test_short_year_calendar_and_unique_dates():
    fy = FiscalYear(2024, date(2024, 2, 20))
    periods = fy.periods()
    assert len(periods) == 11
    assert periods[0].start == date(2024, 2, 20)
    assert periods[0].end == date(2024, 2, 29)
    assert fy.end == date(2024, 12, 31)
    assert resolve_posting_period(date(2024, 3, 1), fy, periods).id == 202403
    with pytest.raises(PeriodError): resolve_posting_period(date(2024, 2, 19), fy, periods)
    assert FiscalYear(2025, fy.activity_start).start == date(2025, 1, 1)
    with pytest.raises(FrozenInstanceError): fy.year = 2026


@pytest.mark.parametrize('day,period_id', [(date(2026, 1, 1), 202601), (date(2026, 12, 31), 202612)])
def test_month_boundaries(day, period_id):
    fy = FiscalYear(2026, date(2026, 1, 1))
    assert resolve_posting_period(day, fy, fy.periods()).id == period_id


def test_fail_closed_temporal_contracts():
    fy = FiscalYear(2026, date(2026, 5, 10)); p = fy.periods()[0]
    for periods, supplied in [((), None), ((p,p), None), ((p,), 202606), ((AccountingPeriod(fy,5,'closed'),), None)]:
        with pytest.raises(PeriodError): resolve_posting_period(date(2026,5,10), fy, periods, supplied)
    with pytest.raises(PeriodError): FiscalYear(2025, fy.activity_start)
    with pytest.raises(PeriodError): AccountingPeriod(fy,4)
    closed = FiscalYear(2026, fy.activity_start, 'closed')
    with pytest.raises(PeriodError): resolve_posting_period(date(2026,5,10), closed, closed.periods())


@pytest.fixture
def db(tmp_path, monkeypatch):
    import aqorath.storage as storage
    from aqorath.models import Account
    from aqorath.entity import Entity, EntityProfile
    from aqorath.entity_repository import create_entity
    path = tmp_path/'periods.db'; monkeypatch.setenv('AQORATH_DB', str(path))
    engine = storage.init_db(str(path))
    with Session(engine) as session:
        entity = create_entity(session, Entity(None,'Example',None,'persona_moral','A.C.',EntityProfile('no_lucrativo',False,(),()),True))
        session.add_all([Account(code='1102', name='Caja',nature='DEBIT'), Account(code='4201',name='Ventas',nature='CREDIT'), Account(code='5102',name='Servicios',nature='DEBIT'), Account(code='3104',name='Acumulado',nature='CREDIT')]);session.commit()
        configure_calendar(session, entity.id, date(2026,5,10))
        open_fiscal_year(session,2026);open_fiscal_year(session,2027);session.commit()
    yield path, engine
    engine.dispose()


def payload(day, amount='200', period_id=None):
    return {'date':day,'state':'posted','period_id':period_id,'lines':[{'account_code':'1102','debit':amount,'credit':'0'},{'account_code':'4201','debit':'0','credit':amount}]}


def test_posting_open_closed_before_start_and_no_implicit_year(db):
    from aqorath.core import post_entry
    path, engine = db
    assert not post_entry(payload(date(2026,5,9)))['ok']
    assert not post_entry(payload(date(2028,1,1)))['ok']
    assert not post_entry(payload(date(2026,5,10),period_id=202606))['ok']
    assert post_entry(payload(date(2026,5,10)))['ok']
    with Session(engine) as session:
        close_period(session,202605);session.commit()
    assert not post_entry(payload(date(2026,5,31)))['ok']
    assert post_entry(payload(date(2026,6,1)))['ok']
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT period_id FROM journalentry ORDER BY id').fetchall()==[(202605,),(202606,)]


def test_corrupted_period_boundaries_rejected(db):
    from aqorath.core import post_entry
    path, engine = db
    with engine.begin() as conn: conn.execute(text("UPDATE accountingperiod SET start_date='2026-05-01' WHERE id=202605"))
    assert not post_entry(payload(date(2026,5,10)))['ok']


def test_closing_after_preparation_rejected(db):
    from aqorath.core import post_entry
    path, engine = db
    with Session(engine) as session:
        assert require_open_period(session,date(2026,5,10)).id==202605
    with Session(engine) as session: close_period(session,202605);session.commit()
    assert not post_entry(payload(date(2026,5,10)))['ok']


def test_period_reports_keep_historical_cutoff(db):
    from aqorath.core import post_entry
    path, engine = db
    assert post_entry(payload(date(2026,5,10),'200'))['ok']
    assert post_entry(payload(date(2026,6,1),'80'))['ok']
    with Session(engine) as session:
        report=get_period_balances(session,202605)
        assert report['movement']['1102']==Decimal('200')
        assert report['closing']['1102']==Decimal('200')


def test_year_closing_zeroes_results_and_is_idempotent(db,tmp_path):
    from aqorath.core import post_entry
    from aqorath.exercise import close_exercise
    path, engine = db
    assert post_entry(payload(date(2026,5,10),'200'))['ok']
    assert post_entry({'date':date(2026,5,11),'state':'posted','lines':[{'account_code':'5102','debit':'150','credit':'0'},{'account_code':'1102','debit':'0','credit':'150'}]})['ok']
    result=close_exercise(year=2026,out_root=tmp_path/'backup')
    assert result['ok'], result
    assert Decimal(result['transferred'])==Decimal(50)
    with Session(engine) as session:
        report=get_period_balances(session,202612)
        assert report['closing']['4201']==0
        assert report['closing']['5102']==0
        assert report['closing']['3104']==Decimal('-50')
    again=close_exercise(year=2026,out_root=tmp_path/'backup')
    assert again['ok'] and again['entry_id']==result['entry_id']
    assert not post_entry(payload(date(2026,12,31)))['ok']
    assert post_entry(payload(date(2027,1,1)))['ok']


def test_year_close_cannot_reopen_december(db,tmp_path):
    from aqorath.exercise import close_exercise
    path,engine=db
    with Session(engine) as session: close_period(session,202612);session.commit()
    assert not close_exercise(year=2026,out_root=tmp_path/'backup')['ok']


def test_migration_v4_preserves_unknown_calendar_and_money(tmp_path):
    from aqorath.migrations import migrate_database, CURRENT_SCHEMA_VERSION
    path=tmp_path/'legacy.db';migrate_database(path)
    with sqlite3.connect(path) as conn:
        conn.execute('PRAGMA user_version=4')
        for table in ('accountingperiod','fiscalyear','accountingcalendar'): conn.execute(f'DROP TABLE {table}')
        conn.execute('CREATE TABLE preserved (amount TEXT)');conn.execute("INSERT INTO preserved VALUES ('12.3400')")
    result=migrate_database(path)
    assert result['from_version']==4 and result['to_version']==CURRENT_SCHEMA_VERSION
    assert result['backup_path']
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT * FROM accountingcalendar').fetchall()==[]
        assert conn.execute('SELECT amount FROM preserved').fetchone()==('12.3400',)


def test_calendar_requires_explicit_legacy_states(db):
    path,engine=db
    with Session(engine) as session:
        with pytest.raises(PeriodError,match='already declared'):
            configure_calendar(session,1,date(2026,1,1))


@pytest.mark.parametrize('route', ['fiscal', 'acquisition', 'depreciation'])
def test_all_atomic_routes_reject_closed_period_without_metadata(tmp_path, monkeypatch, route):
    if route == 'fiscal':
        import test_p5_fiscalized_posting_audit_persistence as fixtures
        from aqorath.fiscalized_posting_persistence import execute_fiscalized_posting_with_audit as execute
        engine, ids = fixtures._canonical_db(tmp_path, monkeypatch)
        instruction = fixtures._instruction(ids=ids)
        table = 'fiscalpostingauditrecord'
    else:
        if route == 'acquisition':
            import _p6q_fixed_asset_acquisition_contracts as fixtures
            from aqorath.fixed_asset_acquisition_persistence import execute_fixed_asset_acquisition_posting_once as execute
            table = 'fixedassetacquisitionpostingrecord'
        else:
            import test_p6_fixed_asset_depreciation_persistence as fixtures
            from aqorath.fixed_asset_depreciation_persistence import execute_fixed_asset_depreciation_posting_once as execute
            table = 'fixedassetdepreciationpostingrecord'
        engine, _, entity_id, asset_id = fixtures._initialize_canonical_db(tmp_path, monkeypatch)
        asset = fixtures._domain_asset(fixed_asset_id=asset_id, entity_id=entity_id)
        with Session(engine) as session:
            instruction = fixtures._instruction(session, asset)
    with Session(engine) as session:
        # Fiscal synthetic fixtures use the current date, asset ones use 2026.
        for row in session.execute(text('SELECT id FROM accountingperiod')).all():
            close_period(session, row[0])
        session.commit()
    result = execute(instruction)
    assert not result['ok'], result
    with Session(engine) as session:
        assert session.execute(text('SELECT COUNT(*) FROM journalentry')).scalar() == 0
        assert session.execute(text('SELECT COUNT(*) FROM journalline')).scalar() == 0
        assert session.execute(text(f'SELECT COUNT(*) FROM {table}')).scalar() == 0


def test_arbitrary_report_range_does_not_create_periods(db):
    from aqorath.core import post_entry
    from aqorath.accounting_period_repository import get_date_range_balances
    path,engine=db
    assert post_entry(payload(date(2026,5,10),'200'))['ok']
    assert post_entry(payload(date(2026,6,15),'80'))['ok']
    with Session(engine) as session:
        before=session.execute(text('SELECT COUNT(*) FROM accountingperiod')).scalar()
        report=get_date_range_balances(session,date(2026,5,9),date(2026,6,20))
        assert report['movement']['1102']==Decimal(280)
        assert session.execute(text('SELECT COUNT(*) FROM accountingperiod')).scalar()==before


def test_explicit_legacy_mapping_preserves_original_ids_and_states(db):
    from aqorath.accounting_period_repository import configure_calendar
    import json
    path,engine=db
    with engine.begin() as conn:
        conn.execute(text('DELETE FROM accountingperiod'));conn.execute(text('DELETE FROM fiscalyear'));conn.execute(text('DELETE FROM accountingcalendar'))
        conn.execute(text("INSERT INTO journalentry(id,date,concept,period_id,state,created_at) VALUES(99,'2026-05-10','legacy',77,'posted','2026-05-10')"))
    with Session(engine) as session:
        with pytest.raises(PeriodError,match='explicit reconciliation'):
            configure_calendar(session,1,date(2026,5,10))
        assert session.execute(text('SELECT COUNT(*) FROM accountingcalendar')).scalar()==0
        states={p.id:'closed' for p in FiscalYear(2026,date(2026,5,10)).periods()}
        configure_calendar(session,1,date(2026,5,10),states,{99:202605},{2026:'closed'})
        session.commit()
        evidence=json.loads(session.execute(text('SELECT declaration_json FROM accountingcalendar')).scalar())
        assert evidence['legacy_assignments']==[{'entry_id':99,'old_period_id':77,'period_id':202605}]
        assert session.execute(text('SELECT period_id FROM journalentry WHERE id=99')).scalar()==202605
        assert load_year_state(session,2026)=='closed'


def load_year_state(session,year):
    return session.execute(text('SELECT state FROM fiscalyear WHERE year=:y'),{'y':year}).scalar()


def test_annual_close_failure_rolls_back_state_and_policies(db,tmp_path,monkeypatch):
    import aqorath.core as core
    from aqorath.exercise import close_exercise
    path,engine=db
    assert core.post_entry(payload(date(2026,5,10)))['ok']
    monkeypatch.setattr(core,'_stage_entry_in_session',lambda *args:(None,'forced staging failure'))
    result=close_exercise(year=2026,out_root=tmp_path/'backup')
    assert not result['ok'] and 'forced staging' in result['error']
    with Session(engine) as session:
        assert load_year_state(session,2026)=='open'
        assert require_open_period(session,date(2026,12,31)).state=='open'
        assert session.execute(text('SELECT COUNT(*) FROM journalentry')).scalar()==1


def test_direct_orm_cannot_move_entry_out_of_closed_period(db):
    from aqorath.core import post_entry
    from aqorath.models import JournalEntry
    path,engine=db
    eid=post_entry(payload(date(2026,5,10)))['entry_id']
    with Session(engine) as session: close_period(session,202605);session.commit()
    with Session(engine) as session:
        entry=session.get(JournalEntry,eid);entry.date=datetime(2026,6,1);entry.period_id=202606
        with pytest.raises(PeriodError): session.commit()
        session.rollback()
    with Session(engine) as session: assert session.get(JournalEntry,eid).period_id==202605


@pytest.mark.parametrize('expense', ['0', '250'])
def test_closing_empty_year_or_loss(db, tmp_path, expense):
    from aqorath.core import post_entry
    from aqorath.exercise import close_exercise
    path, engine = db
    if expense != '0':
        assert post_entry({'date': date(2026,5,10), 'state':'posted', 'lines':[
            {'account_code':'5102','debit':expense,'credit':'0'},
            {'account_code':'1102','debit':'0','credit':expense}]})['ok']
    result = close_exercise(year=2026, out_root=tmp_path/'backup')
    assert result['ok'], result
    assert Decimal(result['transferred']) == -Decimal(expense)
    with Session(engine) as session:
        assert load_year_state(session,2026) == 'closed'
        balances = get_period_balances(session,202612)['closing']
        assert balances.get('5102',0) == 0
        assert balances.get('3104',0) == Decimal(expense)
    if expense == '0':
        assert result['entry_id'] is None


def test_closing_resolves_governed_account_extensions(db, tmp_path):
    from aqorath.catalog import create_entity_account
    from aqorath.core import post_entry
    from aqorath.exercise import close_exercise
    path, engine = db
    with Session(engine) as session:
        account = create_entity_account(session,'4201','Ventas particulares')
        code = account.code
    entry = payload(date(2026,5,10))
    entry['lines'][1]['account_code'] = code
    assert post_entry(entry)['ok']
    result = close_exercise(year=2026,out_root=tmp_path/'backup')
    assert result['ok'], result
    with Session(engine) as session:
        assert get_period_balances(session,202612)['closing'][code] == 0


def test_report_preserves_declared_civil_date_and_maximum_range(db):
    from aqorath.core import post_entry
    from aqorath.accounting_period_repository import get_date_range_balances
    path, engine = db
    assert post_entry(payload('2026-05-31T23:30:00-06:00'))['ok']
    with Session(engine) as session:
        assert get_period_balances(session,202605)['movement']['1102'] == Decimal(200)
        assert get_date_range_balances(session,date.min,date.max)['movement']['1102'] == Decimal(200)


def test_schema_five_missing_calendar_is_rejected(db):
    from aqorath.migrations import migrate_database, CURRENT_SCHEMA_VERSION
    path, engine = db
    with engine.begin() as connection:
        connection.execute(text('DROP TABLE accountingperiod'))
    with pytest.raises(RuntimeError,match='Invalid schema 5'):
        migrate_database(path)
