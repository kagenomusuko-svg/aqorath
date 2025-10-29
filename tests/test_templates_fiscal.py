from aqorath.storage import init_db, get_session
from aqorath.models import Account
from aqorath.core import generate_preview, post_entry
import tempfile
import os

def test_ingreso_gross_with_vat(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    init_db()
    with get_session() as s:
        s.add(Account(code="1000", name="Bancos", nature="DEBIT"))
        s.add(Account(code="4000", name="Ventas", nature="CREDIT"))
        s.add(Account(code="2100", name="IVA trasladado", nature="CREDIT"))
        s.commit()
    # importe bruto (incluye IVA) = 1160 -> base 1000, iva 160
    ctx = {"account_codes": {"bank":"1000","sales":"4000","vat_tr":"2100"}, "vat_rate": 0.16, "desc":"Venta bruto"}
    preview = generate_preview("ingreso_venta_bruto", 1160.0, ctx=ctx)
    assert preview["balanced"] is True
    assert preview["total_debit"] == 1160.0
    # buscar líneas
    sales_line = next((l for l in preview["lines"] if l["account_code"] == "4000"), None)
    vat_line = next((l for l in preview["lines"] if l["account_code"] == "2100"), None)
    assert sales_line and sales_line["credit"] == 1000.0
    assert vat_line and vat_line["credit"] == 160.0

def test_honorarios_with_isr_and_post(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    init_db()
    with get_session() as s:
        s.add(Account(code="1000", name="Bancos", nature="DEBIT"))
        s.add(Account(code="5000", name="Gastos honorarios", nature="DEBIT"))
        s.add(Account(code="2300", name="ISR retenido", nature="CREDIT"))
        s.commit()
    ctx = {"account_codes": {"bank":"1000","expense":"5000","isr_ret":"2300"}, "isr_ret_rate": 0.1, "desc":"Honorarios prueba"}
    preview = generate_preview("honorarios", 1000.0, ctx=ctx)
    assert preview["balanced"] is True
    # net to bank should be 900
    bank_line = next((l for l in preview["lines"] if l["account_code"] == "1000"), None)
    isr_line = next((l for l in preview["lines"] if l["account_code"] == "2300"), None)
    assert bank_line and bank_line["credit"] == 900.0
    assert isr_line and isr_line["credit"] == 100.0
    # test post_entry persists
    entry_id = post_entry("honorarios", 1000.0, ctx=ctx, user="test")
    assert isinstance(entry_id, int)