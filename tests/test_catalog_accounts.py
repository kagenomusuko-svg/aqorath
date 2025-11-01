import json
from pathlib import Path
from sqlmodel import select
from aqorath.storage import get_session
from aqorath.models import Account

CAT_PATH = Path("aqorath/data/catalogo_base.json")

def load_catalog_codes():
    d = json.loads(CAT_PATH.read_text(encoding="utf-8"))
    return set(d.get("accounts", {}).keys())

def test_catalog_codes_have_single_account():
    expected = load_catalog_codes()
    with get_session() as s:
        rows = s.exec(select(Account.code)).all()
        db_codes = set(str(r[0]) for r in rows) if rows else set()
    # todos los codes del catálogo deben existir en DB
    assert expected.issubset(db_codes), f"Faltan códigos en DB: {expected - db_codes}"
    # comprobar unicidad por código
    with get_session() as s:
        dup = s.exec("SELECT code FROM account GROUP BY code HAVING COUNT(*) > 1;").all()
        assert len(dup) == 0, f"Códigos duplicados en account: {dup}"