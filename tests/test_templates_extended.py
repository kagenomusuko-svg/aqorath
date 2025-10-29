from aqorath.storage import init_db, get_session
from aqorath.models import Account
from aqorath.core import generate_preview, post_entry
import tempfile
import os

def test_ingreso_net_with_vat(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    init_db()
    with get_session() as s:
        s.add(Account(code="1000", name="Bancos", nature="DEBIT"))
        s.add(Account(code="4000", name="Ventas", nature="CREDIT"))
        s.add(Account(code="2100", name="IVA trasladado", nature="CREDIT"))
        s.commit()
    ctx = {"account_codes": {"bank":"1000","sales":"4000","vat_tr":"2100"}, "vat_rate": 0.16, "desc":"Venta neta"}
    preview = generate_preview("ingreso_venta", 1000.0, ctx=ctx)
    assert preview["balanced"] is True
    # verify totals: debit should be 1160 (1000 + 160)
    assert preview["total_debit"] == 1160.0