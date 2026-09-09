from datetime import date
from sqlalchemy import text
from sqlmodel import Session
import pytest
from aqorath.accounting_period import PeriodError
from aqorath.accounting_period_repository import close_period
from aqorath.models import JournalEntry
from period_fixtures import seed_engine_calendar


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
