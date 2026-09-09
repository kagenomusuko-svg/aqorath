from datetime import date
from sqlalchemy import text
from sqlmodel import Session
import pytest
from aqorath.accounting_period import PeriodError
from aqorath.accounting_period_repository import close_period
from aqorath.models import JournalEntry
from period_fixtures import seed_engine_calendar


@pytest.fixture
def posted(tmp_path, monkeypatch):
    from aqorath import storage, core
    from aqorath.models import Account
    path = tmp_path / 'protected.db'
    monkeypatch.setenv('AQORATH_DB', str(path))
    engine = storage.init_db(str(path))
    seed_engine_calendar(engine)
    with Session(engine) as s:
        s.add_all([Account(code='1102', name='Caja', nature='DEBIT'), Account(code='4201', name='Ventas', nature='CREDIT')])
        s.commit()
    result = core.post_entry({'date':date.today(), 'state':'posted', 'lines':[
        {'account_code':'1102','debit':'150','credit':'0'}, {'account_code':'4201','debit':'0','credit':'150'}]})
    assert result['ok']
    yield engine, result['entry_id']
    engine.dispose()


def test_balanced_edit_of_posted_lines_rejected(posted):
    from aqorath.models import JournalLine
    from aqorath.ledger_invariants import LedgerInvariantError
    from sqlmodel import select
    engine, eid = posted
    with Session(engine) as s:
        lines = s.exec(select(JournalLine).where(JournalLine.entry_id==eid)).all()
        lines[0].debit='120'; lines[1].credit='120'
        with pytest.raises(LedgerInvariantError, match='immutable'):
            s.commit()
        s.rollback()
        assert str(s.get(JournalLine,lines[0].id).debit)=='150'


def test_reversal_evidence_is_atomic_even_if_caller_catches_failure(posted, monkeypatch):
    from aqorath.reversal import reverse_posted_entry
    import aqorath.audit_event_repository as audit
    engine,eid = posted
    def fail(*args):
        raise RuntimeError('audit failure')
    monkeypatch.setattr(audit,'stage_audit_event',fail)
    with Session(engine) as s:
        with pytest.raises(RuntimeError,match='audit failure'):
            reverse_posted_entry(s,eid,'wrong amount',date.today())
        s.commit()
        assert s.get(JournalEntry,eid).state=='posted'
        assert s.execute(text('SELECT COUNT(*) FROM journalentry')).scalar()==1
        assert s.execute(text('SELECT COUNT(*) FROM journalentryreversal')).scalar()==0


def test_reversal_audit_and_original_remain_immutable(posted):
    import json
    from aqorath.reversal import reverse_posted_entry
    from aqorath.ledger_invariants import LedgerInvariantError
    engine,eid = posted
    with Session(engine) as s:
        result=reverse_posted_entry(s,eid,'wrong amount',date.today()); s.commit()
        details=json.loads(s.execute(text('SELECT details_json FROM auditevent WHERE id=:id'), {'id':result['audit_event_id']}).scalar_one())
        assert details['original_entry_id']==eid
        assert details['reason']=='wrong amount'
        s.get(JournalEntry,eid).concept='edited history'
        with pytest.raises(LedgerInvariantError): s.commit()
        s.rollback()
        s.delete(s.get(JournalEntry,eid))
        with pytest.raises(LedgerInvariantError): s.commit()


def test_correction_keeps_three_entries_and_net_120(posted):
    from decimal import Decimal
    from aqorath import application, core
    from aqorath.economic_facts import EconomicFact
    from aqorath.posting import create_posting_instruction
    engine,eid=posted
    with Session(engine) as s:
        snapshot=application.prepare_economic_fact_confirmation(s, EconomicFact('sale',Decimal('120'),'cash'), {'cash':'1102','sales_revenue':'4201'})
        instruction=create_posting_instruction(application.confirm_economic_fact(snapshot))
        result=application.correct_posted_journal_entry(s,eid,'150 should be 120',instruction,date.today())
        s.commit()
        assert result['replacement_entry_id'] != result['reversal_entry_id']
        assert s.execute(text('SELECT COUNT(*) FROM journalentry')).scalar()==3
        assert s.execute(text("SELECT COUNT(*) FROM auditevent WHERE event_type IN ('entry_corrected','entry_reversed')")).scalar()==2
    assert core.trial_balance()['1102']==Decimal('120')


