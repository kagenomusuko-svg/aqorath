from aqorath.storage import init_db, get_session
from aqorath.models import Account
from aqorath.core import generate_preview, post_entry
import tempfile

def test_nota_credito(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    init_db()
    with get_session() as s:
        s.add(Account(code="1100", name="Clientes", nature="DEBIT"))
        s.add(Account(code="4000", name="Ventas", nature="CREDIT"))
        s.add(Account(code="2100", name="IVA trasladado", nature="CREDIT"))
        s.commit()
    ctx = {"account_codes": {"receivable":"1100","sales":"4000","vat_tr":"2100"}, "vat_rate": 0.16, "desc":"NC prueba"}
    preview = generate_preview("nota_credito", 1000.0, ctx=ctx)
    assert preview["balanced"] is True
    # total credit should be 1160 (reduce receivable)
    assert preview["total_credit"] == 1160.0

def test_pago_con_retencion_iva(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    init_db()
    with get_session() as s:
        s.add(Account(code="1000", name="Bancos", nature="DEBIT"))
        s.add(Account(code="5000", name="Gastos", nature="DEBIT"))
        s.add(Account(code="2000", name="Proveedores", nature="CREDIT"))
        s.add(Account(code="2200", name="IVA acreditable", nature="DEBIT"))
        s.add(Account(code="2400", name="IVA retenido", nature="CREDIT"))
        s.commit()
    ctx = {"account_codes": {"bank":"1000","expense":"5000","payable":"2000","vat_ac":"2200","vat_ret":"2400"}, "vat_rate": 0.16, "vat_ret_rate": 0.5, "desc":"Compra ret IVA"}
    # base = 1000 -> vat = 160, vat_ret=80, paid=1000+160-80=1080
    preview = generate_preview("pago_proveedor_con_retencion_iva", 1000.0, ctx=ctx)
    assert preview["balanced"] is True
    assert preview["total_debit"] == preview["total_credit"]
    # ensure vat_ret (2400) credit exists and equals 80
    vat_ret_line = next((l for l in preview["lines"] if l["account_code"] == "2400"), None)
    assert vat_ret_line and vat_ret_line["credit"] == 80.0

def test_nomina_basic(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    init_db()
    with get_session() as s:
        s.add(Account(code="7000", name="Gasto sueldos", nature="DEBIT"))
        s.add(Account(code="7010", name="Gasto cargas patronales", nature="DEBIT"))
        s.add(Account(code="1000", name="Bancos", nature="DEBIT"))
        s.add(Account(code="2300", name="ISR retenido", nature="CREDIT"))
        s.add(Account(code="2310", name="IMSS obrero", nature="CREDIT"))
        s.add(Account(code="2320", name="IMSS patronal", nature="CREDIT"))
        s.commit()
    # sueldo bruto 10000, default rates: ISR 15%, IMSS obrero 2.75%, IMSS patronal 10%
    ctx = {"account_codes": {"salary_expense":"7000","employer_social_expense":"7010","bank":"1000","isr_ret":"2300","imss_obrero_payable":"2310","imss_patronal_payable":"2320"}, "isr_ret_rate": 0.15, "imss_obrero_rate": 0.0275, "imss_patronal_rate": 0.10, "desc":"Nomina prueba"}
    preview = generate_preview("nomina", 10000.0, ctx=ctx)
    assert preview["balanced"] is True
    # check net paid = 10000 * (1 - .15 - .0275) = 8225.0
    bank_line = next((l for l in preview["lines"] if l["account_code"] == "1000"), None)
    assert bank_line and bank_line["credit"] == 8225.0
    # check ISR credit
    isr_line = next((l for l in preview["lines"] if l["account_code"] == "2300"), None)
    assert isr_line and isr_line["credit"] == 1500.0