import tempfile
from aqorath.storage import init_db, get_session, DB_PATH
from aqorath.core import generate_preview, post_entry, list_templates
from aqorath.models import Account
import os

def test_generate_preview_and_post(tmp_path, monkeypatch):
    # ensure DB is in the XDG test folder
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    init_db()
    # seed minimal accounts
    with get_session() as s:
        s.add(Account(code="1000", name="Bancos", nature="DEBIT"))
        s.add(Account(code="4000", name="Ventas", nature="CREDIT"))
        s.add(Account(code="2100", name="IVA trasladado", nature="CREDIT"))
        s.commit()
    preview = generate_preview("ingreso_venta", 1000.0, ctx={"account_codes": {"bank":"1000","sales":"4000","vat_tr":"2100"}, "vat_rate": 0.16, "desc":"Venta prueba"})
    assert preview["balanced"] is True
    assert preview["total_debit"] == preview["total_credit"]
    entry_id = post_entry("ingreso_venta", 1000.0, ctx={"account_codes": {"bank":"1000","sales":"4000","vat_tr":"2100"}, "vat_rate": 0.16, "desc":"Venta prueba"}, user="test")
    assert isinstance(entry_id, int)