def test_posted_identity_change_and_forged_reversed_state_are_rejected(posted):
    from aqorath.ledger_invariants import LedgerInvariantError
    engine,eid=posted
    with Session(engine) as s:
        s.get(JournalEntry,eid).id=900
        with pytest.raises(LedgerInvariantError): s.commit()
        s.rollback()
        s.add(JournalEntry(date=date.today(),state='reversed'))
        with pytest.raises(LedgerInvariantError): s.commit()
        s.rollback()
        s.delete(s.get(JournalEntry,eid))
        with pytest.raises(LedgerInvariantError): s.commit()


def test_closed_year_correction_is_not_silently_charged_to_new_year(posted, tmp_path):
    from aqorath.exercise import close_exercise
    from aqorath.reversal import reverse_posted_entry
    from aqorath.models import Account
    from aqorath.accounting_period_repository import open_fiscal_year
    engine,eid=posted
    year=date.today().year
    with Session(engine) as s:
        s.add(Account(code='3104',name='Acumulado',nature='CREDIT'));s.commit()
        if not s.execute(text('SELECT year FROM fiscalyear WHERE year=:y'),{'y':year+1}).first():
            open_fiscal_year(s,year+1);s.commit()
    assert close_exercise(year=year,out_root=tmp_path/'backups')['ok']
    with Session(engine) as s:
        count=s.execute(text('SELECT COUNT(*) FROM journalentry')).scalar()
        with pytest.raises(PeriodError,match='explicit accounting policy'):
            reverse_posted_entry(s,eid,'prior year error',date(year+1,1,1))
        s.commit()
        assert s.execute(text('SELECT COUNT(*) FROM journalentry')).scalar()==count
        assert s.execute(text('SELECT COUNT(*) FROM journalentryreversal')).scalar()==0


def test_posted_is_immutable_and_reversal_is_atomic(tmp_path, monkeypatch):
    import aqorath.storage as storage
    from aqorath.core import post_entry
    from aqorath.application import reverse_posted_journal_entry
    path=tmp_path/'a.db'; monkeypatch.setenv('AQORATH_DB',str(path)); engine=storage.init_db(str(path))
    seed_engine_calendar(engine)
    with Session(engine) as s:
        from aqorath.models import Account
        s.add_all([Account(code='1102',name='Caja',nature='DEBIT'),Account(code='4201',name='Ventas',nature='CREDIT')]);s.commit()
    r=post_entry({'date':date.today(),'state':'posted','lines':[{'account_code':'1102','debit':'150','credit':'0'},{'account_code':'4201','debit':'0','credit':'150'}]}); assert r['ok']
    with Session(engine) as s:
        e=s.get(JournalEntry,r['entry_id']); e.concept='edited'
        with pytest.raises(Exception): s.commit()
    with Session(engine) as s:
        result=reverse_posted_journal_entry(s,r['entry_id'],'importe incorrecto',date.today()); s.commit()
        assert result['reversal_entry_id']
    with Session(engine) as s:
        assert s.get(JournalEntry,r['entry_id']).state=='reversed'
        assert s.execute(text('SELECT reason FROM journalentryreversal')).scalar()=='importe incorrecto'
        with pytest.raises(PeriodError): reverse_posted_journal_entry(s,r['entry_id'],'otra')
        s.rollback()


def test_reversal_rejects_closed_destination_without_partial_rows(tmp_path, monkeypatch):
    import aqorath.storage as storage
    from aqorath.core import post_entry
    from aqorath.application import reverse_posted_journal_entry
    path=tmp_path/'b.db'; monkeypatch.setenv('AQORATH_DB',str(path)); engine=storage.init_db(str(path)); seed_engine_calendar(engine)
    with Session(engine) as s:
        from aqorath.models import Account
        s.add_all([Account(code='1102',name='Caja',nature='DEBIT'),Account(code='4201',name='Ventas',nature='CREDIT')]);s.commit()
    r=post_entry({'date':date.today(),'state':'posted','lines':[{'account_code':'1102','debit':'5','credit':'0'},{'account_code':'4201','debit':'0','credit':'5'}]}); assert r['ok']
    with Session(engine) as s: close_period(s,date.today().year*100+date.today().month); s.commit()
    with Session(engine) as s:
        with pytest.raises(PeriodError): reverse_posted_journal_entry(s,r['entry_id'],'closed',date.today())
        assert s.execute(text('SELECT COUNT(*) FROM journalentryreversal')).scalar()==0
