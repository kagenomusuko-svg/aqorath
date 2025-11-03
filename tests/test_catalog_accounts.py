from aqorath.catalog import load_catalog_codes
from aqorath.storage import get_session
from aqorath.models import Account
from sqlmodel import select


def test_catalog_codes_have_single_account():
    expected = load_catalog_codes()

    with get_session() as s:
        rows = s.exec(select(Account.code)).all()
        db_codes = set()
        for r in rows:
            # 🔧 Compatibilidad: según la versión de SQLModel/SQLAlchemy,
            # 'select(Account.code)' puede devolver tuplas (('1101',), ...)
            # o valores escalares ('1101', ...). Este bloque asegura
            # que ambos formatos sean manejados correctamente.
            code = r[0] if isinstance(r, (list, tuple)) else r
            db_codes.add(str(code))

    # Todos los códigos del catálogo deben existir en la base de datos.
    assert expected.issubset(db_codes), f"Faltan códigos en DB: {expected - db_codes}"
