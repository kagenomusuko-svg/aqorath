import tempfile
from aqorath.storage import init_db, get_session, DB_PATH
from aqorath.core import generate_preview, post_entry, list_templates
from aqorath.models import Account
import os

def test_generate_preview_and_post(tmp_path, monkeypatch):
    # ensure DB is in the XDG test folder
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    init_db()
    # Phase 1B.1: P0-4 now validates account_code existence.
    # Use canonical accounts from aqorath/data/catalogo_base.json:
    # - 1101: Bancos (Deudora/debit)
    # - 4101: Ventas al contado (Acreedora/credit)
    # - 2080: IVA trasladado (Acreedora/credit)
    ctx_accounts = {
        "bank": "1101",        # Bancos
        "sales": "4101",       # Ventas al contado
        "vat_tr": "2080"       # IVA trasladado
    }
    preview = generate_preview("ingreso_venta", 1000.0, ctx={"account_codes": ctx_accounts, "vat_rate": 0.16, "desc":"Venta prueba"})
    assert preview["balanced"] is True
    assert preview["total_debit"] == preview["total_credit"]
    entry_id = post_entry("ingreso_venta", 1000.0, ctx={"account_codes": ctx_accounts, "vat_rate": 0.16, "desc":"Venta prueba"}, user="test")
    assert isinstance(entry_id, int)