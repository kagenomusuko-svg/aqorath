"""Common and professional acceptance against the real Application and SQLite."""
from datetime import date
from decimal import Decimal

import pytest
from sqlmodel import select
from test_aqr006_subledger import _seed_runtime


@pytest.mark.parametrize('kind,key,party_type', [
    ('receivable','sale_credit','customer'), ('payable','utility_credit','supplier'),
])
def test_complete_common_and_professional_journey(tmp_path, monkeypatch, kind, key, party_type):
    from aqorath.presentation_controller import LocalPresentationController
    from aqorath import storage
    from aqorath.models import JournalLine
    _seed_runtime(tmp_path, monkeypatch)
    c = LocalPresentationController()
    party = c.create_third_party({'name':'Nuevo tercero', 'party_type':party_type})
    assert party in c.third_parties()
    origins=[]
    for number, amount in [('A','200'),('B','100')]:
        draft=c.prepare_open_item_origin(dict(operation_key=key, amount=amount,
            posting_date='2026-01-01', third_party_id=party['id'], due_date='2026-01-31',
            document_type='invoice', document_number=number, document_date='2026-01-01'))
        assert 'account_code' not in str(draft['preview'])
        assert c.professional_preview(draft['token'])['subledger']['third_party_id']==party['id']
        origins.append(c.confirm(draft['token']))
    item_id=origins[0]['open_item_id']
    def apply(allocations, day):
        draft=c.prepare_open_item_application_batch(dict(allocations=allocations,
            posting_date=day,document_type='payment',document_number=day,document_date=day))
        return c.confirm(draft['token'])
    partial=apply([dict(open_item_id=item_id,amount='80')],'2026-02-01')
    item=c.open_item(item_id,'2026-02-01')
    assert item['open_balance']=='120' and item['status']=='open'
    assert item['aging_bucket']=='1-30'
    with pytest.raises(ValueError,match='exceeds'):
        apply([dict(open_item_id=item_id,amount='121')],'2026-02-02')
    full=apply([dict(open_item_id=item_id,amount='120'),
                dict(open_item_id=origins[1]['open_item_id'],amount='100')],'2026-02-03')
    assert all(i['status']=='settled' for i in c.open_items(kind,'2026-02-03'))
    pro=c.professional_open_item(item_id,'2026-02-03')
    assert pro['open_item']['open_balance']=='0'
    assert pro['source_operation']['entry_id']==origins[0]['entry_id']
    assert pro['source_operation']['documents'][0]['third_party_id']==party['id']
    assert pro['source_operation']['audit']['event_type']=='entry_posted'
    assert pro['reconciliation']['is_reconciled']
    with storage.get_session() as session:
        lines=session.exec(select(JournalLine).where(JournalLine.entry_id==full['entry_id'])).all()
        ids={l.id for l in lines}
        assert {a['line_id'] for a in full['applications']} <= ids
        assert len(lines)==3
    c.reverse_operation(full['entry_id'],{'reason':'Comprobante cancelado','reversal_date':'2026-02-04'})
    assert c.open_item(item_id,'2026-02-04')['open_balance']=='120'
    assert c.open_item(item_id,'2026-02-03')['open_balance']=='0'
    assert c.professional_open_item(item_id,'2026-02-04')['application_operations'][1]['operation']['reversal']
    assert c.subledger_reconciliation(kind,'2026-02-04')['is_reconciled']
    apply([dict(open_item_id=item_id,amount='120'),dict(open_item_id=origins[1]['open_item_id'],amount='100')],'2026-02-05')
    assert c.open_item(item_id,'2026-02-05')['status']=='settled'


def test_surface_error_exposes_historical_gap(tmp_path, monkeypatch):
    from aqorath.presentation_controller import LocalPresentationController
    from test_aqr006_subledger import test_unassigned_control_line_is_detected_without_inventing_open_item
    test_unassigned_control_line_is_detected_without_inventing_open_item(tmp_path, monkeypatch)
    result=LocalPresentationController().subledger_reconciliation('receivable','2026-07-01')
    assert result['difference']=='77' and result['unassigned_line_ids']
    assert not result['is_reconciled']


def test_surface_cancel_and_stale_consent(tmp_path, monkeypatch):
    from aqorath.presentation_controller import LocalPresentationController
    _seed_runtime(tmp_path, monkeypatch)
    c=LocalPresentationController()
    draft=c.prepare_open_item_origin(dict(operation_key='sale_credit',amount='10',posting_date='2026-01-01',
        third_party_id=c.third_parties()[0]['id'],due_date='2026-01-31',document_type='invoice',
        document_number='CANCEL',document_date='2026-01-01'))
    c.cancel(draft['token'])
    assert c.open_items('receivable','2026-02-01')==[]
    with pytest.raises(LookupError): c.confirm(draft['token'])


def test_browser_shell_exposes_same_application_routes():
    from aqorath.web_assets import APP_HTML
    from aqorath.web_surface import app
    for path in ['/api/subledger/third-parties','/api/subledger/origins/prepare',
                 '/api/subledger/applications/batch/prepare']:
        assert path in APP_HTML
        assert path in {r.path for r in app.routes}
    for element in ['prepareCredit','preparePayment','confirmSubledger','confirmReversal',
                    'inspectItem','reconcileButton','creditParty','dueDate']:
        assert f'id="{element}"' in APP_HTML
